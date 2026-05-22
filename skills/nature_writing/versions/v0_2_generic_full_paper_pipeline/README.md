# v0.2 Generic Full-Paper Auto Pipeline

This version is a release-facing NatureOrchestrator skill snapshot for generic
scientific manuscript writing with an automatic full-paper pipeline. It is
derived from benchmark development, but it does not require NatureBench data and
does not assume an oracle manuscript.

Use it with a `nature_orchestrator.manuscript_workspace.v1` workspace:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace \
  --backend prompt-pack
```

The `prompt-pack` backend prepares model instructions, allowed files, forbidden
files, context, and provenance. It is intended as the clone-and-run smoke test
for users without a model API key.

To run the auto pipeline with Codex:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace_auto \
  --backend codex \
  --mode auto \
  --max-refiner-rounds 2 \
  --max-reviewer-workers 3
```

Use `--backend mock --mode auto` to verify the full artifact structure without
calling a model.

## Design Rules

- Evidence from the workspace is the only source of manuscript claims.
- Distilled writing patterns guide structure, not facts.
- Oracle/reference manuscripts are not available in normal use.
- Benchmark adapters may enable oracle scoring after generation only.
- Reviewers must reject fluent drafts that invent evidence, numbers, figures,
  citations, mechanisms, or unsupported novelty claims.
