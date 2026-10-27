# Reservoir

## Unstarted

## In Progress

## Completed This Run

Completion records are transferred to Run 2 and Run 3 entries in `run-log.md`.

## Open Questions
- [?] R006 Automatically tune frontier influence -> OQ001 (`001-frontier-influence.md`).
- [?] R007 Automatically revive candidates across runs -> OQ002 (`002-candidate-identity.md`).
- [?] R013 Distinguish coverage from targeted effects -> OQ003 (`003-intervention-coverage.md`).
- [?] R014 Align prompt length targets and evaluation -> OQ004 (`004-length-objective.md`).
- [?] R016 Define replay granularity under sampling -> OQ005 (`005-replay-granularity.md`).
- [?] R017 Qualify automated judging or establish human anchors -> OQ006 (`006-judge-qualification.md`).

## Needs Synchronization

The previous checkout contained no reservoir, run log, or active questions. This
run starts from main at ac60958, including merged PRs #2, #3, and #4.

Run 1 completed R001-R005 in PR #5 (now merged to main). Run 2 completed
R008-R012, R015, and R018 in PR #6 (now merged to frontier-soft-control).
All generation and judging processes are closed. Complete pairs: 4B 32/32,
12B 32/32, GPT-OSS 27/32; all planned attempts are finished. The judge selected
A in 181/182 responses, leaving 90/91 comparisons order-inconsistent and unknown.
No literary-quality effect or automatic policy is established.

Run 3 completed 2026-10-27: Ryō explicitly authorized replacing the judge with a
large API model and reusing the existing process OPENAI_API_KEY. Scope: compare
the same 91 complete pairs in both orders, no generation, no tuning, no human
gold or automatic qualification claim. GPT-6 Astra is available; low reasoning,
2048 output tokens, 182 calls, no retries, $30 modeled budget with a conservative
$27.7359 plan bound. Initial two requests are operational checks retained in
the final denominator, not new human-gold sentinels. The old report is immutable.

PR #5 is merged to main; PR #6 merged into SpiralReality/frontier-soft-control,
not yet into main. This work starts at that integrated branch's 690a3df and stays
stacked there. Six active questions remain; no synchronization gaps.

R019-R021 are complete in open PR #7. API comparisons: 182/182 valid final
responses, 75/91 order-consistent pairs; dosed on/off/unknown 7/15/5. No claim
of literary correctness or causal benefit. Estimated API cost $3.402755.
All owned API processes are closed. Source generator artifacts, production
code, PRM weights, and the original report remain unchanged.

One bounded frontier refresh found no new independent work. Unstarted 0 / in
progress 0 / active questions 6 / synchronization gaps 0. Stop reason: authorized
fixed-passage comparison, validation, and PR checkpoint complete. Further
sentinel/human qualification or tuning requires a new decision, not an OQ lean.
