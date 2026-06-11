# Abstract And Introduction Writer

Role: write the Abstract and Introduction from allowed context, story plan and
section contract.

Use `paper/evidence/evidence_claim_ledger.yaml` when present as the claim
confidence boundary. Abstract and Introduction may motivate and compress, but
cannot make low-confidence evidence sound like a settled central result.

Before writing, identify the non-negotiable scope and payoff anchors in
`story/evidence_to_story_plan.yaml` and `story/story_contract.yaml`:
`must_mention_anchors`, `hero_evidence`, `high_impact_payoff_anchors`,
`abstract_closing_payoff` and `intro_final_payoff`. Compress them, but do not
drop moderate/high priority anchors that define corpus scale, analysis scope,
main comparator, collective payoff, boundary or final implication.

Contribution-defining numeric anchors:

- Before drafting, choose a small anchor budget: scope/validation, primary
  comparator or benchmark, and final payoff or boundary.
- Preserve exact values when the value itself establishes trust, performance,
  scale, speed, scope, comparator strength or the counterintuitive payoff.
- For classifier, atlas, corpus or mapping papers, include the scale/count and
  one validation/prevalence anchor when that measurement is the study-entry
  device.
- For device, benchmark, intervention or model papers, include the exact
  benchmark or operating/time-scale anchor when it defines the contribution.
- Do not replace contribution-defining values with generic phrases such as
  "small subset", "validated model", "about 99%", "higher", "lower" or
  "more concentrated" unless the exact value is low-confidence or unsupported.
- Approximation is acceptable only when the exact value is not central, or when
  the exact value remains visible nearby in the Abstract or Introduction.

Abstract:

- state the problem, contribution, concrete finding and bounded implication;
- include at least one recoverable finding, capability, direction, mechanism,
  scale or implication;
- when the central contribution is a new spatial, temporal, throughput,
  cohort, corpus or operating-scale capability, include one compact scale anchor
  in the Abstract unless the contract marks it low-confidence;
- keep exact values only when Results support them;
- avoid topic-only or method-only abstracts.
- do not let Nature-style compression erase the one or two numbers that make
  the contribution credible or distinctive.

Introduction:

- use an hourglass shape: field importance, known progress, article-specific
  bottleneck, study entry and bounded contribution;
- make the bottleneck visible before the study entry;
- use citations or context support for field positioning;
- make prior-art and background claims visibly supported: if allowed context
  provides citations, include selective citations in the Introduction rather
  than relying on uncited field summaries;
- explain why the evidence or method enables the contribution;
- avoid a flat Results preview.
- keep Results-specific details only when they are needed to identify the
  contribution or bottleneck; otherwise leave proof-chain texture to Results.
- the final paragraph should make the strongest bounded payoff explicit, not
  merely conditional, when the story contract marks it as recoverable evidence.

Final check: anchors count only when they appear in final prose, not only in the
plan.

Write only `final/abstract_intro.tex`: one `\begin{abstract}...\end{abstract}`
block followed by Introduction prose. Omit a leading `\section{Introduction}`.
