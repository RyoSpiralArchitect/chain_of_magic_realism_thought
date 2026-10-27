# Qualify an Automated Judge or Establish Human Anchors

## Context
R017 arose from the completed Furnace blind review. The frozen Mistral-Nemo
12B / TensorRT-LLM configuration returned valid stop-complete JSON in 182/182
requests, but selected label A in 181/182. Reversing order changed the normalized
winner in 90/91 paired comparisons; all 27 dosed complete pairs remain unknown.
The other pair preferred off, but one consistent result does not qualify a judge.

All 182 presented prompt hashes match the expected seed and reversed visible
passages. This rules out an unswapped request in the saved receipts, not every
possible runtime, tokenization, prompt-design, or model failure. The observed
position sensitivity belongs to this frozen configuration, not all Nemo use.

## Question
A: qualify automated judges on a separate, fixed sentinel bank before another
quality claim, or B: establish blinded human annotations as the first quality
anchor and evaluate model judges against those labels?

## Options
- A: freeze equal-text, clearly corrupted, and order-reversed public sentinels;
  preregister admission criteria and compare renderer/backend/model choices in
  separate runs. Passing sentinels is not proof of literary taste. No cherry-picked
  prompt or output from the current effect study becomes gold.
- B: collect independent blinded human judgments with explicit disagreement and
  unknown categories. Provides an external anchor but costs annotation time and
  still requires scope-limited agreement analysis.

## Assessment
Prefer A as the next diagnostic before paying for a larger automated effect
study, with B eventually supplying independent literary anchors. This is an
assessment, not authorization to launch another GPU study or collect labels.

## Dependencies
R017 blocks new automated literary-quality claims and automatic tuning (R006).
It does not block publication of this negative qualification result (R012).

## References
- `experiments/results/furnace-20261020/audit.json`: labels, manifests, and orders.
- `experiments/frontier_study.py::run_judge`: frozen comparison prompt.
- `experiments/analyze_frontier_study.py`: presented-prompt hash verification.
- `tests/test_frontier_study.py`: always-A, swapped-input, and hash regressions.

## Related Questions
OQ001 needs an independent outcome criterion; OQ003 addresses coverage and
missingness; OQ005 addresses generator repeatability rather than judge validity.

## Portability
The judge saw only seed and two final passages, not conditions, notes, or scores.
Raw observations remain on the Mac and Furnace; their hashes and denominators
are published in the report. No winner was promoted to human gold, and no judge
or generator was retrained or selected from these outcomes.

## Authorized Diagnostic Follow-Up (2026-10-27)
Ryō asked: "ジャッジをAPIの大モデルに素直に変えてどうなるか見てみよ!"
and approved reusing the existing API key. This authorizes a direct comparison
on the same 91 complete pairs through GPT-6 Astra, preserving reversed orders,
rubric text, source hashes, failures, and the old negative result. It does not
decide the broader A/B question, establish sentinel-bank qualification, or
authorize automatic influence tuning. R019-R021 cover this bounded diagnostic.
