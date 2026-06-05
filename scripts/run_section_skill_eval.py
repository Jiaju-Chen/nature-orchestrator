from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nature_orchestrator.agents import api_config_from_env, run_agent  # noqa: E402

TASKS_ROOT = ROOT.parent / "nature-bench" / "data" / "downloads"
DEFAULT_ENV = ROOT.parent / "nature-orchestrator" / ".env"
HOLDOUT_SLUGS = [
    "s41586-025-09922-y",
    "s41586-026-10497-5",
    "s41586-026-10426-6",
    "s41586-026-10414-w",
    "s41586-026-10423-9",
]
ABSTRACT_INTRO_SKILLS = [
    ("yuan_nature", "yuan_nature_writing_abstract_intro"),
    ("pre", "v1_abstract_intro_distill_before_manual_audit"),
    ("v1", "v1_abstract_intro_distill"),
    ("v2", "v2_deep_evidence_abstract_intro"),
    ("v2_1", "v2_1_story_refined_abstract_intro"),
    ("v2_2", "v2_2_payoff_refined_abstract_intro"),
    ("v2_3", "v2_3_story_tournament_abstract_intro"),
]
RESULTS_SKILLS = [
    ("yuan_nature", "yuan_nature_writing_results"),
    ("pre", "v1_results_distill_before_manual_audit"),
    ("v1", "v1_results_distill"),
    ("v2", "v2_deep_evidence_results"),
    ("v2_1", "v2_1_story_refined_results"),
    ("v2_2", "v2_2_payoff_refined_results"),
    ("v2_3", "v2_3_story_tournament_results"),
]
DISCUSSION_SKILLS = [
    ("yuan_nature", "yuan_nature_writing_discussion"),
    ("v2", "v2_deep_evidence_discussion"),
    ("v2_3", "v2_3_story_tournament_discussion"),
]
BACKENDS = ["api", "codex"]
SUPERVISOR_V2_BACKENDS = ["mock", "api", "codex"]
SUPERVISOR_SKILL_ROOT = ROOT / "skills" / "scientific_writing_supervisor"
SUPERVISOR_RUBRIC_PATH = SUPERVISOR_SKILL_ROOT / "rubrics" / "supervisor_v2.yaml"
SUPERVISOR_V21_RUBRIC_PATH = SUPERVISOR_SKILL_ROOT / "rubrics" / "supervisor_v2_1.yaml"
DEFAULT_VENUE_PROFILE_PATH = SUPERVISOR_SKILL_ROOT / "venue_profiles" / "nature_research_article.yaml"
SUPERVISOR_V2_BASE_SCORE_KEYS = [
    "evidence_fidelity",
    "story_quality",
    "evidence_to_writing_grounding",
    "figure_role_understanding",
    "must_mention_anchor_recall",
    "writing_flow",
    "sentence_tightness",
    "paragraph_role_clarity",
    "venue_fit",
    "evidence_selectivity",
    "citation_safety",
    "claim_calibration",
    "reviewer_diagnosis",
]
SUPERVISOR_V21_EXTRA_SCORE_KEYS = [
    "paragraph_transition_logic",
    "nature_sentence_cadence",
    "citation_and_context_positioning",
    "anchor_prioritization",
    "section_role_integrity",
]
SUPERVISOR_V2_SCORE_KEYS = SUPERVISOR_V2_BASE_SCORE_KEYS + SUPERVISOR_V21_EXTRA_SCORE_KEYS
SUPERVISOR_V2_COMPONENT_KEYS = ["abstract_component", "introduction_component"]


@dataclass(frozen=True)
class EvalJob:
    section: str
    skill_label: str
    skill_version: str
    backend: str
    slug: str
    run_id: str

    @property
    def key(self) -> str:
        return f"{self.section}__{self.skill_label}__{self.backend}__{self.slug}"


def read_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except yaml.YAMLError:
        return {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def abstract_intro_parts(text: str) -> tuple[str, str, list[str]]:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text or "", flags=re.S | re.I)
    abstract = match.group(1).strip() if match else ""
    intro = text[match.end() :].strip() if match else text
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", intro or "") if item.strip() and not item.strip().startswith("\\")]
    return abstract, intro, paragraphs


def score_to_float(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("score")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def clamp_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(1.0, min(5.0, float(value))), 3)


def run_dir_from_record(record: dict[str, Any]) -> Path | None:
    status_path = Path(record.get("status_path") or "")
    if status_path.exists():
        return status_path.parent
    return None


def final_file_for_section(run_dir: Path, section: str) -> Path:
    if section == "abstract_intro":
        return run_dir / "final" / "abstract_intro.tex"
    if section == "results":
        return run_dir / "final" / "results.tex"
    if section == "discussion":
        return run_dir / "final" / "discussion.tex"
    return run_dir / "final" / f"{section}.tex"


def relative_existing_files(run_dir: Path, patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        matches = sorted(run_dir.glob(pattern))
        if not matches:
            candidate = run_dir / pattern
            matches = [candidate] if candidate.exists() else []
        for path in matches:
            if path.is_file():
                rel = str(path.relative_to(run_dir))
                if rel not in files:
                    files.append(rel)
    return files


def supervisor_v2_allowed_files(run_dir: Path, section: str) -> list[str]:
    section_final = {
        "abstract_intro": "final/abstract_intro.tex",
        "results": "final/results.tex",
        "discussion": "final/discussion.tex",
    }.get(section, f"final/{section}.tex")
    patterns = [
        "context_pack/context.md",
        "context_pack/context.yaml",
        "context_pack/evidence_manifest.yaml",
        section_final,
        "story/evidence_to_story_plan.yaml",
        "story/story_blueprint.yaml",
        "reviews/*.yaml",
        "audits/*.yaml",
        "supervision/*.yaml",
        "supervision/oracle/*.yaml",
        "oracle_audit.yaml",
        "provenance.yaml",
        "run_manifest.yaml",
        "prompt_pack/task_contract.yaml",
        "skill/manifest.yaml",
        "skill/rubrics/*.yaml",
    ]
    return relative_existing_files(run_dir, patterns)


def supervisor_report_dir(supervisor_version: str) -> str:
    return "supervision_v2_1" if supervisor_version == "v2_1" else "supervision_v2"


def supervisor_schema_version(supervisor_version: str) -> str:
    return "nature_orchestrator.supervisor_report.v2_1" if supervisor_version == "v2_1" else "nature_orchestrator.supervisor_report.v2"


def supervisor_score_keys(supervisor_version: str) -> list[str]:
    return SUPERVISOR_V2_SCORE_KEYS if supervisor_version == "v2_1" else SUPERVISOR_V2_BASE_SCORE_KEYS


def load_supervisor_v2_assets(supervisor_version: str = "v2") -> dict[str, str]:
    rubric_path = SUPERVISOR_V21_RUBRIC_PATH if supervisor_version == "v2_1" else SUPERVISOR_RUBRIC_PATH
    return {
        "skill": read_text(SUPERVISOR_SKILL_ROOT / "SKILL.md"),
        "rubric": read_text(rubric_path),
        "venue_profile": read_text(DEFAULT_VENUE_PROFILE_PATH),
    }


def build_supervisor_v2_prompt(
    record: dict[str, Any],
    run_dir: Path,
    allowed_files: list[str],
    supervisor_version: str = "v2",
) -> str:
    assets = load_supervisor_v2_assets(supervisor_version)
    section = str(record.get("section") or "")
    final_rel = {
        "abstract_intro": "final/abstract_intro.tex",
        "results": "final/results.tex",
        "discussion": "final/discussion.tex",
    }.get(section, f"final/{section}.tex")
    report_dir = supervisor_report_dir(supervisor_version)
    schema_version = supervisor_schema_version(supervisor_version)
    score_lines = "\n".join(f"  {key}: 1-5" for key in supervisor_score_keys(supervisor_version))
    title = "Supervisor V2.1" if supervisor_version == "v2_1" else "Supervisor V2"
    return f"""# Supervisor V2 Independent Evaluation

You are the independent Scientific Writing {title}.

Evaluate one generated manuscript section. This is post-generation benchmark
evaluation, not writer/reviewer self-QC. Reviewer pass/fail is only diagnostic.
Use the allowed evidence/context files and optional benchmark oracle artifacts
only for evaluation. Do not rewrite the section.

Run metadata:
- section: {section}
- slug: {record.get("slug", "")}
- skill_label: {record.get("skill_label", "")}
- skill_version: {record.get("skill_version", "")}
- agent_backend_that_generated_text: {record.get("backend", "")}
- venue_profile: nature_research_article
- generated_text_file: {final_rel}

Allowed files to inspect:
{yaml.safe_dump({"allowed_files": allowed_files}, sort_keys=False, allow_unicode=True)}

Supervisor skill:
```markdown
{assets["skill"]}
```

Supervisor rubric:
```yaml
{assets["rubric"]}
```

Venue profile:
```yaml
{assets["venue_profile"]}
```

Required output file:
- `{report_dir}/supervisor_report.yaml`

For `section: abstract_intro`, score the abstract and Introduction separately in
addition to the combined `scores` and `overall` fields. The combined score is
still required for backward compatibility, but the component scores are used to
diagnose whether failures come from abstract disclosure or Introduction framing.

Write strict YAML with this shape:

```yaml
schema_version: {schema_version}
section: {section}
slug: {record.get("slug", "")}
venue_profile: nature_research_article
skill_label: {record.get("skill_label", "")}
skill_version: {record.get("skill_version", "")}
generated_backend: {record.get("backend", "")}
scores:
{score_lines}
overall:
  score: 1-5
  verdict: pass | needs_revision | fail
abstract_component:
  score: 1-5
  evidence_disclosure: 1-5
  contribution_specificity: 1-5
  claim_calibration: 1-5
  writing_flow: 1-5
  missing_recoverable_anchors: []
  unsupported_or_unrecoverable_claims: []
  diagnosis: []
introduction_component:
  score: 1-5
  gap_ladder: 1-5
  article_specific_bottleneck: 1-5
  contribution_framing: 1-5
  paragraph_flow: 1-5
  results_preview_risk: low | medium | high
  missing_recoverable_anchors: []
  unsupported_or_unrecoverable_claims: []
  diagnosis: []
blocking_failures: []
missing_recoverable_anchors: []
unsupported_or_unrecoverable_claims: []
writing_diagnosis:
  strengths: []
  weaknesses: []
  flow_notes: []
  venue_fit_notes: []
failure_attribution:
  planner: []
  writer: []
  reviewer: []
  refiner: []
  context_limitation: []
prompt_or_skill_lessons:
  promote: []
  revise: []
  avoid: []
reviewer_false_pass_risk: low | medium | high
```

Scoring policy:
- Use integer or one-decimal numeric scores only.
- `overall.score` should be the independent writing-quality score, not a
  reviewer score. Weight evidence fidelity, evidence-to-writing grounding,
  story quality, must-mention recall, claim calibration, and citation safety
  most heavily.
- Penalize invented details, missing recoverable central anchors, weak figure
  role understanding, generic prose, poor paragraph logic, unsupported citations,
  and one-eye-subjournal writing.
- In V2.1, explicitly separate paragraph transition logic, sentence cadence,
  citation/context positioning, anchor prioritization, and section-role integrity
  from the broader flow and venue-fit scores.
- If the reviewer passed despite unresolved grounding or logic failures, lower
  `reviewer_diagnosis` and set `reviewer_false_pass_risk`.
- Include concise evidence-grounded reasons. Do not include long copyrighted
  passages from oracle text.
"""


def deterministic_supervisor_v2_report(record: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    section = str(record.get("section") or "")
    text = read_text(final_file_for_section(run_dir, section))
    context = read_text(run_dir / "context_pack" / "context.md")
    review_status = str(record.get("review_status") or record.get("review_status_status") or record.get("review_status") or "")
    gate_failures = []
    for audit in sorted((run_dir / "audits").glob("*.yaml")):
        data = read_yaml(audit)
        if str(data.get("status", "")).lower() in {"fail", "failed", "gate_failed"}:
            gate_failures.append(audit.name)
    has_text = bool(text.strip())
    mentions_figure = bool(re.search(r"\b(?:Fig\.?|Figure)s?\b", text))
    context_overlap = bool(set(re.findall(r"\b[A-Za-z][A-Za-z-]{4,}\b", text.lower())) & set(re.findall(r"\b[A-Za-z][A-Za-z-]{4,}\b", context.lower())))
    base = 3.0
    if not has_text:
        base = 1.0
    elif gate_failures:
        base = 2.5
    elif context_overlap:
        base = 3.5
    scores = {
        "evidence_fidelity": clamp_score(base + (0.3 if context_overlap else -0.5)),
        "story_quality": clamp_score(base),
        "evidence_to_writing_grounding": clamp_score(base + (0.2 if context_overlap else -0.7)),
        "figure_role_understanding": clamp_score(base + (0.2 if mentions_figure else -0.4)),
        "must_mention_anchor_recall": clamp_score(base),
        "writing_flow": clamp_score(base + 0.2),
        "sentence_tightness": clamp_score(base),
        "paragraph_role_clarity": clamp_score(base),
        "venue_fit": clamp_score(base - 0.1),
        "evidence_selectivity": clamp_score(base),
        "citation_safety": clamp_score(base + 0.1),
        "claim_calibration": clamp_score(base),
        "reviewer_diagnosis": clamp_score(2.5 if gate_failures and review_status == "pass" else 3.5),
    }
    numeric_scores = [score for score in scores.values() if score is not None]
    overall = round(sum(numeric_scores) / len(numeric_scores), 3) if numeric_scores else 1.0
    verdict = "pass" if overall >= 4 else "needs_revision" if overall >= 3 else "fail"
    report = {
        "schema_version": "nature_orchestrator.supervisor_report.v2",
        "section": section,
        "slug": record.get("slug"),
        "venue_profile": "nature_research_article",
        "skill_label": record.get("skill_label"),
        "skill_version": record.get("skill_version"),
        "generated_backend": record.get("backend"),
        "scores": scores,
        "overall": {"score": overall, "verdict": verdict},
        "blocking_failures": gate_failures,
        "missing_recoverable_anchors": [],
        "unsupported_or_unrecoverable_claims": [],
        "writing_diagnosis": {
            "strengths": ["deterministic mock report for runner verification"] if has_text else [],
            "weaknesses": ["missing generated text"] if not has_text else [],
            "flow_notes": [],
            "venue_fit_notes": [],
        },
        "failure_attribution": {
            "planner": [],
            "writer": ["final text missing"] if not has_text else [],
            "reviewer": ["reviewer passed despite failed gates"] if gate_failures and review_status == "pass" else [],
            "refiner": [],
            "context_limitation": [],
        },
        "prompt_or_skill_lessons": {"promote": [], "revise": [], "avoid": []},
        "reviewer_false_pass_risk": "high" if gate_failures and review_status == "pass" else "low",
    }
    if section == "abstract_intro":
        report["abstract_component"] = {
            "score": clamp_score(scores["evidence_fidelity"]),
            "evidence_disclosure": clamp_score(scores["evidence_to_writing_grounding"]),
            "contribution_specificity": clamp_score(scores["story_quality"]),
            "claim_calibration": clamp_score(scores["claim_calibration"]),
            "writing_flow": clamp_score(scores["writing_flow"]),
            "missing_recoverable_anchors": [],
            "unsupported_or_unrecoverable_claims": [],
            "diagnosis": [],
        }
        report["introduction_component"] = {
            "score": clamp_score(scores["story_quality"]),
            "gap_ladder": clamp_score(scores["story_quality"]),
            "article_specific_bottleneck": clamp_score(scores["must_mention_anchor_recall"]),
            "contribution_framing": clamp_score(scores["venue_fit"]),
            "paragraph_flow": clamp_score(scores["paragraph_role_clarity"]),
            "results_preview_risk": "low",
            "missing_recoverable_anchors": [],
            "unsupported_or_unrecoverable_claims": [],
            "diagnosis": [],
        }
    return report


def normalize_supervisor_v2_report(report: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        report = {}
    report.setdefault("schema_version", "nature_orchestrator.supervisor_report.v2")
    report.setdefault("section", record.get("section"))
    report.setdefault("slug", record.get("slug"))
    report.setdefault("venue_profile", "nature_research_article")
    report.setdefault("skill_label", record.get("skill_label"))
    report.setdefault("skill_version", record.get("skill_version"))
    report.setdefault("generated_backend", record.get("backend"))
    raw_scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    scores: dict[str, float] = {}
    for key in SUPERVISOR_V2_SCORE_KEYS:
        score = clamp_score(score_to_float(raw_scores.get(key)))
        if score is not None:
            scores[key] = score
    report["scores"] = scores
    overall = report.get("overall") if isinstance(report.get("overall"), dict) else {}
    overall_score = clamp_score(score_to_float(overall.get("score")))
    if overall_score is None and scores:
        overall_score = round(sum(scores.values()) / len(scores), 3)
    if overall_score is None:
        overall_score = 1.0
    verdict = str(overall.get("verdict") or "")
    if verdict not in {"pass", "needs_revision", "fail"}:
        verdict = "pass" if overall_score >= 4 else "needs_revision" if overall_score >= 3 else "fail"
    report["overall"] = {"score": overall_score, "verdict": verdict}
    if record.get("section") == "abstract_intro":
        for component_key in SUPERVISOR_V2_COMPONENT_KEYS:
            component = report.get(component_key) if isinstance(report.get(component_key), dict) else {}
            component_score = clamp_score(score_to_float(component.get("score")))
            if component_score is None:
                if component_key == "abstract_component":
                    candidates = [
                        score_to_float(component.get("evidence_disclosure")),
                        score_to_float(component.get("contribution_specificity")),
                        score_to_float(component.get("claim_calibration")),
                        score_to_float(component.get("writing_flow")),
                    ]
                else:
                    candidates = [
                        score_to_float(component.get("gap_ladder")),
                        score_to_float(component.get("article_specific_bottleneck")),
                        score_to_float(component.get("contribution_framing")),
                        score_to_float(component.get("paragraph_flow")),
                    ]
                numeric = [float(item) for item in candidates if item is not None]
                component_score = round(sum(numeric) / len(numeric), 3) if numeric else overall_score
            component["score"] = component_score
            for list_key in ("missing_recoverable_anchors", "unsupported_or_unrecoverable_claims", "diagnosis"):
                if not isinstance(component.get(list_key), list):
                    component[list_key] = []
            report[component_key] = component
    for key in ("blocking_failures", "missing_recoverable_anchors", "unsupported_or_unrecoverable_claims"):
        if not isinstance(report.get(key), list):
            report[key] = []
    if not isinstance(report.get("writing_diagnosis"), dict):
        report["writing_diagnosis"] = {}
    if not isinstance(report.get("failure_attribution"), dict):
        report["failure_attribution"] = {}
    for key in ("planner", "writer", "reviewer", "refiner", "context_limitation"):
        if not isinstance(report["failure_attribution"].get(key), list):
            report["failure_attribution"][key] = []
    if not isinstance(report.get("prompt_or_skill_lessons"), dict):
        report["prompt_or_skill_lessons"] = {"promote": [], "revise": [], "avoid": []}
    return report


def flatten_supervisor_v2_report(record: dict[str, Any], report: dict[str, Any], report_path: Path, result: Any | None = None) -> dict[str, Any]:
    updated = dict(record)
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    overall = report.get("overall") if isinstance(report.get("overall"), dict) else {}
    updated["supervisor_v2_status"] = "done"
    updated["supervisor_v2_report_path"] = str(report_path)
    updated["supervisor_v2_overall_score"] = score_to_float(overall.get("score"))
    updated["supervisor_v2_verdict"] = overall.get("verdict")
    updated["supervisor_v2_blocking_failure_count"] = len(report.get("blocking_failures") or [])
    updated["supervisor_v2_missing_anchor_count"] = len(report.get("missing_recoverable_anchors") or [])
    updated["supervisor_v2_unsupported_claim_count"] = len(report.get("unsupported_or_unrecoverable_claims") or [])
    updated["supervisor_v2_reviewer_false_pass_risk"] = report.get("reviewer_false_pass_risk")
    if result is not None:
        updated["supervisor_v2_backend"] = getattr(result, "backend", "")
        updated["supervisor_v2_elapsed_sec"] = getattr(result, "elapsed_sec", None)
        updated["supervisor_v2_returncode"] = getattr(result, "returncode", None)
    for key in SUPERVISOR_V2_SCORE_KEYS:
        value = score_to_float(scores.get(key))
        if value is not None:
            updated[f"supervisor_v2_{key}"] = value
    if record.get("section") == "abstract_intro":
        for component_key in SUPERVISOR_V2_COMPONENT_KEYS:
            component = report.get(component_key) if isinstance(report.get(component_key), dict) else {}
            value = score_to_float(component.get("score"))
            if value is not None:
                updated[f"supervisor_v2_{component_key}_score"] = value
    return updated


def run_supervisor_v2_for_record(
    record: dict[str, Any],
    backend: str = "api",
    timeout: int = 600,
    api_max_tokens: int = 16000,
    env: Path = DEFAULT_ENV,
    model: str | None = None,
    codex_binary: str = "codex",
    force: bool = False,
    supervisor_version: str = "v2",
) -> dict[str, Any]:
    run_dir = run_dir_from_record(record)
    if run_dir is None:
        updated = dict(record)
        updated["supervisor_v2_status"] = "missing_run_dir"
        return updated
    final_path = final_file_for_section(run_dir, str(record.get("section") or ""))
    if not final_path.exists():
        updated = dict(record)
        updated["supervisor_v2_status"] = "missing_final"
        return updated
    report_path = run_dir / supervisor_report_dir(supervisor_version) / "supervisor_report.yaml"
    if report_path.exists() and not force:
        report = normalize_supervisor_v2_report(read_yaml(report_path), record)
        write_yaml(report_path, report)
        return flatten_supervisor_v2_report(record, report, report_path)
    allowed_files = supervisor_v2_allowed_files(run_dir, str(record.get("section") or ""))
    prompt = build_supervisor_v2_prompt(record, run_dir, allowed_files, supervisor_version=supervisor_version)
    write_text(run_dir / supervisor_report_dir(supervisor_version) / "prompt.md", prompt)
    if backend == "mock":
        report = normalize_supervisor_v2_report(deterministic_supervisor_v2_report(record, run_dir), record)
        report["schema_version"] = supervisor_schema_version(supervisor_version)
        write_yaml(report_path, report)
        return flatten_supervisor_v2_report(record, report, report_path)
    if backend not in {"api", "codex"}:
        raise ValueError(f"Unsupported supervisor backend: {backend}")
    api_config = api_config_from_env(env, model, timeout, api_max_tokens) if backend == "api" else None
    result = run_agent(
        "supervisor_v2_1" if supervisor_version == "v2_1" else "supervisor_v2",
        run_dir,
        prompt,
        allowed_files,
        {"files": [f"{supervisor_report_dir(supervisor_version)}/supervisor_report.yaml"]},
        backend,
        timeout,
        codex_binary=codex_binary,
        api_config=api_config,
    )
    write_yaml(
        run_dir / "logs" / "supervisor_v2.agent_result.yaml",
        {
            "role": result.role,
            "backend": result.backend,
            "returncode": result.returncode,
            "status": result.status,
            "elapsed_sec": result.elapsed_sec,
            "files_written": result.files_written,
            "error": result.error,
        },
    )
    if result.returncode != 0 or not report_path.exists():
        updated = dict(record)
        updated["supervisor_v2_status"] = result.status if result.returncode != 0 else "missing_report"
        updated["supervisor_v2_backend"] = backend
        updated["supervisor_v2_elapsed_sec"] = result.elapsed_sec
        updated["supervisor_v2_returncode"] = result.returncode
        updated["supervisor_v2_error"] = result.error
        return updated
    report = normalize_supervisor_v2_report(read_yaml(report_path), record)
    write_yaml(report_path, report)
    return flatten_supervisor_v2_report(record, report, report_path, result=result)


def build_jobs(matrix_id: str) -> list[EvalJob]:
    jobs: list[EvalJob] = []
    for label, skill in ABSTRACT_INTRO_SKILLS:
        for backend in BACKENDS:
            for slug in HOLDOUT_SLUGS:
                jobs.append(EvalJob("abstract_intro", label, skill, backend, slug, f"{matrix_id}__ai__{label}__{backend}__{slug}"))
    for label, skill in RESULTS_SKILLS:
        for backend in BACKENDS:
            for slug in HOLDOUT_SLUGS:
                jobs.append(EvalJob("results", label, skill, backend, slug, f"{matrix_id}__results__{label}__{backend}__{slug}"))
    for label, skill in DISCUSSION_SKILLS:
        for backend in BACKENDS:
            for slug in HOLDOUT_SLUGS:
                jobs.append(EvalJob("discussion", label, skill, backend, slug, f"{matrix_id}__discussion__{label}__{backend}__{slug}"))
    return jobs


def command_for_job(job: EvalJob, max_refiner_rounds: int, api_timeout: int, api_max_tokens: int, codex_timeout: int) -> list[str]:
    if job.section == "abstract_intro":
        return [
            sys.executable,
            "scripts/run_abstract_intro_batch.py",
            "--tasks-root",
            str(TASKS_ROOT),
            "--out",
            "outputs/abstract_intro",
            "--run-id",
            job.run_id,
            "--skill-version",
            job.skill_version,
            "--only-slug",
            job.slug,
            "--image-mode",
            "benchmark_vlm",
            "--agent-backend",
            job.backend,
            "--max-refiner-rounds",
            str(max_refiner_rounds),
            "--oracle-supervisor",
            "--api-timeout",
            str(api_timeout),
            "--api-max-tokens",
            str(api_max_tokens),
            "--codex-timeout",
            str(codex_timeout),
            "--quiet-progress",
        ]
    if job.section == "results":
        return [
            sys.executable,
            "scripts/run_results_batch.py",
            "--tasks-root",
            str(TASKS_ROOT),
            "--out",
            "outputs/results",
            "--run-id",
            job.run_id,
            "--skill-version",
            job.skill_version,
            "--task-name",
            "results_figure_grounded",
            "--only-slug",
            job.slug,
            "--image-mode",
            "benchmark_vlm",
            "--agent-backend",
            job.backend,
            "--max-refiner-rounds",
            str(max_refiner_rounds),
            "--oracle-audit",
            "--api-timeout",
            str(api_timeout),
            "--api-max-tokens",
            str(api_max_tokens),
            "--codex-timeout",
            str(codex_timeout),
        ]
    return [
        sys.executable,
        "scripts/run_discussion_batch.py",
        "--tasks-root",
        str(TASKS_ROOT),
        "--out",
        "outputs/discussion",
        "--run-id",
        job.run_id,
        "--skill-version",
        job.skill_version,
        "--task-name",
        "discussion",
        "--only-slug",
        job.slug,
        "--image-mode",
        "benchmark_vlm",
        "--agent-backend",
        job.backend,
        "--max-refiner-rounds",
        str(max_refiner_rounds),
        "--oracle-audit",
        "--api-timeout",
        str(api_timeout),
        "--api-max-tokens",
        str(api_max_tokens),
        "--codex-timeout",
        str(codex_timeout),
    ]


def status_path_for(job: EvalJob) -> Path | None:
    output_root = {
        "abstract_intro": "outputs/abstract_intro",
        "results": "outputs/results",
        "discussion": "outputs/discussion",
    }.get(job.section, f"outputs/{job.section}")
    root = ROOT / output_root / job.run_id
    if not root.exists():
        return None
    matches = sorted(root.glob(f"*/{job.slug}/status.yaml"))
    if not matches:
        matches = sorted(root.glob(f"*/{job.slug}/results_figure_grounded/status.yaml"))
    if not matches:
        matches = sorted(root.glob(f"*/{job.slug}/discussion/status.yaml"))
    return matches[0] if matches else None


def run_job(job: EvalJob, eval_dir: Path, max_refiner_rounds: int, api_timeout: int, api_max_tokens: int, codex_timeout: int) -> dict[str, Any]:
    logs_dir = eval_dir / "job_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    existing = status_path_for(job)
    if existing:
        status = read_yaml(existing)
        if status.get("status"):
            return {"job": job.__dict__, "skipped": True, "returncode": 0, "status_path": str(existing), "task_status": status.get("status")}
    cmd = command_for_job(job, max_refiner_rounds, api_timeout, api_max_tokens, codex_timeout)
    start = time.time()
    completed = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = round(time.time() - start, 3)
    write_text(logs_dir / f"{job.key}.stdout.log", completed.stdout or "")
    write_text(logs_dir / f"{job.key}.stderr.log", completed.stderr or "")
    status_path = status_path_for(job)
    status = read_yaml(status_path) if status_path else {}
    return {
        "job": job.__dict__,
        "skipped": False,
        "returncode": completed.returncode,
        "elapsed_sec": elapsed,
        "status_path": str(status_path) if status_path else "",
        "task_status": status.get("status", "missing_status"),
    }


def collect_record(job: EvalJob, run_result: dict[str, Any]) -> dict[str, Any]:
    status_path = Path(run_result.get("status_path") or "")
    status = read_yaml(status_path) if status_path.exists() else {}
    run_dir = status_path.parent if status_path.exists() else Path()
    record: dict[str, Any] = {
        "section": job.section,
        "skill_label": job.skill_label,
        "skill_version": job.skill_version,
        "backend": job.backend,
        "slug": job.slug,
        "run_id": job.run_id,
        "returncode": run_result.get("returncode"),
        "task_status": status.get("status") or run_result.get("task_status"),
        "status_path": str(status_path) if status_path.exists() else "",
        "refiner_rounds_used": status.get("refiner_rounds_used", 0),
        "review_rounds": status.get("review_rounds", 0),
    }
    for key, value in status.items():
        if key.endswith("_elapsed_sec") or key in {"failed_gates"}:
            record[key] = value
    if job.section == "abstract_intro":
        text = read_text(run_dir / "final" / "abstract_intro.tex")
        abstract, _intro, paragraphs = abstract_intro_parts(text)
        record.update(
            {
                "word_count": word_count(text),
                "abstract_word_count": word_count(abstract),
                "intro_word_count": sum(word_count(item) for item in paragraphs),
                "intro_paragraph_count": len(paragraphs),
            }
        )
        style_gate = read_yaml(run_dir / "audits" / "nature_style_compression_gate.yaml")
        record["style_gate_status"] = style_gate.get("status")
        review = read_yaml(run_dir / "reviews" / "abstract_intro_review.yaml")
        for key in (
            "abstract_specificity_score",
            "intro_gap_ladder_score",
            "evidence_disclosure_score",
            "story_novelty_score",
            "claim_safety_score",
            "nature_style_score",
            "status",
        ):
            if key in review:
                record[f"review_{key}"] = review[key]
        supervisor = read_yaml(run_dir / "supervision" / "supervisor_report.yaml")
        if not supervisor:
            supervisor = read_yaml(run_dir / "oracle_supervisor.yaml")
        record["supervisor_status"] = supervisor.get("status") or supervisor.get("overall_status")
        for key in ("final_score", "oracle_fidelity", "evidence_fidelity", "story_quality", "must_mention_anchor_recall"):
            if key in supervisor:
                record[f"supervisor_{key}"] = supervisor[key]
    elif job.section == "results":
        text = read_text(run_dir / "final" / "results.tex")
        record["word_count"] = word_count(text)
        record["paragraph_count"] = len([item for item in re.split(r"\n\s*\n", text or "") if item.strip()])
        review = read_yaml(run_dir / "reviews" / "results_review.yaml")
        record["review_status"] = review.get("status")
        scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}
        for key, value in scores.items():
            record[f"review_score_{key}"] = value
        audit = read_yaml(run_dir / "oracle_audit.yaml")
        metrics = audit.get("metrics") if isinstance(audit.get("metrics"), dict) else {}
        quality = metrics.get("results_quality") if isinstance(metrics.get("results_quality"), dict) else {}
        for key, value in quality.items():
            if isinstance(value, (int, float, str, bool)) or value is None:
                record[f"oracle_{key}"] = value
    elif job.section == "discussion":
        text = read_text(run_dir / "final" / "discussion.tex")
        record["word_count"] = word_count(text)
        record["paragraph_count"] = len([item for item in re.split(r"\n\s*\n", text or "") if item.strip()])
        review = read_yaml(run_dir / "reviews" / "discussion_review.yaml")
        record["review_status"] = review.get("status")
        scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}
        for key, value in scores.items():
            record[f"review_score_{key}"] = value
        audit = read_yaml(run_dir / "oracle_audit.yaml")
        metrics = audit.get("metrics") if isinstance(audit.get("metrics"), dict) else {}
        quality = metrics.get("discussion_quality") if isinstance(metrics.get("discussion_quality"), dict) else {}
        for key, value in quality.items():
            if isinstance(value, (int, float, str, bool)) or value is None:
                record[f"oracle_{key}"] = value
    return record


def mean(values: list[float]) -> float | None:
    values = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 3) if values else None


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault((record["section"], record["skill_label"], record["backend"]), []).append(record)
    rows: list[dict[str, Any]] = []
    for (section, skill_label, backend), items in sorted(groups.items()):
        done = [item for item in items if item.get("task_status") == "done"]
        rows.append(
            {
                "section": section,
                "skill_label": skill_label,
                "backend": backend,
                "skill_version": items[0]["skill_version"],
                "total": len(items),
                "done": len(done),
                "failed": len(items) - len(done),
                "success_rate": round(len(done) / len(items), 3) if items else 0,
                "mean_word_count": mean([item.get("word_count") for item in done]),
                "mean_intro_paragraph_count": mean([item.get("intro_paragraph_count") for item in done]),
                "mean_refiner_rounds_used": mean([item.get("refiner_rounds_used") for item in items]),
                "mean_review_rounds": mean([item.get("review_rounds") for item in items]),
                "mean_planner_elapsed_sec": mean([item.get("planner_elapsed_sec") for item in items]),
                "mean_writer_elapsed_sec": mean([item.get("writer_elapsed_sec") for item in items]),
                "mean_reviewer_elapsed_sec": mean([item.get("reviewer_000_elapsed_sec") for item in items]),
                "fail_statuses": sorted({str(item.get("task_status")) for item in items if item.get("task_status") != "done"}),
            }
        )
    return rows


def summarize_supervisor_v2(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored_records = [record for record in records if record.get("supervisor_v2_status") == "done"]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in scored_records:
        groups.setdefault((record["section"], record["skill_label"], record["backend"]), []).append(record)
    rows: list[dict[str, Any]] = []
    for (section, skill_label, backend), items in sorted(groups.items()):
        row: dict[str, Any] = {
            "section": section,
            "skill_label": skill_label,
            "backend": backend,
            "skill_version": items[0]["skill_version"],
            "supervisor_v2_done": len(items),
            "mean_supervisor_v2_overall_score": mean([item.get("supervisor_v2_overall_score") for item in items]),
            "mean_supervisor_v2_blocking_failure_count": mean(
                [item.get("supervisor_v2_blocking_failure_count") for item in items]
            ),
            "mean_supervisor_v2_missing_anchor_count": mean([item.get("supervisor_v2_missing_anchor_count") for item in items]),
            "mean_supervisor_v2_unsupported_claim_count": mean(
                [item.get("supervisor_v2_unsupported_claim_count") for item in items]
            ),
            "verdicts": json.dumps(
                {verdict: len([item for item in items if item.get("supervisor_v2_verdict") == verdict]) for verdict in ["pass", "needs_revision", "fail"]},
                ensure_ascii=False,
            ),
        }
        if section == "abstract_intro":
            row["mean_supervisor_v2_abstract_component_score"] = mean(
                [item.get("supervisor_v2_abstract_component_score") for item in items]
            )
            row["mean_supervisor_v2_introduction_component_score"] = mean(
                [item.get("supervisor_v2_introduction_component_score") for item in items]
            )
        for key in SUPERVISOR_V2_SCORE_KEYS:
            row[f"mean_supervisor_v2_{key}"] = mean([item.get(f"supervisor_v2_{key}") for item in items])
        rows.append(row)
    return rows


def summarize_supervisor_v2_by_paper(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in sorted(
        [item for item in records if item.get("supervisor_v2_status") == "done"],
        key=lambda item: (str(item.get("slug")), str(item.get("section")), str(item.get("skill_label")), str(item.get("backend"))),
    ):
        rows.append(
            {
                "slug": record.get("slug"),
                "section": record.get("section"),
                "skill_label": record.get("skill_label"),
                "backend": record.get("backend"),
                "overall": record.get("supervisor_v2_overall_score"),
                "verdict": record.get("supervisor_v2_verdict"),
                "evidence_fidelity": record.get("supervisor_v2_evidence_fidelity"),
                "story_quality": record.get("supervisor_v2_story_quality"),
                "grounding": record.get("supervisor_v2_evidence_to_writing_grounding"),
                "must_anchor": record.get("supervisor_v2_must_mention_anchor_recall"),
                "writing_flow": record.get("supervisor_v2_writing_flow"),
                "venue_fit": record.get("supervisor_v2_venue_fit"),
                "claim_calibration": record.get("supervisor_v2_claim_calibration"),
                "abstract_component": record.get("supervisor_v2_abstract_component_score"),
                "introduction_component": record.get("supervisor_v2_introduction_component_score"),
                "false_pass_risk": record.get("supervisor_v2_reviewer_false_pass_risk"),
                "report": record.get("supervisor_v2_report_path"),
            }
        )
    return rows


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def write_report(eval_dir: Path, records: list[dict[str, Any]]) -> None:
    rows = summarize(records)
    supervisor_rows = summarize_supervisor_v2(records)
    paper_rows = summarize_supervisor_v2_by_paper(records)
    lines = [
        "# Section Skill Evaluation Report",
        "",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "## Matrix",
        "",
        "- Holdout papers: 5",
        "- Sections: abstract+intro, results, discussion",
        "- Skill levels: pre, v1, v2, v2_1, v2_2, v2_3 where available",
        "- Backends: api, codex",
        "",
        "## Summary",
        "",
        markdown_table(
            rows,
            [
                "section",
                "skill_label",
                "backend",
                "done",
                "failed",
                "success_rate",
                "mean_word_count",
                "mean_intro_paragraph_count",
                "mean_planner_elapsed_sec",
                "mean_writer_elapsed_sec",
                "mean_reviewer_elapsed_sec",
                "fail_statuses",
            ],
        ),
        "",
        "## Independent Supervisor V2 Quality Summary",
        "",
    ]
    if supervisor_rows:
        lines.extend(
            [
                markdown_table(
                    supervisor_rows,
                    [
                        "section",
                        "skill_label",
                        "backend",
                        "supervisor_v2_done",
                        "mean_supervisor_v2_overall_score",
                        "mean_supervisor_v2_abstract_component_score",
                        "mean_supervisor_v2_introduction_component_score",
                        "mean_supervisor_v2_evidence_fidelity",
                        "mean_supervisor_v2_story_quality",
                        "mean_supervisor_v2_evidence_to_writing_grounding",
                        "mean_supervisor_v2_must_mention_anchor_recall",
                        "mean_supervisor_v2_writing_flow",
                        "mean_supervisor_v2_venue_fit",
                        "mean_supervisor_v2_claim_calibration",
                        "mean_supervisor_v2_blocking_failure_count",
                        "verdicts",
                    ],
                ),
                "",
                "## Independent Supervisor V2 Per-Paper Scores",
                "",
                markdown_table(
                    paper_rows,
                    [
                        "slug",
                        "section",
                        "skill_label",
                        "backend",
                        "overall",
                        "verdict",
                        "evidence_fidelity",
                        "story_quality",
                        "grounding",
                        "must_anchor",
                        "writing_flow",
                        "venue_fit",
                        "claim_calibration",
                        "abstract_component",
                        "introduction_component",
                        "false_pass_risk",
                        "report",
                    ],
                ),
                "",
            ]
        )
    else:
        lines.extend(["No Supervisor V2 scores have been written yet.", ""])
    lines.extend(
        [
        "## Per-Run Records",
        "",
        markdown_table(
            records,
            [
                "section",
                "skill_label",
                "backend",
                "slug",
                "task_status",
                "word_count",
                "intro_paragraph_count",
                "review_status",
                "style_gate_status",
                "refiner_rounds_used",
                "review_rounds",
                "supervisor_v2_status",
                "supervisor_v2_overall_score",
                "supervisor_v2_verdict",
                "status_path",
            ],
        ),
        "",
        ]
    )
    write_text(eval_dir / "comparison_report.md", "\n".join(lines))
    write_yaml(
        eval_dir / "summary.yaml",
        {
            "groups": rows,
            "supervisor_v2_groups": supervisor_rows,
            "supervisor_v2_by_paper": paper_rows,
            "records": records,
        },
    )
    if supervisor_rows:
        write_yaml(eval_dir / "supervisor_v2_summary.yaml", {"groups": supervisor_rows, "by_paper": paper_rows})
        write_text(
            eval_dir / "supervisor_v2_report.md",
            "\n".join(
                [
                    "# Supervisor V2 Report",
                    "",
                    "## Mean Scores",
                    "",
                    markdown_table(
                        supervisor_rows,
                        [
                            "section",
                            "skill_label",
                            "backend",
                            "supervisor_v2_done",
                            "mean_supervisor_v2_overall_score",
                            "mean_supervisor_v2_abstract_component_score",
                            "mean_supervisor_v2_introduction_component_score",
                            "mean_supervisor_v2_evidence_fidelity",
                            "mean_supervisor_v2_story_quality",
                            "mean_supervisor_v2_evidence_to_writing_grounding",
                            "mean_supervisor_v2_must_mention_anchor_recall",
                            "mean_supervisor_v2_writing_flow",
                            "mean_supervisor_v2_claim_calibration",
                            "verdicts",
                        ],
                    ),
                    "",
                    "## Per-Paper Scores",
                    "",
                    markdown_table(
                        paper_rows,
                        [
                            "slug",
                            "section",
                            "skill_label",
                            "backend",
                            "overall",
                            "verdict",
                            "evidence_fidelity",
                            "story_quality",
                            "grounding",
                            "must_anchor",
                            "writing_flow",
                            "claim_calibration",
                            "abstract_component",
                            "introduction_component",
                            "report",
                        ],
                    ),
                    "",
                ]
            ),
        )


def collect_existing_records(jobs: list[EvalJob]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for job in jobs:
        status_path = status_path_for(job)
        run_result = {
            "job": job.__dict__,
            "skipped": True,
            "returncode": 0 if status_path else 1,
            "status_path": str(status_path) if status_path else "",
            "task_status": read_yaml(status_path).get("status") if status_path else "missing_status",
        }
        records.append(collect_record(job, run_result))
    return records


def run_supervisor_v2_for_records(
    records: list[dict[str, Any]],
    backend: str,
    workers: int,
    timeout: int,
    api_max_tokens: int,
    env: Path,
    model: str | None,
    codex_binary: str,
    force: bool,
    eval_dir: Path,
    supervisor_version: str = "v2",
) -> list[dict[str, Any]]:
    selected = [record for record in records if record.get("status_path")]
    if not selected:
        return records
    updated_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def key_for(record: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(record.get("section")),
            str(record.get("skill_label")),
            str(record.get("backend")),
            str(record.get("slug")),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(
                run_supervisor_v2_for_record,
                record,
                backend,
                timeout,
                api_max_tokens,
                env,
                model,
                codex_binary,
                force,
                supervisor_version,
            )
            for record in selected
        ]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            scored = future.result()
            updated_by_key[key_for(scored)] = scored
            print(
                f"[supervisor_v2 {index}/{len(selected)}] {scored.get('section')} {scored.get('skill_label')} "
                f"{scored.get('backend')} {scored.get('slug')} status={scored.get('supervisor_v2_status')} "
                f"score={scored.get('supervisor_v2_overall_score')}",
                flush=True,
            )
            partial_records = [updated_by_key.get(key_for(record), record) for record in records]
            write_report(eval_dir, partial_records)
    return [updated_by_key.get(key_for(record), record) for record in records]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run section skill/back-end evaluation matrix.")
    parser.add_argument("--matrix-id", default=f"section_skill_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--max-refiner-rounds", type=int, default=1)
    parser.add_argument("--api-timeout", type=int, default=600)
    parser.add_argument("--api-max-tokens", type=int, default=8000)
    parser.add_argument("--codex-timeout", type=int, default=1800)
    parser.add_argument("--api-workers", type=int, default=5)
    parser.add_argument("--codex-workers", type=int, default=3)
    parser.add_argument("--backends", nargs="+", default=BACKENDS, choices=BACKENDS)
    parser.add_argument("--sections", nargs="+", default=["abstract_intro", "results"], choices=["abstract_intro", "results", "discussion"])
    parser.add_argument(
        "--skill-labels",
        nargs="+",
        default=None,
        help="Optional skill labels to run, e.g. v2_1 or v1 v2_1.",
    )
    parser.add_argument("--supervisor-v2", action="store_true", help="Run independent Supervisor V2 scoring after generation.")
    parser.add_argument("--supervisor-v2-only", action="store_true", help="Score existing matrix outputs without launching writers.")
    parser.add_argument("--supervisor-backend", default="api", choices=SUPERVISOR_V2_BACKENDS)
    parser.add_argument("--supervisor-version", default="v2", choices=["v2", "v2_1"])
    parser.add_argument("--supervisor-workers", type=int, default=4)
    parser.add_argument("--supervisor-timeout", type=int, default=900)
    parser.add_argument("--force-supervisor-v2", action="store_true")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default=None)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    eval_dir = ROOT / "outputs" / "section_skill_eval" / args.matrix_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        job
        for job in build_jobs(args.matrix_id)
        if job.backend in args.backends and job.section in args.sections
        and (args.skill_labels is None or job.skill_label in set(args.skill_labels))
    ]
    write_yaml(eval_dir / "jobs.yaml", [job.__dict__ for job in jobs])
    if args.dry_run:
        print(eval_dir)
        print(f"jobs: {len(jobs)}")
        return 0

    if args.supervisor_v2_only:
        records = collect_existing_records(jobs)
        write_report(eval_dir, records)
        print(f"eval_dir={eval_dir}")
        print(f"supervisor_v2_only_records={len(records)}")
        records = run_supervisor_v2_for_records(
            records,
            args.supervisor_backend,
            args.supervisor_workers,
            args.supervisor_timeout,
            args.api_max_tokens,
            args.env,
            args.model,
            args.codex_binary,
            args.force_supervisor_v2,
            eval_dir,
            args.supervisor_version,
        )
        write_report(eval_dir, records)
        print(eval_dir / "supervisor_v2_report.md")
        return 0

    print(f"eval_dir={eval_dir}")
    print(f"jobs={len(jobs)}")
    results: list[dict[str, Any]] = []
    api_jobs = [job for job in jobs if job.backend == "api"]
    codex_jobs = [job for job in jobs if job.backend == "codex"]
    for label, selected, workers in (("api", api_jobs, args.api_workers), ("codex", codex_jobs, args.codex_workers)):
        print(f"starting {label} jobs={len(selected)} workers={workers}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(run_job, job, eval_dir, args.max_refiner_rounds, args.api_timeout, args.api_max_tokens, args.codex_timeout)
                for job in selected
            ]
            for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                result = future.result()
                results.append(result)
                job = result["job"]
                print(
                    f"[{label} {index}/{len(selected)}] {job['section']} {job['skill_label']} {job['backend']} {job['slug']} "
                    f"returncode={result.get('returncode')} status={result.get('task_status')}",
                    flush=True,
                )
                records = [collect_record(EvalJob(**item["job"]), item) for item in results]
                write_report(eval_dir, records)
    records = [collect_record(EvalJob(**item["job"]), item) for item in results]
    if args.supervisor_v2:
        records = run_supervisor_v2_for_records(
            records,
            args.supervisor_backend,
            args.supervisor_workers,
            args.supervisor_timeout,
            args.api_max_tokens,
            args.env,
            args.model,
            args.codex_binary,
            args.force_supervisor_v2,
            eval_dir,
            args.supervisor_version,
        )
    write_report(eval_dir, records)
    print(eval_dir / "comparison_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
