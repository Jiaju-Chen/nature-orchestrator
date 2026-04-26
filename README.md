# NatureOrchestrator

NatureOrchestrator is an agentic system for turning experiments, figures,
results, literature, and reviewer feedback into Nature-level scientific
manuscripts.

The project is not affiliated with Nature Portfolio or Springer Nature.
"Nature-level" refers to the target quality bar: clear scientific narrative,
strong figure-driven results, careful methods, calibrated claims, and rigorous
review-driven revision.

## Motivation

Most AI writing tools start from text. NatureOrchestrator starts from the
research process: ideas, experiments, notebooks, plots, code outputs, evidence
tables, citations, and coauthor comments. The goal is to coordinate specialized
agents that can draft, critique, revise, and audit a manuscript section by
section.

## Initial Components

- `section-writer`: draft abstract, introduction, results, discussion, methods,
  captions, and rebuttal text.
- `figure-narrator`: turn figures and source data into results narratives.
- `literature-scout`: retrieve and organize relevant prior work.
- `methods-auditor`: find missing experimental and computational details.
- `scientific-reviewer`: review drafts and select sections for rewrite.
- `oracle-auditor`: compare drafts with trusted reference manuscripts when a
  benchmark task allows it.

## Companion Benchmark

Use `nature-bench` to evaluate whether manuscript-writing agents can construct
complete high-impact papers from controlled evidence packs derived from Nature
articles.

