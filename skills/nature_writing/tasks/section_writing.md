# Section Writing Task

Use this task when the user asks for one manuscript section: Results,
Discussion, Abstract plus Introduction, or a targeted revision of one of them.

## Inputs

Use only the allowed context supplied by the workspace or runner:

- figure evidence, captions, result notes and tables
- methods, data availability, model assumptions and controls
- non-target sections when the task permits them
- references or citation notes when field positioning is requested
- paper-level story contract when a full-paper run already produced one

Do not read target-section oracle text or hidden reference manuscripts.

## Workflow

1. Build an evidence-to-story plan for the section.
2. Draft the section from allowed evidence and the section-specific prompt.
3. Run deterministic gates when available.
4. Ask the section-specific reviewer to decide `pass`, `revise` or `fail`.
5. If review or gates require revision, run the refiner with concrete issues.
6. Review again until pass or the refinement budget is exhausted.
7. Preserve the final section and all review artifacts.

## Section Roles

Results report the evidence chain. They should not become a figure catalogue or
a broad Discussion. Give most prose weight to primary findings, then controls,
mechanisms, validation and boundaries.

Discussion interprets what the Results change. It should synthesize, calibrate,
explain limitations and define implications without introducing new results.

Abstract and Introduction frame the paper. The abstract compresses the final
story with concrete recoverable findings; the Introduction narrows from field
importance to article-specific gap and bounded contribution.

## Pass Standard

A section can pass only when it is evidence-grounded, section-appropriate,
story-coherent and specific enough to the current paper. Fluency alone is not
enough.
