# Statistical Pairing or Execution-Invariant Replay

## Context
R016 arose from the no-dose controls in the Furnace study. Completed no-dose
final identity: Gemma 4B 0/24, Gemma 12B 1/28, GPT-OSS 0/12. Their first-stage
requests matched text and intended seed in 48/48, 56/56, and 24/24 comparisons;
identical visible outputs were only 19/48, 25/56, and 0/24. These are observations
under two backends, not a diagnosis of the same underlying runtime cause.

The installed vLLM sampler explicitly routes seeded requests through its Gumbel
path. The observations therefore do not establish that seeds were ignored.
Batch-dependent numerics or other runtime behavior remain hypotheses. The
current protocol promises shared seeds, not bit-identical token trajectories.

## Question
A: retain stochastic paired estimates with a measured no-dose noise baseline,
or B: require a separately validated execution-invariant canary before a new
feedback experiment?

## Options
- A: retain all pairs, counterbalance order, estimate uncertainty by prompt, and
  report the no-dose variation. Cannot attribute a single changed passage to
  reminders or claim exact generative replay.
- B: test supported batch-invariant runtime settings or a single-request
  reference, hash serialized inputs and outputs, then freeze a new study.
  Throughput may fall; a greedy canary alone does not validate sampled replay.

## Assessment
Prefer finishing A under its existing claim limits, then validating B before
automatic influence tuning. Do not silently replace the current measurements
with a deterministic subset or relabel numerical noise as a note effect.

## Dependencies
R016 blocks only a future replay invariant. R010-R012 retain their frozen plan.

## References
- `experiments/frontier_study.py`: seed pairing and counterbalanced task order.
- `experiments/furnace_runtime.py`: per-request seed receipts and batching.
- `experiments/analyze_frontier_study.py`: no-dose root and final identity audit.
- `experiments/results/furnace-20261020/audit.json`: completed denominators.
- Installed vLLM 0.27.1 `v1/worker/gpu/sample/sampler.py`, seeded Gumbel branch.

## Related Questions
OQ001 needs a reliable effect estimate; OQ003 separates dose coverage; OQ002
addresses candidate identity independently of execution determinism.

## Portability
This is an observed reproducibility limit, not a runtime diagnosis or a claim
that the note intervention is ineffective. The existing replay report compares
saved observations; it does not promise to regenerate identical model outputs.
