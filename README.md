# NatureOrchestrator

NatureOrchestrator is a research-writing toolkit for evidence-grounded
scientific manuscripts. It organizes research materials into controlled writing
workspaces, then runs manuscript planning, drafting, review, targeted
refinement, polish, and evaluation stages.

The project is not affiliated with Nature Portfolio or Springer Nature.
"Nature-level" refers to the target quality bar: clear scientific narrative,
figure-driven results, calibrated claims, careful methods, and rigorous review.

## Use Cases

- Draft manuscript sections from figures, methods notes, result summaries,
  constraints, and references.
- Run section or full-paper writing pipelines with planner, writer, reviewer,
  refiner, cross-section reviewer, polisher, and supervisor roles.
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

## Current Nature Writing Skill

The agent-readable skill entry point is:

```text
skills/nature_writing/SKILL.md
```

The current skill is self-contained in `skills/nature_writing/`. It does not
require archived `versions/` packages.

The release-facing skill layout is:

- `tasks/`: section-writing and full-paper-writing entry points
- `methods/`: evidence-to-story, review/refine and supervisor guidance
- `prompts/`: runner-facing planner, writer, reviewer, refiner and polisher
  prompts
- `rubrics/`: reviewer, cross-section and supervisor scoring criteria
- `contracts/`: generic manuscript workspace contract
- `field_profiles/`: optional claim-calibration profiles, not domain fact
  sources

## Current Full-Paper Pipeline

The current NatureBench full-paper runner performs:

```text
paper-level evidence/story contract
-> Results plan, draft, review and targeted refinement
-> Discussion plan, draft, review and targeted refinement
-> Abstract+Introduction plan, draft, review and targeted refinement
-> cross-section evidence ledger
-> cross-section review and targeted repair
-> final polish
-> independent supervisor evaluation
```

Results are drafted before Discussion and Abstract/Introduction because Results
define the recoverable evidence that later sections may safely interpret,
promise and compress.

The generic manuscript-workspace runner remains a clone-and-run smoke path for
users who want to inspect prompt-pack behavior without NatureBench data.

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

For private human review, place generated PDFs, converted ground-truth PDFs and
raw manuscript artifacts in a local case artifact folder or presentation
package. Keep the public repository focused on the skill, runner, tests and
curated review summaries.

## Holdout Review Report

The current release includes a curated five-paper holdout report:

```text
docs/holdout_review_report_nature_writing_current.md
```

It summarizes section reviewer, cross-section reviewer and independent
Supervisor V2.1 opinions. It is not a copy of the original manuscripts or
generated drafts.

## Current Limitations

- The generic manuscript-workspace runner does not yet expose the full
  NatureBench section/full-paper API backend; the NatureBench section and
  full-paper runners do.
- The generic runner expects structured research materials; it does not yet
  parse arbitrary paper folders automatically.
- The quality of `--backend codex --mode auto` depends on the local Codex CLI
  environment and model access.

## Verification

```bash
python -m py_compile \
  scripts/run_manuscript_workspace.py \
  scripts/run_full_paper_batch.py \
  scripts/run_results_batch.py \
  scripts/run_discussion_batch.py \
  scripts/run_abstract_intro_batch.py \
  scripts/run_full_paper_generation.py \
  scripts/evaluate_full_paper_generation.py \
  src/nature_orchestrator/agents.py

python -m unittest tests/test_pipeline.py tests/test_nature_writing_current_release.py -v
```
