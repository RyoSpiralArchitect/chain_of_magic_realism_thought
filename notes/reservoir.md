# Reservoir

## Unstarted

## In Progress

## Completed This Run

Completion records are transferred to the final Run 2 entry in `run-log.md`.

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

Run 1 completed R001-R005 in open PR #5. Run 2 completed R008-R012, R015,
and the final structure-doc refresh R018 in stacked PR #6 (open, unmerged).
All generation and judging processes are closed. Complete pairs: 4B 32/32,
12B 32/32, GPT-OSS 27/32; all planned attempts are finished. The judge selected
A in 181/182 responses, leaving 90/91 comparisons order-inconsistent and unknown.
No literary-quality effect or automatic policy is established.

The final report, machine-readable evidence, archive hash, and validation
receipts are in `experiments/results/furnace-20261020/`. Unstarted 0, in progress
0, open questions 6, synchronization gaps 0. One bounded frontier refresh found
only the now-fixed structure-doc drift. Stop reason: authorized measurement,
analysis, and PR checkpoint scope complete; remaining work needs decisions.
