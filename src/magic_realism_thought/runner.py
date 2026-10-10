from __future__ import annotations

import copy
import dataclasses
from typing import Dict, List, Optional, Sequence

from .memory import (
    best_memory_provider_for_role,
    format_memory_context,
    load_memory_profile,
    profile_snapshot,
    save_memory_profile,
    update_memory_profile_from_run,
)
from .metrics import compute_magic_realism_metrics, make_control_notes, merge_symbols, observe_transition
from .prm import HeuristicPRM, HybridPRM, LLMJudgePRM, ProcessRewardModel
from .prompts import (
    RoleRouter,
    build_aggregation_prompt,
    build_recursive_closure_prompt,
    build_repair_prompt,
    build_stage_prompt,
)
from .providers import BaseProvider, ProviderError, build_provider
from .reward_audit import compute_reward_surface_audit
from .rpm import RPMObserver, build_decision_landscape_record
from .types import (
    BeamConfig,
    BeamPathSnapshot,
    CandidateStep,
    ChainConstraints,
    ChainRun,
    ChainState,
    ChatRequest,
    PRMConfig,
    ProcessReward,
    ProcessStepRecord,
    RPMTrace,
    ROLES,
    RewardSurfaceAudit,
    StageSpec,
)
from .utils import clamp01, clip_text, json_safe, utc_now_iso

class SpiralRpmPrmRunnerV5:
    def __init__(
        self,
        providers: Sequence[str],
        models: Dict[str, str],
        role_providers: Dict[str, str],
        routing: str,
        stages: Sequence[StageSpec],
        system: str,
        constraints: ChainConstraints,
        temperature: Optional[float],
        max_tokens: int,
        dry_run: bool,
        include_prompts: bool,
        candidates: int,
        prm_mode: str,
        accept_threshold: float,
        repair_threshold: float,
        repair_attempts: int,
        judge_provider: Optional[str],
        judge_model: Optional[str],
        judge_temperature: Optional[float],
        judge_max_tokens: int,
        hybrid_llm_weight: float,
        aggregate: bool,
        recursive_closure: bool,
        max_context_chars: int,
        beam_width: int = 1,
        beam_branching: int = 0,
        beam_archive: int = 8,
        memory_profile_path: Optional[str] = None,
        save_memory_profile_path: Optional[str] = None,
        memory_weight: float = 0.25,
        memory_update: bool = True,
        magic_prior: Optional[MagicRealismPrior] = None,
        anchor_profile: Optional[PromptAnchorProfile] = None,
    ) -> None:
        self.provider_names = list(providers)
        self.models = models
        self.role_providers = role_providers
        self.routing = routing
        self.router = RoleRouter(providers, role_providers, routing)
        self.stages = list(stages)
        self.system = system
        self.constraints = constraints
        self.rpm_observer = RPMObserver(constraints)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dry_run = dry_run
        self.include_prompts = include_prompts
        self.candidates = max(1, candidates)
        self.prm_mode = prm_mode
        self.accept_threshold = accept_threshold
        self.repair_threshold = repair_threshold
        self.repair_attempts = max(0, repair_attempts)
        self.judge_provider_name = judge_provider
        self.judge_model = judge_model
        self.judge_temperature = judge_temperature
        self.judge_max_tokens = judge_max_tokens
        self.hybrid_llm_weight = hybrid_llm_weight
        self.aggregate = aggregate
        self.recursive_closure = recursive_closure
        self.max_context_chars = max_context_chars
        self.beam_width = max(1, beam_width)
        self.beam_branching = max(1, beam_branching or self.beam_width)
        self.beam_archive_limit = max(0, beam_archive)
        self.memory_profile_path = memory_profile_path
        self.save_memory_profile_path = save_memory_profile_path or memory_profile_path
        self.memory_weight = clamp01(memory_weight)
        self.memory_update = memory_update
        self.magic_prior = magic_prior
        self.anchor_profile = anchor_profile
        self.memory_profile = load_memory_profile(memory_profile_path)
        self.memory_profile_before = profile_snapshot(self.memory_profile, limit=12)
        self.beam_archive_snapshots: List[BeamPathSnapshot] = []
        self._providers: Dict[str, BaseProvider] = {}
        self._prm: Optional[ProcessRewardModel] = None

    def get_provider(self, name: str) -> BaseProvider:
        if name not in self._providers:
            self._providers[name] = build_provider(name, dry_run=self.dry_run)
        return self._providers[name]

    def build_prm(self) -> ProcessRewardModel:
        if self._prm is not None:
            return self._prm
        heuristic = HeuristicPRM(
            constraints=self.constraints,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
        )
        if self.prm_mode == "heuristic":
            self._prm = heuristic
            return self._prm

        judge_name = self.judge_provider_name or self.default_judge_provider()
        judge_model = self.judge_model or self.models[judge_name]
        llm = LLMJudgePRM(
            provider=self.get_provider(judge_name),
            model=judge_model,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
            temperature=self.judge_temperature,
            max_tokens=self.judge_max_tokens,
        )
        if self.prm_mode == "llm":
            self._prm = llm
        elif self.prm_mode == "hybrid":
            self._prm = HybridPRM(heuristic=heuristic, llm=llm, llm_weight=self.hybrid_llm_weight)
        else:
            raise ValueError(f"Unknown PRM mode: {self.prm_mode}")
        return self._prm

    def default_judge_provider(self) -> str:
        for preferred in ("anthropic", "openai", "google", "mistral"):
            if preferred in self.provider_names:
                return preferred
        if not self.provider_names:
            raise ProviderError("No providers configured.")
        return self.provider_names[0]

    def provider_candidates_for_stage(self, role: str, index_zero_based: int, count: int) -> List[str]:
        providers = self.router.candidate_providers_for(role, index_zero_based, count)
        if self.memory_weight > 0 and int(self.memory_profile.get("run_count", 0) or 0) > 0:
            preferred = best_memory_provider_for_role(self.memory_profile, role, self.provider_names)
            if preferred and preferred in providers:
                providers = [preferred] + [p for p in providers if p != preferred]
            elif preferred and preferred in self.provider_names:
                providers = [preferred] + providers
        # Preserve requested candidate count after memory reordering.
        if not providers:
            return providers
        while len(providers) < max(1, count):
            providers.append(providers[len(providers) % len(providers)])
        return providers[: max(1, count)]

    def memory_context_for_stage(self, stage: StageSpec) -> str:
        return format_memory_context(
            self.memory_profile,
            role=stage.role,
            available_providers=self.provider_names,
            memory_weight=self.memory_weight,
        )

    def call_provider(self, provider_name: str, prompt: str) -> ChatResult:
        model = self.models[provider_name]
        request = ChatRequest(
            model=model,
            system=self.system,
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        result = self.get_provider(provider_name).generate(request)
        if not result.text:
            raise ProviderError(f"{provider_name}: empty response")
        return result

    def make_candidate_from_result(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        candidate_id: str,
        result: ChatResult,
        prompt: str,
        repaired_from: Optional[str] = None,
        repair_attempt: int = 0,
    ) -> CandidateStep:
        symbols_after = merge_symbols(state.symbols, result.text, limit=self.constraints.symbol_limit)
        metrics = observe_transition(previous=state.text, current=result.text, symbols=symbols_after)
        if state.magic_prior:
            metrics.update(compute_magic_realism_metrics(result.text, state=state, stage=stage, transition_metrics=metrics))
        return CandidateStep(
            candidate_id=candidate_id,
            stage_index=index,
            stage_name=stage.name,
            role=stage.role,
            operator=stage.operator,
            provider=result.provider,
            model=result.model,
            output=result.text,
            metrics=metrics,
            symbols_before=list(state.symbols),
            symbols_after=symbols_after,
            reward=None,
            prompt=prompt if self.include_prompts else None,
            usage=result.usage,
            repaired_from=repaired_from,
            repair_attempt=repair_attempt,
        )

    def generate_candidates(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        total: int,
        branch_prefix: str = "",
    ) -> List[CandidateStep]:
        providers = self.provider_candidates_for_stage(stage.role, index - 1, self.candidates)
        candidates: List[CandidateStep] = []
        for offset, provider_name in enumerate(providers, start=1):
            prompt = build_stage_prompt(
                state=state,
                stage=stage,
                index=index,
                total=total,
                candidate_variant=offset,
                max_context_chars=self.max_context_chars,
                memory_context=self.memory_context_for_stage(stage),
            )
            result = self.call_provider(provider_name, prompt)
            candidate = self.make_candidate_from_result(
                state=state,
                stage=stage,
                index=index,
                candidate_id=f"{branch_prefix}s{index}-c{offset}-{provider_name}",
                result=result,
                prompt=prompt,
            )
            candidates.append(candidate)
        return candidates

    def score_candidates(self, state: ChainState, stage: StageSpec, candidates: Sequence[CandidateStep]) -> None:
        prm = self.build_prm()
        for candidate in candidates:
            candidate.reward = prm.score(state, stage, candidate)

    def choose_candidate(self, candidates: Sequence[CandidateStep]) -> CandidateStep:
        if not candidates:
            raise ValueError("No candidates to choose from.")
        return max(candidates, key=lambda c: (c.reward.score if c.reward else -1.0, -c.metrics.get("collapse_score", 1.0)))

    def repair_candidate(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        failed: CandidateStep,
        attempt: int,
    ) -> Optional[CandidateStep]:
        if not failed.reward or not failed.reward.repairable:
            return None
        repair_provider = failed.provider
        prompt = build_repair_prompt(
            state=state,
            stage=stage,
            failed=failed,
            reward=failed.reward,
            max_context_chars=self.max_context_chars,
        )
        result = self.call_provider(repair_provider, prompt)
        repaired = self.make_candidate_from_result(
            state=state,
            stage=stage,
            index=index,
            candidate_id=f"{failed.candidate_id}-r{attempt}",
            result=result,
            prompt=prompt,
            repaired_from=failed.candidate_id,
            repair_attempt=attempt,
        )
        repaired.reward = self.build_prm().score(state, stage, repaired)
        return repaired

    def compute_path_score(self, state: ChainState) -> float:
        rewards = [step.accepted.reward.score if step.accepted.reward else 0.0 for step in state.step_history]
        if not rewards:
            return 0.0
        mean_reward = sum(rewards) / len(rewards)
        last_reward = rewards[-1]
        recurrence = state.metrics.get("recurrence_score", 0.0)
        collapse = state.metrics.get("collapse_score", 0.0)
        drift = state.metrics.get("drift_score", 0.0)
        magic = state.metrics.get("magic_realism_reward", 0.0)
        unresolved = len([c for c in state.rpm_trace.conflicts if not c.resolved])
        drift_penalty = max(0.0, drift - self.constraints.max_drift)
        score = (
            0.58 * mean_reward
            + 0.26 * last_reward
            + 0.10 * recurrence
            + 0.06 * state.metrics.get("entropy_score", 0.0)
            + (0.07 * magic if self.magic_prior else 0.0)
            - 0.08 * collapse
            - 0.06 * drift_penalty
            - 0.025 * unresolved
        )
        return round(clamp01(score), 5)

    def make_beam_snapshot(self, state: ChainState, stage_index: int) -> BeamPathSnapshot:
        rewards = [round(step.accepted.reward.score, 4) if step.accepted.reward else 0.0 for step in state.step_history]
        providers = [step.accepted.provider for step in state.step_history]
        unresolved = len([c for c in state.rpm_trace.conflicts if not c.resolved])
        return BeamPathSnapshot(
            path_id=state.path_id,
            stage_index=stage_index,
            score=state.path_score,
            rewards=rewards,
            providers=providers,
            symbols=list(state.symbols[:12]),
            unresolved_conflicts=unresolved,
            final_text_preview=clip_text(state.text.replace("\n", " "), 360),
        )

    def remember_beam_states(self, states: Sequence[ChainState], stage_index: int) -> None:
        if self.beam_archive_limit <= 0:
            return
        for state in states:
            self.beam_archive_snapshots.append(self.make_beam_snapshot(state, stage_index=stage_index))
        self.beam_archive_snapshots = sorted(
            self.beam_archive_snapshots,
            key=lambda snap: (snap.score, len(snap.rewards)),
            reverse=True,
        )[: self.beam_archive_limit]

    def apply_selected_step(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        best: CandidateStep,
        candidates: Sequence[CandidateStep],
        repaired: Sequence[CandidateStep],
    ) -> ProcessStepRecord:
        metrics_before = dict(state.metrics)
        rejected_by_id: Dict[str, CandidateStep] = {}
        for candidate in list(candidates) + list(repaired):
            if candidate.candidate_id != best.candidate_id:
                rejected_by_id[candidate.candidate_id] = candidate
        if best.repaired_from:
            for candidate in candidates:
                if candidate.candidate_id == best.repaired_from:
                    rejected_by_id[candidate.candidate_id] = candidate

        notes = make_control_notes(best.metrics, best.symbols_after, self.constraints, best.output)
        rpm_cell = self.rpm_observer.update(state, stage, best, metrics_before=metrics_before)
        unresolved = [c for c in state.rpm_trace.conflicts if not c.resolved]
        if unresolved:
            for conflict in unresolved[-3:]:
                notes.append(f"RPM conflict {conflict.conflict_id}: {conflict.repair_instruction}")
        record = ProcessStepRecord(
            index=index,
            name=stage.name,
            role=stage.role,
            operator=stage.operator,
            accepted=best,
            rejected=list(rejected_by_id.values()),
            repaired=list(repaired),
            control_notes_for_next=notes,
        )
        state.rpm_trace.decision_landscape.append(
            build_decision_landscape_record(
                trace=state.rpm_trace,
                stage=stage,
                stage_index=index,
                accepted=best,
                candidates=candidates,
                repaired=repaired,
            )
        )
        _ = rpm_cell
        parent_path = state.path_id or "root"
        state.text = best.output
        state.symbols = best.symbols_after
        state.metrics = best.metrics
        state.control_notes = notes
        state.step_history.append(record)
        state.path_id = f"{parent_path}>{best.candidate_id}"
        state.path_score = self.compute_path_score(state)
        state.memory_notes = [
            f"path_score={state.path_score:.5f}",
            f"last_provider={best.provider}",
            f"last_reward={best.reward.score if best.reward else 0.0:.4f}",
        ]
        return record

    def accept_step(self, state: ChainState, stage: StageSpec, index: int, candidates: List[CandidateStep]) -> ProcessStepRecord:
        self.score_candidates(state, stage, candidates)
        repaired: List[CandidateStep] = []
        best = self.choose_candidate(candidates)

        for attempt in range(1, self.repair_attempts + 1):
            if best.reward and best.reward.accept:
                break
            candidate = self.repair_candidate(state, stage, index, best, attempt)
            if not candidate:
                break
            repaired.append(candidate)
            if candidate.reward and (not best.reward or candidate.reward.score >= best.reward.score):
                best = candidate

        return self.apply_selected_step(state, stage, index, best, candidates, repaired)

    def expand_state_for_beam_stage(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        total: int,
        branch_index: int,
    ) -> List[ChainState]:
        branch_prefix = f"b{branch_index}-"
        candidates = self.generate_candidates(state, stage, index, total, branch_prefix=branch_prefix)
        self.score_candidates(state, stage, candidates)
        ranked = sorted(
            candidates,
            key=lambda c: (c.reward.score if c.reward else -1.0, -c.metrics.get("collapse_score", 1.0)),
            reverse=True,
        )
        expansions: List[ChainState] = []
        for selected in ranked[: min(self.beam_branching, len(ranked))]:
            local_best = selected
            repaired: List[CandidateStep] = []
            for attempt in range(1, self.repair_attempts + 1):
                if local_best.reward and local_best.reward.accept:
                    break
                candidate = self.repair_candidate(state, stage, index, local_best, attempt)
                if not candidate:
                    break
                repaired.append(candidate)
                if candidate.reward and (not local_best.reward or candidate.reward.score >= local_best.reward.score):
                    local_best = candidate
            new_state = copy.deepcopy(state)
            self.apply_selected_step(new_state, stage, index, copy.deepcopy(local_best), copy.deepcopy(candidates), copy.deepcopy(repaired))
            expansions.append(new_state)
        return expansions

    def run_beam_generation_stages(self, initial_state: ChainState, total_visible: int) -> ChainState:
        beam_states: List[ChainState] = [initial_state]
        for stage_index, stage in enumerate(self.stages, start=1):
            expanded: List[ChainState] = []
            for branch_index, state in enumerate(beam_states, start=1):
                expanded.extend(self.expand_state_for_beam_stage(state, stage, stage_index, total_visible, branch_index))
            if not expanded:
                raise ValueError(f"Beam expansion produced no candidates at stage {stage_index}.")
            expanded = sorted(expanded, key=lambda st: st.path_score, reverse=True)
            beam_states = expanded[: self.beam_width]
            self.remember_beam_states(beam_states, stage_index=stage_index)
        return sorted(beam_states, key=lambda st: st.path_score, reverse=True)[0]

    def run_prompt_stage(self, state: ChainState, stage: StageSpec, index: int, prompt: str) -> ProcessStepRecord:
        providers = self.provider_candidates_for_stage(stage.role, index - 1, self.candidates)
        candidates: List[CandidateStep] = []
        for offset, provider_name in enumerate(providers, start=1):
            prompt_with_variant = prompt + f"\n\nRun memory context:\n{self.memory_context_for_stage(stage)}\n\nCandidate variant: {offset}\nReturn a distinct but compatible version."
            result = self.call_provider(provider_name, prompt_with_variant)
            candidate = self.make_candidate_from_result(
                state=state,
                stage=stage,
                index=index,
                candidate_id=f"s{index}-c{offset}-{provider_name}",
                result=result,
                prompt=prompt_with_variant,
            )
            candidates.append(candidate)
        return self.accept_step(state, stage, index, candidates)

    def run_generation_stage(self, state: ChainState, stage: StageSpec, index: int, total: int) -> ProcessStepRecord:
        candidates = self.generate_candidates(state, stage, index, total)
        return self.accept_step(state, stage, index, candidates)

    def run(self, seed: str, language: str, seed_symbols: Sequence[str]) -> ChainRun:
        initial_symbols = merge_symbols(seed_symbols, seed, limit=self.constraints.symbol_limit)
        rpm_trace = RPMTrace()
        if self.magic_prior:
            rpm_trace.axes = list(rpm_trace.axes) + [
                "mundane_anchor",
                "quiet_impossibility",
                "non_explanation",
                "social_normalization",
                "fantasy_drift",
                "symbolic_pressure",
                "ordinary_continuity",
            ]
        state = ChainState(
            seed=seed,
            text=seed,
            symbols=initial_symbols,
            constraints=json_safe(dataclasses.asdict(self.constraints)),
            metrics={},
            control_notes=[],
            memory_notes=[
                f"memory_profile_runs={self.memory_profile.get('run_count', 0)}",
                f"beam_width={self.beam_width}",
            ],
            magic_prior=self.magic_prior,
            anchor_profile=self.anchor_profile,
            rpm_trace=rpm_trace,
            step_history=[],
            path_id="root",
            path_score=0.0,
        )

        total_visible = len(self.stages) + (1 if self.aggregate else 0) + (1 if self.recursive_closure else 0)
        if self.beam_width > 1:
            state = self.run_beam_generation_stages(state, total_visible=total_visible)
            stage_index = len(self.stages) + 1
        else:
            stage_index = 1
            for stage in self.stages:
                self.run_generation_stage(state, stage, index=stage_index, total=total_visible)
                self.remember_beam_states([state], stage_index=stage_index)
                stage_index += 1

        if self.aggregate:
            aggregation_stage = StageSpec(
                name="再統合：PRM accepted pathから最終稿へ",
                role="integrator",
                operator="aggregate_high_reward_path",
                instruction="全accepted pathを再統合して最終稿を作る。",
            )
            aggregation_prompt = build_aggregation_prompt(state, max_context_chars=self.max_context_chars * 2)
            self.run_prompt_stage(state, aggregation_stage, index=stage_index, prompt=aggregation_prompt)
            self.remember_beam_states([state], stage_index=stage_index)
            stage_index += 1

        if self.recursive_closure:
            closure_stage = StageSpec(
                name="再帰クロージャ：Seedへの帰還",
                role="recursive",
                operator="close_loop_to_seed",
                instruction="最終稿をSeedへ変形帰還させる。",
            )
            closure_prompt = build_recursive_closure_prompt(
                state,
                aggregate_text=state.text,
                max_context_chars=self.max_context_chars * 2,
            )
            self.run_prompt_stage(state, closure_stage, index=stage_index, prompt=closure_prompt)
            self.remember_beam_states([state], stage_index=stage_index)

        prm_config = PRMConfig(
            mode=self.prm_mode,
            candidates=self.candidates,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
            judge_provider=self.judge_provider_name or (self.default_judge_provider() if self.prm_mode in ("llm", "hybrid") else None),
            judge_model=self.judge_model,
            hybrid_llm_weight=self.hybrid_llm_weight,
            include_prompts=self.include_prompts,
        )
        beam_config = BeamConfig(
            enabled=self.beam_width > 1,
            beam_width=self.beam_width,
            beam_branching=self.beam_branching,
            archive_limit=self.beam_archive_limit,
        )
        memory_before = dict(self.memory_profile_before)
        provisional_run = ChainRun(
            script="chain_of_magic_realism.py",
            version="5.1",
            started_at_utc=utc_now_iso(),
            language=language,
            seed=seed,
            providers=self.provider_names,
            routing=self.routing,
            role_providers={role: self.role_providers[role] for role in ROLES if role in self.role_providers},
            models={name: self.models[name] for name in self.provider_names},
            constraints=json_safe(dataclasses.asdict(self.constraints)),
            magic_prior=self.magic_prior,
            anchor_profile=self.anchor_profile,
            prm=prm_config,
            beam=beam_config,
            beam_archive=list(self.beam_archive_snapshots),
            memory_profile_path=self.save_memory_profile_path,
            memory_profile_before=memory_before,
            memory_profile_after=profile_snapshot(self.memory_profile, limit=12),
            reward_surface_audit=RewardSurfaceAudit(),
            final=state.text,
            final_state=state,
            rpm_trace=state.rpm_trace,
            steps=state.step_history,
        )
        provisional_run.reward_surface_audit = compute_reward_surface_audit(provisional_run)
        if self.memory_update:
            self.memory_profile = update_memory_profile_from_run(self.memory_profile, provisional_run)
            save_memory_profile(self.save_memory_profile_path, self.memory_profile)
            provisional_run.memory_profile_after = profile_snapshot(self.memory_profile, limit=12)
        return provisional_run
