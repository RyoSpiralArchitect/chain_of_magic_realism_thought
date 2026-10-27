# Seed-Derived Anchors or an Explicit Authored Motif Bank

## Context
R024 arose from offline log scrutiny, not a new provider run. The anchor
extractor injects fixed station/clock/office impossibility templates for every
seed, and fallback errands/objects for uncovered settings such as the kitchen
seed. The same profile slots also contribute a literal-match scoring bonus.
Saved stage-1 requests contain those examples before frontier reminders.

In complete GPT-OSS pairs, 36/54 final passages contain the literal future-
errand phrase, already present in 20/54 selected first-stage passages. This
locates an explicit source of shared imagery; it does not establish a causal
effect size, learned overfitting, or human literary quality.
Only 4/54 GPT-OSS finals match a complete supplied slot exactly; phrase reuse
must not be conflated with actually receiving that exact-match score bonus.

## Question
A: keep automatically extracted profiles strictly seed-derived, leaving
unobserved context/slots empty, or B: retain an optional authored motif bank
with explicit provenance separate from seed evidence and evaluation targets?

## Options
- A: removes unsupported supplied content from the automatic anchor profile.
  Reduces guidance for short seeds; may change generation and scoring behavior.
- B: preserves controllable literary material but makes its source explicit,
  opt-in, and distinguishable from seed-derived evidence. Requires deciding
  whether matching supplied examples belongs in any evaluation score.

## Assessment
Prefer explicit provenance separation before another effect study. Do not
delete examples or tune their scoring bonus based on this assessment. A
separately frozen ablation would be needed to estimate their influence.

## Dependencies
R024 blocks only a new anchor/guidance policy and follow-up ablation. Offline
review documentation R022-R023 is independent and may finish.

## References
- `src/magic_realism_thought/prompts.py::extract_prompt_anchor_profile`.
- `src/magic_realism_thought/metrics.py::compute_magic_realism_metrics`.
- `experiments/results/api-judge-20261027/LOG_REVIEW.md` and `log_review.json`.
- Saved p06 profiles and p04 stage-1 calls under the original Furnace raw root.

## Related Questions
OQ001 covers automatic influence tuning; OQ004 covers length/objective mismatch;
OQ005 covers pre-dose divergence; OQ006 covers semantic judge qualification.

## Portability
The current run was log inspection only. The old generator outputs, judge
results, score formulas, and weights remain unchanged. No automatic policy,
new API call, new model, or human-gold label is authorized by this question.
