---
name: nature-writing
description: Use when drafting, reviewing, revising, or auditing scientific manuscripts from figures, methods, results notes, citations, claim maps, or coauthor constraints.
---

# Nature Writing

## Overview

Nature Writing is an evidence-grounded scientific manuscript skill. It turns a
structured manuscript workspace into manuscript sections through story planning,
section drafting, specialist review, targeted refinement, polish, and audit.

The skill is not a generic copy-editing assistant. It should only make claims
that are supported by the workspace evidence.

## When To Use

Use this skill when the user provides research materials such as:

- research question, intended audience, or target journal style
- methods notes, experiment logs, source data summaries, or analysis outputs
- figure captions, figure manifests, tables, or result notes
- references, citation notes, related-work summaries, or claim maps
- reviewer comments, coauthor constraints, or revision goals

Do not use this skill to infer missing experiments, invent numerical results,
write unsupported novelty claims, or compare against a hidden reference unless
the user explicitly provides an oracle benchmark mode.

## Core Principle

Every scientific claim must trace to evidence in the workspace. Writers may
improve narrative order, emphasis, transitions, and clarity, but they must not
create new findings, unsupported mechanisms, unavailable citations, or hidden
benchmark content.

## Input Contract

The preferred input is a `nature_orchestrator.manuscript_workspace.v1`
workspace. See:

- `contracts/manuscript_workspace.yaml`
- `versions/v0_2_generic_full_paper_pipeline/contracts/manuscript_workspace.yaml`
- `versions/v0_1_generic_full_paper/contracts/manuscript_workspace.yaml`

The workspace declares:

- project metadata and target style
- allowed input files
- output paths for manuscript sections, reviews, decisions, and provenance
- policy flags such as `evidence_only`, `allow_web`, and `oracle_available`

Only files declared by the workspace contract are allowed context. Output
directories, oracle/reference manuscripts, hidden target sections, `.env` files,
and local run logs are forbidden unless explicitly declared for a non-writing
audit.

## Workflow

If the user has already prepared a manuscript workspace and asks to write the
paper, run the auto pipeline instead of only giving advice:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace <path-to-workspace.yaml> \
  --out outputs/manuscript_auto \
  --backend codex \
  --mode auto \
  --max-refiner-rounds 2 \
  --max-reviewer-workers 3
```

For smoke tests without a model backend, use `--backend mock`. For preparation
only, use `--backend prompt-pack` without `--mode auto`.

The auto pipeline runs:

1. Story planning: identify the central question, evidence chain, section roles,
   claim boundaries, and likely reader objections.
2. Results writing: convert figure and result notes into a sequence of supported
   findings. Each subsection should state purpose, observation, boundary or
   control, and contribution to the larger argument.
3. Discussion writing: synthesize what the evidence changes, where it applies,
   limitations, implications, and next questions without overselling.
4. Abstract and introduction writing: state the problem, gap, approach, core
   findings, and contribution with calibrated specificity.
5. Parallel specialist review: separately check evidence grounding, story
   quality, citation safety, methods consistency, and finalization readiness.
6. Blind decision: decide whether to revise, polish, or finalize without using
   an oracle manuscript.
7. Targeted refinement: revise only the issues identified by reviewers or
   deterministic gates.
8. Polish: improve coherence, concision, title-level framing, transitions, and
   Nature-style density without changing the evidence.
9. Final audit: verify allowed-context compliance, unsupported claims, citation
   safety, figure/table references, output paths, and provenance.

## No-Oracle Mode

Use no-oracle mode for normal scientific writing. The model must judge the draft
against the workspace evidence and rubrics only. It must not assume a reference
manuscript exists.

## Benchmark Or Oracle Mode

Use benchmark/oracle mode only for evaluation tasks where a trusted reference is
explicitly available after generation. The oracle can score gaps and guide
future skill development, but it must not be read during drafting or review.

## Output Expectations

Write manuscript sections to the paths declared in `workspace.yaml`. Write
review and decision artifacts as structured files. Record provenance for the
workspace, prompts, allowed context, backend, and generated outputs.

## Common Mistakes

- Treating distilled examples as facts about the current manuscript.
- Writing a broad literature review when the task needs a specific evidence
  chain.
- Passing a draft because it sounds fluent while evidence anchors, figure
  references, or citation support are weak.
- Using oracle or benchmark reference text during normal writing.
- Expanding the pipeline before the workspace contract and audit artifacts are
  stable.
