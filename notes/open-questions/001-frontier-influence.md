# Static Reminders or Measured Influence Tuning

## Context
R006 follows the replay-to-prompt adapter in `src/magic_realism_thought/frontier_control.py`.
Ryō authorized feeding replay observations into the next run as soft control
notes. The current implementation uses fixed templates and bounded note counts.

## Question
A: retain explicit, static prompt reminders, or B: tune their influence from
observed outcomes across runs?

## Options
- A: keep opt-in profiles and review receipts. Requires no new reward surface.
- B: compare fixed configurations with and without notes, define an independent
  quality criterion, and use that evidence to propose influence changes. Adds
  evaluation cost and a new feedback policy.

## Assessment
Prefer A until a controlled comparison separates literary quality from repeated
heuristic success. This assessment does not authorize implementing B.

The Furnace study now retains 32/32 Gemma 4B pairs, 32/32 Gemma 12B pairs,
and 27/32 GPT-OSS pairs. GPT-OSS has a positive complete-case heuristic interval,
but comparable positive variation in no-dose controls and five missing eligible
pairs. This is not a sufficient promotion criterion; see the measurement report.

The authorized 2026-10-27 API follow-up reused those passages. GPT-6 Astra has
75/91 order-consistent comparisons; among 27 dosed pairs, on wins 7, off wins
15, and 5 remain unknown. Of 22 directional dosed preferences, 15 oppose the
heuristic score direction (10/13 for GPT-OSS). This is criterion disagreement,
not human-gold evidence or authorization to optimize against the new judge.

## Dependencies
None for the authorized static adapter. R006 blocks only automatic adaptation.

## References
- `docs/frontier_control.md`: evidence, prompt boundary, and verification limit.
- `src/magic_realism_thought/reward_audit.py`: reward-surface overfitting signals.
- `experiments/results/furnace-20261020/REPORT.md`: measured evidence and limits.
- `experiments/results/api-judge-20261027/REPORT.md`: fixed-passage API comparison.

## Related Questions
OQ002 concerns candidate identity, which must also be defined before automatic revival.

## Portability
The conversational authorization is quoted in Context. Offline tests prove the
connection and scoring separation, not improved prose. Local real-model paired
comparisons are now recorded in the measurement report, including independent
model-review status. Model judgments are not human gold. No automatic influence
policy has been implemented.
