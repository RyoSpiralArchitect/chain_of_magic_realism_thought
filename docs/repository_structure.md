# Repository Structure

The repo keeps runnable code, reusable inputs, and generated examples separate.

```text
.
├── chain_of_magic_realism.py          # compatibility wrapper
├── src/magic_realism_thought/         # package code and CLI implementation
├── examples/
│   ├── stages/                        # reusable stage presets
│   ├── memory/                        # sample run-memory profiles
│   ├── runs/                          # generated JSON/Markdown traces
│   └── evals/                         # small reward-audit eval fixtures
├── docs/                              # design notes and operating guidance
└── tests/                             # contract tests for trace shape
```

`chain_of_magic_realism.py` remains at the repo root so old commands keep working.
For installed usage, `pyproject.toml` exposes `chain-of-magic-realism`.

`examples/runs/dry_run.*` is the current no-API schema example. Provider-named
examples preserve historical live-provider runs and may not contain every newer
trace field.

The implementation is split by responsibility:

- `types.py`: dataclasses, constants, built-in stage presets
- `providers.py`: provider adapters and dry-run provider
- `metrics.py`: local transition and magic-realism metrics
- `rpm.py`: RPM trace, decision landscape, ontology ledger
- `prm.py`: heuristic, LLM, and hybrid PRM scoring
- `prompts.py`: CLI parsing helpers, anchor profile, prompt builders
- `runner.py`: orchestration, beam search, memory updates
- `render.py`: Markdown/JSON output writing
- `reward_audit.py` and `evals.py`: reward-surface audit logic and fixtures
