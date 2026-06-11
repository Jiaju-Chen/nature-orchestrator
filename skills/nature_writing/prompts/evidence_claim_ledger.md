# Evidence Claim Ledger

Role: separate evidence observations from claims before paper-level story
planning.

Write `paper/evidence/evidence_claim_ledger.yaml`.

Required schema:

```yaml
schema_version: nature_orchestrator.evidence_claim_ledger.v1
field:
evidence_items:
  - anchor:
    observation:
    comparator:
    direction:
    confidence_source:
    evidence_role:
    must_write_detail:
    can_compress:
    cannot_claim:
    downstream_section_use: []
story_use_rules: []
```

Use these controlled values:

- `confidence_source`: `caption_supported`, `source_data_supported`,
  `method_supported`, `allowed_context_supported`, `vlm_only`, `unclear`.
- `evidence_role`: `primary_claim`, `support`, `boundary`, `control`,
  `negative_result`, `validation`, `limitation`.
- `downstream_section_use`: `results`, `discussion`, `abstract`,
  `introduction`, `abstract_intro`.

Rules:

- The ledger is not the paper story. It is the evidence-confidence map that
  later story plans must respect.
- Mark comparator and direction as unclear unless they are recoverable from
  allowed captions, source data, methods, tables or result notes.
- VLM-only observations can guide attention to figure texture, but cannot carry
  definitive direction, causality, rescue, prevention or no-effect claims.
- `must_write_detail` should explain what a writer must preserve before
  compressing the item.
- `can_compress` should name what may be shortened after the item's role is
  clear.
- `cannot_claim` should state the unsafe claim boundary in plain language.
- Do not write manuscript prose, citations, hidden reference content or oracle
  facts.
