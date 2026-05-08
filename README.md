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

## Benchmark-Driven Smoke Test

Run a NatureBench section task with the deterministic adapter and post-generation
oracle audit:

```bash
PYTHONPATH=src python -m nature_orchestrator.run_task \
  --task ../nature-bench/data/downloads/<nature-group>/<slug>/benchmark/tasks/results.yaml \
  --out outputs/runs/<slug>/results/fake \
  --adapter fake \
  --oracle-audit
```

The oracle audit is opened only after `final/target_section.tex` exists. Its V1
metrics report token recall, generated-token precision, missing keywords,
unsupported generated keywords, and heading-count gaps.

For controlled-network experiments, use the safe-web task surface and keep the
agent behind the retrieval guard:

```bash
PYTHONPATH=src python -m nature_orchestrator.run_task \
  --task ../nature-bench/data/downloads/<nature-group>/<slug>/benchmark/tasks_safe_web/results.yaml \
  --out outputs/runs/<slug>/results/safe-web-prompt \
  --adapter prompt-pack \
  --network-mode safe_web
```

This writes `retrieval/literature_pack.yaml`, `retrieval/retrieval_log.yaml`,
and `retrieval/network_leakage_report.md`. The prompt pack tells model-backed
agents to request literature through the orchestrator instead of using direct
web access.

For the primary Results-writing setting, use the figure-grounded variant:

```bash
PYTHONPATH=src python -m nature_orchestrator.run_task \
  --task ../nature-bench/data/downloads/<nature-group>/<slug>/benchmark/tasks_safe_web/results_figure_grounded.yaml \
  --out outputs/runs/<slug>/results-figure-grounded/prompt-pack \
  --adapter prompt-pack \
  --network-mode safe_web
```

This copies safe figure assets into `evidence/figures/`, expands captions in
`context_pack/context.md`, and adds Results-specific prompt requirements around
experiment purpose, key observations, controls/boundaries, claim roles, and
Nature-style narrative progression. Patch-like snippets are deferred in V1.
