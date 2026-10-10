from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .prompts import (
    anchor_seed_symbols,
    extract_prompt_anchor_profile,
    format_magic_realism_prior,
    load_stages,
    parse_model_overrides,
    parse_provider_list,
    parse_role_provider_overrides,
    read_seed,
)
from .providers import ProviderError
from .render import render_markdown, save_outputs
from .runner import SpiralRpmPrmRunnerV5
from .types import ChainConstraints, DEFAULT_SYSTEM_TEMPLATE, PROVIDER_NAMES, default_magic_realism_prior

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provider-abstracted PRM-style visible-process magic-realism harness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    provider_group = parser.add_mutually_exclusive_group()
    provider_group.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        help="Single provider to make available. Role routing collapses to this provider.",
    )
    provider_group.add_argument(
        "--providers",
        type=parse_provider_list,
        default=None,
        help="Comma-separated providers made available to the router.",
    )
    parser.add_argument("--routing", choices=("role", "round-robin"), default="role", help="Provider routing mode.")
    parser.add_argument("--role-provider", action="append", default=[], help="Override role routing: role=provider")
    parser.add_argument("--model", action="append", default=[], help="Override model: provider=model")
    parser.add_argument("--prompt", "-p", help="Seed prompt text.")
    parser.add_argument("--prompt-file", help="Read seed prompt from a UTF-8 file.")
    parser.add_argument("--stages-file", help="JSON list of custom stages: [{name, role, operator, instruction}, ...].")
    parser.add_argument("--stage-preset", choices=("default", "seed-independent-magic"), default="default", help="Built-in stage preset to use when --stages-file is omitted.")
    parser.add_argument("--magic-realism-prior", action="store_true", help="Inject the ontology-level magic realism prior into system, stage, repair, and aggregation prompts.")
    parser.add_argument("--anchor-profile", choices=("off", "auto"), default="off", help="Build a PromptAnchorProfile from an ordinary prompt and use it as seed-independent mundane grounding.")
    parser.add_argument("--language", default="Japanese", help="Output language instruction.")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature. Use --no-temperature to omit.")
    parser.add_argument("--no-temperature", action="store_true", help="Do not send temperature to providers.")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max output tokens per generation call.")
    parser.add_argument("--max-context-chars", type=int, default=9000, help="Prompt clipping budget for current state text.")
    parser.add_argument("--seed-symbol", action="append", default=[], help="Manually seed a recurring symbol. Repeatable.")
    parser.add_argument("--symbol-limit", type=int, default=12, help="Maximum symbols kept in ChainState.")

    parser.add_argument("--max-drift", type=float, default=0.82, help="Adaptive-control upper bound for drift_score.")
    parser.add_argument("--min-drift", type=float, default=0.18, help="Adaptive-control lower bound for drift_score.")
    parser.add_argument("--max-repetition", type=float, default=0.28, help="Adaptive-control upper bound for repetition_score.")
    parser.add_argument("--min-recurrence", type=float, default=0.15, help="Adaptive-control lower bound for recurrence_score.")
    parser.add_argument("--min-novelty", type=float, default=0.18, help="Adaptive-control lower bound for novelty_score.")
    parser.add_argument("--max-collapse", type=float, default=0.55, help="Adaptive-control upper bound for collapse_score.")
    parser.add_argument("--required-prefix", help="Prompt-level prefix constraint for visible outputs.")

    parser.add_argument("--prm", choices=("heuristic", "llm", "hybrid"), default="heuristic", help="Process reward model mode.")
    parser.add_argument("--candidates", type=int, default=2, help="Candidate steps generated per stage before PRM selection.")
    parser.add_argument("--accept-threshold", type=float, default=0.62, help="PRM score threshold for immediate acceptance.")
    parser.add_argument("--repair-threshold", type=float, default=0.50, help="PRM score threshold below which a candidate may be too weak to repair.")
    parser.add_argument("--repair-attempts", type=int, default=1, help="Optional repair calls for low-reward selected candidates.")
    parser.add_argument("--judge-provider", choices=PROVIDER_NAMES, help="Provider used for LLM PRM judge in llm/hybrid mode.")
    parser.add_argument("--judge-model", help="Model used for LLM PRM judge. Defaults to the chosen judge provider model.")
    parser.add_argument("--judge-temperature", type=float, default=0.0, help="Sampling temperature for LLM judge.")
    parser.add_argument("--judge-max-tokens", type=int, default=900, help="Max output tokens for LLM judge calls.")
    parser.add_argument("--hybrid-llm-weight", type=float, default=0.45, help="LLM judge weight in hybrid PRM mode.")

    parser.add_argument("--no-aggregate", action="store_true", help="Disable aggregation stage.")
    parser.add_argument("--no-recursive-closure", action="store_true", help="Disable recursive closure stage.")

    parser.add_argument("--beam-width", type=int, default=1, help="Keep this many top process paths after each generation stage. 1 disables beam search.")
    parser.add_argument("--beam-branching", type=int, default=0, help="From each path, keep this many top candidates before pruning. 0 uses --beam-width.")
    parser.add_argument("--beam-archive", type=int, default=8, help="Number of high-scoring path snapshots kept in the report.")

    parser.add_argument("--memory-profile", help="Load a run-memory JSON profile and use it as a soft prior.")
    parser.add_argument("--save-memory-profile", help="Write updated run-memory JSON here. Defaults to --memory-profile when provided.")
    parser.add_argument("--memory-weight", type=float, default=0.25, help="Soft influence of run memory in prompts/provider ordering.")
    parser.add_argument("--no-memory-update", action="store_true", help="Load memory if present but do not update/save it after the run.")
    parser.add_argument("--output-json", help="Write the full run to JSON.")
    parser.add_argument("--output-md", help="Write a Markdown report.")
    parser.add_argument("--show-stages", action="store_true", help="Print all accepted visible state transitions, not only final.")
    parser.add_argument("--show-candidates", action="store_true", help="Print rejected and repaired candidate IDs in Markdown output.")
    parser.add_argument("--show-rpm", action="store_true", help="Print the RPM matrix, rule hypotheses, conflicts, and repair plans.")
    parser.add_argument("--include-prompts", action="store_true", help="Include rendered prompts in JSON output.")
    parser.add_argument("--dry-run", action="store_true", help="Use fake providers; no SDK imports or API calls.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        seed = read_seed(args)
        providers = args.providers or ([args.provider] if args.provider else ["openai"])
        models = parse_model_overrides(args.model)
        role_providers = parse_role_provider_overrides(args.role_provider)
        stages = load_stages(args.stages_file, preset=args.stage_preset)
        temperature = None if args.no_temperature else args.temperature
        judge_temperature = None if args.no_temperature else args.judge_temperature
        system = DEFAULT_SYSTEM_TEMPLATE.format(language=args.language)
        magic_prior = default_magic_realism_prior() if args.magic_realism_prior or args.stage_preset == "seed-independent-magic" else None
        anchor_profile = extract_prompt_anchor_profile(seed) if args.anchor_profile == "auto" else None
        if magic_prior:
            system = f"{system}\n\n{format_magic_realism_prior(magic_prior, anchor_profile)}"
        seed_symbols = list(args.seed_symbol)
        if anchor_profile and not seed_symbols:
            seed_symbols = anchor_seed_symbols(anchor_profile, limit=args.symbol_limit)
        constraints = ChainConstraints(
            max_drift=args.max_drift,
            min_drift=args.min_drift,
            max_repetition=args.max_repetition,
            min_recurrence=args.min_recurrence,
            min_novelty=args.min_novelty,
            max_collapse=args.max_collapse,
            required_prefix=args.required_prefix,
            symbol_limit=args.symbol_limit,
        )

        runner = SpiralRpmPrmRunnerV5(
            providers=providers,
            models=models,
            role_providers=role_providers,
            routing=args.routing,
            stages=stages,
            system=system,
            constraints=constraints,
            temperature=temperature,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
            include_prompts=args.include_prompts,
            candidates=args.candidates,
            prm_mode=args.prm,
            accept_threshold=args.accept_threshold,
            repair_threshold=args.repair_threshold,
            repair_attempts=args.repair_attempts,
            judge_provider=args.judge_provider,
            judge_model=args.judge_model,
            judge_temperature=judge_temperature,
            judge_max_tokens=args.judge_max_tokens,
            hybrid_llm_weight=args.hybrid_llm_weight,
            aggregate=not args.no_aggregate,
            recursive_closure=not args.no_recursive_closure,
            max_context_chars=args.max_context_chars,
            beam_width=args.beam_width,
            beam_branching=args.beam_branching,
            beam_archive=args.beam_archive,
            memory_profile_path=args.memory_profile,
            save_memory_profile_path=args.save_memory_profile,
            memory_weight=args.memory_weight,
            memory_update=not args.no_memory_update,
            magic_prior=magic_prior,
            anchor_profile=anchor_profile,
        )
        run = runner.run(seed=seed, language=args.language, seed_symbols=seed_symbols)
        save_outputs(
            run,
            args.output_json,
            args.output_md,
            show_stages=True,
            show_candidates=args.show_candidates,
            show_rpm=True,
        )

        if args.show_stages or args.show_rpm:
            print(render_markdown(run, show_stages=args.show_stages, show_candidates=args.show_candidates, show_rpm=args.show_rpm or args.show_stages))
        else:
            print(run.final)

        if args.output_json or args.output_md:
            written = [p for p in (args.output_json, args.output_md) if p]
            print(f"\nWrote: {', '.join(written)}", file=sys.stderr)
        return 0

    except (ValueError, ProviderError, argparse.ArgumentTypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
