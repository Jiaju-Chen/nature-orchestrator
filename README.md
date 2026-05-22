# NatureOrchestrator

NatureOrchestrator is an agentic system for evidence-grounded scientific
manuscript writing. It turns structured research materials into manuscript
sections through story planning, writing, specialist review, targeted
refinement, polish, and audit.

The project is not affiliated with Nature Portfolio or Springer Nature.
"Nature-level" refers to the target quality bar: clear scientific narrative,
strong figure-driven results, careful methods, calibrated claims, and rigorous
review-driven revision.

## What This Repository Provides

NatureOrchestrator now has two layers:

- Generic writing skill: a portable `skills/nature_writing/SKILL.md` and
  `manuscript_workspace.v1` contract for users who want to organize their own
  research materials.
- NatureBench adapter: benchmark-facing runners for controlled evaluation on
  NatureBench artifacts when those artifacts are available locally.

Normal users do not need NatureBench data. NatureBench is an evaluation adapter,
not the core input format.

## Quickstart A: Generic Manuscript Workspace

The generic workspace is the recommended entry point for new users. It uses only
synthetic example materials and does not require API keys or downloaded papers.

```bash
python scripts/run_manuscript_workspace.py \
  --workspace examples/minimal_manuscript_workspace/workspace.yaml \
  --out outputs/examples/minimal_workspace \
  --backend prompt-pack
```

This writes:

- `prompt_pack/task_contract.yaml`
- `prompt_pack/allowed_files.yaml`
- `prompt_pack/forbidden_files.yaml`
- `prompt_pack/*_prompt.md`
- `context_pack/context.md`
- `provenance.yaml`
- `run_manifest.yaml`

The `prompt-pack` backend prepares all artifacts without calling a model. Use it
to inspect the contract, prompts, allowed context, and provenance before running
a model-backed backend.

## Generic Workspace Contract

A minimal workspace looks like this:

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

## Quickstart B: NatureBench Adapter

Researchers with local NatureBench artifacts can use the benchmark adapter to
prepare prompt packs from benchmark tasks:

```bash
python scripts/run_full_paper_batch.py \
  --prepare-only \
  --tasks-root <path-to-nature-bench-data-downloads> \
  --out outputs/naturebench_prepare \
  --run-id public_release_prepare_smoke \
  --only-slug <naturebench-slug> \
  --generators nature-orchestrator \
  --image-mode benchmark_vlm \
  --quiet-progress
```

For lower-level section experiments, the original module entry point remains:

```bash
PYTHONPATH=src python -m nature_orchestrator.run_task \
  --task <path-to-naturebench-taskfile> \
  --out outputs/runs/<slug>/results/prompt-pack \
  --adapter prompt-pack \
  --network-mode safe_web
```

Oracle audit is for benchmark evaluation only and should be opened after
generation, never during writing.

## Public Release Boundary

Safe to publish:

- skill docs and prompts
- generic workspace contract
- synthetic examples
- prompt-pack runner
- tests and adapter docs

Do not commit:

- `outputs/`
- `vendor_baselines/`
- downloaded publisher PDFs or HTML
- downloaded NatureBench benchmark artifacts
- generated manuscripts from real papers
- run logs containing model output from real papers
- `.env`, API keys, provider tokens, or local machine paths

## Components

- `section-writer`: draft abstract, introduction, results, discussion, methods,
  captions, and rebuttal text.
- `figure-narrator`: turn figures and source data into results narratives.
- `literature-scout`: retrieve and organize relevant prior work when policy
  permits.
- `methods-auditor`: find missing experimental and computational details.
- `scientific-reviewer`: review drafts and select sections for rewrite.
- `oracle-auditor`: compare drafts with trusted references only when a benchmark
  task explicitly allows post-generation oracle evaluation.
