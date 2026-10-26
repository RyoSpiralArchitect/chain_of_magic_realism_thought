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

## Dependencies
None for the authorized static adapter. R006 blocks only automatic adaptation.

## References
- `docs/frontier_control.md`: evidence, prompt boundary, and verification limit.
- `src/magic_realism_thought/reward_audit.py`: reward-surface overfitting signals.

## Related Questions
OQ002 concerns candidate identity, which must also be defined before automatic revival.

## Portability
The conversational authorization is quoted in Context. Offline tests prove the
connection and scoring separation, not improved prose. No live-provider quality
comparison or automatic influence policy has been implemented.
