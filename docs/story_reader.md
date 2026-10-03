# Offline story reader

This is a read-only presentation layer over saved run JSON. It does not generate
stories, rescore candidates, update memory, or revive a candidate in the runner.
It does not expose provider prompts or hidden reasoning. No external assets or
network requests are used; a restrictive content-security policy disables them.

## Data contract

- Text is copied from `steps[].accepted`, `steps[].rejected`, or `steps[].repaired`
  by **stage index and candidate ID**. Direct `output` fields in decision
  candidates are also supported. Missing text is never borrowed from another
  stage, another run, the final output, or an archive preview.
- Selection uses `accepted_candidate_id`; it is distinct from a PRM reward's
  `accept` threshold. Rejected repairs retain their original status and source.
- A `usage.dry_run: true` flag marks mock output even if the provider/model fields
  name a real service. `dry-run` provider / `fixture` model marks fixed fixtures.
  Other saved provenance is displayed as unverified, without new live checks.
- Revival comes only from the existing `frontier-replay-1.0` event
  `contradicted_prior_abandonment`. The reader does not implement a second replay
  algorithm. ID/stage equality is not proof of textual identity or better writing.
- Deferred judgments and ontology growth use the existing replay result. A
  `resolved` label means absent from the next saved frontier under that harness's
  criteria, not a guarantee that a real-world or literary problem is solved.
- SHA-256 identifies each input file. Embedded source references use basenames
  and field names, not absolute local paths. Run IDs must be distinct.
- Legacy traces without a decision landscape use their stored step statuses.
  Empty traces show an empty state. Different or missing seeds are rejected.

## Run and verify

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m magic_realism_thought.evals
python -m py_compile src/magic_realism_thought/story_reader.py
```

The Python tests cover saved prose identity, mock provenance, replay parity,
missing prose, repair states, stage/ID joins, legacy and empty traces, seed and
ID validation, script escaping, input preservation and CLI error handling.

Browser smoke checklist for both README examples:

1. Open the generated HTML, including directly from disk while offline.
2. Read selected and discarded passages; expand provenance and final output.
3. Change stages, use Previous/Next, and repeat filter clicks.
4. Filter for a nonexistent revival; return to All from the empty state.
5. In the two-run export, choose record B and filter for the revived `s01-c02`.
6. Expand replay: confirm symbol loss is resolved, operator mismatch is still
   open with an improved value, and new ontology terms need rationale.
7. Use browser Back/Forward and reload; confirm record/stage/filter restore.
8. Check narrow layouts and keyboard focus. No page errors or network fetches
   should occur. Candidate text containing HTML must display as inert text.

The HTML template is package data, so installed and wheel-based usage work.
Export two distinct readers for the full-prose dry-run and the metadata-only
replay family rather than implying that these independent runs form one lineage.
