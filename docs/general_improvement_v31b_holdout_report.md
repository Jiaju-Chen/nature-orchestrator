# Nature Writing General Improvement V31b Holdout Report

Date: 2026-06-11

Branch: `codex/nature-writing-general-improvement`

Evaluator: Supervisor v2.1, `text-source=final-manuscript`

Current release baseline:

| metric | baseline |
| --- | ---: |
| Results | 4.260 |
| Discussion | 4.380 |
| Abstract+Intro | 4.220 |
| Cross-section | 4.494 |
| Mean of four | 4.338 |

## Result

V31b improves all four tracked metrics over the current release baseline on the five holdout full-paper generation runs.

| metric | release baseline | V31b mean | delta |
| --- | ---: | ---: | ---: |
| Results | 4.260 | 4.460 | +0.200 |
| Discussion | 4.380 | 4.580 | +0.200 |
| Abstract+Intro | 4.220 | 4.420 | +0.200 |
| Cross-section | 4.494 | 4.570 | +0.076 |
| Mean of four | 4.338 | 4.508 | +0.170 |

All five final manuscripts passed cross-section review.

| slug | field | Results | Discussion | Abstract+Intro | Cross | Mean4 | status | cross rounds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| s41586-025-09922-y | scientific_community_and_society | 4.700 | 4.500 | 4.300 | 4.650 | 4.537 | done/pass | 2 |
| s41586-026-10423-9 | physical_sciences | 4.500 | 4.700 | 4.500 | 4.650 | 4.588 | done/pass | 3 |
| s41586-026-10414-w | health_sciences | 4.200 | 4.600 | 4.400 | 4.550 | 4.438 | done/pass | 6 |
| s41586-026-10497-5 | earth_and_environmental_sciences | 4.400 | 4.500 | 4.400 | 4.550 | 4.463 | done/pass | 3 |
| s41586-026-10426-6 | biological_sciences | 4.500 | 4.600 | 4.500 | 4.450 | 4.513 | done/pass | 3 |

## Run Ids

Full-paper generation runs:

| slug | run id |
| --- | --- |
| s41586-025-09922-y | `general_improvement_v31b_society_api` |
| s41586-026-10423-9 | `general_improvement_v31b_physical_api` |
| s41586-026-10414-w | `general_improvement_v31b_health_api` |
| s41586-026-10497-5 | `general_improvement_v31b_earth_api` |
| s41586-026-10426-6 | `general_improvement_v31b_bio_api` |

Supervisor v2.1 evaluation runs:

| slug | eval id |
| --- | --- |
| s41586-025-09922-y | `general_improvement_v31b_society_v21` |
| s41586-026-10423-9 | `general_improvement_v31b_physical_v21` |
| s41586-026-10414-w | `general_improvement_v31b_health_v21` |
| s41586-026-10497-5 | `general_improvement_v31b_earth_v21` |
| s41586-026-10426-6 | `general_improvement_v31b_bio_v21` |

## Main Changes Tested

- Added an evidence-to-claim ledger before paper-level story planning so the paper story can order and weight evidence without upgrading uncertain or VLM-only observations into definitive claims.
- Strengthened section writer/reviewer/refiner prompts to preserve contribution-defining anchors while avoiding figure-list prose.
- Added quote-level review validation so reviewers cannot cite invented final-text snippets.
- Added cross-section evidence ledger, cross-section repair planner and targeted section patcher for local cross-section fixes.
- Added final section anchor gates to catch cross-section polishers or patchers deleting reviewer-confirmed numeric anchors.
- Added API retry handling for common transient provider failures.
- Added `--max-cross-repair-rounds` so full-paper cross-section repair has its own budget instead of being tied to section refiner rounds.

## Reviewer And Supervisor Signals

### Society

Cross reviewer passed with 4.65. Remaining notes were minor: keep data-availability interpretation descriptive, keep policy implications bounded, and avoid unnecessary repetition of core measurement and growth numbers.

Supervisor v2.1 scored Results 4.7, Discussion 4.5 and Abstract+Intro 4.3. Strengths were accurate quantitative recovery, calibrated observational claims and a clear individual-reward versus collective-concentration story.

### Physical Sciences

Cross reviewer passed with 4.65. Remaining notes were minor: keep Q2/Q5 dot-origin wording aligned with Results, avoid extra repetition of CZ/teleportation headline values and preserve the simulation boundary for elongated-potential saturation.

Supervisor v2.1 scored Results 4.5, Discussion 4.7 and Abstract+Intro 4.5. Strengths were the conveyor-to-CZ-to-teleportation chain, strong numeric anchor recall and good conditional-teleportation boundaries.

### Health Sciences

Health was the hardest cross-section case. It initially failed cross review because Introduction and Discussion contained result-level details that Results did not visibly support, including preserved conduction, specific transcriptional categories, ATP wording and ageing baseline phrasing.

The added independent cross-section repair budget allowed five targeted repair rounds. The final cross reviewer passed with 4.55. Remaining notes were minor: keep adaptive-versus-pathogenic framing tied to timing and repair outcome, maintain therapy-related qualifiers and avoid implying human pathway identity from background motivation.

Supervisor v2.1 scored Results 4.2, Discussion 4.6 and Abstract+Intro 4.4. Results remained the weakest section because the biological evidence chain is dense and easy to over-compress, but the final manuscript preserved the main numeric and directional anchors.

### Earth And Environmental Sciences

Cross reviewer passed with 4.55. Remaining notes were minor: keep finite-foreshock impulse interpretation bounded, avoid further repetition of 0.6--12.7 ms and about 80 ms duration anchors and keep natural-earthquake comparisons qualified.

Supervisor v2.1 scored Results 4.4, Discussion 4.5 and Abstract+Intro 4.4. Strengths were strong duration and Vmin anchors, a clear regime-map story and careful natural-event caveats.

### Biological Sciences

Cross reviewer passed with 4.45. Remaining notes were minor: use about 80% consistently, soften physical-proximity claims and avoid repeating validation and whisker-trimming values outside their highest-value locations.

Supervisor v2.1 scored Results 4.5, Discussion 4.6 and Abstract+Intro 4.5. Strengths were a coherent tracer-validation to network-selectivity to plasticity chain, good numeric anchor recall and well-bounded tracer-readout claims.

## Interpretation

The strongest improvement is not a single prompt patch. The general improvement comes from making the pipeline more evidence-aware and more repairable:

- Evidence is separated from claims before story planning.
- Section writers still have room to write, but reviewers and gates now catch unsupported specificity.
- Cross-section repair can target the exact section that introduced drift instead of rewriting the whole manuscript.
- Extra cross-section repair budget matters for dense biological papers where late-stage issues only become visible after several repairs.

The main remaining risk is that cross-section repair can still spend too many rounds adding Results support when the cleaner move is to soften an outside-Results claim. The health run eventually passed, but it needed six cross review rounds. Future work should make repair planning more decisive about when to remove or soften external claims rather than repeatedly trying to support them from Results.

## Verification

Unit tests:

```text
python -m unittest discover -s tests
Ran 45 tests in 0.478s
OK
```

No generated manuscripts, PDFs, oracle files or API keys are included in this report.
