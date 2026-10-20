# Frontier Reminder Study on Furnace

Status: **IN_PROGRESS**. These are local measurements, not a quality promotion,
merge, release, or public dataset deposit. Read `audit.json` for exact artifact
hashes and `primary.json` for prompt-cluster intervals. Blind review has not yet
run; its missing results are null, not zero preferences.

## Design and Progress

Eight authored Japanese prompt clusters x four sampling replicates per model;
32 planned off/on pairs. Separate calibration runs freeze the reminders before
the paired outputs. Three stages, two candidates, beam width/branching two,
no repair, aggregation, closure, or memory updates. Output budget: 2048 tokens.

| Generator | Planned Pairs | Complete Pairs | Dosed Pairs / Clusters | Backend | State |
|---|---:|---:|---|---|---|
| Gemma 3 4B | 32 | 32 | 8 / 2 | frozen vLLM | complete |
| Gemma 3 12B | 32 | 32 | 4 / 1 | frozen vLLM | complete |
| GPT-OSS 20B MXFP4 | 32 | UNKNOWN | pending | managed TensorRT-LLM | protocol rerun pending |

Runtime: RTX 5090, 32607 MiB, compute capability 12.0, driver 595.84. Generation
Gemma generation source is commit `9e77ff6`. The initial GPT-OSS render contract
was also measured there; its native-system protocol rerun is recorded separately.
Later resume/analysis hardening is distinct from measured generation. Size is confounded with family,
quantization, and backend; no size-only scaling claim is made.

## Verified 4B Observations

- Eight calibration and 64 evaluation runs completed, with zero run failures.
- Only p01 and p08 received reminders, all concerning repetition. Six profiles
  were empty. Nominal n=32 is not n=32 active interventions.
- Mean heuristic path-score difference (on minus off): +0.0025559375. The
  exploratory prompt-cluster bootstrap 95% interval is
  [-0.00541, +0.009989375]. Improvement is not established.
- Empty-profile controls had 0/24 identical final passages. First-stage calls
  matched request text and intended seed in 48/48 comparisons, but only 19/48
  had identical output. This is a reproducibility observation, not a diagnosis
  that seeds were ignored. Individual passage changes are not identified effects.
- Of 126 reused stage-local candidate IDs, 101 referred to different visible
  text across the pair. ID equality does not establish passage identity.
- Only 2/96 accepted steps in each arm met the experiment's soft 140-240
  character target. Median final lengths were 954.5 off and 992 on. The scorer
  rewards grounding length up to 360 characters; causation is not established.
- Receipt: 722 stop-complete requests including two canaries, 331718 completion
  tokens, 999.2263 summed engine batch seconds, about 331.97 tokens/second.

## Verified 12B Observations

- Eight calibration and 64 evaluation runs completed, with zero run failures.
- Only p08 received a reminder, concerning weak impossibility: four dosed pairs
  in one prompt cluster. Seven profiles were empty.
- Mean heuristic path-score difference: -0.0011146875; exploratory 95% prompt
  interval [-0.0129825, +0.011893125]. Improvement is not established.
- Empty-profile controls had 1/28 identical finals. Root request text and seed
  matched in 56/56 comparisons, while 25/56 outputs were identical.
- Of 134 shared candidate IDs, 103 had different text and 31 had equal text.
- Soft-length adherence was 28/96 accepted steps off and 29/96 on. Final median
  lengths were 385 off and 396 on. Character counts use Python code-point length.
- Receipt: 722 stop-complete requests including two canaries, 145351 completion
  tokens, 980.5492 engine batch seconds, about 148.23 tokens/second.

Token throughput measures engine completion tokens, not literary quality or
normalized visible-output speed. GPT-OSS counts may include reasoning-channel
tokens even though their text is not retained.

## Negative Pilot and Runtime Failures

TensorRT Gemma 3 4B/12B canaries failed with an attention metadata `kv_layout`
mismatch. Frozen vLLM was used with failure receipts, without changing managed
packages. An initial vLLM launch needed the existing ninja/CUDA tools in its
process PATH; the adapter's structured-tokenizer handling was also corrected.
All failed canaries and logs are retained.

The initial GPT-OSS render contract completed its small canary, but only 1/8
calibration runs passed the final-only output gate. All 44 requests finished
with `stop`; seven were rejected for an unexpected channel. No paired evaluation
was admitted. Its 9791 completion tokens and 20.8328 batch seconds are retained
as protocol qualification evidence. A native-system final-channel instruction
is being tested in a separate frozen directory; the gate is unchanged.

The 512-token 4B pilot had 0/8 complete calibration runs, 1/32 complete off runs,
0/32 complete on runs, and 0/32 complete pairs. Its 239 requests included 39
truncated completions. It is negative compatibility evidence, not a note-effect
measurement. The wider configuration is a new frozen directory. The subsequent
calibration gate prevents admitting evaluation when any calibration source fails.

## Pending Independent Review

Mistral-Nemo-Instruct-2407 will see only the seed and two final passages in both
A/B orders, without conditions, notes, or PRM scores. Invalid or inconsistent
judgments remain unknown. Model judgments are not human gold.

A two-input English/Japanese tokenizer smoke matched between the corrected
older HF tokenizer and MistralCommon backend: 14 and 37 tokens, encoded-sequence
SHA-256 `bcaf031b141d198512765ab96796e739b5120d258925acae581437ee6b84d58c`.
This does not establish global tokenizer equivalence or literary quality.

## Open Decisions

- [OQ001: influence tuning](../../../notes/open-questions/001-frontier-influence.md).
- [OQ002: candidate identity](../../../notes/open-questions/002-candidate-identity.md).
- [OQ003: coverage and effect](../../../notes/open-questions/003-intervention-coverage.md).
- [OQ004: length objective](../../../notes/open-questions/004-length-objective.md).
- [OQ005: replay granularity](../../../notes/open-questions/005-replay-granularity.md).

Full raw evidence lives on Furnace at
`/home/ryospiralarchitect/scratch/cmrt-frontier-evidence-20261020/` and is pulled
to ignored `artifacts/furnace/20261020/` on the Mac. Summaries verify all listed
manifest hashes before analysis. The raw corpus is not included in Git.
