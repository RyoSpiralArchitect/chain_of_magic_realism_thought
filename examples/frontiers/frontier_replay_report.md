# Frontier Replay Report

- Contract: `frontier-replay-1.0`
- Runs: `2`
- Seed consistency: `True`
- Seed: 雨が祖母の筆跡を覚えていた。

## Runs

| run | decisions | frontier | active | abandoned | deferred | hesitations |
|---|---:|---:|---:|---:|---:|---:|
| `frontier-replay-a` | 2 | 5 | 2 | 1 | 2 | 3 |
| `frontier-replay-b` | 3 | 6 | 3 | 1 | 2 | 3 |

## Replay Transitions

### `frontier-replay-a` -> `frontier-replay-b`

| kind | state | stage | detail |
|---|---|---:|---|
| accepted_path | `contradicted_prior_abandonment` | stage:1 | s01-c01 -> s01-c02: a previously abandoned candidate became accepted |
| stage_presence | `added` | stage:3 | social normalization |
| deferred_judgment | `resolved` | 1 | stage:1:deferred:symbol_loss |
| deferred_judgment | `improved_but_open` | 2 | stage:2:deferred:operator_mismatch |
| deferred_judgment | `new` | 3 | stage:3:deferred:high_drift |

Ontology growth gate:
- `conflict_type` added `high_drift`: requires_rationale
- `operator` added `normalize`: requires_rationale

## Latest Frontier

- `d02-01` deferred_judgment `c02-01-operator_mismatch` score `0.55`: make the operator visible through objects rather than commentary
- `d03-01` deferred_judgment `c03-01-high_drift` score `0.7`: re-anchor the rain and handwriting before the next transition

Architectural hesitations:
- `d02-01` open_structural_conflict
- `d03-01` low_selection_margin=0.0400
- `d03-01` open_structural_conflict

## Recommendations

- Review latest open deferred judgments before treating the path as settled.
- Inspect revived abandoned candidates; the replay surfaced a visible ranking reversal.
- Attach rationale for new ontology terms before promoting them into durable trace vocabulary.
