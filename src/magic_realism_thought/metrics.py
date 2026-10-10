from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence

from .types import (
    COSMIC_EXPLANATION_TERMS,
    DREAM_REVEAL_TERMS,
    EXPLANATION_TERMS,
    FANTASY_LORE_TERMS,
    IMPOSSIBLE_FACT_TERMS,
    MUNDANE_OBJECT_TERMS,
    ORDINARY_CONTINUITY_TERMS,
    PURPLE_ABSTRACTION_TERMS,
    SOCIAL_NORMALIZATION_TERMS,
    STOP_SYMBOLS,
    ChainConstraints,
    ChainState,
    StageSpec,
    default_magic_realism_prior,
)
from .utils import clamp01, safe_div

TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_'-]*|[0-9]+(?:\.[0-9]+)?|[一-龯々〆ヵヶ]{2,}|[ァ-ヴー]{2,}|[ぁ-ゖ]{2,}",
    re.UNICODE,
)
QUOTE_RE = re.compile(r"[「『\"']([^」』\"']{1,16})[」』\"']")


def normalize_for_similarity(text: str, max_chars: int = 6000) -> str:
    text = re.sub(r"\s+", "", text)
    return text[:max_chars]


def tokenize_text(text: str) -> List[str]:
    tokens = [m.group(0).lower() for m in TOKEN_RE.finditer(text)]
    return [t for t in tokens if t and t not in STOP_SYMBOLS]


def char_ngrams(text: str, n: int = 3, limit: int = 2500) -> List[str]:
    clean = normalize_for_similarity(text, max_chars=limit)
    if not clean:
        return []
    if len(clean) <= n:
        return [clean]
    return [clean[i : i + n] for i in range(0, len(clean) - n + 1)]


def metric_units(text: str) -> List[str]:
    tokens = tokenize_text(text)
    if len(tokens) < 12:
        tokens.extend(char_ngrams(text, n=3, limit=1200))
    return tokens


def shannon_entropy_score(units: Sequence[str]) -> float:
    if not units:
        return 0.0
    counts = Counter(units)
    total = len(units)
    if len(counts) <= 1:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
    return clamp01(entropy / math.log(len(counts)))


def observe_transition(previous: str, current: str, symbols: Sequence[str]) -> Dict[str, float]:
    prev_norm = normalize_for_similarity(previous)
    curr_norm = normalize_for_similarity(current)
    similarity = difflib.SequenceMatcher(None, prev_norm, curr_norm).ratio() if prev_norm or curr_norm else 1.0
    surface_drift = 1.0 - similarity

    prev_units = metric_units(previous)
    curr_units = metric_units(current)
    prev_set = set(prev_units)
    curr_set = set(curr_units)
    union = prev_set | curr_set
    intersection = prev_set & curr_set
    jaccard_similarity = safe_div(len(intersection), len(union), default=1.0)
    lexical_drift = 1.0 - jaccard_similarity
    novelty = safe_div(sum(1 for unit in curr_units if unit not in prev_set), len(curr_units), default=0.0)

    counts = Counter(curr_units)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    repetition = safe_div(repeated, len(curr_units), default=0.0)

    active_symbols = [sym for sym in symbols if sym]
    if active_symbols:
        present = 0.0
        for sym in active_symbols:
            present += min(1.0, current.count(sym) / 2.0)
        recurrence = present / len(active_symbols)
    else:
        recurrence = 0.0

    entropy = shannon_entropy_score(curr_units)
    char_len = float(len(current))
    shortness = 1.0 if char_len < 80 else max(0.0, 1.0 - char_len / 450.0)
    collapse = clamp01(0.55 * repetition + 0.30 * shortness + 0.15 * (1.0 - entropy))
    compression_ratio = safe_div(len(current), len(previous), default=1.0)
    drift_score = clamp01(0.65 * surface_drift + 0.35 * lexical_drift)

    return {
        "char_len": round(char_len, 4),
        "unit_count": round(float(len(curr_units)), 4),
        "similarity": round(similarity, 4),
        "surface_drift": round(surface_drift, 4),
        "lexical_drift": round(lexical_drift, 4),
        "drift_score": round(drift_score, 4),
        "novelty_score": round(novelty, 4),
        "repetition_score": round(repetition, 4),
        "recurrence_score": round(recurrence, 4),
        "entropy_score": round(entropy, 4),
        "collapse_score": round(collapse, 4),
        "compression_ratio": round(compression_ratio, 4),
    }


def term_hit_count(text: str, terms: Iterable[str]) -> int:
    lower = str(text or "").lower()
    return sum(1 for term in terms if term and term.lower() in lower)


def term_score(text: str, terms: Iterable[str], target: int) -> float:
    return clamp01(term_hit_count(text, terms) / max(1, target))


def profile_hit_score(text: str, values: Sequence[str], target: int) -> float:
    lower = str(text or "").lower()
    hits = 0
    for value in values:
        value = str(value or "").strip()
        if value and value.lower() in lower:
            hits += 1
    return clamp01(hits / max(1, target))


def compute_magic_realism_metrics(
    text: str,
    state: Optional[ChainState] = None,
    stage: Optional[StageSpec] = None,
    transition_metrics: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    profile = state.anchor_profile if state else None
    prior = state.magic_prior if state else None
    transition_metrics = transition_metrics or {}
    mundane_profile = 0.0
    social_profile = 0.0
    object_profile = 0.0
    continuity_profile = 0.0
    impossible_profile = 0.0
    if profile:
        mundane_profile = profile_hit_score(text, profile.mundane_anchors, target=3)
        social_profile = 0.35 if profile.social_setting and any(part in text for part in profile.social_setting.split("と")) else 0.0
        object_profile = profile_hit_score(text, profile.ordinary_objects, target=4)
        continuity_profile = profile_hit_score(text, profile.routine_actions, target=3)
        impossible_profile = profile_hit_score(text, profile.impossible_fact_slots, target=1)

    mundane_grounding = clamp01(0.45 * term_score(text, MUNDANE_OBJECT_TERMS, 6) + 0.35 * object_profile + 0.20 * mundane_profile)
    quiet_impossibility = clamp01(
        0.55 * term_score(text, IMPOSSIBLE_FACT_TERMS, 2)
        + 0.25 * impossible_profile
        + 0.20 * transition_metrics.get("novelty_score", 0.0)
    )
    explanation_density = clamp01(term_hit_count(text, EXPLANATION_TERMS) / 4.0)
    non_explanation = clamp01(1.0 - explanation_density)
    social_normalization = clamp01(0.65 * term_score(text, SOCIAL_NORMALIZATION_TERMS, 4) + 0.20 * social_profile + 0.15 * mundane_grounding)
    concrete_object = clamp01(0.70 * term_score(text, MUNDANE_OBJECT_TERMS, 7) + 0.30 * object_profile)
    symbolic_pressure = clamp01(
        0.45 * transition_metrics.get("recurrence_score", 0.0)
        + 0.25 * quiet_impossibility
        + 0.20 * concrete_object
        + 0.10 * (1.0 - transition_metrics.get("collapse_score", 0.0))
    )
    ordinary_continuity = clamp01(
        0.50 * term_score(text, ORDINARY_CONTINUITY_TERMS, 4)
        + 0.30 * continuity_profile
        + 0.20 * mundane_grounding
    )

    fantasy_lore_penalty = clamp01(term_hit_count(text, FANTASY_LORE_TERMS) / 2.0)
    dream_reveal_penalty = clamp01(term_hit_count(text, DREAM_REVEAL_TERMS) / 1.0)
    cosmic_explanation_penalty = clamp01(term_hit_count(text, COSMIC_EXPLANATION_TERMS) / 2.0)
    purple_abstraction_penalty = clamp01(term_hit_count(text, PURPLE_ABSTRACTION_TERMS) / 5.0)
    anti_fantasy = clamp01(1.0 - fantasy_lore_penalty)
    restraint = clamp01(1.0 - max(fantasy_lore_penalty, dream_reveal_penalty, cosmic_explanation_penalty, purple_abstraction_penalty, explanation_density * 0.6))

    weights = prior or default_magic_realism_prior()
    positive = (
        weights.mundane_grounding * mundane_grounding
        + weights.impossible_fact_density * quiet_impossibility
        + weights.explanatory_restraint * non_explanation
        + weights.social_normalization * social_normalization
        + weights.symbolic_recurrence * symbolic_pressure
        + weights.sensory_concreteness * concrete_object
        + weights.ordinary_continuity * ordinary_continuity
        + weights.restraint * restraint
    )
    positive_total = (
        weights.mundane_grounding
        + weights.impossible_fact_density
        + weights.explanatory_restraint
        + weights.social_normalization
        + weights.symbolic_recurrence
        + weights.sensory_concreteness
        + weights.ordinary_continuity
        + weights.restraint
    ) or 1.0
    penalty = (
        weights.anti_fantasy_penalty * fantasy_lore_penalty
        + weights.anti_dream_penalty * dream_reveal_penalty
        + weights.anti_cosmic_explanation_penalty * cosmic_explanation_penalty
        + weights.anti_purple_prose_penalty * purple_abstraction_penalty
    )
    penalty_total = (
        weights.anti_fantasy_penalty
        + weights.anti_dream_penalty
        + weights.anti_cosmic_explanation_penalty
        + weights.anti_purple_prose_penalty
    ) or 1.0
    magic_reward = clamp01((positive / positive_total) - 0.38 * (penalty / penalty_total))

    if stage and stage.operator in {"quiet_impossibility_injection", "make_magic_a_weather_condition_not_a_message"}:
        quiet_impossibility = clamp01(0.82 * quiet_impossibility + 0.18 * magic_reward)
    if stage and stage.operator in {"social_normalization", "stabilize_magic_as_world_law"}:
        social_normalization = clamp01(0.82 * social_normalization + 0.18 * magic_reward)

    return {
        "mundane_grounding_score": round(mundane_grounding, 4),
        "quiet_impossibility_score": round(quiet_impossibility, 4),
        "non_explanation_score": round(non_explanation, 4),
        "social_normalization_score": round(social_normalization, 4),
        "anti_fantasy_score": round(anti_fantasy, 4),
        "concrete_object_score": round(concrete_object, 4),
        "symbolic_pressure_score": round(symbolic_pressure, 4),
        "ordinary_continuity_score": round(ordinary_continuity, 4),
        "restraint_score": round(restraint, 4),
        "fantasy_lore_penalty": round(fantasy_lore_penalty, 4),
        "dream_reveal_penalty": round(dream_reveal_penalty, 4),
        "cosmic_explanation_penalty": round(cosmic_explanation_penalty, 4),
        "purple_abstraction_penalty": round(purple_abstraction_penalty, 4),
        "explanation_density_score": round(explanation_density, 4),
        "magic_realism_reward": round(magic_reward, 4),
    }


def candidate_symbols_from_text(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for raw in QUOTE_RE.findall(text):
        candidate = raw.strip()
        if 1 <= len(candidate) <= 16 and candidate.lower() not in STOP_SYMBOLS:
            counts[candidate] += 4
    for token in tokenize_text(text):
        if token in STOP_SYMBOLS:
            continue
        if len(token) <= 1:
            continue
        if re.fullmatch(r"[ぁ-ゖ]+", token):
            continue
        weight = 1
        if re.search(r"[一-龯ァ-ヴー]", token):
            weight += min(3, len(token) // 2)
        elif len(token) >= 5:
            weight += 1
        counts[token] += weight
    return counts


def merge_symbols(existing: Sequence[str], text: str, limit: int) -> List[str]:
    cleaned_existing: List[str] = []
    seen = set()
    for sym in existing:
        sym = sym.strip()
        if not sym or sym.lower() in STOP_SYMBOLS or sym in seen:
            continue
        cleaned_existing.append(sym)
        seen.add(sym)

    candidates = candidate_symbols_from_text(text)
    for sym in cleaned_existing:
        candidates[sym] += 6 + min(4, text.count(sym))

    ranked = sorted(candidates.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    merged: List[str] = []
    seen_lower = set()
    for sym, _score in ranked:
        key = sym.lower()
        if key in seen_lower or key in STOP_SYMBOLS:
            continue
        if len(sym) > 18:
            continue
        merged.append(sym)
        seen_lower.add(key)
        if len(merged) >= limit:
            break
    return merged


def make_control_notes(metrics: Dict[str, float], symbols: Sequence[str], constraints: ChainConstraints, text: str) -> List[str]:
    notes: List[str] = []
    drift = metrics.get("drift_score", 0.0)
    novelty = metrics.get("novelty_score", 0.0)
    repetition = metrics.get("repetition_score", 0.0)
    recurrence = metrics.get("recurrence_score", 0.0)
    collapse = metrics.get("collapse_score", 0.0)

    if drift > constraints.max_drift:
        notes.append("Drift is high: preserve the seed's scene, narrator, and 1-2 existing symbols before adding new material.")
    elif drift < constraints.min_drift:
        notes.append("Drift is low: introduce one controlled mutation that changes the scene without replacing its ground.")

    if novelty < constraints.min_novelty:
        notes.append("Novelty is low: add fresh concrete detail rather than paraphrasing the prior stage.")

    if repetition > constraints.max_repetition:
        notes.append("Repetition is high: vary images and sentence shapes; transform symbols instead of repeating the same words.")

    if symbols and recurrence < constraints.min_recurrence:
        notes.append("Symbol recurrence is weak: reintroduce one existing symbol through action, sound, or object behavior.")

    if collapse > constraints.max_collapse:
        notes.append("Collapse risk is high: expand sensory grounding and avoid short, generic abstraction.")

    if "magic_realism_reward" in metrics:
        if metrics.get("mundane_grounding_score", 1.0) < 0.45:
            notes.append("Magic realism prior: restore a mundane social setting, concrete object, or routine action.")
        if metrics.get("quiet_impossibility_score", 1.0) < 0.35:
            notes.append("Magic realism prior: add one small material impossibility without explaining it.")
        if metrics.get("social_normalization_score", 1.0) < 0.35:
            notes.append("Magic realism prior: show a person, office, shop, rule, or habit adapting to the impossible fact.")
        if metrics.get("non_explanation_score", 1.0) < 0.70:
            notes.append("Magic realism prior: remove explanation, dream logic, magic-system language, or interpretive summary.")
        if metrics.get("ordinary_continuity_score", 1.0) < 0.35:
            notes.append("Magic realism prior: let work, travel, paperwork, food, or another ordinary task continue after the impossible fact.")

    if constraints.required_prefix and not text.startswith(constraints.required_prefix):
        notes.append(f"Required prefix was missing: future controlled outputs should begin with {constraints.required_prefix!r}.")

    return notes
