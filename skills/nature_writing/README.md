# Nature Writing Skill

This directory is the current public entry point for the NatureOrchestrator
writing skill. It describes the recommended manuscript-writing workflow and
contains the prompts and rubrics used by the current runners.

The skill has two user-facing tasks:

- section writing
- full-paper writing

Both tasks use the same core method: convert allowed evidence into a story plan,
draft from that plan, review the draft, refine targeted failures, and evaluate
the final output with an independent supervisor.

The current skill is self-contained in this directory and does not require a
user or agent to read archived experiment packages.

## Directory Map

- `SKILL.md`: agent entry point
- `tasks/`: what users can ask the agent to do
- `methods/`: reusable writing, review and evaluation methods
- `prompts/`: runner-facing role prompts
- `rubrics/`: reviewer and supervisor scoring criteria
- `contracts/`: generic manuscript workspace contract
- `tools/`: notes for invoking the repository runner
- `field_profiles/`: optional claim-calibration profiles; these are not domain
  knowledge packs and must not introduce facts absent from allowed evidence

## Current Full-Paper Flow

```text
paper-level story contract
-> Results write/review/refine
-> Discussion write/review/refine
-> Abstract+Introduction write/review/refine
-> cross-section evidence ledger
-> cross-section review
-> final polish
-> supervisor evaluation
```

## Evidence Policy

The skill writes only from allowed context. It may reorganize, compress,
emphasize and polish evidence-backed claims, but it must not invent new
findings, hidden citations, unsupported mechanisms, or benchmark oracle content.

## Field Profiles

Field profiles are optional guardrails for claim calibration. They do not tell
the agent what a biological, health, physical or social-science paper should
claim. They only remind the reviewer/writer to preserve recoverable details
when compression would change the claim, such as comparator structure, proxy
measurement limits, model boundaries, perturbation logic or unit of analysis.
