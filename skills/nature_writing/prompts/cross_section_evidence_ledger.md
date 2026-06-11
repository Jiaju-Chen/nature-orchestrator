# Cross-Section Evidence Ledger

Role: compare actual manuscript claims against Results support before
cross-section review.

Write structured YAML with:

```yaml
schema_version: nature_orchestrator.cross_section_evidence_ledger.v1
abstract_promises: []
intro_promises: []
discussion_claims: []
background_context_claims: []
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

Classification rules:

- Classify each outside-Results claim exactly once.
- Do not classify broad Introduction background or motivation as
  `missing_support` merely because Results do not discuss it. Put it in
  `background_context_claims` unless it contains exact study values,
  paper-specific findings, unsupported mechanisms, causal conclusions or
  contribution promises.
- Put an Introduction statement in `missing_support` only when it promises a
  study-specific finding, exact value, comparator, mechanism, scope boundary or
  contribution that Results should visibly support.
- If current Results visibly support a claim, put the support excerpt in
  `results_support_lines` and do not also list the same claim in
  `missing_support`.
- Use `recoverable_results_repairs` only when the current Results do not yet
  contain the support line and an allowed plan/review directly supports adding
  it.
- If a previously suggested repair has already been added to current Results,
  treat it as current Results support, not as missing support.
