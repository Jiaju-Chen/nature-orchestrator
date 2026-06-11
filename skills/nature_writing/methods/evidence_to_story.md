# Evidence To Story Method

Use this method before writing any section.

Start with the evidence-claim ledger when it exists. The ledger answers what
the evidence can safely support; the story plan answers how to order and weight
that support for readers.

## Core Questions

Ask:

- What central claim can the allowed evidence actually support?
- Which figures are primary evidence, support evidence, controls, validation,
  mechanism, boundary or setup?
- Which methods change claim strength, workload, access, validity or boundary?
- Which exact values, comparator directions, controls or limitations are
  must-mention anchors?
- Which exact values are contribution-defining anchors that must survive into
  the final prose rather than being converted into vague comparative language?
- If the work is data-intensive or effect-size driven, what is the smallest
  numeric spine that preserves the paper's identity across measurement,
  primary effect, secondary contrast and downstream/boundary implication?
- Which intervention, rescue, prevention, failure or no-effect directions must
  be preserved exactly?
- Which claims are observed Results evidence, and which are only model,
  Methods, abstract-level or interpretive context that should be deferred,
  bounded or omitted from Results?
- Which evidence is weak, proxy-based, null, subgroup-specific or model-bound?
- Which details should be compressed or omitted because they do not serve the
  section role?
- Which evidence rows are VLM-only or unclear, and therefore cannot carry
  definitive direction, causality, rescue, prevention or no-effect wording?
- Which supporting or validation evidence can be compressed only after its role
  in the proof chain is visible?

## Required Plan Fields

For section writing, produce or update:

```yaml
central_headline_claim:
must_mention_anchors: []
paired_observables: []
figure_role_map: []
method_contribution_map: []
direction_comparator_table: []
claim_boundary_table: []
weak_or_missing_context: []
observed_vs_interpretive_claims: []
section_strategy:
```

For full-paper writing, also track section roles and cross-section dependencies.

## Evidence Hierarchy

Use primary evidence for the thesis, support evidence for credibility, boundary
evidence for calibration, and weak or missing context to prevent overclaiming.
Do not make all evidence equally prominent.

Do not let the story plan become a lossy substitute for evidence. If a panel,
control, negative result or validation item matters to whether a reader trusts a
claim, keep its role visible even when the prose later compresses it.

## Recoverability

Mark whether an anchor is directly recoverable, indirectly recoverable, or not
recoverable from allowed context. Direct and indirect anchors may be used with
proper boundaries. Unrecoverable details must not enter the manuscript.
