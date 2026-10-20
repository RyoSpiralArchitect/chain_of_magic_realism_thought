# All-Prompt Coverage or Calibration-Enriched Evaluation

## Context
R013 arose during the Furnace Gemma 3 4B study. The frozen calibration profiles
in `gemma3-4b-study2/profiles/` contain notes for p01 and p08 only (three
repetition concerns total). Six of eight prompt profiles are empty after final
conflict flags are honored. Thus the 32 planned paired units contain at most
eight dosed units from two prompt clusters. This was observed before paired
outcomes were analyzed.

## Question
A: retain all prompts to estimate deployment coverage and overall effects, or
B: predefine a calibration-enriched prompt bank for a separate targeted effect
study?

## Options
- A: keep empty profiles in the denominator, as the current frozen plan does.
  Measures how often the adapter acts, but a null overall effect mixes no-dose
  cases with intervention outcomes.
- B: use independent calibration to freeze eligible prompts before evaluating
  either arm. Report eligibility rate and selected-domain limits. Requires more
  independent prompt clusters; increasing repeats of two prompts is insufficient.

## Assessment
Prefer A for this run's coverage measurement and B as a separately labeled
future experiment. Do not select cases using observed off/on outcomes or silently
replace the current denominator. This assessment authorizes no new policy.

## Dependencies
R013 blocks only a future enriched study. R010-R012 continue under the current plan.

## References
- `experiments/README.md`: denominator and cluster definitions.
- `experiments/frontier_study.py`: independent calibration and `dose_pairs`.
- Furnace evidence root: `/home/ryospiralarchitect/scratch/cmrt-frontier-evidence-20261020/`.

## Related Questions
OQ001 concerns automatic influence tuning; its evidence must distinguish coverage
from effects. OQ004 concerns prompt constraint adherence.

## Portability
The observation is calibration-only and is not a claim about paired outcomes or
the other models. Read the final checked-in experiment report for completed
denominators and artifact hashes. Empty profiles are valid, not missing data.
