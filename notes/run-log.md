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

## 2026-10-20 Run 2 (Pilot and Wider Output Budget)
- vLLM warmup passed after the per-process PATH correction. A tokenizer return
  shape mismatch in the experiment adapter was repaired and regression-tested;
  failed canaries remain separate. All owned failed workers were shut down.
- The 512-token 4B pilot completed its launch, but all eight calibration runs
  failed on truncated completions. Its paired matrix is not evidence of a note
  effect. The full pilot, requests, and negative results are retained.
- The next frozen configuration uses 2048 output tokens. This change addresses
  completion budget before comparing off/on outcomes; it does not tune quality
  scores. The calibration gate now blocks evaluation if any source is missing.
- Added successful per-call visible artifacts so later run failures do not erase
  earlier visible outputs. Incomplete text is never admitted to the state path.
- Current local tests: 46 passed. R008-R009 complete; R010 in progress.

## 2026-10-20 Run 2 (Live Checkpoint, Not Final)
- Draft stacked PR #6:
  https://github.com/RyoSpiralArchitect/chain_of_magic_realism_thought/pull/6
- Generation source is frozen on Furnace at 9e77ff6. Do not update that checkout
  until the three generator studies finish. Local uncommitted changes harden
  resume fingerprints/writes, add manifest-verified analysis, and correct the
  known Mistral tokenizer regex flag for the later independent judge. They do
  not change production generation or scoring.
- Active launch: gemma3-4b-study2 (2048 tokens, vLLM), unified-exec session 64179;
  output root /home/ryospiralarchitect/scratch/cmrt-frontier-evidence-20261020/.
  At this checkpoint: 40/64 evaluation runs finished, without a reported run
  failure. Re-read status.json for current counts.
- Calibration: all 8 complete. Only p01 (2 notes) and p08 (1 note) are dosed;
  all concern types are repetition. Thus at most 8/32 paired units, from 2/8
  prompt clusters, receive an intervention. R013/OQ003 records the coverage issue.
- The 512-token pilot is retained at gemma3-4b-study1: calibration 0/8 complete;
  off 1/32 complete; on 0/32 complete; 0/32 complete pairs. Request receipts:
  239 requests, 200 stop-complete, 39 length-truncated, 84,369 completion tokens,
  297.8466 summed engine batch seconds. Local copy is ignored under
  artifacts/furnace/20261020/gemma3-4b-study1; manifest audit passed.
- R014/OQ004 records the soft-length-target/scorer mismatch. Do not alter weights
  or select outcomes based on these observations.
- Remaining generators, same source and 2048-token recipe: Gemma 3 12B snapshot
  96b6f1eccf38110c56df3a15bffe176da04bfd80 via frozen vLLM with its own failed
  gemma3-12b-canary1/status.json; then GPT-OSS 20B native MXFP4 through the managed
  launcher, model directory aether-nextnext-tooling/models/openai_gpt-oss-20b_
  6cee5e81ee83917806bbde320786a8fb61efebee, pinned Harmony final-only adapter.
- Later judge: Mistral-Nemo-Instruct-2407 snapshot
  04d8a90549d23fc6bd7f642064003592df51e9b3. Both frozen tokenizer stacks encode a
  CPU canary; the older TRT tokenizer requires fix_mistral_regex=True. Compare
  final passages in both orders; judge results are not human gold.
- Current local tests: 49 pass. No runtime package changes, model downloads,
  other workload termination, or merge.

## 2026-10-20 Run 2 (4B Complete, 12B Active)
- gemma3-4b-study2 completed 8 calibration runs and 64/64 evaluation runs, no
  failures: 32/32 complete pairs, 8 dosed pairs from 2 prompt clusters.
- Pulled the full directory to artifacts/furnace/20261020/gemma3-4b-study2 and
  verified its manifest before analysis. Local primary/audit JSON files are in
  that same ignored parent directory.
- 4B mean on-minus-off path score: +0.0025559375; exploratory prompt-cluster
  bootstrap 95% interval [-0.00541, +0.009989375]. No improvement established.
- No-dose controls: 0/24 identical finals; first-stage root candidates had
  matching request text and seed in 48/48 comparisons, but identical output in
  only 19/48. This does not diagnose a seed-handling bug. OQ005 retains the
  statistical-pairing versus execution-invariant replay question.
- 4B accepted-step soft-length adherence: 2/96 in each arm met 140-240 characters.
  Final median characters: off 954.5, on 992.0. OQ004 retains the objective issue.
- 4B candidate IDs: 126 shared stage-local IDs, 25 equal visible texts and 101
  different texts. ID reuse alone is not passage identity (OQ002).
- 4B inference receipt: 722 stop-complete requests including 2 canaries,
  331,718 completion tokens, 999.2263 engine batch seconds (~331.97 tokens/sec).
- Active: gemma3-12b-study2 at the same remote source 9e77ff6, session 92889,
  2048-token budget and frozen vLLM fallback. Canary passed; calibration is
  running. GPU observed about 30 GB; KV cache budget 4.28 GiB.
- Mistral-Nemo CPU tokenizer smoke: corrected older HF tokenizer and current
  MistralCommon backend agreed on two public English/Japanese inputs (14 and 37
  tokens), encoded-sequence SHA-256
  bcaf031b141d198512765ab96796e739b5120d258925acae581437ee6b84d58c.
  This is a smoke result, not full tokenizer equivalence or literary quality.

## 2026-10-20 Run 2 (12B Complete, 20B Active)
- gemma3-12b-study2 completed 8 calibration runs and 64/64 evaluation runs,
  zero failures: 32 pairs, 4 dosed pairs in 1 prompt cluster (p08 weak_impossibility).
- Raw directory pulled locally and manifest audit passed. Public interim
  primary/audit JSON and REPORT.md are under experiments/results/furnace-20261020/.
- 12B mean path-score delta: -0.0011146875; exploratory prompt-cluster interval
  [-0.0129825, +0.011893125]. No improvement established.
- No-dose control identity: 1/28 finals equal; 25/56 first-stage outputs equal
  despite matching input text and seed in 56/56. Shared candidate IDs: 103/134
  different text, 31/134 equal text.
- Accepted-step soft-length adherence: off 28/96, on 29/96; final medians 385/396.
- 12B receipt: 722 stop-complete requests, 145351 completion tokens,
  980.5492 summed batch seconds (~148.23 tokens/sec).
- Active GPT-OSS 20B launch: gptoss20b-study2, session 18202, managed TensorRT
  launcher, max_tokens=2048, concurrency=8, pinned final-only Harmony adapter.
  Remote generation source remains 9e77ff6. Wait for this before updating the
  remote checkout for the judge and final CPU tests.

## 2026-10-20 Run 2 (GPT-OSS Render Qualification)
- GPT-OSS study2 passed its small canary but only 1/8 calibration runs passed.
  All 44 requests stopped; 37 were admitted final artifacts and seven failed
  the pinned Harmony gate with unexpected_channel. This is not truncation.
- The calibration gate admitted zero paired evaluations. Preserved full raw
  directory locally and remotely: 9791 completion tokens, 20.8328 batch seconds.
- The generic v1 transport merged system instructions into a user message.
  Added opt-in native system-role rendering with an explicit final-channel
  instruction; the pinned output adapter and rejection rules are unchanged.
  Channel names (not text) are added as diagnostics. Rerun goes to a new frozen
  directory, never replacing study2 samples. Managed environment stays immutable.
- Local tests now 50 pass, including native role boundaries. Gemma generator
  observations remain at source 9e77ff6; the GPT rerun source will be recorded
  by its own frozen.json. Production scoring and prompt builders are unchanged.
