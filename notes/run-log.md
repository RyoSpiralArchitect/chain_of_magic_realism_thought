# Run Log

## 2026-10-20 Run 1 (Started)
- Initial reservoir: 5 tasks, 0 active questions, 0 synchronization gaps.
- Scope: Ryō approved feeding replay observations into the next run as soft
  control notes. Explicit opt-in, visible provenance, and unchanged scoring are
  the implementation boundary.
- Baseline: origin/main ac60958; 25 local tests passed.
- In progress: R001.
- Prior frontier: replay labels missing deferred items `resolved`, and candidate
  IDs are local to a run. Neither establishes a verified cross-run resolution
  or candidate identity. The control adapter must preserve that uncertainty.

## 2026-10-20 Run 1 (Implementation Checkpoint)
- Completed: R001, R002, R003, R004. R005 documentation is complete; PR publication
  remains in progress.
- Opened: R006 -> OQ001 (influence tuning), R007 -> OQ002 (candidate identity).
- Local verification: 39 unit/contract tests, reward-audit fixtures, compilation,
  and whitespace checks passed. The tests include beam/repair, aggregation and
  closure, judge isolation, source preservation, malformed inputs, budgets, and
  a subprocess CLI entrypoint with warnings treated as errors.
- Installed verification: built and installed the package into a temporary venv;
  invoked console scripts outside the checkout with PYTHONPATH unset. Export,
  dry-run generation, Markdown/JSON output, and re-export succeeded.
- Observed installed receipt: fc001/fc002/fc003 applied to stages 1/2/3; no unused
  notes. Re-export contained zero prompt notes and one explicitly_resolved review
  item, honoring the final conflict flag over the historical open snapshot.
- Temporary evidence: `/tmp/frontier-control-check.onTjD5/` (not durable storage).
  Source profile SHA-256:
  `6f787231a3be44c05f79ca4600322588acb3925c93710bab9706c3bfaf284d57`;
  run JSON SHA-256:
  `667a1015588ea6b704f8394e32dc31f872efffff1d0dfc4cd7f95e63e51094ed`.
- No live-provider generation, quality improvement claim, merge, or release.
- Frontier refresh: inspected README/docs, examples, tests, source references,
  and the current diff. No additional independent implementation task found in
  this scope. Remaining frontier is the two active design questions.
