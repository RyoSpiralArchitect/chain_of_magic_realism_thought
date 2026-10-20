# Exact Passage Identity or Declared Lineage

## Context
R007 concerns `frontier_replay.py::_compare_accepted_paths`, which compares
stage-local candidate IDs across runs. The generator reuses ID shapes. The
story-reader's handwritten revival fixture deliberately shares IDs and prose.
The new control adapter keeps all revival events review-only.

## Question
A: require identical visible-passage hashes for revival, or B: require an
explicit cross-run lineage reference that can also describe revised passages?

## Options
- A: exact output-byte hashes establish text equality, but require full saved
  candidate text and exclude revisions. Equality alone does not establish a
  shared generation history.
- B: store source run SHA-256, stage, and candidate ID as lineage, optionally
  with an output hash. Supports revisions but needs producer/consumer validation
  and a declared policy for missing source records.

## Assessment
Prefer B for automatic reuse because it makes provenance explicit; use A as an
independent integrity check. This assessment does not authorize either change.

## Dependencies
None for static concern reminders. R007 blocks automatic candidate revival.

## References
- `src/magic_realism_thought/runner.py`: candidate ID generation.
- `src/magic_realism_thought/frontier_replay.py`: accepted-path comparison.
- `examples/frontiers/handwritten_revival/`: authored equal-passage example.
- `tests/test_handwritten_revival.py`: current report and reader contracts.

## Related Questions
OQ001 concerns automatic influence; neither requires automatic revival.

## Portability
The current replay and reader retain their legacy ID-matching behavior. No
cross-run candidate identity guarantee follows from those labels. This task's
authorization covers prompt reminders, not automatic passage reuse.
