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

## 2026-10-20 Run 1 (Final Checkpoint)
- Completed: R001 (inspection), R002 (export), R003 (prompt integration), R004
  (verification), R005 (documentation and PR publication).
- PR: https://github.com/RyoSpiralArchitect/chain_of_magic_realism_thought/pull/5
  against main; implementation commit 348cd3b. This final notes-only checkpoint
  is included on the same branch.
- Reservoir: 0 unstarted, 0 in progress, 2 active questions, 0 synchronization gaps.
- Stop reason: authorized implementation and offline validation complete;
  frontier refresh found no independent remaining task within scope.
- Next frontier: R006/OQ001 asks how to evaluate and tune influence; R007/OQ002
  asks how to establish cross-run candidate identity before automatic revival.
- Publication is a review checkpoint, not a merge, release, or empirical quality
  result. Live-provider effects remain unmeasured.

## 2026-10-20 Run 2 (Started)
- Authorization: Ryō requested larger models and sample counts on Furnace, and
  exploration of the remaining questions using the observations.
- Started: R008-R012. Existing R006/OQ001 and R007/OQ002 remain open.
- Local base: PR #5 head e3ea93f. New branch SpiralReality/furnace-frontier-study.
- Remote checkout: /home/ryospiralarchitect/scratch/cmrt-frontier-study-20261020,
  cloned in isolation at the same base, never modifying another research checkout.
- Initial resources: RTX 5090 32 GB, no compute owner; about 119 GiB available RAM,
  86 GB free disk. Existing cached weights only; no model downloads planned.
- Runtime: managed TensorRT-LLM doctor passed, freeze SHA-256
  691228a4ad195457253d2ab913b08a79332ad97f7365f0523e8ea22df8517ca8.
  No managed environment changes. vLLM fallback requires an unsupported-model
  result or a preserved failed canary.
- Frozen design target: 8 Japanese prompt clusters x 4 independent sampling
  replicates, paired notes off/on per model, with independent calibration runs.
  Explore 4B/12B/20B cached models, then use a separate blind judge in both orders.

## 2026-10-20 Run 2 (Runtime Preflight)
- Remote CPU tests passed (42 at first transfer). TensorRT Gemma 3 4B and 12B
  canaries failed with FlashInfer/TrtllmAttentionMetadata `kv_layout` mismatch.
  Both failures and logs remain in the evidence directory.
- Frozen vLLM 4B canary 1 reached kernel warmup but failed because `ninja` was
  absent from the process PATH. The existing binary is in the frozen venv;
  the retry uses that bin directory and /usr/local/cuda-13.1/bin in PATH, with
  CUDA_HOME set per process. No package or system configuration changes.
- Fallback keeps the stop/final-only completion gates and requires the hash of
  the failed TRT status receipt. vLLM is restricted to text-only requests here.
