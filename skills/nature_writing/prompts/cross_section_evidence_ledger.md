# Cross-Section Evidence Ledger

Role: compare actual manuscript claims against Results support before
cross-section review.

Write structured YAML with:

```yaml
schema_version: nature_orchestrator.cross_section_evidence_ledger.v1
abstract_promises: []
intro_promises: []
discussion_claims: []
results_support_lines: []
missing_support: []
exact_value_mismatches: []
direction_conflicts: []
repetition_overload: []
recoverable_results_repairs: []
```

Use the paper story and section plans as templates, but verify the actual
manuscript text. A claim is supported only when Results visibly support it or a
recoverable repair is directly available from allowed plans/reviews.
