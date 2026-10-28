# Saved-Log Scrutiny

Date: 2026-10-27. Offline inspection only: no API call, regeneration, repair,
rescoring policy change, or human-gold annotation. The original reports and raw
evidence are unchanged. Exact descriptive counts are in [log_review.json](log_review.json).

## Scope and Integrity

Read all 182 visible API judgment reasons, including both orders of every
dosed pair and every order-disagreement case. Matched the corresponding source
passages, stage histories, profiles, and saved requests for the cases below.

- All five source/judge manifests verified, including the earlier Nemo receipts.
- All 182 API request hashes, issued-payload hashes, source passage hashes,
  parsed JSON, condition mapping, config hashes, and unique request IDs checked.
- All 182 paired final passages' transition/magic metrics recomputed from saved
  stage-2 text and stage-3 output/symbols; all matched. Recomputing their final
  candidate reward also gave 182/182 exact matches. This is not a recomputation
  of every candidate or a semantic validation of the formulas.

No label-swap, serialization, or metric-calculation mismatch was found in this
scope. Saved request hashes are local integrity receipts, not server-side
attestation of model computation.

## 1. The Prompt Supplies the Repeated Imagery

`prompts.py::extract_prompt_anchor_profile` inserts the same six impossible-fact
templates into every seed. Four are fixed commute/clock motifs; two substitute
an ordinary object. Examples include the rain/stamping clock and the trace of
an errand that has not happened. These appear in the system instructions and
again in the stage prompt, including stage 1 before frontier reminders.

For the rice-washing seed p06, the fallback ordinary objects are shoes, bag,
clock, documents, wallet, and umbrella; fallback actions are leaving home,
doing errands, and waiting at a counter. The original seed's kitchen/rice/mother
still occur in outputs, but the supplied examples also steer the continuation
toward stations, offices, and paperwork. This is observed conditioning, not
evidence of a model-intrinsic style or a frontier-note effect.

| Generator | Paired Finals | Literal Future-Errand Phrase | Literal Stamping Term | Ticket-Gate Term |
|---|---:|---:|---:|---:|
| Gemma 4B | 64 | 26 | 27 | 42 |
| Gemma 12B | 64 | 5 | 9 | 42 |
| GPT-OSS 20B | 54 | 36 | 16 | 13 |

Counts are exact substring hits, not semantic originality scores. The future-
errand phrase already occurs in 20/54 GPT-OSS selected first-stage passages.
The same supplied `impossible_fact_slots` are also checked by
`metrics.py::profile_hit_score`, with a positive contribution to the impossibility
metric. Generation examples and the scoring surface therefore share content.
Do not confuse a shared phrase with a complete slot match: at least one full
slot matches in only 9/64 4B, 0/64 12B, and 4/54 GPT-OSS finals. The lexical
bonus therefore cannot explain all motif reuse. The observed reuse does not
prove learned reward hacking or quantify causation.
OQ007 separates seed-derived evidence from an optional authored motif bank.

## 2. A Score Named Restraint Is Not a Semantic Restraint Test

`restraint_score` is one minus the maximum of lexical fantasy, dream, cosmic,
purple-prose, and explanation penalties. It does not count unrelated impossible
events or check action chronology. The ordinary-continuity metric also uses
term/profile hits rather than an event-order model.

| Generator | Restraint = 1 | Non-Explanation = 1 |
|---|---:|---:|
| Gemma 4B | 59/64 | 64/64 |
| Gemma 12B | 63/64 | 63/64 |
| GPT-OSS 20B | 54/54 | 54/54 |

Concrete case: GPT-OSS p02 r02, final path score off 0.68239 / on 0.76836.
The on text adds a luminous nonexistent floor, a crowd's surprise, and an
explicit warm emotional ending. Its restraint and non-explanation metrics are
still both 1.0. Both API orders prefer off, explicitly citing these additions.

Another logged on passage, p02 r01, says:
"私はいつものようにタイムカードを押し、会社へと歩き出す。"
Both API orders criticize the clock-in-before-arrival sequence. p04 r01 on
has "靴を脱ぎ" before going outside. These are concrete reasons for a semantic
judge to diverge from keyword metrics, not independently adjudicated literary
errors. A human could interpret unusual actions intentionally.

The previous 10/13 GPT-OSS disagreement count used path score, which includes
mean stage rewards, last reward, recurrence, entropy, collapse and conflicts.
It is not the same target as judging final prose. As a sensitivity check, using
only the final candidate's reward still gives 10/13 opposing directional
preferences among dosed, order-consistent GPT-OSS pairs. The mismatch here is
not solely an artifact of comparing a path metric to a final-text judgment.

## 3. Individual Pairs Diverge Before the Reminder

All dose-eligible profiles begin at stage 2 or later; stage-1 selected candidates
carry no frontier-note IDs. Nevertheless:

| Generator | Dosed Complete Pairs | Equal Stage-1 Selected Text | Root Calls With Same Input + Seed | Equal Root Output |
|---|---:|---:|---:|---:|
| Gemma 4B | 8 | 2/8 | 16/16 | 5/16 |
| Gemma 12B | 4 | 0/4 | 8/8 | 1/8 |
| GPT-OSS 20B | 15 | 0/15 | 30/30 | 0/30 |

This is stronger than a no-dose final-output check: the narratives can already
differ before the tested reminder is presented. For p03 r01, the on branch's
rain/stamping clock is present in its selected stage-1 text, while its first
frontier note is attached at stage 2. That image cannot be attributed to that
note in this pair.

This does not prove there is no average intervention effect. It does prevent
treating each visible difference as a controlled edit caused by the reminder.
Shared intended seeds are not execution-invariant replay; the underlying
runtime cause was not diagnosed. OQ005 retains the protocol choice.

## 4. Winner Stability Overstates Full Judgment Stability

The 75/91 headline is correct for the overall winner. It is not a count of fully
stable judgments. After normalizing A/B to passage identity:

- Overall winner stable: 75/91.
- All three category labels stable: 39/91.
- Winner and all three categories stable together: **38/91**.
- Winner flips despite all three categories being stable: one pair.

That last case is GPT-OSS p08 r00. In both orders, continuity and freshness
prefer off, while restraint prefers on. The first overall winner is on; the
second is off. The reasons consistently describe the trade-off. The prompt
does not prescribe a deterministic weighting/tie-break rule for the categories,
so aggregate judgment can change without a category-label change. This is an
observed instability, not a diagnosed causal mechanism or a license to replace
the model's winner with a posthoc vote.

Other disagreements also involve changing attention or category judgments.
Thus order effects and subjective trade-offs should be retained separately;
the records do not expose private reasoning, and no hidden cause is inferred.
The one identical-text no-dose pair (Gemma 12B p03 r02) is correctly tied in
both orders. It is a useful natural sanity check, not a new qualification bank.

## 5. Selected Does Not Mean Above the Reward Threshold

Of the 546 selected steps in complete pairs, 70 have `reward.accept=false`:
4B 8/192, 12B 23/192, GPT-OSS 39/162. The beam runner selects available
candidates even below threshold when repair attempts are zero. This follows
the current implementation and is not evidence of a failed transport gate.

Keep provider completion, selected-path membership, reward-threshold status,
and literary preference distinct. No threshold or selection behavior was changed.

## Evidence Pointers

Source code: `prompts.py` lines 140-210 (anchors/slots), `metrics.py` lines
151-190 (profile/lexical scoring), `prm.py` grounding and weighted axes,
`runner.py` lines 324-345 (path score) and 452-497 (beam selection).

Raw case files, relative to the repo root:

- `artifacts/furnace/20261020/gptoss20b-study3/runs/p02-on-r02.json` and off.
- `artifacts/furnace/20261020/gptoss20b-study3/runs/p03-on-r01.json` and off.
- `artifacts/furnace/20261020/gptoss20b-study3/runs/p06-off-r00.json`.
- `artifacts/furnace/20261027/astra-judge1/judgments/gptoss20b-study3-p02-r02-o0.json`
  and o1; `gptoss20b-study3-p08-r00-o0.json` and o1.

## Next Decision

Prioritize the distinction between seed-derived anchors and authored examples,
semantic metric coverage, and repeatable pre-intervention generation before
optimizing weights against the API judge. These are proposed diagnostic targets,
not authorized changes or established causal explanations. All prior failures,
missing pairs, and order-disagreement unknowns remain in their denominators.
