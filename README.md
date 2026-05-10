# Chain of Magic Realism Thought

`chain_of_magic_realism.py` packages the V5 RPM-PRM harness as a small repo for magical-realist visible-thought generation. It extends the V4 harness with two major mechanisms:

1. **Beam search over visible process paths**
   - Each stage can generate multiple candidates.
   - PRM scores each candidate.
   - The runner keeps the top `beam_width` state paths after each stage.
   - The final aggregation/recursive closure is run on the highest-scoring path.

2. **Run-to-run memory profile**
   - A JSON memory profile records provider-role reward, stage reward, operator reward, and symbol reward.
   - Future runs can load that profile as a soft prior.
   - Memory can gently reorder provider candidates and add profile hints to stage prompts.

The script still avoids private chain-of-thought exposure. It treats only **visible stage outputs** as process steps.

---

## Repository layout

```text
chain_of_magic_realism.py          # compatibility wrapper
src/magic_realism_thought/         # package code and CLI implementation
examples/stages/                   # reusable stage presets
examples/memory/                   # sample run-memory profiles
examples/runs/                     # generated trace examples
examples/evals/                    # small reward-audit eval fixtures
docs/                              # design notes
tests/                             # trace contract tests
```

See [`docs/repository_structure.md`](docs/repository_structure.md) for the current file map.
`examples/runs/dry_run.*` is the current no-API schema example; provider-named examples preserve historical live-provider runs.

---

## Install

```bash
pip install -r requirements.txt
```

API keys, depending on which providers you use:

```bash
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export MISTRAL_API_KEY="..."
```

---

## Dry run

```bash
python chain_of_magic_realism.py \
  --dry-run \
  --providers openai,google,anthropic,mistral \
  --prompt "雨が祖母の筆跡を覚えていた。" \
  --seed-symbol 雨 \
  --seed-symbol 祖母 \
  --beam-width 2 \
  --beam-branching 2 \
  --candidates 3 \
  --memory-profile examples/memory/chain_of_magic_realism_memory.json \
  --output-md examples/runs/chain_of_magic_realism.md \
  --output-json examples/runs/chain_of_magic_realism.json \
  --show-stages \
  --show-candidates \
  --show-rpm
```

---

## Seed-Independent Magic Realism

Use this when the input is ordinary but the output should enter a magic-realism field.
The harness injects a `MagicRealismPrior`, extracts a mundane anchor profile from the prompt, and scores candidates against magic-realism reward axes such as quiet impossibility, non-explanation, social normalization, anti-fantasy drift, and ordinary continuity.

```bash
python chain_of_magic_realism.py \
  --provider openai \
  --no-temperature \
  --magic-realism-prior \
  --anchor-profile auto \
  --stage-preset seed-independent-magic \
  --no-recursive-closure \
  --prompt "朝、会社に行く。" \
  --beam-width 2 \
  --beam-branching 2 \
  --candidates 3 \
  --memory-profile examples/memory/openai_seed_independent_memory.json \
  --output-md examples/runs/openai_seed_independent_run.md \
  --output-json examples/runs/openai_seed_independent_run.json \
  --show-stages \
  --show-candidates \
  --show-rpm
```

The prior treats magic realism as ontology rather than style: one small impossible fact is materially real inside ordinary social life, while fantasy lore, dream reveal, cosmic explanation, and over-explained supernatural logic are penalized.

---

## Beam search

The important controls are:

```bash
--candidates 3       # candidates generated per path/stage
--beam-width 3       # paths kept after each stage
--beam-branching 2   # candidates kept from each path before global pruning
--beam-archive 12    # path snapshots retained in the report
```

A useful starting point:

```bash
--candidates 3 --beam-width 2 --beam-branching 2
```

A heavier exploratory run:

```bash
--candidates 4 --beam-width 3 --beam-branching 3
```

Be careful: total provider calls grow with beam width and branching.

---

## Run memory

Load and update a memory profile:

```bash
python chain_of_magic_realism.py \
  --providers openai,google,anthropic,mistral \
  --prompt "駅の時計は3時17分で止まったのに、誰もがまだ秒針の音を聞いていた。" \
  --memory-profile examples/memory/chain_of_magic_realism_memory.json \
  --beam-width 2 \
  --candidates 3
```

Use one profile as input and save to another path:

```bash
--memory-profile examples/memory/old_profile.json --save-memory-profile examples/memory/new_profile.json
```

Load memory but do not update it:

```bash
--memory-profile examples/memory/chain_of_magic_realism_memory.json --no-memory-update
```

Adjust the prompt/provider influence of memory:

```bash
--memory-weight 0.15
--memory-weight 0.40
```

Memory is a soft prior. It does not force a provider, symbol, or operator.

---

## PRM modes

```bash
--prm heuristic
--prm llm
--prm hybrid
```

For hybrid judging:

```bash
python chain_of_magic_realism.py \
  --providers openai,anthropic,mistral \
  --prm hybrid \
  --judge-provider anthropic \
  --hybrid-llm-weight 0.45 \
  --candidates 3 \
  --beam-width 2 \
  --prompt "雨が祖母の筆跡を覚えていた。"
```

---

## Output structure

The JSON trace includes:

- `final`
- `final_state`
- `steps`
- `rpm_trace`
  - `decision_landscape`
  - `ontology_ledger`
- `beam`
- `beam_archive`
- `magic_prior`
- `anchor_profile`
- `memory_profile_before`
- `memory_profile_after`
- `reward_surface_audit`

The Markdown trace includes:

- RPM matrix
- Decision landscape
- Ontology ledger
- Beam archive
- Run memory snapshot
- Reward surface audit
- PRM-scored visible process path
- Final output

---

## Design-risk instrumentation

The harness now reports the three main risks that appear in long-running visible-state systems.

- Ontology inflation: `rpm_trace.ontology_ledger` lists active axes, operators, conflict types, and rule kinds, plus pressure warnings when the local vocabulary gets too large.
- Reward surface overfitting: `reward_surface_audit` flags saturated axes, low selection margins, and near-duplicate candidate sets. Run memory also tells providers not to imitate prior rewarded style.
- Visible-only limits: `rpm_trace.decision_landscape` records accepted, rejected, repaired, abandoned, and deferred candidate decisions without exposing hidden chain-of-thought. Version `decision-landscape-2.0` also emits `frontier_items`, `frontier_reason`, and `architectural_hesitations`.

See [`docs/design_risks.md`](docs/design_risks.md).

---

## Reward-audit evals

Run the small no-provider reward-surface fixtures:

```bash
PYTHONPATH=src python -m magic_realism_thought.evals
```

Installed usage also exposes:

```bash
chain-reward-audit-evals
```

The fixture file is [`examples/evals/reward_audit_cases.json`](examples/evals/reward_audit_cases.json).

---

## Conceptual map

```text
PRM = scores visible state transitions
RPM = records what each transition changed in the state matrix
Beam = keeps multiple possible state paths alive
Memory = learns soft priors across runs
Decision landscape = records accepted/rejected/repaired/abandoned/deferred visible candidates
Ontology ledger = audits the vocabulary used by the trace itself
Reward surface audit = checks whether scoring has become too flat or imitable
Recursive closure = returns the final output to the seed
```

V5 is therefore no longer just a chain. It is a small search-and-memory harness for visible symbolic state transitions.
