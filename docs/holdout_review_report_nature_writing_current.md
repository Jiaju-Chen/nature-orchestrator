# Nature Writing Current Skill Holdout Review Report

本报告整理当前 root-level `skills/nature_writing` 最新版在 5 篇 holdout 上的最终生成结果。目的不是保存 raw output，而是把人类评审最需要看的判断集中起来：section reviewer 是否指出了关键问题，cross-section reviewer 是否检查了全文一致性，独立 Supervisor V2.1 是否认可最终稿件。

本报告不是原论文正文、ground truth manuscript 或 generated manuscript 的复制。它是从 reviewer/supervisor 结构化输出中整理出的人工可读摘要，保留最终分数、主要判断、剩余问题和对 skill 的改进建议。

## Scope

- Pipeline: paper story planner -> Results -> Discussion -> Abstract+Intro -> cross-section evidence ledger -> cross-section reviewer/refiner loop -> final polish.
- Backend: API agent executor.
- Text source for Supervisor V2.1: final polished manuscript, not intermediate section draft.
- Committed content: skill, runner/evaluator code, tests, and this curated report. Raw `outputs/`, generated manuscripts, and article source data are not committed.

## Overall Scores

| field | slug | Abstract+Intro | Results | Discussion | mean | cross reviewer |
|---|---|---:|---:|---:|---:|---|
| health sciences | `s41586-026-10414-w` | 4.700 | 4.500 | 4.500 | 4.567 | 4.600 pass |
| earth/environment | `s41586-026-10497-5` | 4.500 | 4.600 | 4.500 | 4.533 | 4.650 pass |
| biological sciences | `s41586-026-10426-6` | 4.500 | 4.500 | 4.600 | 4.533 | 4.620 pass |
| physical sciences | `s41586-026-10423-9` | 4.500 | 4.600 | 4.600 | 4.567 | 4.550 pass |
| scientific community/society | `s41586-025-09922-y` | 4.500 | 4.600 | 4.600 | 4.567 | 4.650 pass |

| aggregate | score |
|---|---:|
| Abstract+Intro mean | 4.540 |
| Results mean | 4.560 |
| Discussion mean | 4.560 |
| overall mean | 4.553 |
| Supervisor verdicts | 15 pass / 0 needs_revision / 0 fail |

## How To Read The Reviewer Opinions

- Section reviewer: pipeline 内部 reviewer，分别审 Results、Discussion、Abstract+Intro，主要看该 section 的 evidence fidelity、story quality、anchor recall、claim boundary 和 writing quality。
- Cross-section reviewer: pipeline 内部全文 reviewer，检查 Abstract/Intro/Results/Discussion 之间的 promise-support 一致性、重复、边界和 unsupported claims。
- Supervisor V2.1: 独立评价者，用最终 polished manuscript 评分，不是 writer/reviewer 自评；重点看 grounding、story、写作流畅度、句子紧密性、claim calibration 和 reviewer 是否漏审。

## Case: `s41586-026-10414-w` (health sciences)

Run: `rollout_nature_writing_fix7_health_api_20260605`
Supervisor eval: `rollout_nature_writing_fix7_health_api_20260605_supervisor_final`

| source | Abstract+Intro | Results | Discussion |
|---|---:|---:|---:|
| Supervisor V2.1 | 4.70 | 4.50 | 4.50 |

### Section Reviewer Final Opinions

**Abstract+Intro reviewer**: `pass`; score `4.667`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.8, section_function 4.7, anchor_recall 5.0, claim_boundary 4.5, writing_quality 4.6.
Final concerns:
- text_level_issues: Consider retaining the wording 'calcium photometry' rather than 'firing' in future edits because photometry is a proxy, although the current abstract uses activity for the main claim.
- text_level_issues: The abstract is dense but still readable and within section function.
- unrecoverable_detail_risk: The abstract says local inhibition of microglial CSF1R signalling; evidence supports local PLX5622 CSF1R inhibition reducing IO microglia, so this is acceptable but should remain depletion-focused downstream.
Representative anchor recall:
- CCP_to_IO_preserved_integrity: recalled in abstract and Introduction with preserved axonal integrity/conduction and no IO neuron loss
- 60_percent_activity_decrease: recalled with timing around 7 d.p.l. and recovery as remyelination begins
- threefold_local_IO_microgliosis: recalled with 14 d.p.l. peak and localization

**Results reviewer**: `pass`; score `4.567`; accepted `True`.
Scores: evidence_fidelity 4.6, story_quality 4.5, section_function 4.6, anchor_recall 4.8, claim_boundary 4.5, writing_quality 4.4.
Final concerns:
- text_level_issues: Minor: the phrase 'conditions associated with poorer repair' slightly overpackages the aged-rat comparison; the surrounding prose keeps this as a chronicity comparison, so it is not blocking.
Representative anchor recall:
- fig1_remote_activity_3_5mm: recalled with 3.5 mm CCP-to-IO geometry, 7 d.p.l. reduced spike rate and AUC versus baseline
- fig1_region_selective_microgliosis: recalled with IO and lesion IBA1 increase plus Purkinje layer and DCN no-increase boundary
- fig1_synaptic_engulfment_markers: recalled with C1q, C1q-vGLUT2, CD68/lysosome and PSD95-in-lysosome increases at 14 d.p.l.

**Discussion reviewer**: `pass`; score `4.733`; accepted `True`.
Scores: evidence_fidelity 4.7, story_quality 4.8, section_function 4.8, anchor_recall 4.7, claim_boundary 4.8, writing_quality 4.6.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- CCP_to_IO_mapping_preserved_neurons_axons: Recalled: 'calbindin-positive IO projection neurons located about 3.5 mm away, without detectable IO neuronal loss or loss of axonal density.'
- activity_decrease: Recalled: 'IO neuronal calcium activity fell transiently by about 60%, reaching its nadir around 7 d.p.l.'
- microgliosis_timecourse_locality: Recalled: 'increased from 7 d.p.l., peaked at about threefold at 14 d.p.l. and resolved by 28 d.p.l.' plus no GFAP/adjacent/downstream response.

### Cross-Section Reviewer Final Opinion

Status `pass`; score `4.600`; accepted `True`.
- central thesis: 4.7 - Consistent with the story contract: focal CCP demyelination drives a remote IO activity, metabolic and microglial programme linked to synaptic remodeling and repair outcome.
- evidence support: 4.6 - The evidence ledger marks all Abstract promises and study-entry claims as supported or contextual literature claims. No exact-value mismatches or direction conflicts were identified.
- discussion boundary: 4.5 - Discussion interprets rather than adds unsupported results. It correctly limits cross-model findings to microglial-density recurrence and states human relevance as model-based.
- claim boundary: 4.7 - Central qualifiers are consistent: remote IO grey-matter response, calcium proxy, density-only cross-model conservation, depletion-focused PLX5622 support, and model-based human implications.
Final targeted watch-points:
- Keep PLX5622 wording depletion-focused and avoid implying a defined CSF1R molecular mechanism.
- If revising Results, add the model-depth boundary that the full mechanistic sequence is in the young female rat CCP-to-IO circuit.
- Avoid further numerical repetition of the 3.5 mm, 7 d.p.l., 14 d.p.l. and 28 d.p.l. anchors outside Results.
- Preserve the boundary that cross-model conservation applies to microglial density, not the full activity/ATP/transcriptomic/synaptic sequence.
- Maintain ageing as blunted inducible-response evidence rather than direct proof of repair failure.
Unsupported/contextual claims noted by cross reviewer:
- Contextual literature framing, not a Results promise.
- Useful boundary in Discussion; sex/model-depth boundary is not visible in Results text but is not a blocking result-level claim.

### Independent Supervisor V2.1 Final Opinion

**Abstract+Intro supervisor**: `pass`; score `4.70`; evidence `4.8`; story `4.7`; flow `4.5`; claim calibration `4.6`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: focal white-matter demyelination recruits a remote IO microglia-neuron programme linked to activity, synapses and repair.
- High-value quantitative anchors are included without excessive marker lists.
- Contribution is calibrated by preserved axonal integrity, neuron survival, recovery with remyelination, ageing failure and blocked-repair persistence.
Weaknesses / watch-points:
- Several abstract sentences carry many clauses and could be lighter for main-journal cadence.
- Figure-role understanding is implicit because the section has no figure references; the prose explains experimental roles but not panel hierarchy.
- The phrase 'coordinate activity and repair' is directionally supported but close to mechanistic compression of several experiments.
Skill lessons:
- promote: Keep explicit model-boundary language when previewing cross-model generality.
- promote: Preserve quantitative anchors that define the contribution rather than peripheral methodological details.
- revise: Encourage one fewer compound clause in abstracts when many anchors compete for attention.
- revise: Separate causal intervention claims from broader coordination language when mechanism is inferred across experiments.
Supervisor comment on reviewer:
- Reviewer pass was mostly reliable, but it slightly underweighted sentence-cadence and mechanistic-compression cautions.

**Results supervisor**: `pass`; score `4.50`; evidence `4.5`; story `4.6`; flow `4.4`; claim calibration `4.5`; reviewer false-pass risk `low`.
Strengths:
- Clear narrative chain from remote activity change to microgliosis, spatial states, cellular remodeling, perturbation and repair-failure chronicity.
- Central numeric and directional anchors are recovered: 3.5 mm distance, approximately 60% activity decrease, 7 and 14 d.p.l. timing, ATP decrease and 28 d.p.l. failed-repair endpoint.
- Figure roles are hierarchical rather than catalogued, with Fig. 4 used as the functional perturbation pivot.
Weaknesses / watch-points:
- Some sentences are densely packed with many assays, especially the Fig. 1 and Fig. 3 paragraphs.
- The ageing paragraph slightly overpackages aged animals as 'conditions associated with poorer repair' rather than a narrower chronicity/blunted-response comparison.
- A few mechanistic verbs such as 'link' and 'regulate' approach the upper boundary of what marker and perturbation evidence alone proves, though surrounding caveats keep this non-blocking.
Grounding concerns:
- unsupported: Low severity: 'surveillance-like microglial state' is interpretive shorthand from morphology/transcriptional data and would be safer as 'morphology consistent with a less phagocytic state' unless supported by source text.
Skill lessons:
- promote: Keep figure-role planning that assigns discovery, state-resolution, cellular-mechanism, perturbation and chronicity functions before drafting.
- promote: Preserve explicit boundary clauses when extending a density response across lesion methods or circuits.
- revise: Add a final pass for inferred biological labels such as 'surveillance-like' that may not be explicitly recoverable from captions.
- revise: Ask reviewers to flag overloaded assay-list sentences separately from evidence fidelity.
Supervisor comment on reviewer:
- Reviewer pass was broadly justified and caught the minor ageing overpackage.
- Reviewer underweighted the 'surveillance-like' wording and dense sentence cadence as small remaining polish issues.

**Discussion supervisor**: `pass`; score `4.50`; evidence `4.5`; story `4.7`; flow `4.6`; claim calibration `4.6`; reviewer false-pass risk `low`.
Strengths:
- Clear central thesis: focal white-matter demyelination drives a remote, circuit-specific grey-matter programme linked to repair outcome.
- Paragraph roles are distinct: thesis, temporal mechanism, perturbation, generalization boundary, ageing/failed repair, and implication.
- Strong claim calibration around cross-model conservation, young female rat model depth, GCaMP proxy status, and human disease relevance.
Weaknesses / watch-points:
- Some central numerical anchors are intentionally softened, which improves discussion flow but slightly reduces recoverable specificity.
- No explicit citations appear in the discussion; most claims are internal results synthesis, but broader disease and therapeutic-context statements rely on earlier context rather than visible citation support.
- Figure-role understanding is implicit through experiments and mechanisms rather than explicit discussion of figure hierarchy.
Grounding concerns:
- missing: The discussion recalls ATP decline timing but omits the recoverable 13.2 +/- 1.3% magnitude; acceptable as selectivity, but a central quantitative ATP anchor is softened.
- missing: The activity and microglial time courses are directionally correct but omit the about 60% activity fall and about threefold microglial peak, limiting quantitative force.
- unsupported: The phrase 'pre-activated-like but unresponsive state' for aged microglia is a reasonable synthesis but should remain explicitly inferential, as repair impairment in ageing is not directly proven by these data.
- unsupported: The final therapeutic implication about preserving adaptive microglial functions is calibrated as a strategy direction, but it is not directly tested in human lesions.
Skill lessons:
- promote: Keep the discussion organized around conceptual moves rather than figure order.
- promote: Require explicit boundaries for cross-model conservation and model depth.
- revise: Reviewer checks should compare the final text itself against must-mention quantitative anchors instead of relying on planned or previous wording.
- revise: Discussion prompts should specify which numerical anchors are essential versus optional for selectivity.
Supervisor comment on reviewer:
- Reviewer pass is mostly justified, but it overstated exact anchor recall by marking omitted magnitudes such as about 60%, about threefold, and 13.2 +/- 1.3% as recalled.
- Reviewer did not flag the absence of visible citation support for broader disease-positioning statements.


## Case: `s41586-026-10497-5` (earth/environment)

Run: `rollout_nature_writing_fix7_earth_api_20260605`
Supervisor eval: `rollout_nature_writing_fix7_earth_api_20260605_supervisor_final`

| source | Abstract+Intro | Results | Discussion |
|---|---:|---:|---:|
| Supervisor V2.1 | 4.50 | 4.60 | 4.50 |

### Section Reviewer Final Opinions

**Abstract+Intro reviewer**: `pass`; score `4.833`; accepted `True`.
Scores: evidence_fidelity 5.0, story_quality 5.0, section_function 5.0, anchor_recall 5.0, claim_boundary 5.0, writing_quality 4.0.
Final concerns:
- text_level_issues: Introduction is dense in the final paragraph; acceptable for this pass but could be lightly trimmed in copy-edit.
- text_level_issues: Abstract final clause 'different frictional length scales' is safe but less specific than the Introduction's 0.3-3.0 mm range.
Representative anchor recall:
- PMMA biaxial experiments with high-speed photoelastic imaging plus strain displacement and accelerometer data: recalled in abstract and Introduction
- ten experiments five nominal normal stresses and 94 dynamic events: recalled in abstract and Introduction
- representative durations 0.6-12.7 ms and suite maximum about 80 ms: recalled in abstract and Introduction

**Results reviewer**: `pass`; score `4.650`; accepted `True`.
Scores: evidence_fidelity 4.7, story_quality 4.6, section_function 4.6, anchor_recall 4.8, claim_boundary 4.7, writing_quality 4.5.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- same_150_bar_stress_vs_12_7_3_6_0_6_ms: recalled
- foreshock_to_10_m_s_threshold_clock: recalled
- fig2_normal_peak_shear_and_comparable_weakening: recalled

**Discussion reviewer**: `pass`; score `4.683`; accepted `True`.
Scores: evidence_fidelity 4.7, story_quality 4.6, section_function 4.7, anchor_recall 4.8, claim_boundary 4.8, writing_quality 4.5.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- 0.6-12.7 ms and about 80 ms: Recalled in paragraph 1: '0.6 to 12.7 ms' and 'about 80 ms'.
- PMMA observable nucleation begins with foreshock and exceptions go direct: Recalled in paragraph 1 with PMMA-series boundary and direct dynamic rupture exception.
- weakening rate insufficient and pressure-insensitive initial drop: Recalled in paragraph 1: similar weakening rates and pressure-insensitive strength drop do not account for two-decade spread.

### Cross-Section Reviewer Final Opinion

Status `pass`; score `4.650`; accepted `True`.
- central thesis: 4.7 - consistent
- evidence support: 4.7 - strong
- discussion boundary: 4.6 - well_bounded
- claim boundary: 4.7 - consistent
Final targeted watch-points:
- Keep repeated duration anchors compressed outside Results: 0.6--12.7 ms and about 80 ms are central but appear in all sections.
- Avoid adding further paraphrases of the foreshock-to-V_min directionality outside Results and the current Discussion synthesis.
- Preserve the PMMA-series boundary for foreshock initiation; do not imply a universal foreshock requirement for all faults.
- Maintain natural-earthquake language as selected, indirect, proxy-dependent consistency tests rather than diagnostic proof.
- Keep V_min framed as an inferred/model-bounded organizing variable, not a uniquely sufficient predictor independent of assumptions.

### Independent Supervisor V2.1 Final Opinion

**Abstract+Intro supervisor**: `pass`; score `4.50`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.6`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: foreshock-set V_min organizes nucleation duration and regime better than stress state, weakening rate or normal stress alone.
- Must-mention numeric anchors are recalled without anchor dumping.
- Natural-earthquake comparison is explicitly bounded by indirect velocity estimation and different frictional length scales.
Weaknesses / watch-points:
- Figure roles are implied through evidentiary functions but no figure hierarchy is visible in the introduction text.
- Some long sentences in the abstract and methods-entry paragraph are information-dense enough to slow Nature-style cadence.
- The last introduction paragraph previews a quantitative natural-fault parameter inference that may be better reserved for Results or Discussion.
Skill lessons:
- promote: Keep explicit abstract disclosure of dataset scale, anomaly, organizing variable, mechanism and boundary condition.
- promote: Use Introduction paragraphs to convert prior controls into the article-specific bottleneck before presenting the study system.
- revise: Ask writers to flag when final Introduction sentences cross from contribution framing into quantitative Results or Discussion payoff.
- revise: Encourage one cadence pass on abstracts with many numerical and mechanistic anchors.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified, but it underweighted the mild section-role risk from the 0.3-3.0 mm natural L statement.

**Results supervisor**: `pass`; score `4.60`; evidence `4.6`; story `4.7`; flow `4.5`; claim calibration `4.6`; reviewer false-pass risk `low`.
Strengths:
- Strong opening contrast: same 150 bar experiment and similar pre-dynamic stresses are tied to 12.7, 3.6 and 0.6 ms durations.
- Key measurement boundary is explicit: nucleation starts at accelerometer foreshock and ends at 10 m s^-1 rupture velocity.
- Fig. 2 is used as a control against simple weakening or normal-stress explanations rather than as a figure recap.
Weaknesses / watch-points:
- A few phrases such as 'decisive organizing relation' are editorially strong and could be softened while retaining the same conclusion.
- The EoM paragraph is dense, combining parameters, overstress, regime boundary and nucleation-length implication in one block.
- The full-suite 'about 80 ms' anchor is included but not developed with much context from the available figure evidence.
Skill lessons:
- promote: Keep requiring figure-role maps that turn controls into argument steps, especially Fig. 2-style negative/comparator evidence.
- promote: Preserve explicit model-boundary language for inferred variables and natural-event extrapolations.
- revise: Ask writers to flag overly emphatic connective phrases when the evidence is a consistency relation rather than direct proof.
- revise: Encourage splitting parameter-heavy model sentences if they combine assumptions, results and implications.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified; minor cadence and overemphasis issues were not highlighted but are non-blocking.

**Discussion supervisor**: `pass`; score `4.50`; evidence `4.6`; story `4.6`; flow `4.5`; claim calibration `4.7`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: foreshock-induced transient velocity V_min organizes nucleation timing and length better than initial stress or weakening rate alone.
- Key numerical anchors are recovered: 0.6-12.7 ms representative range, about 80 ms suite maximum, and 0.3-3.0 mm natural-event inference.
- Discussion places limitations close to extrapolations: PMMA-specific foreshock association, proxy-dependent natural estimates, and model dependence are explicit.
Weaknesses / watch-points:
- Figure role is mostly implicit because the Discussion avoids figure references; this is acceptable but slightly weakens traceability of V_min and length claims.
- Classical-expectation and natural-event positioning rely on prior section context rather than visible citations in the Discussion itself.
- The phrase that V_min predicts spatial development is supported by the plan and Results but could sound more deterministic than the model-bounded evidence warrants.
Skill lessons:
- promote: Keep Discussion organized around anomaly-to-mechanism-to-boundary rather than figure-order recapitulation.
- promote: Preserve explicit experimental-system boundaries when extending laboratory nucleation results to natural faults.
- revise: Require a citation/context check for Discussion sentences invoking classical expectations or selected natural cases.
- revise: Ask writers to distinguish observable prediction from model-bounded organization when using terms such as 'predicts'.
Supervisor comment on reviewer:
- Reviewer pass was broadly justified; minor missed issue is underemphasis of citation visibility in the Discussion prose.


## Case: `s41586-026-10426-6` (biological sciences)

Run: `rollout_nature_writing_fix7_bio_api_20260605`
Supervisor eval: `rollout_nature_writing_fix7_bio_api_20260605_supervisor_final`

| source | Abstract+Intro | Results | Discussion |
|---|---:|---:|---:|
| Supervisor V2.1 | 4.50 | 4.50 | 4.60 |

### Section Reviewer Final Opinions

**Abstract+Intro reviewer**: `pass`; score `4.633`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.6, section_function 4.5, anchor_recall 5.0, claim_boundary 4.6, writing_quality 4.4.
Final concerns:
- text_level_issues: Abstract is information-dense; optional final polish could reduce one validation clause, but no required revision.
- text_level_issues: The phrase 'remodel with sensory experience' is acceptable from context, though 'alter after sensory deprivation' would be slightly more bounded.
Representative anchor recall:
- AAV5-GfaABC1D-Cx43:TID:HA astrocyte network tracer: recalled
- HA infected cells and streptavidin in-network cells with low background: recalled
- around 10% infected labels more than 80% in-network in culture: recalled

**Results reviewer**: `pass`; score `4.567`; accepted `True`.
Scores: evidence_fidelity 4.6, story_quality 4.5, section_function 4.4, anchor_recall 4.8, claim_boundary 4.6, writing_quality 4.5.
Final concerns:
- text_level_issues: Minor: the phrase 'adult sensory manipulation' rests mainly on the abstract/context timeline rather than a detailed age statement in the Fig. 5 caption, but it does not distort the result.
Representative anchor recall:
- fig1_cell_classes: recalled with HA/streptavidin classes
- fig1_culture_sparse_to_broad: recalled: 10% infection, 80% network
- fig1_localization: recalled: expansion/SMLM and 20.73 Å median distance

**Discussion reviewer**: `pass`; score `4.750`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.7, section_function 4.8, anchor_recall 4.8, claim_boundary 4.8, writing_quality 4.6.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- Cx43_TID_cell_classes: Recalled: 'Cx43 to TurboID under the GfaABC1D promoter' and 'separates infected HA-positive astrocytes from HA-negative, streptavidin-positive cells... unlabeled gaps'.
- culture_gap_junction_dependence: Recalled: 'approximately 10\% infected cells labeled more than 80\% of cells as in-network' and 'depending on gap junctions'.
- proximity_anchor: Recalled: 'median HA-to-nearest-Cx43 distance of 20.73 \AA{}'.

### Cross-Section Reviewer Final Opinion

Status `pass`; score `4.620`; accepted `True`.
- central thesis: 4.7 - consistent
- evidence support: 4.6 - supported
- discussion boundary: 4.75 - pass
- claim boundary: 4.7 - consistent
Final targeted watch-points:
- Optional: in Abstract and final Introduction sentence, prefer 'altered after sensory deprivation' over stronger 'remodel with sensory experience' if further tightening is desired.
- Optional: keep repeated validation anchors compact outside Results, especially 10%/80% culture labeling and 20.73 Å proximity.
- Optional: maintain qualitative-only wording for astrocyte-neuron divergence; do not add overlap statistics unless supported elsewhere.
Unsupported/contextual claims noted by cross reviewer:
- claim: Dye transfer and reduced preparations cannot define distant recipient cells in intact brain volumes.; section: Introduction; severity: nonblocking
- claim: Future causal roles of astrocyte network remodeling in neuronal plasticity and behaviour.; section: Discussion; severity: nonblocking

### Independent Supervisor V2.1 Final Opinion

**Abstract+Intro supervisor**: `pass`; score `4.50`; evidence `4.7`; story `4.5`; flow `4.4`; claim calibration `4.6`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: a Cx43-TurboID tracer reveals organized, connexin-dependent and experience-sensitive astrocyte gap-junction networks.
- Must-mention anchors from the story plan are recovered without obvious invention.
- Claims are bounded to tracer-defined networks rather than unqualified physiological function or behaviour.
Weaknesses / watch-points:
- Abstract compresses many method and result anchors into one long sentence chain, reducing Nature-style cadence.
- Figure roles are implicit rather than actively explained; the section names experimental readouts but not a sharp hierarchy of visual evidence.
- Some broad opening claims rely on selective citations and could be more visibly tied to the literature context.
Skill lessons:
- promote: Keep abstract_intro plans that force separate tracer logic, validation anchors, in vivo mapping and bounded biological payoff.
- promote: Preserve final-introduction contribution framing that previews scope without detailed results inventory.
- revise: Ask writers to check whether Nature abstract anchors can be grouped into fewer rhetorical moves rather than listed sequentially.
- revise: Add an explicit citation-positioning check for broad opening claims in Introduction paragraphs.
Supervisor comment on reviewer:
- Reviewer passed appropriately overall, but slightly underweighted abstract density and implicit figure-role hierarchy.

**Results supervisor**: `pass`; score `4.50`; evidence `4.6`; story `4.5`; flow `4.4`; claim calibration `4.7`; reviewer false-pass risk `low`.
Strengths:
- Builds a clear validation-to-mapping-to-perturbation-to-plasticity chain rather than a flat panel list.
- Recalls central numeric anchors: 10% infection, 80% network, 20.73 Å proximity, connexin cKO P values, and whisker-trim ratio.
- Calibrates boundaries well: tracer-defined coupling, no exchange directionality, no neuronal projection or synaptic-connectivity claim.
Weaknesses / watch-points:
- Some sentences are dense and specialist-report-like, especially in the cKO paragraph with genotype, staining, location and statistics compressed together.
- Figure 2 receives a modestly descriptive treatment; the distinct biological payoff emerges more strongly only after the Fig. 3 atlas analysis.
- The final astrocyte-neuron comparison remains qualitative, appropriately bounded but less mechanistically satisfying than the preceding quantitative claims.
Grounding concerns:
- missing: Minor: Fig. 5 sample sizes and one-sided Mann-Whitney test are recoverable but omitted; the central ratio and P value are present.
- missing: Minor: Fig. 3 multiple-testing details and 60% composite-subregion rule are omitted, acceptable for main Results narrative.
Skill lessons:
- promote: Keep explicit boundary clauses after tracer and neuronal-comparison claims.
- promote: Use reader-question subsection order for Results instead of strict figure inventory.
- revise: Require optional compression check for genotype-heavy control paragraphs in Nature-style Results.
- revise: Ask writers to include sample size/statistical-test anchors only when they materially affect reader confidence.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified; it noted the minor adult-sensory wording risk and qualitative-only neuronal comparison boundary.

**Discussion supervisor**: `pass`; score `4.60`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.7`; reviewer false-pass risk `low`.
Strengths:
- Opens with a real synthesis: local/disrupted preparations are reframed into intact-brain tracer-defined astrocyte network architecture.
- Recalls the central method anchors: HA-positive infected cells, HA-negative streptavidin-positive in-network cells, unlabeled gaps, low biotin background and in vivo workflow.
- Includes key validation numbers: 10 percent infection to about 80 percent in-network labeling and 20.73 Angstrom proximity anchor.
Weaknesses / watch-points:
- Second paragraph is slightly validation-heavy for a Discussion and could be more selective for Nature cadence.
- Figure roles are understood indirectly, but no explicit figure hierarchy is articulated in the discussion prose.
- The culture anchor says 80 percent rather than over 80 percent, a small precision loss from the recoverable evidence.
Grounding concerns:
- unsupported: claim: The phrase 'communication routes' and 'communication architecture' could be read functionally, although later sentences correctly bound the maps to endpoint membership and future cargo or physiology tests.; severity: minor; evidence_boundary: Allowed results support tracer-defined regional enrichment, not direction, cargo, conductance or rate.
Skill lessons:
- promote: Keep Discussion openings centered on conceptual conversion rather than figure recap.
- promote: Require limitation sentences next to endpoint-map claims to prevent physiological overreach.
- revise: Ask writers to preserve comparator modifiers such as 'over 80 percent' when numeric anchors are central.
- revise: Encourage one fewer validation detail in Discussion when the same evidence is already prominent in Results.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified; it did not materially miss blocking grounding issues.
- Reviewer was somewhat generous on discussion compactness and Nature sentence cadence.


## Case: `s41586-026-10423-9` (physical sciences)

Run: `rollout_nature_writing_fix7_physical_api_20260605`
Supervisor eval: `rollout_nature_writing_fix7_physical_api_20260605_supervisor_final`

| source | Abstract+Intro | Results | Discussion |
|---|---:|---:|---:|
| Supervisor V2.1 | 4.50 | 4.60 | 4.60 |

### Section Reviewer Final Opinions

**Abstract+Intro reviewer**: `pass`; score `4.500`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.6, section_function 4.5, anchor_recall 5.0, claim_boundary 4.7, writing_quality 4.4.
Final concerns:
- text_level_issues: The Introduction's final paragraph is long and information-dense; acceptable for this draft, but further expansion would risk Results-preview feel.
- text_level_issues: The abstract closing phrase 'bounded route' is safe but slightly less idiomatic than the rest of the prose.
- unrecoverable_detail_risk: No blocking risk found; exact values are tied to planned/context anchors. The 320 nm teleportation distance is supported by the story contract and plan even though not prominent in the visible Results excerpt.
Representative anchor recall:
- six_dot_device_mobile_Q2_Q5_Q1_Q6_ancillas: recalled in abstract and final intro paragraph
- phase_shifted_conveyor_potentials_towards_B3: recalled in abstract and intro
- EDSR_shifts_and_line_splitting: recalled in abstract and intro

**Results reviewer**: `pass`; score `4.667`; accepted `True`.
Scores: evidence_fidelity 4.7, story_quality 4.6, section_function 4.7, anchor_recall 4.8, claim_boundary 4.7, writing_quality 4.5.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- fig1_device_control: recalled: conceptual architecture/device, Q2/Q5 Rabi control, 11.657 GHz, 11.999 GHz, and 11.90 GHz EDSR split are included without overclaiming a scaled processor.
- fig2_exchange_tuning: recalled: DCPhase-derived J versus conveyor cycles/nominal displacement and B3 pulsed offset is central.
- fig2_boundaries: recalled: T2* variation and merged-potential exchange saturation are tied to the usable-regime boundary.

**Discussion reviewer**: `pass`; score `4.683`; accepted `True`.
Scores: evidence_fidelity 4.7, story_quality 4.6, section_function 4.7, anchor_recall 4.8, claim_boundary 4.8, writing_quality 4.5.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- Q2_Q5_conveyor_and_Q1_Q6_ancillas: Present: 'Q2 and Q5 were carried in separate travelling conveyor minima... while Q1 and Q6 provided stationary parity-readout ancillas.'
- EDSR_shift_and_split: Present: 'EDSR spectra shift with the number of conveyor cycles...' and 'the spectra split in a state-dependent manner'.
- J_tuning_90MHz: Present: '$J$ is tuned by conveyor displacement and by the pulsed offset on B3... reaching up to 90 MHz'.

### Cross-Section Reviewer Final Opinion

Status `pass`; score `4.550`; accepted `True`.
- central thesis: 4.6 - consistent
- evidence support: 4.6 - strong
- discussion boundary: 4.5 - bounded
- claim boundary: 4.7 - consistent
Final targeted watch-points:
- If space permits, compress the repeated Q2/Q5/Q1/Q6 device-role inventory outside Results.
- Avoid adding further repeats of the quantitative capstone chain: 90 MHz, 0.9 cycles/33 MHz, 58 ns/98.86%, 320 nm/86.7%.
- Keep the architecture and scale-up language framed as motivation or prospective boundary, not as a demonstrated processor-scale routing result.
- Preserve the conditional and post-selected qualifier whenever teleportation is summarized.
- Maintain the gate claim as trajectory-specific rather than applicable to arbitrary shuttling conditions.

### Independent Supervisor V2.1 Final Opinion

**Abstract+Intro supervisor**: `pass`; score `4.50`; evidence `4.7`; story `4.5`; flow `4.3`; claim calibration `4.7`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: conveyor-mode motion becomes the entangling resource through transport-activated exchange.
- All central numeric anchors checked against context are preserved with correct direction and qualifiers.
- Causal claims are calibrated to characterization, benchmarking and bounded architectural implication.
Weaknesses / watch-points:
- Introduction's final paragraph is long and anchor-heavy for Nature cadence.
- Figure roles are implied through observables rather than explicitly separated into a hierarchy of evidence.
- Some opening architecture-pressure language remains broad, though supported by discussion and literature context.
Skill lessons:
- promote: Keep separate abstract disclosure and introduction gap-ladder scoring.
- promote: Require explicit qualifiers for conditional post-selected protocols and trajectory-specific gate claims.
- revise: Ask writers to limit final introduction previews to the minimum quantitative payoff anchors.
- revise: Add a check for over-dense final paragraphs even when all anchors are grounded.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified, but it underweighted the medium results-preview risk in the final introduction paragraph.

**Results supervisor**: `pass`; score `4.60`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.8`; reviewer false-pass risk `low`.
Strengths:
- Clear chain from mobile-spin control to exchange tuning, CZ benchmarking and teleportation capstone.
- Central numeric anchors are present: 11.657 GHz, 11.999 GHz, 11.90 GHz, 90 MHz, 120 nm per spin, 240 nm total, 33 MHz, 58 ns, 98.86 ± 0.29%, 320 nm and 86.7 ± 0.9%.
- Claims are well bounded to the demonstrated semiconductor linear-array implementation and conditional post-selected channel.
Weaknesses / watch-points:
- Some sentences are dense and carry multiple evidentiary jobs, especially in the device-control and CZ paragraphs.
- The Fig. 2 merged-potential discussion could better preserve the caption's physical interpretation rather than only stating saturation.
- The final teleportation paragraph is slightly compressed relative to the complexity of Bell measurement, verification and process tomography.
Grounding concerns:
- missing: Fig. 2e caption links the merged elongated potential to strong Coulomb interaction and possible Wigner-molecule formation; the draft keeps the saturation boundary but omits this mechanistic qualifier.
- missing: Fig. 4a identifies the teleportation circuit stages and composite U gate; the draft captures the stages but not the U-gate detail, which is secondary for the Results narrative.
Skill lessons:
- promote: Keep Results organized by reader questions rather than figure order when the evidence supports a mechanistic chain.
- promote: Preserve numeric payoff anchors while bounding claims to the demonstrated device and protocol.
- revise: Ask writers to retain one concise physical qualifier when a figure caption explains why a boundary or saturation occurs.
- revise: Encourage splitting sentences that combine device geometry, measurement mode and inference in one line.
Supervisor comment on reviewer:
- Reviewer pass is reasonable; it did not flag the secondary Fig. 2e qualifier omission but no blocking issue remains.

**Discussion supervisor**: `pass`; score `4.60`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.8`; reviewer false-pass risk `low`.
Strengths:
- Opens with a specific synthesis: motion is used as an entangling resource, not merely as transport.
- Recalls central anchors: Q2/Q5 conveyor minima, Q1/Q6 ancillas, EDSR shifts and splitting, 90 MHz exchange, 0.9 cycles and 33 MHz, 58 ns CZ at 98.86 plus-minus 0.29%, and 320 nm teleportation at 86.7 plus-minus 0.9%.
- Places limitations next to claims: exchange saturation, exchange-coherence compromise, conditional post-selection, and lack of processor-scale routing are clearly bounded.
Weaknesses / watch-points:
- Some first-sentence paragraph transitions use generic signposting rather than sharper consequence or contrast.
- The discussion is highly competent but slightly compressed into evidence-chain exposition; it could carry a more memorable field-level closing implication.
- No explicit figure references are used, which is acceptable in Discussion but slightly limits figure-role traceability for a benchmark evaluator.
Skill lessons:
- promote: For Discussion sections, require a reverse outline with claim, boundary, and implication roles before drafting.
- promote: Preserve quantitative anchors only when each advances a synthesis point rather than a figure recap.
- revise: Encourage sharper paragraph transitions that express consequence or limitation, not only topic progression.
- revise: Ask writers to avoid repeating the same boundary anchor unless the second use adds a distinct implication.
Supervisor comment on reviewer:
- Reviewer pass is mostly justified; it did not overstate the small cadence and consolidation issues.


## Case: `s41586-025-09922-y` (scientific community/society)

Run: `rollout_nature_writing_fix7_society_api_20260605`
Supervisor eval: `rollout_nature_writing_fix7_society_api_20260605_supervisor_final`

| source | Abstract+Intro | Results | Discussion |
|---|---:|---:|---:|
| Supervisor V2.1 | 4.50 | 4.60 | 4.60 |

### Section Reviewer Final Opinions

**Abstract+Intro reviewer**: `pass`; score `4.833`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.7, section_function 4.8, anchor_recall 5.0, claim_boundary 4.7, writing_quality 4.6.
Final concerns:
- text_level_issues: Abstract is long but acceptable for Nature-style density; no required cut because specificity and flow remain strong.
- text_level_issues: Introduction could add citations in final production, but no citation-specific claim is unsafe in the provided context.
Representative anchor recall:
- 41,298,433 OpenAlex papers, 1980-2025, six natural-science disciplines: recalled in abstract and introduction
- 310,957 AI-augmented papers, 0.75% of selected papers: recalled in abstract and introduction
- BERT ensemble validation F1 0.875 and Fleiss kappa 0.964: recalled in abstract and introduction

**Results reviewer**: `pass`; score `4.733`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.7, section_function 4.6, anchor_recall 4.9, claim_boundary 4.8, writing_quality 4.6.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- classifier_validation: recalled with corpus scope, two-stage BERT, kappa >= 0.93, F1 >= 0.85 and abstract F1 = 0.875
- scale_scope: recalled with 41,298,433 papers, 1980-2025, 5,377,346 researchers, six natural-science disciplines and CS/math exclusion
- adoption_trajectory: recalled across ML, DL and recent generative-AI eras with log-trend boundary

**Discussion reviewer**: `pass`; score `4.733`; accepted `True`.
Scores: evidence_fidelity 4.8, story_quality 4.7, section_function 4.8, anchor_recall 4.8, claim_boundary 4.7, writing_quality 4.6.
Final concerns: no blocking issue; no required revision.
Representative anchor recall:
- 41,298,433 papers, 1980-2025, six disciplines: Recalled in paragraph 1.
- BERT validation and F1-score 0.875: Recalled in paragraph 1; expert agreement noted.
- 310,957 AI-augmented papers and 0.75% corpus: Recalled in paragraph 1.

### Cross-Section Reviewer Final Opinion

Status `pass`; score `4.650`; accepted `True`.
- central thesis: n/a - strong
- evidence support: n/a - strong
- discussion boundary: n/a - pass_with_minor_watchpoints
- claim boundary: n/a - strong
Final targeted watch-points:
- Keep the final Discussion recommendations explicitly framed as implications rather than tested policy results.
- Preserve the observational-association language in Abstract, Results and Discussion; do not upgrade to causal effects.
- Retain the selected-natural-sciences and title-abstract-detection boundaries wherever corpus-level claims are summarized.
- If shortening, compress repeated corpus and classifier anchors in Introduction/Discussion before removing Results anchors.
- Keep the generative-AI statement bounded to an initial post-2023 adoption trend and future question.

### Independent Supervisor V2.1 Final Opinion

**Abstract+Intro supervisor**: `pass`; score `4.50`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.5`; reviewer false-pass risk `low`.
Strengths:
- Central thesis is specific: individual visibility and career advantages coincide with narrower, more concentrated collective knowledge production.
- High-value numeric anchors are prioritized rather than dumped, especially in the abstract.
- The introduction separates measurement gap, study entry and contribution framing with clear paragraph roles.
Weaknesses / watch-points:
- No citations appear in the introduction, weakening Nature-style field positioning and intellectual-debt signalling.
- Figure roles are only implicit; acceptable for abstract_intro but less strong than prose that maps the main evidentiary modules more deliberately.
- A few sentences are long and densely packed, especially where multiple validation and outcome anchors are compressed.
Grounding concerns:
- missing: Visible literature citations are missing from the Introduction despite broad claims about AI use in image classification, materials modelling, biomedical analysis and scientific-record mining.
Skill lessons:
- promote: Keep the problem-scale-validation-findings-payoff abstract pattern for quantitative observational papers.
- promote: Maintain explicit observational and proxy boundaries in both abstract and introduction.
- revise: Require visible citations for broad field-progress and prior-work claims in Nature-style introductions.
- revise: Ask writers to include a compact evidence-module map when figure roles matter, without turning the introduction into a Results preview.
Supervisor comment on reviewer:
- Reviewer correctly passed the section on evidence fidelity and story structure.
- Reviewer underweighted the absence of citations for background and field-positioning claims.

**Results supervisor**: `pass`; score `4.60`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.8`; reviewer false-pass risk `low`.
Strengths:
- Central paradox is clear: individual visibility and career advantages contrast with collective contraction and weaker mutual engagement.
- Core numeric anchors are recalled accurately, including corpus size, AI-paper count, 0.75%, F1 0.875, 98.70%, 4.84x, 3.02x, 1.37 years, 4.63%, 22%, and Gini values.
- Important design boundaries are explicit: selected natural sciences, exclusion of AI-method fields, title-abstract classifier, observational association, and preliminary post-2023 generative-AI window.
Weaknesses / watch-points:
- Some sentences carry many values and caveats, giving the section a slightly report-like cadence compared with the most polished Nature Results prose.
- The first subsection compresses classifier validation, adoption trends and adoption correlates; the last of these is less grounded locally than the main figure chain.
- Embedding-space interpretation is well bounded but could more directly name the text-embedding model to aid recoverability.
Grounding concerns:
- missing: SPECTER is not named in the Results text when describing the 768-dimensional embedding proxy, although the embedding method is otherwise described.
- missing: The adoption-correlate result mentions data availability over topicality, prior impact or funding priority without giving the associated panel or quantitative support in the local prose.
Skill lessons:
- promote: Require Results drafts to state study-design boundaries next to high-impact association claims.
- promote: Use figure subsections as reader questions that build toward the central paradox.
- revise: Ask writers to name central measurement models or proxies at first Results use when recoverability depends on them.
- revise: Require local figure or quantitative support for secondary claims inserted outside the main figure chain.
Supervisor comment on reviewer:
- Reviewer pass was largely justified and caught the main anchor, boundary and figure-role requirements.
- Reviewer did not flag minor local recoverability issues around the embedding model name and adoption-correlate support.

**Discussion supervisor**: `pass`; score `4.60`; evidence `4.7`; story `4.6`; flow `4.5`; claim calibration `4.7`; reviewer false-pass risk `low`.
Strengths:
- Clear synthesis route: population-scale measurement, individual rewards, collective narrowing, downstream engagement, limitations, implications.
- High recall of central anchors: corpus size, AI-paper count, F1 validation, citation/productivity/career effects, 4.63% narrowing, 22% engagement drop and Gini contrast.
- Limitations are placed near the claims they qualify, especially observational selection, last-authorship proxy, title/abstract classification and generative-AI recency.
Weaknesses / watch-points:
- Figure-role understanding is implicit rather than explicit; the section explains evidentiary roles but does not directly remind readers which figure families establish them.
- Some sentences are dense with multiple numeric anchors, giving a slightly report-like cadence rather than fully polished main-journal compression.
- The policy/evaluation recommendations are reasonable but broad, and could be more tightly tied to the measured constructs of extent, engagement and concentration.
Grounding concerns:
- unsupported: Minor calibration watch: the phrase 'may reshape the allocation of attention across scientific questions' is supported as an implication, but should remain conditional rather than policy-level conclusion.
- unsupported: Minor mechanistic watch: data-rich established areas being easier to exploit is grounded in adoption-correlate analyses, but is still interpretive rather than directly causal.
Skill lessons:
- promote: Use a reverse-outline discussion pattern that synthesizes findings before limitations and implications.
- promote: Keep numerical anchors when they define the central paradox, but attach boundaries to causal and proxy-sensitive claims.
- revise: Ask writers to distinguish mechanistic interpretations from directly tested causal mechanisms in the Discussion.
- revise: Encourage final implication paragraphs to reuse the paper's own measured constructs rather than broad governance language alone.
Supervisor comment on reviewer:
- Reviewer pass is broadly justified; it slightly underemphasized the remaining risk that interpretive mechanism language could be read causally.


## Interpretation

- 当前最新版已经不是只靠 writer 生成；每个 section 有独立 reviewer，全文还有 cross-section evidence ledger 和 cross-section reviewer，最后再由独立 Supervisor V2.1 评分。
- 5 篇 holdout 的主要剩余问题不是硬性失败，而是 Nature-style cadence、个别句子过密、少数解释性标签略接近 evidence boundary。
- Reviewer 的意见整体有可读性：section reviewer 能看到 anchor recall 和 direction/comparator 问题；cross-section reviewer 能发现 section 之间的 promise-support 是否一致；Supervisor 能进一步指出 reviewer 是否放过了句子节奏、claim calibration 或解释性标签问题。
- 下一步如果继续提升，不建议继续堆长 prompt；更值得做的是把 Supervisor 的 recurring watch-points 转成更短、更可执行的 reviewer checklist，尤其是句子密度、解释性标签、Results/Discussion 边界。
