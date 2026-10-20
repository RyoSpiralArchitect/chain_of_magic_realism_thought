# Reservoir

## Unstarted
- [ ] R011 Analyze measurements, inspect disagreements, and refresh design questions.
- [ ] R012 Preserve receipts and publish a PR checkpoint.

## In Progress
- [~] R010 Run the frozen study on available Furnace models at 32 pairs/model.

## Completed This Run
- [x] R008 Verified Furnace availability, runtime policy, cached weights, and isolated checkout.
- [x] R009 Added resumable paired generation, independent blind review, and missingness gates.

## Open Questions
- [?] R006 Automatically tune frontier influence -> OQ001 (`001-frontier-influence.md`).
- [?] R007 Automatically revive candidates across runs -> OQ002 (`002-candidate-identity.md`).

## Needs Synchronization

The previous checkout contained no reservoir, run log, or active questions. This
run starts from main at ac60958, including merged PRs #2, #3, and #4.

Last checkpoint: R001-R005 completed in PR #5. No unstarted/in-progress work or
synchronization gaps remain. R006 and R007 are future design choices; neither
blocks the implemented opt-in reminder workflow. See the run log for validation.
