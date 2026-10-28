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

## 2026-10-20 Run 2 (Evidence Integrity Checkpoint)
- Native-system GPT-OSS study3 passed all eight calibration runs and is in
  paired evaluation at source 47e7dcd. At least one evaluated on-arm run was
  blocked by a length-truncated candidate. It remains a failed run, not a
  replacement/resampling opportunity. Re-read terminal status for final counts.
- Local analysis now rejects unlisted JSON evidence and verifies judge-to-source
  manifests plus per-order passage hashes. Added regressions for extra files,
  mismatched source manifests, and substituted passage inputs. Local tests: 52
  pass; reward-audit fixtures: 3/3 pass. Remote current-head CPU tests remain to
  be verified after generation finishes and the isolated checkout is updated.
- R015 is complete. R010-R012 remain active. Draft stacked PR #6 is open; PR #5
  remains open. No merge, automatic tuning, or candidate revival is authorized.

## 2026-10-20 Run 2 (Resume Rejection Protection)
- A CLI resume rejected before frozen-configuration admission now leaves the
  previous status and manifest unchanged and never loads a model. Regression
  compares every saved JSON byte before and after rejection. Local tests: 53 pass;
  compilation and diff whitespace checks pass.
- Negative pilot summaries now include terminal status, model/runtime identity,
  manifest hashes, zero complete-pair denominators, and request completion counts.
  They are checked in separately from the final effect measurements.
- GPT-OSS generation remains at source 47e7dcd, unaffected by these local fixes.
  At this checkpoint it is still evaluating; retain all candidate truncations.

## 2026-10-20 Run 2 (Final Checkpoint)
- Completed: R008, R009, R010, R011, R012, R015. Frontier refresh found one
  bounded documentation task, R018: add experiments and ignored evidence to the
  README/file map. R018 is complete. Production `src/` is unchanged by PR #6.
- Final generator attempts: 24/24 calibration runs; 192/192 evaluation attempts
  finished, 187 complete and five failed. Complete pairs: Gemma 4B 32/32,
  Gemma 12B 32/32, GPT-OSS 27/32. Actual dosed complete pairs: 8, 4, and 15.
  All five missing GPT pairs were calibration-eligible; they are not resampled.
- Gemma sources: 9e77ff6, frozen vLLM after preserved failed TRT canaries.
  GPT native-system source: 47e7dcd, managed TRT. The GPT complete-case path
  delta is +0.012658, exploratory prompt interval [+0.003033, +0.021565], but
  no-dose mean variation is +0.012738 and missingness is selective. No causal
  reminder or literary-quality effect follows.
- Independent judge source 3d36150: Mistral-Nemo 12B / managed TRT returned
  182/182 stop-complete valid JSON judgments, with A chosen 181 times. All 182
  presented-prompt hashes were verified; 90/91 pairs disagree under order
  reversal. All 27 dosed complete pairs have unknown preference. The other
  pair preferred off, but does not qualify this judge. R017 -> OQ006 records
  automated qualification versus human anchors; no follow-up is authorized.
- Validation code checkpoint a997c830b03387ffa568955c9c04940bcce2060b: 53 tests
  pass on both Mac Python 3.13 and Furnace system Python 3.14; reward-audit
  fixtures pass 3/3 on both. Local compilation and diff checks pass. CI is not
  asserted. The static measurement figure was visually inspected.
- Full raw archive is on both machines, SHA-256
  c64f92f49e62fe4d521b68a5aa5d068217ad64bfd55707a1be9ebb764caf0225;
  all 2751 archived files match their Mac copies. Source root on Furnace:
  /home/ryospiralarchitect/scratch/cmrt-frontier-evidence-20261020/; Mac:
  artifacts/furnace/20261020/. Four early failed canaries lack execution
  manifests; retrospective file indices do not replace that missing proof.
- Managed runtime doctor still passes with unchanged freeze SHA. No packages
  or weights were modified/downloaded. All owned compute processes are closed;
  final GPU observation: 10 MiB, 0% utilization, zero compute owners.
- PR checkpoint: #6 stacked on open #5, neither merged. Results, method,
  negative pilots, request/model/source hashes, and claim ceilings are committed.
- Stop reason: authorized scope complete after one frontier refresh. Reservoir:
  unstarted 0 / in progress 0 / questions 6 / synchronization gaps 0.
- Unreached frontier: decisions OQ001-OQ006, especially judge qualification,
  generative replay, and independently calibrated prompt diversity. Do not
  launch a new experiment, tune weights, or revive candidates from a lean.

## 2026-10-27 Run 3 (API Judge Start)
- Starting reservoir: unstarted 0 / questions 6 / synchronization gaps 0.
  User explicitly requested a large API judge and then authorized reusing the
  existing key. Added R019 implementation, R020 fixed-passage review, R021
  comparison/publication. OQ006's full qualification decision remains open.
- Verified checkout and raw sources. PR #6 merged into frontier-soft-control
  (690a3df); main currently includes #5 but not #6. New branch:
  SpiralReality/api-frontier-judge, based on the integrated frontier branch.
- Official docs and live model listing confirm gpt-6-astra is available. Use
  Responses instructions/user input, low reasoning, no temperature/seed/tools,
  2048 output tokens, default tier, store=false, 30m caching. Semantic rubric
  and presented passages are unchanged, but model/runtime/rendering/sampling
  differences mean this is not a causal model-size-only comparison.
- Plan: 182 calls on the same 91 complete pairs. Conservative byte-token plus
  framing bound and output allowance: $27.7359, below the fixed $30 budget.
  No automatic retries; pre-call issued markers prohibit ambiguous resends.
  Existing source manifests are verified before calls; final-only API outputs
  and safe request/usage metadata are retained, never hidden reasoning text.

## 2026-10-27 Run 3 (Measurements Complete)
- R019 and R020 complete. R021 is final publication/PR checkpoint work.
  Execution source dc003792616706979c2b1ba9be8313b5608cd6c4; analysis code
  checkpoint fb586264adc46b86c16468115446fcbb4c3e0223.
- All 182/182 API requests completed with valid final JSON. The first two calls
  remain in the denominator; no retries or resampling. All input/payload hashes
  checked; 182 unique provider response IDs and client request IDs. No key or
  hidden reasoning text was persisted. API alias returned: gpt-6-astra.
- Order consistency: 75/91 versus Nemo 1/91. Per generator: 27/32, 25/32, 23/27.
  Labels A/B/tie: 82/98/2. Sixteen order-disagreement unknowns remain. Freshness
  category agreement is 57/91, so overall stability is not blanket qualification.
- Dosed complete pairs: on 7 / off 15 / unknown 5. No-dose comparisons also vary;
  eight shared prompts and selective generator completion preclude a causal
  intervention or size-only claim. Among 22 directional dosed preferences,
  15 oppose heuristic score direction, including 10/13 for GPT-OSS.
- Usage: 192808 input, 23586 output including 8392 reasoning tokens. The latter
  are counted, never saved as text. Estimated published-rate cost $3.402755,
  not an invoice. No additional key/env file, GPU run, or weight change.
- Portable API-only archive on Mac:
  artifacts/furnace/20261027/api-judge-evidence-portable.tar.gz, SHA-256
  aa94773ed9638b58c038e743ca6b7359db8a0488da6afca713a53c5d78adc218.
  All 369 archived files match local copies. Initial macOS-metadata pack is
  retained separately; portable packaging did not change evidence files.
- Validation: 59 tests pass locally; reward-audit fixtures 3/3; compilation,
  diff, source hashes, archive, and presented-input checks pass. Figure visually
  inspected. No CI claim. Results: experiments/results/api-judge-20261027/.
- One bounded frontier refresh found no new independent task: current README,
  experiment protocol, tests, original result immutability, and active-question
  links are aligned. Remaining six questions are decision-bound. Publication
  and final PR confirmation remain before stopping.

## 2026-10-27 Run 3 (Final PR Checkpoint)
- Completed R019, R020, R021 in PR #7:
  https://github.com/RyoSpiralArchitect/chain_of_magic_realism_thought/pull/7.
  Base is the integrated frontier-soft-control branch containing merged #6;
  main integration is a distinct operation. PR #7 is open, not merged.
- All owned API execution/test sessions closed. Raw evidence is Mac-only under
  artifacts/furnace/20261027/; no extra Furnace workload or credential write.
- Final claim ceiling: a new API configuration substantially improved order
  stability but did not establish human correctness or reminder benefit.
  Retained unknowns and the five original generator missing pairs remain visible.
- Reservoir transferred/cleared completed entries: unstarted 0 / in progress 0 /
  active questions 6 / synchronization gaps 0. Stop: authorized scope complete
  after one bounded frontier refresh, not merely because a PR exists.
- Unreached frontier: OQ006 sentinel qualification versus human anchors;
  OQ001 criterion disagreement before automatic influence tuning. No additional
  study, judge selection, training, or automatic revival is authorized.

## 2026-10-27 Run 4 (Offline Log Scrutiny)
- User requested closer log inspection. Started with unstarted 0 / questions 6 /
  synchronization gaps 0. R022: read/verify saved logs; R023: preserve findings;
  R024 -> OQ007: seed-derived anchors versus an explicit authored motif bank.
- Read all 182 visible API reasons. Verified manifests, all 182 input/payload
  hashes, parsed response JSON, condition/config mapping, and unique request IDs.
  Recomputed transition/magic metrics and final candidate rewards for all 182
  paired final passages with exact agreement. No wiring/calculation mismatch
  found in this scope; no hidden reasoning was accessed or requested.
- Repeated motifs originate in fixed impossible_fact_slots, already present
  before reminders; scoring checks the same slots. Future-errand phrase occurs
  in 36/54 GPT-OSS finals and 20/54 selected stage-1 passages. Only 4/54 finals
  fully match a slot; literal motif reuse is not the same as the exact-match
  bonus and does not prove learned reward hacking.
- Semantic coverage: all 54 GPT-OSS final passages have restraint=1 and
  non_explanation=1 despite observed chronology breaks, crowd reactions, and
  unrelated anomalies. API reasons point to those concrete text features. This
  diagnoses a metric-coverage limitation, not a human-gold error annotation.
- Pre-dose root calls in dosed pairs: input/seed match 16/16, 8/8, 30/30;
  output matches 5/16, 1/8, 0/30 for 4B/12B/GPT-OSS. Selected stage-1 text
  matches 2/8, 0/4, 0/15 pairs before any frontier note. Individual differences
  cannot be attributed directly to reminders; average effects remain unproven,
  not logically excluded.
- Winner stability is 75/91; all three categories stable 39/91; winner and all
  categories jointly stable only 38/91. GPT-OSS p08 r00 flips winner despite
  stable category preferences. The prompt leaves category aggregation unspecified;
  no deterministic vote or tie-break rule was retrofitted.
- Selected steps with reward.accept=false: 8/192, 23/192, 39/162. Beam selection
  with zero repairs is not a hard reward-threshold admission gate. Original
  transport completion and quality claims remain distinct.
- Findings and exact counts: experiments/results/api-judge-20261027/LOG_REVIEW.md
  and log_review.json. R022 complete; R023 is documentation checkpoint work.
  No source code, metrics, weights, original summaries, or raw artifacts changed.
  No API/GPU/provider call, regeneration, or new experiment. Existing PR #7 is open.

## 2026-10-27 Run 4 (Documentation Checkpoint)
- R022-R023 complete. Added LOG_REVIEW.md, exact descriptive log_review.json,
  OQ007, and evidence updates to OQ005/OQ006. PR #7 remains the checkpoint;
  no production or experiment-runner source changes, weight changes, or reruns.
- All original manifests reverified after inspection; original reports and
  comparison/audit/primary artifacts are unchanged. Only new derived review
  artifacts and active documentation are added. Validation used offline
  integrity/recalculation/assertion checks, not new provider or GPU calls.
- One bounded frontier refresh checked current docs, code pointers, protocol,
  preserved evidence, and active-question synchronization. No independent
  remaining task found. Stop: authorized log inspection and documentation done.
- Reservoir: unstarted 0 / in progress 0 / active questions 7 / sync gaps 0.
  Next decision-bound frontier: OQ007 anchor provenance, OQ005 repeatable
  pre-intervention state, and OQ006 category aggregation/qualification. No lean
  authorizes implementing a policy or launching an experiment.
