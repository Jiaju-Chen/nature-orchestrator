# NatureOrchestrator Project Record

This document records the current method design behind the public
`nature_writing` skill and the NatureBench evaluation adapter.

## One-Sentence Goal

NatureOrchestrator coordinates agents that plan evidence, draft manuscript
sections, review them against allowed context, refine targeted failures, polish
the assembled paper, and evaluate final writing quality with an independent
supervisor.

## Current Method

The project treats scientific writing as evidence orchestration rather than
plain text completion. Figures, captions, methods, result notes, controls,
claim boundaries, citations and reviewer feedback are routed to different
roles at different stages.

The current full-paper order is:

```text
paper story contract
-> Results write/review/refine
-> Discussion write/review/refine
-> Abstract+Introduction write/review/refine
-> cross-section evidence ledger
-> cross-section review/repair
-> final polish
-> supervisor evaluation
```

Results come first because they define what the later sections may safely
promise, interpret and compress.

## Agent Roles

- Planner: converts allowed evidence into a story/evidence contract.
- Writer: drafts a section from the contract and allowed context.
- Reviewer: checks evidence fidelity, story quality, section function, anchor
  recall, claim boundary and writing quality.
- Refiner: addresses concrete reviewer or gate failures without rewriting
  stable claims.
- Cross-section reviewer: checks whether Abstract/Intro promises and
  Discussion claims are supported by Results.
- Supervisor: independently scores final writing quality and diagnoses whether
  reviewers missed important issues.

## Backend Strategy

The runners support the same orchestration with different executors:

- Codex executor: better workspace-level behavior and file operations.
- API executor: faster controlled agent calls with allowed-file and output-file
  tools.
- Hybrid mode: Codex can write/repair while API agents review or supervise.
- Mock/prompt-pack modes: deterministic local smoke tests without model calls.

## Core Boundary

Generation context must never include hidden oracle or target manuscript text.
Benchmark oracle material is opened only after generation, and only for
evaluation. Normal writing uses the user-provided workspace or the generated
NatureBench evidence pack as its evidence source.

## Public Artifacts

Safe public artifacts include:

- skill prompts, methods and rubrics
- runner and evaluator code
- tests
- synthetic example workspaces
- curated holdout reviewer/supervisor summaries

Do not publish real generated manuscripts, converted ground-truth manuscripts,
publisher PDFs/HTML, raw NatureBench data, model logs, API keys or local path
configuration.

## Human Review Artifacts

Generated PDFs and converted ground-truth PDFs are useful for private human
review. They should live in a local case artifact folder or presentation bundle,
with a public markdown summary that explains what was compared and what the
reviewers/supervisor concluded.
