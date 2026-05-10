# Design Risk Notes

This harness intentionally manages visible state transitions, not hidden chain-of-thought.
The current mitigations are trace-first and conservative: they make pressure visible without silently changing the literary objective.

## Ontology Inflation

Risk: axes, operators, conflict types, repair plans, and rule hypotheses can multiply until ontology maintenance becomes the real task.

Mitigation:

- `rpm_trace.ontology_ledger` records active axes, observed operators, conflict types, and rule kinds.
- The ledger includes `ontology_pressure` warnings when counts cross local caps.
- New concepts should change a downstream decision, repair, score, or review path. Otherwise keep them as prose in docs or as report-only evidence.

## Reward Surface Overfitting

Risk: repeated scoring can teach the system to imitate high-reward-looking prose rather than produce genuinely better transitions.

Mitigation:

- `reward_surface_audit` reports saturated axes, low selection margins, and near-duplicate candidate sets.
- Run memory now reminds providers that memory is continuity evidence, not a style target.
- Memory notes record the audit risk level, making reward pressure visible across runs.

Useful checks:

- Run blind prompts that should not fit the prior.
- Keep low-margin rejected candidates for review.
- Avoid raising weights on already saturated axes.

## Visible-Only Limits

Risk: hidden CoT is avoided correctly, but important judgment can live in rejected, repaired, deferred, or abandoned paths.

Mitigation:

- `rpm_trace.decision_landscape` records accepted, rejected, and repaired candidates with scores and visible reasons.
- Unresolved conflicts are carried as deferred judgments in the decision record.
- The trace records decision terrain without asking any model to reveal private reasoning.

This is a judgment-landscape log, not a thought log.
