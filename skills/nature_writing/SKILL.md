---
name: nature-writing
description: Use when drafting, reviewing, refining, or evaluating scientific manuscript sections or full papers from figures, methods, result notes, references, claim maps, or structured manuscript workspaces.
---

# Nature Writing

## Purpose

Nature Writing is an evidence-grounded scientific writing skill. Use it to turn
allowed research materials into manuscript sections or a full paper without
inventing findings, citations, mechanisms, numbers, or unsupported novelty.

The default style is a Nature research article, but the method is broader than
Nature: plan the evidence, write the section, review it against evidence and
section purpose, refine targeted failures, then evaluate with an independent
supervisor.

## When To Use

Use this skill when the user provides any of:

- figures, captions, result notes, source-data summaries, tables, or claim maps
- methods, protocols, model assumptions, datasets, controls, or limitations
- research question, target venue, references, coauthor constraints, or review
  comments
- a manuscript workspace declaring allowed input files and output paths

Do not use this skill to fill missing experiments, infer hidden results, create
fake citations, or compare against an oracle/reference manuscript during normal
writing.

## Primary Tasks

For a single section, read `tasks/section_writing.md`.

For a full paper, read `tasks/full_paper_writing.md`.

For a generic manuscript workspace, prepare or run the prompt-pack workflow with:

```bash
python scripts/run_manuscript_workspace.py \
  --workspace skills/nature_writing/contracts/manuscript_workspace.yaml \
  --out outputs/manuscript_workspace_demo \
  --backend prompt-pack \
  --mode auto \
  --max-reviewer-workers 3
```

For any writing task, use these shared methods as needed:

- `methods/evidence_to_story.md`
- `methods/write_review_and_refine.md`
- `methods/supervisor_evaluation.md`

The runner-facing prompts live in `prompts/`. The reviewer and supervisor
rubrics live in `rubrics/`.

## Operating Contract

Only use files explicitly provided by the user, the workspace contract, or the
runner's allowed-file list. Treat generated plans and reviews as coordination
artifacts, not as new evidence.

Every important claim must be recoverable from allowed context:

- exact values, directions and comparators must match the evidence
- figure-specific mechanisms must be tied to the corresponding figure or method
- weak, null, proxy, subgroup or model-dependent evidence must bound the claim
- broader implications must be downstream of Results support
- citation or context support is required for field-positioning claims

## Full-Paper Order

The default full-paper order is:

1. Evidence-claim ledger: separate observations, confidence, comparators,
   directions and claim boundaries.
2. Paper-level story contract: choose the route without upgrading evidence.
3. Results plan, draft, review and targeted refinement.
4. Discussion plan, draft, review and targeted refinement.
5. Abstract and Introduction plan, draft, review and targeted refinement.
6. Cross-section evidence ledger.
7. Cross-section review and targeted polish.
8. Independent supervisor evaluation.

Results come before Discussion and Abstract/Introduction because they define
the evidence that later sections may safely promise, interpret and compress.
The evidence-claim ledger comes before the paper story because story is allowed
to organize evidence, not replace the evidence-confidence boundary.

## Section Reviewer Policy

Use a shared reviewer framework, but not a single generic reviewer. Results,
Discussion, and Abstract/Introduction each have separate reviewer prompts. They
share the base scoring logic in `rubrics/section_reviewer_rubric.yaml`.

Reviewer decisions:

- `pass`: section is evidence-grounded, section-appropriate and publishable
  enough for downstream assembly.
- `revise`: targeted failures are fixable from allowed evidence.
- `fail`: output is malformed, unsafe, oracle-dependent, or too far from the
  evidence to repair locally.

Supervisor evaluation is separate from reviewer evaluation. Reviewers guide
revision; the supervisor scores final writing quality and diagnoses false
passes.

When reviewers cite a concrete manuscript problem, use `final_text_quote` with
an exact substring from the current draft. Do not invent quotes or use ellipses
inside quote fields.

## Benchmark Mode

Use oracle or benchmark reference material only after generation, and only when
the task explicitly requests evaluation. Never read oracle text while planning,
writing, reviewing or refining a normal manuscript draft.
