from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .types import ChainRun
from .utils import json_safe, utc_now_iso

def empty_memory_profile() -> Dict[str, Any]:
    return {
        "version": "5-memory-1.0",
        "created_at_utc": utc_now_iso(),
        "updated_at_utc": utc_now_iso(),
        "run_count": 0,
        "provider_role_scores": {},
        "stage_scores": {},
        "operator_scores": {},
        "symbol_scores": {},
        "notes": [],
    }


def load_memory_profile(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return empty_memory_profile()
    profile_path = Path(path)
    if not profile_path.exists():
        return empty_memory_profile()
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not read memory profile {path!r}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Memory profile {path!r} must contain a JSON object.")
    base = empty_memory_profile()
    base.update(data)
    return base


def save_memory_profile(path: Optional[str], profile: Dict[str, Any]) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json_safe(profile), ensure_ascii=False, indent=2), encoding="utf-8")


def update_mean_stat(bucket: Dict[str, Any], key: str, value: float, extra: Optional[Dict[str, Any]] = None) -> None:
    rec = bucket.setdefault(key, {"count": 0, "mean_reward": 0.0})
    count = int(rec.get("count", 0)) + 1
    prior = float(rec.get("mean_reward", 0.0))
    rec["count"] = count
    rec["mean_reward"] = round(prior + (float(value) - prior) / count, 5)
    if extra:
        for k, v in extra.items():
            rec[k] = v


def profile_snapshot(profile: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
    def top_items(bucket_name: str) -> List[Dict[str, Any]]:
        bucket = profile.get(bucket_name, {})
        if not isinstance(bucket, dict):
            return []
        items = []
        for key, rec in bucket.items():
            if isinstance(rec, dict):
                items.append({"key": key, **{k: rec.get(k) for k in ("count", "mean_reward") if k in rec}})
        return sorted(items, key=lambda x: (float(x.get("mean_reward") or 0.0), int(x.get("count") or 0)), reverse=True)[:limit]

    provider_roles: List[Dict[str, Any]] = []
    raw_provider_roles = profile.get("provider_role_scores", {})
    if isinstance(raw_provider_roles, dict):
        for role, provider_bucket in raw_provider_roles.items():
            if not isinstance(provider_bucket, dict):
                continue
            for provider, rec in provider_bucket.items():
                if isinstance(rec, dict):
                    provider_roles.append({
                        "role": role,
                        "provider": provider,
                        "count": rec.get("count", 0),
                        "mean_reward": rec.get("mean_reward", 0.0),
                    })
    provider_roles = sorted(provider_roles, key=lambda x: (float(x.get("mean_reward") or 0.0), int(x.get("count") or 0)), reverse=True)[:limit]
    return {
        "version": profile.get("version"),
        "run_count": profile.get("run_count", 0),
        "updated_at_utc": profile.get("updated_at_utc"),
        "top_provider_roles": provider_roles,
        "top_stages": top_items("stage_scores"),
        "top_operators": top_items("operator_scores"),
        "top_symbols": top_items("symbol_scores"),
    }


def best_memory_provider_for_role(profile: Dict[str, Any], role: str, available: Sequence[str], min_count: int = 1) -> Optional[str]:
    role_bucket = profile.get("provider_role_scores", {}).get(role, {}) if isinstance(profile.get("provider_role_scores"), dict) else {}
    if not isinstance(role_bucket, dict):
        return None
    best: Optional[Tuple[float, int, str]] = None
    for provider in available:
        rec = role_bucket.get(provider)
        if not isinstance(rec, dict):
            continue
        count = int(rec.get("count", 0))
        if count < min_count:
            continue
        score = float(rec.get("mean_reward", 0.0))
        item = (score, count, provider)
        if best is None or item > best:
            best = item
    return best[2] if best else None


def format_memory_context(profile: Dict[str, Any], role: str, available_providers: Sequence[str], memory_weight: float, max_lines: int = 8) -> str:
    if not profile or int(profile.get("run_count", 0) or 0) <= 0 or memory_weight <= 0:
        return "No prior run memory is active for this stage."
    lines: List[str] = []
    preferred = best_memory_provider_for_role(profile, role, available_providers)
    if preferred:
        rec = profile.get("provider_role_scores", {}).get(role, {}).get(preferred, {})
        lines.append(f"Memory-preferred provider for role {role!r}: {preferred} (mean_reward={rec.get('mean_reward')}, count={rec.get('count')}).")
    snapshot = profile_snapshot(profile, limit=5)
    if snapshot.get("top_symbols"):
        syms = ", ".join(f"{x['key']}:{x.get('mean_reward')}" for x in snapshot["top_symbols"][:5])
        lines.append("Previously stable/rewarded symbols: " + syms)
    if snapshot.get("top_operators"):
        ops = ", ".join(f"{x['key']}:{x.get('mean_reward')}" for x in snapshot["top_operators"][:4])
        lines.append("Previously strong operators: " + ops)
    if snapshot.get("top_provider_roles"):
        prs = ", ".join(f"{x['role']}/{x['provider']}:{x.get('mean_reward')}" for x in snapshot["top_provider_roles"][:4])
        lines.append("Provider-role memory: " + prs)
    lines.append(f"Memory weight: {memory_weight:.2f}; treat this as a soft prior, not a hard rule.")
    lines.append("Reward-surface guard: do not imitate prior rewarded style; use memory to test continuity, not to force symbols, tone, or operators.")
    return "\n".join(lines[:max_lines])


def update_memory_profile_from_run(profile: Dict[str, Any], run: "ChainRun") -> Dict[str, Any]:
    profile = json_safe(profile)
    profile.setdefault("version", "5-memory-1.0")
    profile.setdefault("created_at_utc", utc_now_iso())
    profile["updated_at_utc"] = utc_now_iso()
    profile["run_count"] = int(profile.get("run_count", 0) or 0) + 1
    provider_role_scores = profile.setdefault("provider_role_scores", {})
    stage_scores = profile.setdefault("stage_scores", {})
    operator_scores = profile.setdefault("operator_scores", {})
    symbol_scores = profile.setdefault("symbol_scores", {})

    for step in run.steps:
        cand = step.accepted
        reward = cand.reward.score if cand.reward else 0.0
        role_bucket = provider_role_scores.setdefault(step.role, {})
        update_mean_stat(role_bucket, cand.provider, reward, extra={"last_model": cand.model})
        update_mean_stat(stage_scores, step.name, reward, extra={"last_role": step.role})
        update_mean_stat(operator_scores, step.operator or step.role, reward, extra={"last_role": step.role})
        for sym in cand.symbols_after[:10]:
            update_mean_stat(symbol_scores, sym, reward, extra={"last_seen_stage": step.name})

    notes = profile.setdefault("notes", [])
    if isinstance(notes, list):
        notes.append(
            f"run {profile['run_count']}: mean_reward={sum((s.accepted.reward.score if s.accepted.reward else 0.0) for s in run.steps)/max(1,len(run.steps)):.4f}; "
            f"reward_surface_risk={run.reward_surface_audit.risk_level}; final_symbols={', '.join(run.final_state.symbols[:6])}"
        )
        profile["notes"] = notes[-25:]
    return profile
