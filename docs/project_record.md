# NatureOrchestrator Project Record

This document records the method-side design that pairs with NatureBench. It is
intended to feed a future manuscript-style project report and public README.

## One-Sentence Goal

NatureOrchestrator coordinates specialized agents to draft, review, revise, and
audit scientific manuscript sections from structured evidence packs.

## Motivation

Most writing tools treat manuscripts as text-completion problems. The intended
system treats writing as evidence orchestration: figures, source data, tables,
methods, code, citations, limitations, and reviewer feedback must be routed to
the right specialized agent at the right stage.

NatureBench is the first controlled test bed. Real usage should later support
unpublished experiments, notebooks, draft figures, lab notes, and coauthor
feedback.

## Method Sketch

The V1 pipeline is benchmark-driven and consumes NatureBench task files through
a file contract:

1. `load_task`: parse a section-masking task.
2. `build_context`: assemble allowed context and enforce leakage policy.
3. `plan_section`: decompose the task into evidence, writing, review, and
   rewrite stages.
4. `draft_section`: generate a section using an adapter.
5. `review_rewrite`: critique and revise the draft.
6. `oracle_audit`: after generation, compare against hidden ground truth.

## Adapter Strategy

The first adapters are deliberately minimal:

- `fake`: deterministic adapter for tests and pipeline debugging.
- `prompt-pack`: writes a prompt package for Codex, Claude Code, or another
  model-backed agent.

Future adapters can call specific model APIs, Claude Code skills, Codex
subagents, or local toolchains. They should not change the NatureBench file
contract.

## Core Boundary

Generation context must never include `benchmark/oracle/` files or the target
section source path. Oracle files are opened only after a draft exists.

Safe-web runs add another boundary: the agent does not receive raw web tools.
It receives a blind task id, sanitized evidence, and a network policy. If it
needs literature, it writes query requests; NatureOrchestrator filters the
queries, search results, and fetched page text against NatureBench's hidden
target fingerprint before writing `retrieval/literature_pack.yaml`.

Network modes are:

- `official_offline`: no live network; use curated cutoff-safe literature only.
- `safe_web`: controlled search/fetch with guard logs.
- `open_web`: unrestricted demo mode, not part of official scoring.

## Relationship To AutoResearchClaw

AutoResearchClaw motivates stage-based execution, gates, run artifacts,
human-in-the-loop checkpoints, and multi-agent verification. NatureOrchestrator
borrows those architectural ideas but does not copy the full 23-stage
research-automation pipeline. The V1 scope is narrower: controlled manuscript
section writing from NatureBench evidence packs.

## Public Run Artifacts

Each run should write:

```text
outputs/runs/<slug>/<task>/<run_id>/
  run_manifest.yaml
  context_pack/
  retrieval/
  prompt_pack/
  drafts/
  reviews/
  final/
  oracle_audit.yaml
```

The `context_pack` and `prompt_pack` are generation-stage artifacts. The
`oracle_audit.yaml` is post-generation only.

## Current Oracle Audit Metrics

The V1 oracle audit is intentionally lightweight and deterministic. After a
draft exists, it reads NatureBench oracle text and reports token recall,
generated-token precision, missing ground-truth keywords, unsupported generated
keywords, and LaTeX heading counts. These metrics are not a final semantic
judge; they are a leakage-safe first pass for omissions, unsupported claims,
and structure gaps.

For Results tasks, the audit also writes `results_quality` metrics:

- `structure_score`: coarse coverage of the ground-truth Results heading
  structure.
- `figure_grounding_score`: how many main figures in the evidence pack are
  explicitly discussed.
- `claim_role_score`: whether the draft includes empirical, design,
  interpretive, and narrative claim roles.
- `nature_narrative_score`: a heuristic combination of structure, evidence
  grounding, and claim-role progression.
- `leakage_score`: whether hidden target identifiers appear after generation.
- `oracle_similarity`: token recall and precision kept as auxiliary signals,
  not as the primary reward.

The first Results-specific prompt surface is `results.figure_grounded`. It
materializes figure PNGs and caption files into the run workspace under
`evidence/figures/`, expands captions into `context_pack/context.md`, and
instructs the agent to build a Nature-style chain of findings rather than a
flat summary. Patch-like method snippets, role hints, and claim-level evidence
patches are deferred to a later benchmark variant; V1 does not expose them as
generation context.

When a Results oracle audit runs, NatureOrchestrator also writes
`reports/results_quality_report.md`. This is a human-readable layer over the
machine-readable `oracle_audit.yaml`: expected and mentioned figures, missing
figures, panel mention coverage, claim-role coverage, narrative heuristic,
leakage hits, and oracle similarity. It is designed for quick inspection after
a Codex/Claude run and should not be fed back into generation context.

The golden smoke comparison for `s41586-026-10319-8` writes
`outputs/smoke/s41586-026-10319-8/results_variant_comparison.md`. Current
prompt-pack runs are marked `prompt_pack_only` because the adapter prepares the
workspace and prompt but does not itself produce a substantive model-generated
Results section.

## README Draft Hooks

The public README should answer:

- What is NatureOrchestrator?
- How does it consume a NatureBench task?
- What are the `fake` and `prompt-pack` adapters?
- How does it prevent oracle leakage?
- How do I run one task?
- How do I inspect the output directory?

## Manuscript Draft Hooks

A future method paper can describe NatureOrchestrator as the agentic method and
NatureBench as the controlled evaluation substrate. The key methodological
claim is not that the system writes perfect papers, but that it makes
evidence-grounded writing, review, revision, and oracle audit explicit and
measurable.
