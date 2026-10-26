# Frontier Control

`frontier-control-1.0` turns saved visible concerns into optional reminders for a
subsequent generation run. Export with `chain-frontier-replay ...
--output-control profile.json`, then opt in with `chain-of-magic-realism
--frontier-control profile.json`. Nothing is loaded automatically.

## Evidence and Scope

- Sources must contain `decision-landscape-2.0` decisions with explicit
  `frontier_items`, and share the same stripped seed. Sources are compared in
  command-line order, not sorted by timestamps.
- Each source is read once. SHA-256 identifies those exact bytes; source receipts
  store basenames and saved run IDs without embedding local absolute paths.
- Trends use the last two runs; a single source produces snapshot reminders.
  Earlier runs remain in the replay report and source receipts.
- Comparison groups concerns by stage index, name, operator, and conflict type.
  Multiple concerns of the same type retain all evidence references. Severity
  trends are emitted only for one concern per group on each side.
- A stage added or renamed between sources is not treated as a new observation
  of an equivalent stage. An open concern there is `observed_open`; concerns
  from a removed stage become `stage_not_comparable` review items.
- Final `rpm_trace.conflicts[].resolved` flags override historical snapshots.
  Matrix conflict links recover open concerns outside the last-five frontier
  snapshot window. Conflicts without a mapped stage remain review items.
- No disappearance proves resolution. An earlier open concern absent from the
  latest observations produces `not_observed`. Explicit current resolution
  flags are retained as review evidence, not a cross-run identity assertion.

The legacy `frontier-replay-1.0` report and story reader are unchanged. Their
`resolved` and candidate revival labels retain their previous meanings. The
control adapter does not turn those labels into automatic closure or revival.

## Prompt Boundary

Only code-defined templates enter prompts. Saved reasons, repair instructions,
candidate prose, ontology terms, source IDs, and review items are not copied into
the control context. Unknown conflict types receive a generic continuity check.
The loader validates the contract, guidance templates, reference shapes and indices, and
note limits before any provider call. The normalized seed hash must match.
It does not reread source files; the profile stays portable with its receipts.

Runtime matching requires the same stage index, name, and operator. Unmatched
notes are skipped and recorded as unused. Stage instructions, roles, constraints,
model versions, and temperatures are not an equivalence proof under this first
contract; keep configurations fixed for meaningful comparisons.

Notes appear in ordinary generation, beam candidates, repairs, aggregation, and
recursive closure when their stage matches. They never enter the LLM judge
prompt or the heuristic scoring formula. A model may respond differently to
the reminders, so resulting text, metrics, repairs, and rankings can still change.

## Budgets and Receipts

Export selects at most three notes per stage and 24 total, ordered by stage and
then concern state (`worsened`, `new`, `still_open`, `improved_but_open`,
`observed_open`, `not_observed`). Ties use conflict type. Evidence omitted by
these limits remains in `review_items` with state `note_budget`.

`ChainRun.frontier_control` stores the input profile, its file SHA-256, and
`applied_note_ids` / `unused_note_ids`. Each saved candidate carries
`frontier_note_ids`, including repairs. These receipts record prompt application,
not whether the model followed the advice. Use `--include-prompts` to inspect
the exact generation inputs. Export and generation reject output paths that
would overwrite the control inputs.

## Verification Limit

The repository fixtures are authored examples, not live measurements. The
offline tests verify export/load/generation/re-export, provenance, uncertainty,
stage matching, budgets, prompt separation, and unchanged scoring for identical
dry-run outputs. They do not demonstrate better prose or fewer real conflicts.

Automatic influence tuning requires controlled comparisons and an independent
quality criterion. Candidate revival requires an explicit cross-run identity
contract. Both remain in `notes/open-questions/`.
