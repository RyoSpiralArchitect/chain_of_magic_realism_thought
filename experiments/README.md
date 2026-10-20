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

Only completions with finish reason `stop` and a nonempty final passage enter
the existing harness. A failed candidate blocks that run even if it might have
been rejected later. For GPT-OSS the pinned Harmony adapter admits only its
accepted final channel; analysis stays out of saved passages and prompts.
Content-blind channel counts/hashes can appear in request receipts.

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
