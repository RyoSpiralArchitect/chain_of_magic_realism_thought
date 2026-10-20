# Prompt Length Target or Explicit Evaluation Constraint

## Context
R014 arose while diagnosing the 512-token 4B pilot. All eight calibration runs
were blocked by at least one truncated candidate. A completed off-arm example
had accepted stage lengths of 286, 578, and 616 characters despite the experiment
instruction requesting 140-240. Early complete calls in the wider-output
calibration ranged from 265 to 1211 characters.

The experiment adds this short target for bounded inference. The production
`HeuristicPRM.score` uses `char_len / 360` in its grounding score, saturating at
360 characters. The target is currently prompt-only, not an acceptance check.
This is a potential objective mismatch introduced by the study configuration;
the observations do not establish that the score caused the longer outputs.

Completed paired accepted-step adherence (off/on): Gemma 4B 2/96 and 2/96;
Gemma 12B 28/96 and 29/96; GPT-OSS 63/81 and 53/81. The GPT-OSS denominator
contains only 27 complete pairs; its five truncated runs remain missing from
paired quality measurements. Shorter output is not independently better prose.

## Question
A: retain a soft prompt target and report adherence separately, or B: define
stage-specific explicit length constraints for a future experiment?

## Options
- A: preserve the current frozen scoring formula and compare off/on under the
  same condition. Audit length adherence alongside reward and blind preference.
- B: specify acceptable length by stage and decide separately whether it is an
  evaluation dimension, admission rule, or reward term. Requires a new frozen
  protocol and can change the selection objective.

## Assessment
Prefer A for the current observations. Before a future B, compare independent
literary judgments against compliance; shorter is not automatically better.
Do not alter reward weights using this run's outcomes.

## Dependencies
R014 blocks only a future constraint policy. R010-R012 retain the fixed formula.

## References
- `src/magic_realism_thought/prm.py::HeuristicPRM.score`.
- `experiments/frontier_study.py::make_runner`.
- `gemma3-4b-study1/runs/p02-off-r00.json` in the Furnace evidence root and local
  ignored `artifacts/furnace/20261020/` copy.

## Related Questions
OQ001 concerns reward feedback; OQ003 concerns the number of active interventions.

## Portability
The 512-token pilot is negative compatibility evidence, with zero complete pairs.
The wider budget is a separate frozen configuration, not a replacement of failed
samples. The report now records adherence on complete pairs, with all planned
trials and incomplete candidates retained separately.
