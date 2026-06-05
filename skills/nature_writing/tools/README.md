# Runner Notes

The skill can be used directly by an agent as process guidance, or through the
NatureOrchestrator runners.

Current runner profiles:

```bash
python scripts/run_full_paper_generation.py \
  --section-skill-profile nature_writing \
  --full-paper-polisher-profile nature_writing \
  --agent-backend api \
  --max-refiner-rounds 2
```

For single sections, use the runner-specific skill version:

```bash
python scripts/run_results_batch.py --skill-version nature_writing_current_results
python scripts/run_discussion_batch.py --skill-version nature_writing_current_discussion
python scripts/run_abstract_intro_batch.py --skill-version nature_writing_current_abstract_intro
```

These profiles read prompt and rubric files from `skills/nature_writing/`.
