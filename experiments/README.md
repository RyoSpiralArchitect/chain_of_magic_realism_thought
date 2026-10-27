# Furnace Frontier Study

This exploratory study tests the opt-in frontier reminders on cached local
models. It does not train models, tune reward weights, or automatically promote
a control policy.

## Frozen Plan

- Eight authored Japanese prompt clusters, four sampling replicates per prompt:
  32 paired off/on units per model, not 32 independent prompt domains.
- One separate calibration run per prompt/model creates a fixed control profile
  before any off/on outputs are observed. Empty profiles remain in the denominator.
- Three generation stages, two candidates, beam width/branching two; no repairs,
  aggregation, recursive closure, or run-memory updates. Stage output instructions
  request 140-240 Japanese characters.
- Temperature 0.8, top-p 0.95, top-k 40. Each pair shares its base sampling seed;
  request seeds derive from call ordinal. This does not assert identical random
  token trajectories or determinism across backend schedules.
- Initial targets: Gemma 3 4B, Gemma 3 12B, and native-MXFP4 GPT-OSS 20B. Model
  family, quantization, backend, and size are confounded; this is not a size-only
  scaling experiment. Cached model bytes are hashed before generation.
- Default runtime: managed TensorRT-LLM. A preserved failed canary is required
  before opting into the separately frozen vLLM fallback. No runtime repair or
  package mutation is part of this study.

## Receipts and Missingness

Use `frontier_study.py generate --help` through the selected runtime. Each output
directory freezes source hashes, commit, prompt pack, sampling configuration,
and backend choice. Changing those values requires a new output directory.
Completed trial files are reused only with identical trial metadata. Failure
files remain failures; they are not silently resampled. Session receipts are
separate on resume, so prior requests and canaries are retained.
A rejected frozen-configuration resume leaves the existing status and manifest
unchanged and does not load the model.
If any calibration run fails, the paired evaluation is not admitted. A new
resource configuration requires a new frozen directory, preserving the negative
pilot. Successful visible calls before a later failure remain in `calls/`;
incomplete calls retain request/error receipts without entering the state path.

Only completions with finish reason `stop` and a nonempty final passage enter
the existing harness. A failed candidate blocks that run even if it might have
been rejected later. For GPT-OSS the pinned Harmony adapter admits only its
accepted final channel; analysis stays out of saved passages and prompts.
Content-blind channel counts/hashes can appear in request receipts.
GPT-OSS can opt into `--harmony-final-instruction`, which preserves the native
system role and explicitly requests one final-channel artifact. Its render
contract is frozen separately. This does not relax the pinned output gate;
failed earlier render contracts remain separate negative pilots.

Every profile records the calibration file hash. Every controlled run records
profile and note application receipts. `manifest.json` hashes saved artifacts.
Logs and failure receipts are preserved alongside the successful runs.

## Analysis

`summarize` reports planned/completed/dosed pairs, differences in heuristic
path score, drift, magic reward, final unresolved conflicts, and output length.
Intervals resample prompt means, keeping the four replicates in their prompt
cluster. With eight clusters these are exploratory, not general population
estimates. Heuristic improvement is not independent evidence of better prose.

A separate generator-independent judge sees only the seed and two final
passages, in both A/B orders, without notes, conditions, or PRM scores. Its
categories are continuity, restraint, freshness, and overall preference. Invalid
or order-inconsistent judgments remain unknown. These are model judgments,
not human gold. Exact text identity under reused stage-local candidate IDs is
also counted to inform the cross-run identity question.

Raw evidence is kept outside Git in a task-owned Furnace directory and pulled
to the Mac. Checked-in summaries must include manifests, denominators, runtime
fallbacks, and claim limits. No model download is needed.

`analyze_frontier_study.py` verifies the saved manifests before describing
coverage, soft length adherence, candidate-ID reuse, and no-dose output identity.
It rejects unlisted JSON files, mismatched judge source manifests, and judgments
whose passage hashes or presented-prompt hashes do not match the generated pair
and declared A/B order. Valid JSON does not qualify a judge: aggregate label
counts and order disagreements are retained separately in the audit. See
[the Furnace report](results/furnace-20261020/REPORT.md) for the observed negative
judge-qualification result and incomplete-trial denominators.
`--plot` optionally uses matplotlib for a static figure. Unrun blind judgments
are null; attempted invalid or order-inconsistent judgments are unknown.

## API Judge Follow-Up

`api_frontier_judge.py` reuses the same rubric and fixed source passages through
OpenAI Responses. It verifies source manifests before sending visible passages,
never regenerates trials, and saves its own frozen directory. The first two
calls can be limited with `--limit 2`, then resumed with the same configuration;
they remain part of the 182-call denominator. This is an operational check,
not a separate gold-label qualification set.

Default: `gpt-6-astra`, low reasoning, 2048 output tokens, four concurrent calls,
180-second timeout, default tier, 30m caching, `store=false`, no tools, no SDK
retries. The temperature/seed settings from local inference are unsupported
under this reasoning mode and are omitted, so the backend/model comparison has
explicit rendering and sampling confounds. No hidden reasoning text is saved.

`--plan-only` performs no API call. A $30 modeled budget gates the whole plan
using UTF-8 byte-token bounds plus 256 framing tokens and maximum output tokens,
at conservative short-context cache-write/output rates. Rates are dated in the
frozen config; this is a modeled bound, not an invoice or account spending cap.
Issued receipts are written before each call. An issued request lacking a
terminal receipt blocks resumption; it is never silently sent twice. Failed,
refused, incomplete, and invalid outputs remain unknown without resampling.
Reuse or creation of an API key requires explicit user authorization.

`compare_frontier_judges.py --previous OLD --current NEW --studies ... --output
FILE` audits both judges on the same source manifests. It reports per-model and
per-prompt order consistency, dosed/no-dose preferences, category-level order
agreement, heuristic-sign alignment, and usage-based cost estimates. `--plot`
adds an optional static figure. Rate-based costs are not invoices. Neither order
agreement nor agreement with the heuristic establishes literary correctness.
The [2026-10-27 API report](results/api-judge-20261027/REPORT.md) records all
182 attempts, 75/91 order-consistent comparisons, and the retained unknowns.
The subsequent [offline log scrutiny](results/api-judge-20261027/LOG_REVIEW.md)
checks all visible reasons, metric recomputation, supplied imagery, pre-dose
divergence, and joint category/winner stability without any new provider call.
