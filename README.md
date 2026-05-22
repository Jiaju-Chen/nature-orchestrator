# NatureOrchestrator

NatureOrchestrator is a research-writing toolkit for evidence-grounded
scientific manuscripts. It organizes research materials into a controlled
workspace, prepares model-readable writing tasks, and can run a generic
full-paper drafting pipeline with review, revision, polish, and audit artifacts.

The project is not affiliated with Nature Portfolio or Springer Nature.
"Nature-level" refers to the target quality bar: clear scientific narrative,
figure-driven results, calibrated claims, careful methods, and rigorous review.

## Use Cases

- Draft manuscript sections from figures, methods notes, result summaries,
  constraints, and references.
- Run a generic no-oracle full-paper writing pipeline from a structured
  workspace.
- Prepare reproducible prompt packs with explicit allowed and forbidden context.
- Evaluate benchmark tasks through the NatureBench adapter when local benchmark
  artifacts are available.

## Quickstart

The synthetic example works without API keys, downloaded articles, or
NatureBench data.

Prepare a prompt pack:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace \
  --backend prompt-pack
```

Run the same workspace through the automatic full-paper pipeline with Codex:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace_auto \
  --backend codex \
  --mode auto \
  --max-refiner-rounds 2 \
  --max-reviewer-workers 3
```

For a no-model smoke test of the same artifact structure, use:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace_auto \
  --backend mock \
  --mode auto \
  --max-refiner-rounds 1 \
  --max-reviewer-workers 3
```

## Manuscript Workspace

The generic input format is
`nature_orchestrator.manuscript_workspace.v1`. A workspace declares project
metadata, allowed input files, output paths, and writing policy.

```yaml
schema_version: nature_orchestrator.manuscript_workspace.v1
project:
  title: ""
  target_style: nature_research_article
  field: ""
inputs:
  research_question: inputs/research_question.md
  methods: inputs/methods.md
  results_notes: inputs/results_notes.md
  figures: inputs/figures.yaml
  references: inputs/references.bib
  constraints: inputs/constraints.md
outputs:
  results: manuscript/results.tex
  discussion: manuscript/discussion.tex
  abstract_intro: manuscript/abstract_intro.tex
  reviews: reviews/
  decisions: decisions/
  provenance: provenance.yaml
policy:
  evidence_only: true
  allow_web: false
  oracle_available: false
```

The public contract is stored at
`skills/nature_writing/contracts/manuscript_workspace.yaml`.

## Pipeline

In `--mode auto`, the generic runner performs:

```text
story blueprint
-> writer draft_000
-> parallel reviewers: evidence, story, citation
-> blind decision
-> targeted refiner rounds
-> polisher
-> final audit
```

The run writes structured artifacts under the output directory, including:

- `prompt_pack/`
- `context_pack/context.md`
- `story/story_blueprint.yaml`
- `drafts/`
- `reviews/`
- `decisions/`
- `final/manuscript.tex`
- `audits/final_audit.yaml`
- `provenance.yaml`

The default public pipeline is no-oracle: it must judge drafts against the
workspace evidence and rubrics, not against a hidden reference manuscript.

## Skill Files

The agent-readable skill entry point is:

```text
skills/nature_writing/SKILL.md
```

The current full-paper pipeline version is:

```text
skills/nature_writing/versions/v0_2_generic_full_paper_pipeline/
```

Version `v0_1_generic_full_paper` is retained as the earlier prompt-pack
snapshot.

## NatureBench Adapter

NatureBench is supported as a benchmark adapter, not as the only input format.
Researchers with local NatureBench artifacts can prepare benchmark prompt packs:

```bash
python scripts/run_full_paper_batch.py \
  --prepare-only \
  --tasks-root <path-to-nature-bench-downloads> \
  --out outputs/naturebench_prepare \
  --run-id public_release_prepare_smoke \
  --only-slug <naturebench-slug> \
  --generators nature-orchestrator \
  --image-mode benchmark_vlm \
  --quiet-progress
```

Oracle audit is for benchmark evaluation only and should be opened after
generation, never during normal drafting.

## Public Data Boundary

Safe to publish:

- skill documentation and prompts
- generic workspace contracts
- synthetic examples
- runner scripts
- tests and adapter documentation

Do not commit:

- `outputs/`
- `vendor_baselines/`
- downloaded publisher PDFs or HTML
- downloaded NatureBench benchmark artifacts
- generated manuscripts from real papers
- run logs containing model output from real papers
- `.env`, API keys, provider tokens, or local machine paths

## Current Limitations

- The generic pipeline expects users to provide structured research materials;
  it does not yet parse arbitrary paper folders automatically.
- The public API backend is reserved for a future release.
- Section-specific specialist pipelines are not yet exposed in the generic
  runner.
- The quality of `--backend codex --mode auto` depends on the local Codex CLI
  environment and model access.

## Verification

```bash
python -m py_compile scripts/run_manuscript_workspace.py scripts/run_full_paper_batch.py
python -m unittest tests/test_pipeline.py -v
```
