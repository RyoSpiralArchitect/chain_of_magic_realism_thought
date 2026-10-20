# Reservoir

## Unstarted
- [ ] R011 Analyze measurements, inspect disagreements, and refresh design questions.
- [ ] R012 Preserve receipts and publish a PR checkpoint.
- [ ] R015 Include stage recipes in resume fingerprints and harden interrupted atomic writes.

## In Progress
- [~] R010 Run the frozen study on available Furnace models at 32 pairs/model.

## Completed This Run
- [x] R008 Verified Furnace availability, runtime policy, cached weights, and isolated checkout.
- [x] R009 Added resumable paired generation, independent blind review, and missingness gates.

## Open Questions
- [?] R006 Automatically tune frontier influence -> OQ001 (`001-frontier-influence.md`).
- [?] R007 Automatically revive candidates across runs -> OQ002 (`002-candidate-identity.md`).
- [?] R013 Distinguish coverage from targeted effects -> OQ003 (`003-intervention-coverage.md`).
- [?] R014 Align prompt length targets and evaluation -> OQ004 (`004-length-objective.md`).
- [?] R016 Define replay granularity under sampling -> OQ005 (`005-replay-granularity.md`).

## Needs Synchronization

The previous checkout contained no reservoir, run log, or active questions. This
run starts from main at ac60958, including merged PRs #2, #3, and #4.

Run 1 completed R001-R005 in PR #5. Run 2 is active: R010 covers the Furnace
study; R011-R012 cover analysis and publication; R015 is local resume hardening.
4B is complete, 12B is running, and 20B plus independent judging remain. Source
9e77ff6 stays fixed remotely until generator measurements finish. See the latest
run-log checkpoint and live remote status files before resuming. Five active
questions do not block this frozen experiment. No synchronization gaps.
