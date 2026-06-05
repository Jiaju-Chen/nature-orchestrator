# Holdout Comparison Case Notes

This page is the public case index for the five-paper holdout comparison. It is
intended to help a human reviewer inspect the method, reviewer comments and
supervisor comments without requiring raw benchmark outputs in the repository.

## What Belongs In The Public Repo

- The method summary and score table.
- Curated section reviewer, cross-section reviewer and supervisor opinions.
- The exact run identifiers used to locate local artifacts.
- Notes about remaining writing weaknesses and reviewer false-pass risks.

The current curated report is:

```text
docs/holdout_review_report_nature_writing_current.md
```

## What Belongs In The Private Case Artifacts

Generated manuscripts and converted ground-truth manuscripts should be kept as
private review artifacts, not public release files. For local review, use this
layout:

```text
docs/cases/holdout_review/
  index.html
  generated/
    <slug>.pdf
  ground_truth/
    <slug>.pdf
  private_artifacts/
    reviewer_logs/
    supervisor_reports/
```

The `generated/`, `ground_truth/` and `private_artifacts/` subdirectories are
git-ignored in this repository. This lets the local case folder behave like a
single review package for collaborators while keeping the public GitHub release
focused on the skill and reproducible evaluation summary.

## Current Holdout Set

- health sciences
- earth/environment
- biological sciences
- physical sciences
- scientific community/society

The public summary intentionally avoids copying original paper prose or the
generated manuscripts. It records scores, reviewer judgments, supervisor
judgments and skill-improvement lessons.
