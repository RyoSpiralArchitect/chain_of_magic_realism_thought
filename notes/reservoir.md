# Reservoir

## Unstarted

## In Progress
- [~] R010 Run the frozen study on available Furnace models at 32 pairs/model.
- [~] R011 Analyze measurements, inspect disagreements, and refresh design questions.
- [~] R012 Preserve receipts and publish a PR checkpoint (draft PR #6 open).

## Completed This Run
- [x] R008 Verified Furnace availability, runtime policy, cached weights, and isolated checkout.
- [x] R009 Added resumable paired generation, independent blind review, and missingness gates.
- [x] R015 Included stage recipes in resume fingerprints and hardened interrupted atomic writes.

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
study; R011-R012 cover analysis and publication; R015 is complete.
4B and 12B are complete at source 9e77ff6. GPT-OSS study2 failed qualification;
study3 is running at 47e7dcd with native system-role rendering. Independent
judging remains. Do not update the remote checkout during generation. See the latest
run-log checkpoint and live remote status files before resuming. Five active
questions do not block this frozen experiment. No synchronization gaps.
