---
name: verify
description: Verify KBQA retrieval, refusals and source traceability using the project tests and labelled evaluation set.
---

# Verify KBQA behavior

Use for regression checks, retrieval experiments, or validating a reported answer.

- Run `py -3 tests/test_app.py` and `.claude/hooks/preflight.ps1` after relevant edits.
- For comparative quality, run `py -3 scripts/evaluate.py --check`; it uses a temporary database and preserves per-question evidence in `eval/results.json`.
- Inspect source, chunk ID, original page and snippet for every citation. A well-formed citation marker is not proof that a claim is supported.
- Separate retrieval recall from answer correctness. When a real local model is configured, run `py -3 scripts/evaluate.py --llm` and report its mode, warning, and failures as observed. Never infer a successful model call from configuration alone.
- State that `eval/` is a small project-written development set, not an independent or production benchmark.
