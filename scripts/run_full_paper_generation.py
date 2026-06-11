#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nature_orchestrator.agents import api_config_from_env, run_agent  # noqa: E402
from nature_orchestrator.evidence_ledger import evidence_claim_ledger_gate  # noqa: E402

DEFAULT_TASKS_ROOT = ROOT.parent / "nature-bench" / "data" / "downloads"
DEFAULT_OUT = ROOT / "outputs" / "full_paper_generation"
DEFAULT_ENV = ROOT.parent / "nature-orchestrator" / ".env"
SKILL_VERSION = "v2_4_full_paper_generation"
SECTION_ORDER = ["results", "discussion", "introduction", "abstract"]
PASS_THRESHOLD = 4.2
SECTION_SKILL_PROFILES = {
    "v2_3": {
        "results": "v2_3_story_tournament_results",
        "discussion": "v2_3_story_tournament_discussion",
        "abstract_intro": "v2_3_story_tournament_abstract_intro",
    },
    "yuan_nature": {
        "results": "yuan_nature_writing_results",
        "discussion": "yuan_nature_writing_discussion",
        "abstract_intro": "yuan_nature_writing_abstract_intro",
    },
    "yuan_nature_hybrid": {
        "results": "v2_3_story_tournament_results",
        "discussion": "yuan_nature_writing_discussion",
        "abstract_intro": "yuan_nature_writing_abstract_intro",
    },
    "v2_5": {
        "results": "v2_5_yuan_informed_results",
        "discussion": "v2_5_yuan_informed_discussion",
        "abstract_intro": "v2_5_yuan_informed_abstract_intro",
    },
    "v2_6": {
        "results": "v2_3_story_tournament_results",
        "discussion": "v2_6_nature_informed_discussion",
        "abstract_intro": "v2_6_nature_informed_abstract_intro",
    },
    "v2_6_1": {
        "results": "v2_6_1_nature_informed_results",
        "discussion": "v2_6_1_nature_informed_discussion",
        "abstract_intro": "v2_6_1_nature_informed_abstract_intro",
    },
    "v2_6_2": {
        "results": "v2_6_2_nature_informed_results",
        "discussion": "v2_6_2_nature_informed_discussion",
        "abstract_intro": "v2_6_2_nature_informed_abstract_intro",
    },
    "v2_7": {
        "results": "v2_6_1_nature_informed_results",
        "discussion": "v2_6_1_nature_informed_discussion",
        "abstract_intro": "v2_6_1_nature_informed_abstract_intro",
    },
    "v2_7_1": {
        "results": "v2_6_1_nature_informed_results",
        "discussion": "v2_6_1_nature_informed_discussion",
        "abstract_intro": "v2_6_1_nature_informed_abstract_intro",
    },
    "v2_7_2": {
        "results": "v2_6_1_nature_informed_results",
        "discussion": "v2_6_1_nature_informed_discussion",
        "abstract_intro": "v2_6_1_nature_informed_abstract_intro",
    },
    "v2_8": {
        "results": "v2_6_1_nature_informed_results",
        "discussion": "v2_6_1_nature_informed_discussion",
        "abstract_intro": "v2_8_sanitized_abstract_intro",
    },
    "nature_writing": {
        "results": "nature_writing_current_results",
        "discussion": "nature_writing_current_discussion",
        "abstract_intro": "nature_writing_current_abstract_intro",
    },
}
FULL_PAPER_SKILL_PROFILES = {
    "v2_4": "v2_4_full_paper_generation",
    "v2_5": "v2_5_yuan_informed_full_paper_generation",
    "v2_6": "v2_6_nature_informed_full_paper_generation",
    "v2_6_1": "v2_6_1_nature_informed_full_paper_generation",
    "v2_6_2": "v2_6_2_nature_informed_full_paper_generation",
    "v2_7": "v2_7_nature_informed_full_paper_generation",
    "v2_7_1": "v2_7_1_nature_informed_full_paper_generation",
    "v2_7_2": "v2_7_2_targeted_cross_section_repair_full_paper_generation",
    "v2_8": "v2_7_1_nature_informed_full_paper_generation",
    "nature_writing": "nature_writing_current_full_paper",
}
NATURE_POLISHING_ROOT = ROOT.parent / "nature-skills" / "skills" / "nature-polishing"
PAPER_STORY_CONTRACT_PROFILES = {"v2_7", "v2_7_1", "v2_7_2", "nature_writing"}
PAPER_STORY_ALIGNMENT_PROFILES = {"v2_7", "v2_7_1", "nature_writing"}
CROSS_SECTION_LEDGER_PROFILES = {"v2_7_1", "v2_7_2", "nature_writing"}
EVIDENCE_CLAIM_LEDGER_PROFILES = {"nature_writing"}
TARGETED_REPAIR_PROFILES = {"v2_7_2", "nature_writing"}
REPAIR_SECTION_ORDER = ["results", "discussion", "abstract_intro"]
REPAIR_EDIT_TYPES = {
    "add_results_support",
    "soften_external_claim",
    "harmonize_method_label",
    "harmonize_direction",
    "remove_unsupported_claim",
    "trim_repetition",
}


def effective_cross_repair_rounds(args: argparse.Namespace) -> int:
    value = getattr(args, "max_cross_repair_rounds", None)
    if value is None:
        return max(0, int(getattr(args, "max_refiner_rounds", 0)))
    return max(0, int(value))


def parse_section_agent_backends(value: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if not value:
        return overrides
    valid_sections = {"results", "discussion", "abstract_intro"}
    valid_backends = {"api", "codex", "codex+api"}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"section backend override must be section=backend, got {item!r}")
        section, backend = [part.strip() for part in item.split("=", 1)]
        if section not in valid_sections:
            raise argparse.ArgumentTypeError(f"unsupported section backend override section: {section}")
        if backend not in valid_backends:
            raise argparse.ArgumentTypeError(f"unsupported section backend override backend: {backend}")
        overrides[section] = backend
    return overrides


def section_backend(args: argparse.Namespace, section: str) -> str:
    overrides = getattr(args, "section_agent_backend_overrides", {}) or {}
    return overrides.get(section, args.agent_backend)


def read_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except yaml.YAMLError:
        return {}


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


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


def average_scores(scores: Any) -> float | None:
    if not isinstance(scores, dict):
        return None
    values = [score_to_float(value) for value in scores.values()]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    average = sum(numeric) / len(numeric)
    if 0 < average <= 1:
        average = average * 5
    if average > 5:
        average = average / 2
    return round(average, 3)


def normalized_review_score(review: dict[str, Any]) -> float | None:
    score = score_to_float(review.get("overall_score") or review.get("overall"))
    if score is not None:
        if 0 < score <= 1:
            return round(score * 5, 3)
        return score
    explicit_score_keys = [
        "abstract_specificity_score",
        "intro_gap_ladder_score",
        "evidence_disclosure_score",
        "story_novelty_score",
        "claim_safety_score",
        "nature_style_score",
    ]
    explicit_values = [score_to_float(review.get(key)) for key in explicit_score_keys if key in review]
    numeric_explicit = [value for value in explicit_values if value is not None]
    if numeric_explicit:
        score = sum(numeric_explicit) / len(numeric_explicit)
        if 0 < score <= 1:
            score = score * 5
        return round(score, 3)
    return average_scores(review.get("scores"))


def paper_story_plan_gate(plan: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "central_thesis",
        "paper_level_contribution",
        "results_role",
        "discussion_role",
        "introduction_role",
        "abstract_role",
        "must_preserve_claims",
        "must_preserve_evidence_anchors",
        "claim_boundaries",
        "cross_section_repetition_risks",
        "downstream_dependency_notes",
    ]
    issues = [f"missing paper_story_plan key: {key}" for key in required if key not in plan]
    if plan.get("schema_version") != "nature_orchestrator.paper_story_plan.v1":
        issues.append("schema_version must be nature_orchestrator.paper_story_plan.v1")
    return {
        "schema_version": "nature_orchestrator.paper_story_plan_gate.v1",
        "status": "failed" if issues else "passed",
        "blocking_issues": issues,
    }


def normalize_paper_story_contract(contract: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(contract)
    roles = normalized.get("section_roles")
    if isinstance(roles, dict):
        normalized_roles = dict(roles)
        combined = (
            normalized_roles.get("abstract_intro")
            or normalized_roles.get("abstract+intro")
            or normalized_roles.get("abstract_and_introduction")
        )
        if combined is not None:
            normalized_roles.setdefault("introduction", combined)
            normalized_roles.setdefault("abstract", combined)
        normalized["section_roles"] = normalized_roles
    return normalized


def paper_story_contract_gate(contract: dict[str, Any]) -> dict[str, Any]:
    contract = normalize_paper_story_contract(contract)
    required = [
        "schema_version",
        "central_thesis",
        "paper_level_contribution",
        "main_tension_or_surprise",
        "story_candidates",
        "selected_route",
        "figure_to_section_allocation",
        "must_preserve_evidence_anchors",
        "claim_boundary_table",
        "section_roles",
        "cross_section_repetition_risks",
        "known_uncertainties",
        "section_feedback_updates",
        "downstream_dependency_notes",
    ]
    issues = [f"missing paper_story_contract key: {key}" for key in required if key not in contract]
    if contract.get("schema_version") != "nature_orchestrator.paper_story_contract.v2":
        issues.append("schema_version must be nature_orchestrator.paper_story_contract.v2")
    for key in ["story_candidates", "figure_to_section_allocation", "must_preserve_evidence_anchors", "claim_boundary_table"]:
        if key in contract and not contract.get(key):
            issues.append(f"{key} must not be empty")
    section_roles = contract.get("section_roles") or {}
    if isinstance(section_roles, dict):
        for section in ["results", "discussion", "introduction", "abstract"]:
            if section not in section_roles:
                issues.append(f"section_roles missing {section}")
    else:
        issues.append("section_roles must be a mapping")
    return {
        "schema_version": "nature_orchestrator.paper_story_contract_gate.v1",
        "status": "failed" if issues else "passed",
        "blocking_issues": issues,
    }


def cross_section_evidence_ledger_gate(ledger: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "abstract_promises",
        "intro_promises",
        "discussion_claims",
        "results_support_lines",
        "missing_support",
        "exact_value_mismatches",
        "direction_conflicts",
        "repetition_overload",
        "recoverable_results_repairs",
    ]
    issues = [f"missing cross_section_evidence_ledger key: {key}" for key in required if key not in ledger]
    if ledger.get("schema_version") != "nature_orchestrator.cross_section_evidence_ledger.v1":
        issues.append("schema_version must be nature_orchestrator.cross_section_evidence_ledger.v1")
    for key in required:
        if key == "schema_version":
            continue
        if key in ledger and not isinstance(ledger.get(key), list):
            issues.append(f"{key} must be a list")
    if "results_support_lines" in ledger and not ledger.get("results_support_lines"):
        issues.append("results_support_lines must not be empty")
    return {
        "schema_version": "nature_orchestrator.cross_section_evidence_ledger_gate.v1",
        "status": "failed" if issues else "passed",
        "blocking_issues": issues,
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_repair_section(section: str) -> str:
    section = str(section)
    if section in {"abstract", "introduction", "abstract_intro", "abstract+intro"}:
        return "abstract_intro"
    if section in {"results", "discussion"}:
        return section
    return section


def repair_plan_target_sections(plan: dict[str, Any]) -> list[str]:
    targets: set[str] = set()
    for action in plan.get("repair_actions") or []:
        if not isinstance(action, dict):
            continue
        for section in _as_list(action.get("affected_sections")):
            normalized = normalize_repair_section(str(section))
            if normalized in REPAIR_SECTION_ORDER:
                targets.add(normalized)
        for target_file in _as_list(action.get("target_files")):
            target_text = str(target_file)
            if "abstract.tex" in target_text or "introduction.tex" in target_text:
                targets.add("abstract_intro")
            elif "results.tex" in target_text:
                targets.add("results")
            elif "discussion.tex" in target_text:
                targets.add("discussion")
    return [section for section in REPAIR_SECTION_ORDER if section in targets]


def cross_section_repair_plan_gate(plan: dict[str, Any]) -> dict[str, Any]:
    required = ["schema_version", "round_index", "repair_actions", "unresolved_or_deferred"]
    issues = [f"missing cross_section_repair_plan key: {key}" for key in required if key not in plan]
    if plan.get("schema_version") != "nature_orchestrator.cross_section_repair_plan.v1":
        issues.append("schema_version must be nature_orchestrator.cross_section_repair_plan.v1")
    repair_actions = plan.get("repair_actions")
    if not isinstance(repair_actions, list):
        issues.append("repair_actions must be a list")
        repair_actions = []
    if isinstance(repair_actions, list) and not repair_actions:
        issues.append("repair_actions must not be empty when a repair plan is requested")
    if "unresolved_or_deferred" in plan and not isinstance(plan.get("unresolved_or_deferred"), list):
        issues.append("unresolved_or_deferred must be a list")
    valid_files = {
        "manuscript/abstract.tex",
        "manuscript/introduction.tex",
        "manuscript/results.tex",
        "manuscript/discussion.tex",
    }
    for index, action in enumerate(repair_actions if isinstance(repair_actions, list) else []):
        if not isinstance(action, dict):
            issues.append(f"repair_actions[{index}] must be a mapping")
            continue
        prefix = f"repair_actions[{index}]"
        for key in ["issue_id", "source", "edit_type", "problem", "desired_outcome", "evidence_basis"]:
            if not str(action.get(key) or "").strip():
                issues.append(f"{prefix}.{key} must be non-empty")
        if action.get("edit_type") not in REPAIR_EDIT_TYPES:
            issues.append(f"{prefix}.edit_type must be one of {sorted(REPAIR_EDIT_TYPES)}")
        affected_sections = _as_list(action.get("affected_sections"))
        if not affected_sections:
            issues.append(f"{prefix}.affected_sections must not be empty")
        else:
            for section in affected_sections:
                if normalize_repair_section(str(section)) not in REPAIR_SECTION_ORDER:
                    issues.append(f"{prefix}.affected_sections contains unsupported section: {section}")
        target_files = _as_list(action.get("target_files"))
        if not target_files:
            issues.append(f"{prefix}.target_files must not be empty")
        else:
            for target_file in target_files:
                if str(target_file) not in valid_files:
                    issues.append(f"{prefix}.target_files contains unsupported file: {target_file}")
        if "blocking" in action and not isinstance(action.get("blocking"), bool):
            issues.append(f"{prefix}.blocking must be boolean when present")
    return {
        "schema_version": "nature_orchestrator.cross_section_repair_plan_gate.v1",
        "status": "failed" if issues else "passed",
        "blocking_issues": issues,
    }


def section_score_gate(review: dict[str, Any], threshold: float = PASS_THRESHOLD) -> dict[str, Any]:
    score = normalized_review_score(review)
    blocking = review.get("blocking_issues") or []
    accepted = review.get("accepted_by_reviewers")
    issues: list[str] = []
    if score is None:
        issues.append("missing overall_score")
    elif score < threshold:
        issues.append(f"overall_score below {threshold}: {score}")
    if blocking:
        issues.append("blocking_issues must be empty")
    if accepted is False:
        issues.append("accepted_by_reviewers must not be false")
    return {
        "schema_version": "nature_orchestrator.section_score_gate.v1",
        "status": "failed" if issues else "passed",
        "overall_score": score,
        "threshold": threshold,
        "blocking_issues": issues,
    }


NUMERIC_ANCHOR_RE = re.compile(
    r"(?<![\w.])"
    r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"(?:\s*\\?%|\s*(?:times|x)\b|\s*[- ]?years?\b)?",
    re.IGNORECASE,
)
METRIC_VALUE_RE = re.compile(r"(?<![\w.])(?:0?\.\d+|1\.0+)(?![\w.])")
METRIC_CONTEXT_CUE_RE = re.compile(
    r"\b(?:f1|f1-score|kappa|fleiss|agreement|auc|score)\b|\\kappa|κ",
    re.IGNORECASE,
)


def _normalize_anchor_text(value: str) -> str:
    normalized = value.replace("\\%", "%").replace("–", "-").replace("—", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for child in value.values():
            strings.extend(_iter_strings(child))
        return strings
    if isinstance(value, list):
        strings = []
        for child in value:
            strings.extend(_iter_strings(child))
        return strings
    return []


def extract_numeric_anchor_claims(review: dict[str, Any]) -> list[str]:
    """Extract reviewer-confirmed numeric anchors that polish must not erase."""

    sources: list[Any] = []
    for key in [
        "must_mention_anchor_recall",
        "payoff_anchor_audit",
        "story_contract_audit",
    ]:
        if key in review:
            sources.append(review[key])
    anchors: list[str] = []
    seen: set[str] = set()
    for text in _iter_strings(sources):
        for match in NUMERIC_ANCHOR_RE.finditer(text):
            anchor = _normalize_anchor_text(match.group(0))
            if not anchor:
                continue
            # Single-digit integers from labels are usually not useful final anchors.
            if re.fullmatch(r"\d", anchor):
                continue
            key = anchor.lower().replace(",", "")
            if key not in seen:
                anchors.append(anchor)
                seen.add(key)
    return anchors


def _numeric_anchor_present(anchor: str, final_text: str) -> bool:
    anchor_norm = _normalize_anchor_text(anchor).lower()
    text_norm = _normalize_anchor_text(final_text).lower()
    if anchor_norm in text_norm:
        return True
    # Accept comma-free rendering of large counts.
    if "," in anchor_norm and anchor_norm.replace(",", "") in text_norm.replace(",", ""):
        return True
    multiplier_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:x|times)", anchor_norm)
    if multiplier_match:
        number = re.escape(multiplier_match.group(1))
        multiplier_pattern = rf"(?<![\w.]){number}\s*(?:x|times|fold)\b|(?<![\w.]){number}-fold\b"
        if re.search(multiplier_pattern, text_norm, re.IGNORECASE):
            return True
    metric_match = re.fullmatch(r"0?\.\d+|1\.0+", anchor_norm)
    if metric_match:
        try:
            threshold = float(anchor_norm)
        except ValueError:
            threshold = -1.0
        if 0.8 <= threshold <= 1.0:
            for value_match in METRIC_VALUE_RE.finditer(text_norm):
                try:
                    value = float(value_match.group(0))
                except ValueError:
                    continue
                if value + 1e-12 < threshold:
                    continue
                window = text_norm[max(0, value_match.start() - 90) : value_match.end() + 90]
                if METRIC_CONTEXT_CUE_RE.search(window):
                    return True
    return False


def final_section_anchor_gate(section: str, review: dict[str, Any], final_text: str) -> dict[str, Any]:
    numeric_anchors = extract_numeric_anchor_claims(review)
    missing = [anchor for anchor in numeric_anchors if not _numeric_anchor_present(anchor, final_text)]
    return {
        "schema_version": "nature_orchestrator.final_section_anchor_gate.v1",
        "section": section,
        "status": "failed" if missing else "passed",
        "numeric_anchors": numeric_anchors,
        "missing_numeric_anchors": missing,
        "blocking_issues": [
            (
                f"{section} final text dropped reviewer-confirmed numeric anchors: "
                + ", ".join(missing)
            )
        ]
        if missing
        else [],
    }


def write_final_section_anchor_gates(run_dir: Path) -> dict[str, Any]:
    section_files = {
        "results": "manuscript/results.tex",
        "discussion": "manuscript/discussion.tex",
    }
    section_gates: dict[str, Any] = {}
    blocking_issues: list[str] = []
    for section, rel_text_path in section_files.items():
        review = read_yaml(run_dir / "sections" / section / "reviews" / "section_review.yaml")
        final_text = read_text(run_dir / rel_text_path)
        gate = final_section_anchor_gate(section=section, review=review if isinstance(review, dict) else {}, final_text=final_text)
        section_gates[section] = gate
        write_yaml(run_dir / "audits" / f"final_section_anchor_gate_{section}.yaml", gate)
        blocking_issues.extend(gate["blocking_issues"])
    summary = {
        "schema_version": "nature_orchestrator.final_section_anchor_gate_summary.v1",
        "status": "failed" if blocking_issues else "passed",
        "section_gates": section_gates,
        "blocking_issues": blocking_issues,
    }
    write_yaml(run_dir / "audits" / "final_section_anchor_gate.yaml", summary)
    return summary


def apply_final_section_anchor_gate(run_dir: Path, review: dict[str, Any]) -> dict[str, Any]:
    gate = write_final_section_anchor_gates(run_dir)
    if gate["status"] == "passed":
        return review
    updated = dict(review)
    updated["status"] = "revise"
    updated["accepted_by_reviewers"] = False
    current_score = score_to_float(updated.get("overall_score"))
    updated["overall_score"] = min(current_score if current_score is not None else PASS_THRESHOLD - 0.1, PASS_THRESHOLD - 0.1)
    blocking = updated.get("blocking_issues") or []
    if not isinstance(blocking, list):
        blocking = [str(blocking)]
    for issue in gate["blocking_issues"]:
        blocking.append(
            {
                "issue": issue,
                "severity": "blocking",
                "required_fix": (
                    "Restore the reviewer-confirmed decisive numeric anchor in the "
                    "same final section, unless the cross-section evidence ledger "
                    "explicitly marks it unsupported."
                ),
            }
        )
    updated["blocking_issues"] = blocking
    targeted = updated.get("targeted_revisions") or []
    if not isinstance(targeted, list):
        targeted = [str(targeted)]
    targeted.extend(gate["blocking_issues"])
    updated["targeted_revisions"] = targeted
    write_yaml(run_dir / "reviews" / "cross_section_review.yaml", updated)
    write_yaml(run_dir / "audits" / "cross_section_score_gate.yaml", section_score_gate(updated))
    return updated


def latest_review_file(section_run: Path, section: str) -> Path | None:
    names = {
        "results": "results_review",
        "discussion": "discussion_review",
        "abstract_intro": "abstract_intro_review",
    }
    stem = names.get(section, section)
    candidates = list(section_run.rglob(f"{stem}.yaml")) + list(section_run.rglob(f"{stem}_round_*.yaml"))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def normalize_section_review(status_path: Path, section: str) -> dict[str, Any]:
    section_run = status_path.parent
    status = read_yaml(status_path)
    source_review_path = latest_review_file(section_run, "abstract_intro" if section in {"abstract", "introduction"} else section)
    source_review = read_yaml(source_review_path) if source_review_path else {}
    if not isinstance(source_review, dict):
        source_review = {}
    blocking = source_review.get("blocking_issues") or []
    required = source_review.get("required_revisions") or []
    score = normalized_review_score(source_review)
    if score is None and status.get("status") == "done":
        score = PASS_THRESHOLD
    accepted = source_review.get("accepted_by_reviewers")
    if accepted is None:
        accepted = source_review.get("status") == "pass" or status.get("status") == "done"
    review = {
        "schema_version": "nature_orchestrator.full_paper_section_review_proxy.v1",
        "status": source_review.get("status") or ("pass" if status.get("status") == "done" else "revise"),
        "overall_score": score,
        "accepted_by_reviewers": bool(accepted),
        "blocking_issues": blocking if isinstance(blocking, list) else [str(blocking)],
        "required_revisions": required if isinstance(required, list) else [str(required)],
        "section": section,
        "source_status_path": str(status_path),
        "source_review_path": str(source_review_path) if source_review_path else "",
    }
    if isinstance(source_review.get("scores"), dict):
        review["source_scores"] = source_review["scores"]
    for key in [
        "missing_recoverable_anchors",
        "direction_comparator_errors",
        "over_conservatism",
        "unrecoverable_detail_risk",
        "must_mention_anchor_recall",
        "story_level_issues",
        "text_level_issues",
    ]:
        if key in source_review:
            review[key] = source_review[key]
    return review


def infer_field(tasks_root: Path, slug: str, fallback: str) -> str:
    if fallback:
        return fallback
    for path in tasks_root.rglob(slug):
        if path.is_dir() and path.name == slug and path.parent.name:
            return path.parent.name
    return "unknown_field"


def build_mock_paper_story_plan(slug: str, field: str) -> dict[str, Any]:
    return {
        "schema_version": "nature_orchestrator.paper_story_plan.v1",
        "central_thesis": f"{slug} presents an evidence-grounded scientific story in {field}.",
        "paper_level_contribution": "The manuscript links provided results to a bounded contribution.",
        "results_role": "Establish the evidence hierarchy and supported findings.",
        "discussion_role": "Synthesize meaning, limitations and implications without adding new results.",
        "introduction_role": "Frame the article-specific problem and contribution after the evidence path is known.",
        "abstract_role": "Compress the final paper story without adding unsupported claims.",
        "must_preserve_claims": ["central evidence-grounded contribution"],
        "must_preserve_evidence_anchors": ["Fig. 1"],
        "claim_boundaries": ["Do not exceed the provided evidence context."],
        "cross_section_repetition_risks": ["Avoid repeating the Results evidence list in Discussion."],
        "downstream_dependency_notes": [
            "Results must pass before Discussion.",
            "Discussion must pass before Introduction.",
            "Introduction must pass before Abstract.",
        ],
    }


def _safe_copy_to_run(source: Path, target: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def _find_case_dir(tasks_root: Path, slug: str) -> Path | None:
    for path in tasks_root.rglob(slug):
        if path.is_dir() and path.name == slug:
            return path
    return None


def prepare_paper_story_context(run_dir: Path, tasks_root: Path, slug: str) -> list[str]:
    case_dir = _find_case_dir(tasks_root, slug)
    context_dir = run_dir / "paper" / "context"
    allowed: list[str] = []
    if case_dir is None:
        return allowed
    copy_map = [
        (case_dir / "benchmark" / "tasks" / "full_paper_masked.yaml", context_dir / "full_paper_task.yaml"),
        (case_dir / "benchmark" / "tasks_safe_web" / "full_paper_masked.yaml", context_dir / "full_paper_task_safe_web.yaml"),
        (case_dir / "benchmark" / "evidence_pack.figure_grounded.yaml", context_dir / "evidence_pack.yaml"),
        (case_dir / "benchmark" / "vlm_figure_evidence.md", context_dir / "vlm_figure_evidence.md"),
        (case_dir / "renderers" / "custom_nature_template" / "sections" / "methods.tex", context_dir / "methods.tex"),
        (case_dir / "renderers" / "custom_nature_template" / "sections" / "availability.tex", context_dir / "availability.tex"),
    ]
    for source, target in copy_map:
        if _safe_copy_to_run(source, target):
            allowed.append(str(target.relative_to(run_dir)))
    return allowed


def _downstream_sections_from_role_hints(figure: dict[str, Any]) -> list[str]:
    sections = {"results"}
    for hint in figure.get("role_hints") or []:
        if not isinstance(hint, dict):
            continue
        section = str(hint.get("section") or "").strip().lower()
        if section in {"abstract", "introduction", "abstract_intro", "discussion", "results"}:
            sections.add(section)
        if section == "abstract_intro":
            sections.update({"abstract", "introduction"})
    return sorted(sections)


def build_mock_evidence_claim_ledger(run_dir: Path, field: str = "unknown_field") -> dict[str, Any]:
    evidence_pack = read_yaml(run_dir / "paper" / "context" / "evidence_pack.yaml")
    figures = []
    if isinstance(evidence_pack, dict):
        figures = evidence_pack.get("figure_evidence") or evidence_pack.get("figures") or []
    if not isinstance(figures, list):
        figures = []

    evidence_items: list[dict[str, Any]] = []
    for index, figure in enumerate(figures, start=1):
        if not isinstance(figure, dict):
            continue
        figure_id = str(figure.get("id") or figure.get("figure") or f"figure-{index}")
        caption = str(figure.get("caption_text") or figure.get("caption") or "").strip()
        if not caption and figure.get("caption_path"):
            caption = str(figure.get("caption_path"))
        observation = caption or f"{figure_id} is available as figure-grounded evidence."
        method_snippets = figure.get("method_snippets") or []
        has_method = bool(method_snippets)
        evidence_items.append(
            {
                "anchor": figure_id,
                "observation": observation[:500],
                "comparator": "use only comparators explicitly stated in caption, method or source data",
                "direction": "unclear unless the allowed context explicitly states a signed direction",
                "confidence_source": "caption_supported" if caption else "allowed_context_supported",
                "evidence_role": "primary_claim" if index == 1 else "support",
                "must_write_detail": (
                    "state what this evidence contributes to the Results chain; preserve comparator, "
                    "direction and numeric values only when they are recoverable from allowed files"
                ),
                "can_compress": "setup, assay logistics or validation details after their evidence role is made clear",
                "cannot_claim": (
                    "do not upgrade visual impressions or unstated comparisons into definite direction, "
                    "causality, rescue, prevention or no-effect claims"
                ),
                "downstream_section_use": _downstream_sections_from_role_hints(figure),
            }
        )
        if has_method:
            evidence_items.append(
                {
                    "anchor": f"{figure_id}:method",
                    "observation": str(method_snippets[0].get("text") if isinstance(method_snippets[0], dict) else method_snippets[0])[:500],
                    "comparator": "method context only",
                    "direction": "not a result direction",
                    "confidence_source": "method_supported",
                    "evidence_role": "validation",
                    "must_write_detail": "use method detail to explain why the readout is interpretable when needed",
                    "can_compress": "procedural detail not needed for a reader to trust the claim",
                    "cannot_claim": "do not treat method description as an independent result",
                    "downstream_section_use": ["results", "discussion"],
                }
            )

    vlm_text = read_text(run_dir / "paper" / "context" / "vlm_figure_evidence.md").strip()
    if vlm_text:
        evidence_items.append(
            {
                "anchor": "vlm_figure_evidence",
                "observation": vlm_text[:500],
                "comparator": "visual-model observation; comparator may be incomplete",
                "direction": "unclear",
                "confidence_source": "vlm_only",
                "evidence_role": "boundary",
                "must_write_detail": "use as a prompt to inspect allowed captions/source context, not as signed proof",
                "can_compress": "visual texture that is not supported by caption, methods or source data",
                "cannot_claim": "definite signed effects, causal mechanisms, rescue, prevention or no-effect",
                "downstream_section_use": ["results"],
            }
        )

    if not evidence_items:
        evidence_items.append(
            {
                "anchor": "allowed_paper_context",
                "observation": f"Allowed paper context exists for a {field} manuscript, but no structured figure rows were found.",
                "comparator": "unclear",
                "direction": "unclear",
                "confidence_source": "unclear",
                "evidence_role": "boundary",
                "must_write_detail": "mark missing evidence explicitly and avoid invented claim direction",
                "can_compress": "all unsupported detail",
                "cannot_claim": "specific figure, comparator, number or mechanism not present in allowed files",
                "downstream_section_use": ["results", "discussion", "abstract", "introduction"],
            }
        )

    return {
        "schema_version": "nature_orchestrator.evidence_claim_ledger.v1",
        "field": field,
        "evidence_items": evidence_items,
        "story_use_rules": [
            "Story plans may order and weight evidence but must not replace this ledger.",
            "A paper or section story can narrow claims, but cannot upgrade vlm_only or unclear evidence into definite direction.",
            "Compression is allowed only after the item's evidence role, comparator boundary and unsupported claims are clear.",
        ],
    }


def build_evidence_claim_ledger_prompt() -> str:
    return """# Evidence-to-Claim Ledger

Read only the allowed files. Before paper story planning, build a structured
ledger that separates evidence observations from manuscript claims.

Inputs may include:
- paper/context/full_paper_task.yaml
- paper/context/full_paper_task_safe_web.yaml
- paper/context/evidence_pack.yaml
- paper/context/vlm_figure_evidence.md
- paper/context/methods.tex
- paper/context/availability.tex
- skill/prompts/evidence_claim_ledger_prompt.md

Write:
- paper/evidence/evidence_claim_ledger.yaml

Use schema_version `nature_orchestrator.evidence_claim_ledger.v1`.
Each `evidence_items` row must include:
- anchor
- observation
- comparator
- direction
- confidence_source: caption_supported | source_data_supported |
  method_supported | allowed_context_supported | vlm_only | unclear
- evidence_role: primary_claim | support | boundary | control |
  negative_result | validation | limitation
- must_write_detail
- can_compress
- cannot_claim
- downstream_section_use

Rules:
- Do not write manuscript prose.
- Use VLM-only observations as uncertainty/boundary cues unless caption,
  method, source data or other allowed context supports a signed direction.
- A later story plan may order or weight rows, but may not upgrade confidence.
- Before finishing, validate the YAML output.
"""


def write_evidence_claim_ledger(run_dir: Path, args: argparse.Namespace, slug: str, field: str) -> dict[str, Any]:
    allowed_files = prepare_paper_story_context(run_dir, args.tasks_root, slug)
    skill_version = full_paper_skill_version(getattr(args, "full_paper_polisher_profile", "v2_4"))
    allowed_files.append(copy_skill_file_to_run(run_dir, "prompts/evidence_claim_ledger_prompt.md", skill_version))
    if getattr(args, "agent_backend", "mock") == "mock":
        ledger = build_mock_evidence_claim_ledger(run_dir, field=field)
        write_yaml(run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml", ledger)
        write_yaml(run_dir / "audits" / "evidence_claim_ledger_gate.yaml", evidence_claim_ledger_gate(ledger))
        return ledger

    backend = "api" if getattr(args, "agent_backend", "api") in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role="evidence_claim_ledger",
        run_dir=run_dir,
        prompt=build_evidence_claim_ledger_prompt(),
        allowed_files=allowed_files,
        output_contract={"files": {"paper/evidence/evidence_claim_ledger.yaml": "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / "evidence_claim_ledger.agent_result.yaml", result.__dict__)
    ledger = read_yaml(run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml")
    gate = evidence_claim_ledger_gate(ledger if isinstance(ledger, dict) else {})
    if not isinstance(ledger, dict) or result.status != "done" or gate["status"] != "passed":
        ledger = build_mock_evidence_claim_ledger(run_dir, field=field)
        ledger.setdefault("story_use_rules", []).append(
            f"Agent ledger failed or was invalid for {slug}; fallback ledger is conservative."
        )
        write_yaml(run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml", ledger)
        gate = evidence_claim_ledger_gate(ledger)
    write_yaml(run_dir / "audits" / "evidence_claim_ledger_gate.yaml", gate)
    return ledger


def build_mock_paper_story_contract(slug: str, field: str, run_dir: Path) -> dict[str, Any]:
    evidence_text = "\n".join(
        read_text(path)
        for path in [
            run_dir / "paper" / "context" / "vlm_figure_evidence.md",
            run_dir / "paper" / "context" / "methods.tex",
            run_dir / "paper" / "context" / "evidence_pack.yaml",
        ]
        if path.exists()
    )
    anchors: list[str] = []
    for pattern in [r"Figure\s+\d+[^\n.]*", r"Fig\.\s*\d+[^\n.]*", r"\b\d+(?:\.\d+)?\s*%[^\n.]*"]:
        for match in re.findall(pattern, evidence_text, flags=re.I):
            item = " ".join(str(match).split())[:180]
            if item and item not in anchors:
                anchors.append(item)
            if len(anchors) >= 6:
                break
        if len(anchors) >= 6:
            break
    if not anchors:
        anchors = ["Main figure evidence", "Methods and availability context"]
    central = anchors[0].rstrip(".")
    return {
        "schema_version": "nature_orchestrator.paper_story_contract.v2",
        "central_thesis": central,
        "paper_level_contribution": f"A bounded {field} contribution supported by recoverable figure and method evidence.",
        "main_tension_or_surprise": "The strongest paper-level framing must be selected from recoverable evidence rather than inferred from oracle text.",
        "story_candidates": [
            {"route_name": "evidence-first", "central_thesis": central, "risk": "May understate broader motivation."},
            {"route_name": "contribution-first", "central_thesis": f"{field} contribution grounded in figure evidence", "risk": "May overclaim if not checked against Results."},
        ],
        "selected_route": "evidence-first",
        "figure_to_section_allocation": {
            "results": anchors[:4],
            "discussion": anchors[:2],
            "introduction": anchors[:2],
            "abstract": anchors[:3],
        },
        "must_preserve_evidence_anchors": anchors,
        "claim_boundary_table": [
            {"claim": central, "boundary": "State only as supported by allowed figure/method context."},
            {"claim": "paper-level contribution", "boundary": "Do not add oracle-only motivation or target-section prose."},
        ],
        "section_roles": {
            "results": "Prove the recoverable evidence chain with figure roles, numeric anchors and comparator boundaries.",
            "discussion": "Synthesize meaning and limitations without introducing new Results.",
            "introduction": "Motivate the article-specific gap after Results and Discussion boundaries are known.",
            "abstract": "Compress the final supported story without adding unsupported claims.",
        },
        "cross_section_repetition_risks": ["Do not repeat the full Results evidence list in Discussion or Introduction."],
        "known_uncertainties": ["Section planners may narrow this contract if detailed evidence does not support a broad route."],
        "section_feedback_updates": [],
        "downstream_dependency_notes": [
            "Results plan may correct figure allocation and claim boundaries.",
            "Discussion plan may narrow implications to what Results established.",
            "Abstract+Intro tournament should use the updated contract, not invent a new paper story.",
        ],
    }


def write_mock_section(run_dir: Path, section: str) -> dict[str, Any]:
    texts = {
        "results": "\\section{Results}\nThe evidence establishes a primary supported finding anchored to Fig.~1. Control and boundary observations are reported without extending beyond the mock evidence pack.\n",
        "discussion": "\\section{Discussion}\nThese findings support a bounded interpretation of the central result. The discussion states the implication, limitation and next question without introducing new results.\n",
        "introduction": "\\section{Introduction}\nA focused scientific problem motivates the study. Existing evidence leaves an article-specific gap that the present results address through a bounded, figure-grounded contribution.\n",
        "abstract": "\\begin{abstract}\nThis mock manuscript tests a full-paper generation wrapper. The evidence supports a central result, a bounded interpretation and a concise contribution without adding unsupported claims.\n\\end{abstract}\n",
    }
    out = run_dir / "manuscript" / f"{section}.tex"
    write_text(out, texts[section])
    review = {
        "status": "pass",
        "overall_score": 4.2,
        "accepted_by_reviewers": True,
        "blocking_issues": [],
        "required_revisions": [],
        "section": section,
    }
    gate = section_score_gate(review)
    write_yaml(run_dir / "sections" / section / "reviews" / "section_review.yaml", review)
    write_yaml(run_dir / "sections" / section / "audits" / "section_score_gate.yaml", gate)
    return {"review": review, "score_gate": gate, "output": str(out)}


def split_abstract_intro(text: str) -> tuple[str, str]:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, flags=re.S | re.I)
    if not match:
        return "", text.strip() + "\n"
    abstract = "\\begin{abstract}" + match.group(1).strip() + "\\end{abstract}\n"
    introduction = text[match.end() :].strip()
    return abstract, introduction + ("\n" if introduction else "")


def assemble_final(run_dir: Path) -> Path:
    parts = [
        read_text(run_dir / "manuscript" / "abstract.tex").strip(),
        read_text(run_dir / "manuscript" / "introduction.tex").strip(),
        read_text(run_dir / "manuscript" / "results.tex").strip(),
        read_text(run_dir / "manuscript" / "discussion.tex").strip(),
    ]
    main = "\n\n".join(part for part in parts if part) + "\n"
    write_text(run_dir / "manuscript" / "main.tex", main)
    final_path = run_dir / "final" / "manuscript.tex"
    write_text(final_path, main)
    return final_path


def write_static_cross_section_review(run_dir: Path) -> dict[str, Any]:
    review = {
        "schema_version": "nature_orchestrator.cross_section_review.v1",
        "status": "pass",
        "overall_score": 4.2,
        "accepted_by_reviewers": True,
        "blocking_issues": [],
        "targeted_revisions": [],
    }
    write_yaml(run_dir / "reviews" / "cross_section_review.yaml", review)
    write_yaml(run_dir / "audits" / "cross_section_score_gate.yaml", section_score_gate(review))
    return review


def copy_skill_file_to_run(run_dir: Path, relative: str, skill_version: str = SKILL_VERSION) -> str:
    if skill_version == "nature_writing_current_full_paper":
        root = ROOT / "skills" / "nature_writing"
        source_map = {
            "prompts/paper_story_prompt.md": root / "prompts" / "paper_story_planner.md",
            "prompts/paper_story_aligner_prompt.md": root / "prompts" / "paper_story_aligner.md",
            "prompts/evidence_claim_ledger_prompt.md": root / "prompts" / "evidence_claim_ledger.md",
            "prompts/cross_section_evidence_ledger_prompt.md": root / "prompts" / "cross_section_evidence_ledger.md",
            "prompts/cross_section_reviewer_prompt.md": root / "prompts" / "cross_section_reviewer.md",
            "prompts/cross_section_repair_planner_prompt.md": root / "prompts" / "cross_section_repair_planner.md",
            "prompts/targeted_section_patcher_prompt.md": root / "prompts" / "targeted_section_patcher.md",
            "prompts/full_paper_polisher_prompt.md": root / "prompts" / "final_polisher.md",
            "rubrics/cross_section_rubric.yaml": root / "rubrics" / "cross_section_rubric.yaml",
        }
        source = source_map.get(relative)
        if source is None:
            raise FileNotFoundError(f"Unsupported current full-paper skill file: {relative}")
    else:
        source = ROOT / "skills" / "nature_writing" / "versions" / skill_version / relative
    target = run_dir / "skill" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return str(Path("skill") / relative)


def full_paper_skill_version(profile: str) -> str:
    return FULL_PAPER_SKILL_PROFILES.get(profile, SKILL_VERSION)


def uses_paper_story_contract(profile: str) -> bool:
    return profile in PAPER_STORY_CONTRACT_PROFILES


def uses_paper_story_alignment(profile: str) -> bool:
    return profile in PAPER_STORY_ALIGNMENT_PROFILES


def uses_cross_section_evidence_ledger(profile: str) -> bool:
    return profile in CROSS_SECTION_LEDGER_PROFILES


def uses_evidence_claim_ledger(profile: str) -> bool:
    return profile in EVIDENCE_CLAIM_LEDGER_PROFILES


def uses_targeted_cross_section_repair(profile: str) -> bool:
    return profile in TARGETED_REPAIR_PROFILES


def build_paper_story_controller_prompt() -> str:
    return """# Paper-Level Story Controller

Read only the allowed files. Generate a paper-level story contract before
section writing. This contract is a soft controller: it defines the central
paper route, section roles, evidence allocation and claim boundaries, but later
section planners may refine or correct it with more detailed evidence audits.

Inputs may include:
- paper/evidence/evidence_claim_ledger.yaml
- paper/context/full_paper_task.yaml
- paper/context/full_paper_task_safe_web.yaml
- paper/context/evidence_pack.yaml
- paper/context/vlm_figure_evidence.md
- paper/context/methods.tex
- paper/context/availability.tex
- skill/prompts/paper_story_prompt.md

Write:
- paper/story/paper_story_contract.yaml

Treat `paper/evidence/evidence_claim_ledger.yaml` as the evidence-confidence
authority when present. The paper story may order and weight evidence, but it
must not upgrade VLM-only or unclear rows into definitive direction, causality,
rescue, prevention or no-effect claims.

The YAML must include:
- schema_version: nature_orchestrator.paper_story_contract.v2
- central_thesis
- paper_level_contribution
- main_tension_or_surprise
- story_candidates
- selected_route
- figure_to_section_allocation
- must_preserve_evidence_anchors
- claim_boundary_table
- section_roles
- cross_section_repetition_risks
- known_uncertainties
- section_feedback_updates
- downstream_dependency_notes

`section_roles` must contain separate keys for `results`, `discussion`,
`introduction` and `abstract`. Do not only emit a combined `abstract_intro`
role.

Before finishing, validate the YAML output.
"""


def write_paper_story_contract(run_dir: Path, args: argparse.Namespace, slug: str, field: str) -> dict[str, Any]:
    allowed_files = prepare_paper_story_context(run_dir, args.tasks_root, slug)
    skill_version = full_paper_skill_version(getattr(args, "full_paper_polisher_profile", "v2_4"))
    if (run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml").exists():
        allowed_files.append("paper/evidence/evidence_claim_ledger.yaml")
    allowed_files.append(copy_skill_file_to_run(run_dir, "prompts/paper_story_prompt.md", skill_version))
    if getattr(args, "agent_backend", "mock") == "mock":
        contract = normalize_paper_story_contract(build_mock_paper_story_contract(slug, field, run_dir))
        write_yaml(run_dir / "paper" / "story" / "paper_story_contract.yaml", contract)
        write_yaml(run_dir / "audits" / "paper_story_contract_gate.yaml", paper_story_contract_gate(contract))
        write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", contract)
        write_yaml(run_dir / "audits" / "paper_story_plan_gate.yaml", paper_story_plan_gate(build_mock_paper_story_plan(slug, field)))
        return contract
    backend = "api" if getattr(args, "agent_backend", "api") in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role="paper_story_controller",
        run_dir=run_dir,
        prompt=build_paper_story_controller_prompt(),
        allowed_files=allowed_files,
        output_contract={"files": {"paper/story/paper_story_contract.yaml": "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / "paper_story_controller.agent_result.yaml", result.__dict__)
    contract = read_yaml(run_dir / "paper" / "story" / "paper_story_contract.yaml")
    if not isinstance(contract, dict) or result.status != "done":
        contract = build_mock_paper_story_contract(slug, field, run_dir)
        contract["known_uncertainties"].append(f"paper_story_controller failed: {result.error or result.status}")
    contract = normalize_paper_story_contract(contract)
    write_yaml(run_dir / "paper" / "story" / "paper_story_contract.yaml", contract)
    write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", contract)
    write_yaml(run_dir / "audits" / "paper_story_contract_gate.yaml", paper_story_contract_gate(contract))
    return contract


def build_paper_story_alignment_prompt(section: str) -> str:
    return f"""# Paper Story Contract Alignment

Section just completed: `{section}`.

Read only the allowed files. Update the paper-level story contract so later
sections use the best current evidence and section feedback.

Inputs may include:
- paper/story/paper_story_contract.yaml
- manuscript/{'abstract.tex and manuscript/introduction.tex' if section == 'abstract_intro' else section + '.tex'}
- sections/{section}/story/evidence_to_story_plan.yaml
- sections/{section}/story/story_contract.yaml
- sections/{section}/reviews/section_review.yaml
- sections/{section}/audits/section_score_gate.yaml
- skill/prompts/paper_story_aligner_prompt.md

Write:
- paper/story/paper_story_contract_after_{section}.yaml

Rules:
- Preserve schema_version `nature_orchestrator.paper_story_contract.v2`.
- Keep the current central thesis unless the section evidence requires
  narrower wording.
- Append a concrete entry to `section_feedback_updates` for `{section}`.
- Add downstream dependency notes for the next section writer.
- Do not invent new evidence, numbers, methods or claims.
- Keep this as a coordination artifact, not prose.
"""


def _mock_align_paper_story_contract(contract: dict[str, Any], section: str) -> dict[str, Any]:
    updated = dict(contract)
    updates = list(updated.get("section_feedback_updates") or [])
    updates.append(
        {
            "section": section,
            "status": "aligned",
            "source": f"sections/{section}/reviews/section_review.yaml",
            "contract_changes": [
                f"Recorded {section} output and review as downstream context.",
            ],
        }
    )
    notes = list(updated.get("downstream_dependency_notes") or [])
    notes.append(
        {
            "after_section": section,
            "note": f"Use the completed {section} evidence and review to narrow later section claims.",
        }
    )
    updated["section_feedback_updates"] = updates
    updated["downstream_dependency_notes"] = notes
    updated.setdefault("schema_version", "nature_orchestrator.paper_story_contract.v2")
    return normalize_paper_story_contract(updated)


def write_paper_story_alignment(run_dir: Path, args: argparse.Namespace, section: str) -> dict[str, Any]:
    current_path = run_dir / "paper" / "story" / "paper_story_contract.yaml"
    current = read_yaml(current_path)
    if not isinstance(current, dict) or not current:
        return {}
    target_rel = f"paper/story/paper_story_contract_after_{section}.yaml"
    skill_version = full_paper_skill_version(getattr(args, "full_paper_polisher_profile", "v2_4"))
    allowed_files = [
        "paper/story/paper_story_contract.yaml",
        f"sections/{section}/story/evidence_to_story_plan.yaml",
        f"sections/{section}/story/story_contract.yaml",
        f"sections/{section}/reviews/section_review.yaml",
        f"sections/{section}/audits/section_score_gate.yaml",
    ]
    if section == "abstract_intro":
        allowed_files.extend(["manuscript/abstract.tex", "manuscript/introduction.tex"])
    else:
        allowed_files.append(f"manuscript/{section}.tex")
    allowed_files.append(copy_skill_file_to_run(run_dir, "prompts/paper_story_aligner_prompt.md", skill_version))
    if getattr(args, "agent_backend", "mock") == "mock":
        updated = _mock_align_paper_story_contract(current, section)
        write_yaml(run_dir / target_rel, updated)
        write_yaml(current_path, updated)
        write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", updated)
        write_yaml(run_dir / "audits" / f"paper_story_contract_gate_after_{section}.yaml", paper_story_contract_gate(updated))
        return updated
    backend = "api" if getattr(args, "agent_backend", "api") in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role=f"paper_story_aligner_{section}",
        run_dir=run_dir,
        prompt=build_paper_story_alignment_prompt(section),
        allowed_files=allowed_files,
        output_contract={"files": {target_rel: "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / f"paper_story_aligner_{section}.agent_result.yaml", result.__dict__)
    updated = read_yaml(run_dir / target_rel)
    if isinstance(updated, dict):
        updated = normalize_paper_story_contract(updated)
    gate = paper_story_contract_gate(updated if isinstance(updated, dict) else {})
    if not isinstance(updated, dict) or result.status != "done" or gate["status"] != "passed":
        updated = _mock_align_paper_story_contract(current, section)
        uncertainties = list(updated.get("known_uncertainties") or [])
        uncertainties.append(f"paper_story_aligner_{section} failed or produced invalid contract")
        updated["known_uncertainties"] = uncertainties
        write_yaml(run_dir / target_rel, updated)
        gate = paper_story_contract_gate(updated)
    write_yaml(current_path, updated)
    write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", updated)
    write_yaml(run_dir / "audits" / f"paper_story_contract_gate_after_{section}.yaml", gate)
    return updated


def attach_paper_story_contract(section_run_root: Path, full_run_dir: Path) -> None:
    source = full_run_dir / "paper" / "story" / "paper_story_contract.yaml"
    if not source.exists():
        return
    target = section_run_root / "paper" / "story" / "paper_story_contract.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def attach_paper_context_artifacts(section_run_root: Path, full_run_dir: Path) -> None:
    artifacts = [
        (
            full_run_dir / "paper" / "story" / "paper_story_contract.yaml",
            section_run_root / "paper" / "story" / "paper_story_contract.yaml",
        ),
        (
            full_run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml",
            section_run_root / "paper" / "evidence" / "evidence_claim_ledger.yaml",
        ),
    ]
    for source, target in artifacts:
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def build_cross_section_reviewer_prompt() -> str:
    return """# Full-Paper Cross-Section Review

Read only the allowed files. Review the assembled manuscript as a single paper,
not as four independent sections.

Inputs:
- paper/story/paper_story_contract.yaml when present
- paper/story/paper_story_plan.yaml
- paper/evidence/evidence_claim_ledger.yaml when present
- audits/cross_section_evidence_ledger.yaml when present
- manuscript/abstract.tex
- manuscript/introduction.tex
- manuscript/results.tex
- manuscript/discussion.tex
- sections/*/reviews/section_review.yaml
- skill/prompts/cross_section_reviewer_prompt.md
- skill/rubrics/cross_section_rubric.yaml

Write:
- reviews/cross_section_review.yaml

The YAML must include:
- schema_version: nature_orchestrator.cross_section_review.v1
- status: pass | revise | fail
- overall_score: number from 1 to 5
- accepted_by_reviewers: true only when status is pass and no blocking issues remain
- blocking_issues: list
- targeted_revisions: list
- central_thesis_consistency
- evidence_support
- discussion_boundary
- repetition_control
- claim_boundary_consistency

Use the pass threshold 4.2. Block if the Abstract/Introduction promise
paper-specific study claims not supported by Results, Discussion introduces new
Results, or the central claim/qualifiers conflict across sections. Do not
require general Introduction background or motivation statements to be visible
in Results unless they contain exact study values, paper-specific empirical
findings, causal claims, or unsupported mechanistic claims. If a broad
background sentence is too strong, mark it as citation/background-safety advice,
not a blocking cross-section support failure. Do not make every unsupported
method parameter a blocking failure: a missing dose, injection volume, buffer,
acquisition setting, strain detail or implementation parameter is
minor_nonblocking unless it changes the comparator, effect direction, sample
scope, claim strength or interpretation. Ask for removal/softening, but do not
fail the paper for a small non-central method detail. If
`paper_story_contract.yaml` is present, use it as the authoritative soft
controller and report any section that ignored or correctly narrowed the
contract.

If `audits/cross_section_evidence_ledger.yaml` is present, use it as the
claim-support map. Do not re-infer unsupported claims from scratch when the
ledger already identifies missing support, exact-value mismatches, direction
conflicts or repetition overload.
"""


def build_cross_section_evidence_ledger_prompt() -> str:
    return """# Cross-Section Evidence Ledger

Read the actual manuscript sections and the paper story contract. Build a
ledger that compares planned anchors against what the current manuscript
actually promises.

Use the plan as a template, but do not trust the plan as evidence of what was
written. Inspect the actual Abstract, Introduction, Results and Discussion.

Inputs:
- paper/story/paper_story_contract.yaml
- paper/story/paper_story_plan.yaml
- paper/evidence/evidence_claim_ledger.yaml when present
- manuscript/abstract.tex
- manuscript/introduction.tex
- manuscript/results.tex
- manuscript/discussion.tex
- sections/*/reviews/section_review.yaml
- sections/*/story/evidence_to_story_plan.yaml
- skill/prompts/cross_section_evidence_ledger_prompt.md

Write:
- audits/cross_section_evidence_ledger.yaml

The YAML must include:
- schema_version: nature_orchestrator.cross_section_evidence_ledger.v1
- abstract_promises: list of claims made by the current Abstract, each with
  `claim`, `exact_values`, `results_support`, and `status`
- intro_promises: list of claims made by the current Introduction, each with
  `claim`, `exact_values`, `results_support`, and `status`
- discussion_claims: list of claims made by the current Discussion, each with
  `claim`, `exact_values`, `results_support`, and `status`
- background_context_claims: optional list of broad Introduction background or
  motivation claims that do not need Results support unless over-specific
- results_support_lines: list of Results lines or compact excerpts that support
  the promises; include `anchor` and `line`
- missing_support: claims in Abstract/Introduction/Discussion with no visible
  Results support
- exact_value_mismatches: exact values promised outside Results that are absent,
  rounded differently, or contradicted in Results
- direction_conflicts: treatment/effect/comparator directions that conflict
  across sections
- repetition_overload: anchors repeated too often across sections
- recoverable_results_repairs: missing Results support lines that can be added
  because the value/claim is present in the paper story contract or section
  evidence plans; include `anchor`, `source`, and `suggested_results_line`

Consistency rules:
- Classify each outside-Results claim exactly once. If current Results visibly
  support the claim, mark that claim `supported` or `partially_supported` and
  add the supporting excerpt to `results_support_lines`; do not also include it
  in `missing_support`.
- Do not put broad Introduction background in `missing_support` merely because
  Results do not discuss it. Background belongs in `background_context_claims`
  when it frames the field or motivation without paper-specific exact values,
  new mechanisms, or causal conclusions.
- Put an Introduction statement in `missing_support` only when it promises a
  study-specific finding, exact value, comparator, mechanism, scope boundary or
  contribution that the Results should visibly support.
- Use `recoverable_results_repairs` only when current Results do not yet contain
  the support line but an allowed paper contract, section plan or section review
  directly supports adding one. If the suggested repair has already been added
  to current Results, move it into `results_support_lines` instead.
- Do not mark a claim `not_visible_in_results` merely because it originated from
  Discussion or a plan. Inspect the current Results text first.

This is not a quality review. It is a claim-support accounting artifact for the
cross-section reviewer and full-paper polisher.
"""


def _compact_sentences(text: str, limit: int = 6) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not cleaned:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return [sentence[:500] for sentence in sentences if sentence.strip()][:limit]


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:\s*(?:%|MHz|nm|ns|mm|ms|Å|\\AA))?", text))


def build_mock_cross_section_evidence_ledger(run_dir: Path) -> dict[str, Any]:
    abstract = read_text(run_dir / "manuscript" / "abstract.tex")
    introduction = read_text(run_dir / "manuscript" / "introduction.tex")
    results = read_text(run_dir / "manuscript" / "results.tex")
    discussion = read_text(run_dir / "manuscript" / "discussion.tex")
    contract = read_yaml(run_dir / "paper" / "story" / "paper_story_contract.yaml")
    result_lines = _compact_sentences(results, limit=10)
    result_numbers = _numeric_tokens(results)

    def promise_rows(section_text: str, section: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sentence in _compact_sentences(section_text, limit=5):
            numbers = sorted(_numeric_tokens(sentence))
            supported = bool(sentence and any(token in result_numbers for token in numbers)) if numbers else bool(result_lines)
            rows.append(
                {
                    "section": section,
                    "claim": sentence,
                    "exact_values": numbers,
                    "results_support": result_lines[0] if supported and result_lines else "",
                    "status": "supported" if supported else "missing_support",
                }
            )
        return rows

    exact_value_mismatches = []
    for section, section_text in [("abstract", abstract), ("introduction", introduction), ("discussion", discussion)]:
        missing = sorted(_numeric_tokens(section_text) - result_numbers)
        if missing:
            exact_value_mismatches.append({"section": section, "values": missing})

    recoverable_repairs = []
    for anchor in contract.get("must_preserve_evidence_anchors") or []:
        anchor_text = str(anchor)
        anchor_numbers = _numeric_tokens(anchor_text)
        if anchor_numbers and not anchor_numbers.issubset(result_numbers):
            recoverable_repairs.append(
                {
                    "anchor": anchor_text,
                    "source": "paper_story_contract.must_preserve_evidence_anchors",
                    "suggested_results_line": anchor_text,
                }
            )

    ledger = {
        "schema_version": "nature_orchestrator.cross_section_evidence_ledger.v1",
        "abstract_promises": promise_rows(abstract, "abstract"),
        "intro_promises": promise_rows(introduction, "introduction"),
        "discussion_claims": promise_rows(discussion, "discussion"),
        "results_support_lines": [
            {"anchor": f"results_line_{index + 1}", "line": line}
            for index, line in enumerate(result_lines)
        ],
        "missing_support": [],
        "exact_value_mismatches": exact_value_mismatches,
        "direction_conflicts": [],
        "repetition_overload": [],
        "recoverable_results_repairs": recoverable_repairs,
    }
    ledger["missing_support"] = [
        {"section": row["section"], "claim": row["claim"]}
        for row in ledger["abstract_promises"] + ledger["intro_promises"] + ledger["discussion_claims"]
        if row["status"] == "missing_support"
    ]
    return ledger


def write_cross_section_evidence_ledger(run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.agent_backend == "mock":
        ledger = build_mock_cross_section_evidence_ledger(run_dir)
        write_yaml(run_dir / "audits" / "cross_section_evidence_ledger.yaml", ledger)
        write_yaml(run_dir / "audits" / "cross_section_evidence_ledger_gate.yaml", cross_section_evidence_ledger_gate(ledger))
        return ledger

    skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
    allowed_files = [
        "paper/story/paper_story_contract.yaml",
        "paper/story/paper_story_plan.yaml",
        "paper/evidence/evidence_claim_ledger.yaml",
        "audits/cross_section_evidence_ledger.yaml",
        "manuscript/abstract.tex",
        "manuscript/introduction.tex",
        "manuscript/results.tex",
        "manuscript/discussion.tex",
        "sections/results/reviews/section_review.yaml",
        "sections/discussion/reviews/section_review.yaml",
        "sections/introduction/reviews/section_review.yaml",
        "sections/abstract/reviews/section_review.yaml",
        "sections/results/story/evidence_to_story_plan.yaml",
        "sections/discussion/story/evidence_to_story_plan.yaml",
        "sections/abstract_intro/story/evidence_to_story_plan.yaml",
        copy_skill_file_to_run(run_dir, "prompts/cross_section_evidence_ledger_prompt.md", skill_version),
    ]
    backend = "api" if args.agent_backend in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role="cross_section_evidence_ledger",
        run_dir=run_dir,
        prompt=build_cross_section_evidence_ledger_prompt(),
        allowed_files=allowed_files,
        output_contract={"files": {"audits/cross_section_evidence_ledger.yaml": "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / "cross_section_evidence_ledger.agent_result.yaml", result.__dict__)
    ledger = read_yaml(run_dir / "audits" / "cross_section_evidence_ledger.yaml")
    gate = cross_section_evidence_ledger_gate(ledger if isinstance(ledger, dict) else {})
    if not isinstance(ledger, dict) or result.status != "done" or gate["status"] != "passed":
        ledger = build_mock_cross_section_evidence_ledger(run_dir)
        ledger["missing_support"].append(
            {
                "section": "ledger",
                "claim": f"cross_section_evidence_ledger failed or produced invalid ledger: {result.error or result.status}",
            }
        )
        write_yaml(run_dir / "audits" / "cross_section_evidence_ledger.yaml", ledger)
        gate = cross_section_evidence_ledger_gate(ledger)
    write_yaml(run_dir / "audits" / "cross_section_evidence_ledger_gate.yaml", gate)
    return ledger


def _external_target_files(section: str | None = None) -> list[str]:
    if section == "abstract":
        return ["manuscript/abstract.tex"]
    if section == "introduction":
        return ["manuscript/introduction.tex"]
    if section == "discussion":
        return ["manuscript/discussion.tex"]
    return ["manuscript/abstract.tex", "manuscript/introduction.tex", "manuscript/discussion.tex"]


def _repair_action(
    issue_id: str,
    source: str,
    edit_type: str,
    affected_sections: list[str],
    target_files: list[str],
    problem: str,
    desired_outcome: str,
    evidence_basis: str,
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "source": source,
        "edit_type": edit_type,
        "affected_sections": affected_sections,
        "target_files": target_files,
        "problem": problem,
        "desired_outcome": desired_outcome,
        "evidence_basis": evidence_basis,
        "blocking": blocking,
    }


def build_mock_cross_section_repair_plan(run_dir: Path, round_index: int) -> dict[str, Any]:
    ledger = read_yaml(run_dir / "audits" / "cross_section_evidence_ledger.yaml")
    review = read_yaml(run_dir / "reviews" / "cross_section_review.yaml")
    if not isinstance(ledger, dict):
        ledger = {}
    if not isinstance(review, dict):
        review = {}
    actions: list[dict[str, Any]] = []
    for index, repair in enumerate(ledger.get("recoverable_results_repairs") or [], start=1):
        if not isinstance(repair, dict):
            continue
        anchor = str(repair.get("anchor") or f"recoverable_anchor_{index}")
        suggested = str(repair.get("suggested_results_line") or anchor)
        actions.append(
            _repair_action(
                issue_id=f"recoverable_results_repair_{index:03d}",
                source="audits/cross_section_evidence_ledger.yaml:recoverable_results_repairs",
                edit_type="add_results_support",
                affected_sections=["results"],
                target_files=["manuscript/results.tex"],
                problem=f"Results is missing recoverable support for {anchor}.",
                desired_outcome=f"Add or harmonize a bounded Results support line: {suggested}",
                evidence_basis=str(repair.get("source") or "recoverable_results_repairs"),
            )
        )
    mismatch_index = 0
    for mismatch in ledger.get("exact_value_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        status_text = " ".join(
            str(mismatch.get(key) or "")
            for key in ["status", "results_status", "ledger_status"]
        ).lower()
        if "present_same_value" in status_text or "same_value" in status_text:
            continue
        mismatch_index += 1
        problem = str(mismatch.get("claim") or mismatch)
        outside_value = str(mismatch.get("outside_results_value") or "")
        results_value = str(mismatch.get("results_value") or "")
        actions.append(
            _repair_action(
                issue_id=f"exact_value_mismatch_{mismatch_index:03d}",
                source="audits/cross_section_evidence_ledger.yaml:exact_value_mismatches",
                edit_type="harmonize_method_label" if outside_value or results_value else "soften_external_claim",
                affected_sections=["abstract", "introduction", "results"],
                target_files=["manuscript/abstract.tex", "manuscript/introduction.tex", "manuscript/results.tex"],
                problem=problem,
                desired_outcome=(
                    "Use one compatible, Results-supported label across sections"
                    if outside_value or results_value
                    else "Remove or soften the unsupported exact value outside Results"
                ),
                evidence_basis=f"outside_results_value={outside_value}; results_value={results_value}",
            )
        )
    for index, conflict in enumerate(ledger.get("direction_conflicts") or [], start=1):
        actions.append(
            _repair_action(
                issue_id=f"direction_conflict_{index:03d}",
                source="audits/cross_section_evidence_ledger.yaml:direction_conflicts",
                edit_type="harmonize_direction",
                affected_sections=["abstract", "introduction", "results", "discussion"],
                target_files=[
                    "manuscript/abstract.tex",
                    "manuscript/introduction.tex",
                    "manuscript/results.tex",
                    "manuscript/discussion.tex",
                ],
                problem=str(conflict),
                desired_outcome="Make the comparator, direction and qualifier identical across affected sections.",
                evidence_basis="direction_conflicts",
            )
        )
    for index, missing in enumerate(ledger.get("missing_support") or [], start=1):
        if not isinstance(missing, dict):
            continue
        section = str(missing.get("section") or "")
        if normalize_repair_section(section) == "results":
            continue
        target_files = _external_target_files(section if section in {"abstract", "introduction", "discussion"} else None)
        actions.append(
            _repair_action(
                issue_id=f"missing_support_{index:03d}",
                source="audits/cross_section_evidence_ledger.yaml:missing_support",
                edit_type="soften_external_claim",
                affected_sections=[section] if section else ["abstract", "introduction", "discussion"],
                target_files=target_files,
                problem=str(missing.get("claim") or missing),
                desired_outcome="Remove the unsupported promise outside Results or replace it with a broader Results-supported phrase.",
                evidence_basis="missing_support",
            )
        )
    if not actions:
        for index, issue in enumerate(review.get("blocking_issues") or [], start=1):
            if isinstance(issue, dict):
                sections = [str(section) for section in _as_list(issue.get("sections")) if str(section)]
                problem = str(issue.get("issue") or issue.get("problem") or issue)
                desired = str(issue.get("required_fix") or "Resolve the blocking cross-section issue.")
            else:
                sections = []
                problem = str(issue)
                desired = "Resolve the blocking cross-section issue."
            target_files: list[str] = []
            for section in sections:
                normalized = normalize_repair_section(section)
                if normalized == "results":
                    target_files.append("manuscript/results.tex")
                elif normalized == "discussion":
                    target_files.append("manuscript/discussion.tex")
                elif normalized == "abstract_intro":
                    target_files.extend(["manuscript/abstract.tex", "manuscript/introduction.tex"])
            if not target_files:
                target_files = [
                    "manuscript/abstract.tex",
                    "manuscript/introduction.tex",
                    "manuscript/discussion.tex",
                ]
            actions.append(
                _repair_action(
                    issue_id=f"cross_review_blocking_issue_{index:03d}",
                    source="reviews/cross_section_review.yaml:blocking_issues",
                    edit_type="soften_external_claim",
                    affected_sections=sections or ["abstract", "introduction", "discussion"],
                    target_files=sorted(set(target_files)),
                    problem=problem,
                    desired_outcome=desired,
                    evidence_basis="cross_section_review.blocking_issues",
                )
            )
    return {
        "schema_version": "nature_orchestrator.cross_section_repair_plan.v1",
        "round_index": round_index,
        "repair_actions": actions,
        "unresolved_or_deferred": [],
    }


def sanitize_repair_plan_for_recoverable_results(plan: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Avoid deleting summary-section anchors that should be fixed by adding Results support first."""

    recoverable = ledger.get("recoverable_results_repairs") if isinstance(ledger, dict) else []
    if not recoverable:
        return plan
    sanitized = dict(plan)
    kept: list[Any] = []
    deferred = list(sanitized.get("unresolved_or_deferred") or [])
    for action in sanitized.get("repair_actions") or []:
        if not isinstance(action, dict):
            kept.append(action)
            continue
        source = str(action.get("source") or "").lower()
        edit_type = str(action.get("edit_type") or "").lower()
        target_files = " ".join(str(item).lower() for item in _as_list(action.get("target_files")))
        affected_sections = {
            normalize_repair_section(str(section))
            for section in _as_list(action.get("affected_sections"))
        }
        touches_front_matter = (
            "abstract_intro" in affected_sections
            or "abstract" in affected_sections
            or "introduction" in affected_sections
            or "manuscript/abstract.tex" in target_files
            or "manuscript/introduction.tex" in target_files
        )
        if "exact_value_mismatches" in source and edit_type in {
            "soften_external_claim",
            "remove_unsupported_claim",
            "harmonize_method_label",
            "harmonize_direction",
        }:
            deferred.append(
                {
                    "issue_id": action.get("issue_id"),
                    "reason": (
                        "deferred because recoverable Results support exists; "
                        "rerun the cross-section ledger after adding Results support "
                        "before softening Abstract, Introduction or Discussion anchors"
                    ),
                    "original_action": action,
                }
            )
            continue
        if "missing_support" in source and touches_front_matter and edit_type in {
            "soften_external_claim",
            "remove_unsupported_claim",
            "harmonize_method_label",
            "harmonize_direction",
        }:
            deferred.append(
                {
                    "issue_id": action.get("issue_id"),
                    "reason": (
                        "deferred because recoverable Results support exists and "
                        "this action would edit Abstract/Introduction before the "
                        "new Results support can be re-ledgered"
                    ),
                    "original_action": action,
                }
            )
            continue
        kept.append(action)
    sanitized["repair_actions"] = kept
    sanitized["unresolved_or_deferred"] = deferred
    return sanitized


def _merge_repair_actions(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    if merged.get("repair_actions"):
        merged.setdefault("schema_version", "nature_orchestrator.cross_section_repair_plan.v1")
        merged.setdefault("round_index", fallback.get("round_index", 1))
        merged.setdefault("unresolved_or_deferred", [])
        existing = {
            str(action.get("issue_id"))
            for action in merged.get("repair_actions") or []
            if isinstance(action, dict)
        }
        actions = list(merged.get("repair_actions") or [])
        for action in fallback.get("repair_actions") or []:
            if not isinstance(action, dict):
                continue
            source = str(action.get("source") or "")
            edit_type = str(action.get("edit_type") or "")
            # Keep the anti-bloat behavior from API plans: do not append extra
            # repairs when the planner already chose a narrow repair path. The
            # exception is recoverable Results support: it must be added before
            # outside-Results anchors are softened, otherwise the repair loop can
            # erase contribution-defining numbers from the Abstract/Introduction.
            # Still add ledger-proven unsupported outside-Results claims, because
            # those are small softening/removal edits and can otherwise surface
            # only after the final review round.
            if "recoverable_results_repairs" in source and edit_type == "add_results_support":
                pass
            elif "missing_support" not in source or edit_type not in {
                "soften_external_claim",
                "remove_unsupported_claim",
            }:
                continue
            issue_id = str(action.get("issue_id"))
            if issue_id in existing:
                continue
            actions.append(action)
            existing.add(issue_id)
        merged["repair_actions"] = actions
        return merged
    existing = {
        str(action.get("issue_id"))
        for action in merged.get("repair_actions") or []
        if isinstance(action, dict)
    }
    actions = list(merged.get("repair_actions") or [])
    for action in fallback.get("repair_actions") or []:
        if isinstance(action, dict) and str(action.get("issue_id")) not in existing:
            actions.append(action)
    merged["repair_actions"] = actions
    merged.setdefault("schema_version", "nature_orchestrator.cross_section_repair_plan.v1")
    merged.setdefault("round_index", fallback.get("round_index", 1))
    merged.setdefault("unresolved_or_deferred", [])
    return merged


def build_cross_section_repair_planner_prompt(round_index: int) -> str:
    return f"""# Cross-Section Targeted Repair Planner Round {round_index}

Read the current cross-section review and evidence ledger. Write a narrow,
issue-level repair plan instead of rewriting the whole paper.

Inputs:
- reviews/cross_section_review.yaml
- audits/cross_section_evidence_ledger.yaml
- manuscript/abstract.tex
- manuscript/introduction.tex
- manuscript/results.tex
- manuscript/discussion.tex
- skill/prompts/cross_section_repair_planner_prompt.md

Write:
- repairs/cross_section_repair_plan.yaml

The YAML schema is `nature_orchestrator.cross_section_repair_plan.v1` and must
contain `round_index`, `repair_actions` and `unresolved_or_deferred`.

Each repair action must include:
- issue_id
- source
- edit_type: add_results_support | soften_external_claim |
  harmonize_method_label | harmonize_direction | remove_unsupported_claim |
  trim_repetition
- affected_sections
- target_files
- problem
- desired_outcome
- evidence_basis
- blocking

Rules:
- Do not ask for a whole-paper rewrite.
- Prefer the smallest section-local patch that resolves the blocking issue.
- In round 2 or later, prefer softening Abstract, Introduction or Discussion
  over adding more Results support unless the reviewer explicitly asks for a
  recoverable Results line.
- If the ledger has `recoverable_results_repairs`, create a Results action.
- If a recoverable Results action can support an exact value, do not also create
  a same-round Abstract/Introduction/Discussion softening action for that same
  exact value. First add Results support, then let the next ledger/review decide
  whether any outside-Results wording still needs narrowing.
- When recoverable Results support exists, avoid same-round actions that edit
  Abstract or Introduction for `missing_support` created only by the current
  Results omission. Patch Results first; re-evaluate support in the next round.
- You may still patch a Discussion-only unsupported claim in the same round when
  it is not resolved by adding Results support.
- If the ledger has outside-Results `missing_support` rows, create a small
  softening/removal action for those section files even when another review
  issue is more prominent.
- If the ledger has exact-value or method-label mismatches, create a
  harmonization action that names both the outside-Results and Results wording.
- Preserve contribution-defining exact anchors in Abstract and Introduction when
  they are directly recoverable and can be made Results-supported.
- If support is not recoverable, soften or remove the claim outside Results.
"""


def write_cross_section_repair_plan(run_dir: Path, args: argparse.Namespace, round_index: int) -> dict[str, Any]:
    fallback = build_mock_cross_section_repair_plan(run_dir, round_index)
    if args.agent_backend == "mock":
        plan = fallback
        write_yaml(run_dir / "repairs" / "cross_section_repair_plan.yaml", plan)
        write_yaml(run_dir / "audits" / "cross_section_repair_plan_gate.yaml", cross_section_repair_plan_gate(plan))
        return plan
    skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
    allowed_files = [
        "reviews/cross_section_review.yaml",
        "audits/cross_section_evidence_ledger.yaml",
        "manuscript/abstract.tex",
        "manuscript/introduction.tex",
        "manuscript/results.tex",
        "manuscript/discussion.tex",
        copy_skill_file_to_run(run_dir, "prompts/cross_section_repair_planner_prompt.md", skill_version),
    ]
    backend = "api" if args.agent_backend in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role=f"cross_section_repair_planner_{round_index:03d}",
        run_dir=run_dir,
        prompt=build_cross_section_repair_planner_prompt(round_index),
        allowed_files=allowed_files,
        output_contract={"files": {"repairs/cross_section_repair_plan.yaml": "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / f"cross_section_repair_planner_{round_index:03d}.agent_result.yaml", result.__dict__)
    plan = read_yaml(run_dir / "repairs" / "cross_section_repair_plan.yaml")
    if not isinstance(plan, dict) or result.status != "done":
        plan = fallback
    else:
        plan = _merge_repair_actions(plan, fallback)
    ledger = read_yaml(run_dir / "audits" / "cross_section_evidence_ledger.yaml")
    plan = sanitize_repair_plan_for_recoverable_results(plan, ledger if isinstance(ledger, dict) else {})
    gate = cross_section_repair_plan_gate(plan)
    if gate["status"] != "passed":
        plan = sanitize_repair_plan_for_recoverable_results(fallback, ledger if isinstance(ledger, dict) else {})
        gate = cross_section_repair_plan_gate(plan)
    write_yaml(run_dir / "repairs" / "cross_section_repair_plan.yaml", plan)
    write_yaml(run_dir / "audits" / "cross_section_repair_plan_gate.yaml", gate)
    return plan


def build_targeted_section_patcher_prompt(section: str, round_index: int) -> str:
    return f"""# Targeted Cross-Section Patcher: {section} Round {round_index}

Patch only the current section files needed to resolve the repair actions that
target `{section}`.

Inputs:
- repairs/cross_section_repair_plan.yaml
- reviews/cross_section_review.yaml
- audits/cross_section_evidence_ledger.yaml
- current manuscript section file(s)
- skill/prompts/targeted_section_patcher_prompt.md

Rules:
- Do not rewrite unaffected sections.
- Do not rewrite the whole paper for style.
- Apply every repair action that targets this section.
- Preserve all section-local evidence anchors that already passed section review.
- Add Results support only when the repair plan cites recoverable evidence.
- If support is unrecoverable, soften or remove the outside-Results claim.
- For Abstract, Introduction and Discussion, inspect the current Results text
  before softening exact values. If the same value, a clearer exact value, or an
  equivalent expression is now visible in Results, preserve the outside-Results
  anchor and only adjust wording for calibration.
- If the repair plan contains both `add_results_support` and
  `soften_external_claim` for the same anchor family, do not delete the
  outside-Results anchor in the same round; let the next cross-section review
  decide after Results support has been added.
- Do not replace contribution-defining numbers with generic phrases such as
  "small subset", "validated model", "more visible" or "more concentrated" when
  supported exact values are available.
- Keep LaTeX structure intact and write only the declared output files.
"""


def _target_files_for_repair_section(section: str) -> list[str]:
    if section == "results":
        return ["manuscript/results.tex"]
    if section == "discussion":
        return ["manuscript/discussion.tex"]
    if section == "abstract_intro":
        return ["manuscript/abstract.tex", "manuscript/introduction.tex"]
    return []


def run_targeted_cross_section_patchers(
    run_dir: Path,
    args: argparse.Namespace,
    round_index: int,
    repair_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    target_sections = repair_plan_target_sections(repair_plan)
    if not target_sections:
        return records
    if args.agent_backend == "mock":
        for section in target_sections:
            record = {"section": section, "status": "done", "returncode": 0, "error": ""}
            records.append(record)
            write_yaml(run_dir / "repairs" / f"targeted_patch_round_{round_index:03d}_{section}.yaml", record)
        assemble_final(run_dir)
        return records
    skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
    backend = "api" if args.agent_backend == "api" else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    for section in target_sections:
        target_files = _target_files_for_repair_section(section)
        allowed_files = [
            "repairs/cross_section_repair_plan.yaml",
            "reviews/cross_section_review.yaml",
            "audits/cross_section_evidence_ledger.yaml",
            *target_files,
            copy_skill_file_to_run(run_dir, "prompts/targeted_section_patcher_prompt.md", skill_version),
        ]
        result = run_agent(
            role=f"targeted_{section}_patcher_{round_index:03d}",
            run_dir=run_dir,
            prompt=build_targeted_section_patcher_prompt(section, round_index),
            allowed_files=allowed_files,
            output_contract={"files": {target_file: "latex" for target_file in target_files}},
            backend=backend,
            timeout=args.api_timeout if backend == "api" else args.codex_timeout,
            codex_binary=args.codex_binary,
            api_config=api_config,
        )
        write_yaml(run_dir / "logs" / f"targeted_{section}_patcher_{round_index:03d}.agent_result.yaml", result.__dict__)
        record = {"section": section, "status": result.status, "returncode": result.returncode, "error": result.error}
        records.append(record)
        write_yaml(run_dir / "repairs" / f"targeted_patch_round_{round_index:03d}_{section}.yaml", record)
        if result.status != "done":
            break
    assemble_final(run_dir)
    return records


def build_full_paper_polisher_prompt(round_index: int, full_paper_polisher_profile: str = "v2_4") -> str:
    ledger_rules = ""
    if full_paper_polisher_profile in {"v2_7_1", "nature_writing"}:
        ledger_rules = """
Ledger-aware repair:
- Read `audits/cross_section_evidence_ledger.yaml` before editing.
- Do not default to deleting exact anchors when the ledger lists them under
  `recoverable_results_repairs`.
- If a missing support problem can be repaired from
  `recoverable_results_repairs`, add the missing Results support line using the
  suggested wording or an equally bounded sentence.
- Only add a Results support line when the value or claim is present in the
  paper story contract, a section evidence plan, or a section review. Otherwise
  soften or remove the unsupported claim outside Results.
- If the reviewer flags an unsupported parameter category, comparator, temporal
  order, or causal sequence, do not infer it from adjacent evidence. Either add
  an explicit bounded Results line only when the ledger source directly supports
  that exact relation, or remove/narrow the claim from Introduction, Abstract or
  Discussion.
- Do not turn calibration variables into unsupported sweep variables. For
  example, if Results support displacement/cycle and barrier voltage but not a
  speed or velocity sweep, remove "velocity" from the framing rather than
  implying it was selected from the map.
- Do not invent event ordering. If Results establish separated-site fidelity or
  conditional measurement but not the order of entangling, shuttling and
  readout, phrase the claim without "subsequently", "before", "after" or other
  temporal sequence language.
- Use `exact_value_mismatches` and `direction_conflicts` as required checklist
  items. Resolve direction conflicts by making Results, Abstract, Introduction
  and Discussion use the same comparator and effect direction.
- Use `repetition_overload` to reduce repeated anchors outside Results; keep the
  most precise statement in Results and the most compressed version in Abstract.
"""
    return f"""# Full-Paper Targeted Polish Round {round_index}

Read the current manuscript sections and `reviews/cross_section_review.yaml`.
Revise only the cross-section problems raised by the reviewer.

Write all four files:
- manuscript/abstract.tex
- manuscript/introduction.tex
- manuscript/results.tex
- manuscript/discussion.tex

Rules:
- Keep the section order and LaTeX section boundaries.
- Do not invent new evidence, numbers, figure references or claims.
- If a number/claim appears in one section but is unsupported by another section,
  prefer aligning wording conservatively rather than adding unseen evidence.
- If the reviewer offers "add to Results or remove from Discussion/Intro/Abstract",
  first check `audits/cross_section_evidence_ledger.yaml`. When the same item is
  listed under `recoverable_results_repairs`, add exactly one bounded Results
  support line. Choose removal/softening only when the ledger does not directly
  support a recoverable repair.
- Do not add new result-level facts to Results during full-paper polish; Results
  can only be compressed, clarified or made consistent with its existing content,
  except for ledger `recoverable_results_repairs` that are directly supported by
  the allowed paper contract, section plans or section reviews.
- Before finish, make a claim ledger for yourself: every number, figure-specific
  mechanism, named qubit/object, comparator and protocol detail in Abstract,
  Introduction and Discussion must be visibly supported by Results text. If not,
  remove it or replace it with a broader Results-supported phrase.
- Treat every example named under `blocking_issues` as a required checklist item.
  For each named detail, either find it verbatim or near-verbatim in Results, or
  delete/soften it from Abstract, Introduction and Discussion. Do not leave a
  named blocking example unresolved because the overall story still sounds good.
- For each `missing_support` item in the cross-section ledger, write down the
  exact sentence that creates the problem before editing. If the current Results
  do not already contain a visible support line and the ledger does not list the
  item under `recoverable_results_repairs`, remove or narrow that sentence
  outside Results. Do not preserve it by adding a new Results fact.
- If you choose to use a `recoverable_results_repairs` item, add one bounded
  Results support sentence and also remove any stronger version from Abstract,
  Introduction or Discussion. Do not leave the same claim marked as missing.
- If a targeted revision asks for a compact Results scope/support line and the
  ledger lists a matching `recoverable_results_repairs` entry, apply it. Do not
  ignore recoverable support repairs in favor of style-only compression.
- Exact numeric values in Abstract should only remain when the same values are in
  Results. Otherwise use directional phrasing.
- Do not use repetition control to erase decisive section anchors that the
  section reviewer already accepted. Read `sections/results/reviews/section_review.yaml`,
  `sections/discussion/reviews/section_review.yaml` and
  `audits/final_section_anchor_gate.yaml` when present. If the final anchor gate
  says Results or Discussion dropped reviewer-confirmed numeric anchors, restore
  them in the same section unless the cross-section evidence ledger explicitly
  marks them unsupported.
- For Discussion, compression means avoid a full Results recap, not replacing
  central magnitudes with vague phrases. Preserve a small set of decisive
  quantitative comparators when they define the paper's main contrast.
- Preserve section roles: Results report evidence, Discussion synthesizes,
  Introduction frames the gap after Results are known, Abstract compresses the
  final story.
- Address every blocking issue and targeted revision in the cross-section review.
{ledger_rules}
"""


def build_yuan_nature_polisher_prompt(round_index: int) -> str:
    return f"""# Yuan Nature-Polishing Full-Paper Polish Round {round_index}

Read the current manuscript sections, `reviews/cross_section_review.yaml`, and
the bundled `skill/vendor/nature-polishing/` files. Apply Yuan's
Nature-polishing guidance as a full-paper consistency polish, not as new
scientific authorship.

Write all four files:
- manuscript/abstract.tex
- manuscript/introduction.tex
- manuscript/results.tex
- manuscript/discussion.tex

Rules:
- Preserve all section roles: Results report observations, Discussion interprets
  with boundaries, Introduction frames the gap, Abstract compresses the final
  paper.
- Do not invent evidence, references, numbers, sample sizes, mechanisms or
  figure claims.
- Fix cross-section contradictions before polishing style.
- Use claim/evidence/boundary checks from nature-polishing.
- Use the hourglass structure where relevant, but do not add unsupported
  broad claims.
- If a claim in Abstract, Introduction or Discussion is not supported by
  Results, soften or remove it rather than adding new Results facts.
- Keep Nature-style prose tight, but do not compress away essential evidence
  anchors requested by the reviewer.
"""


def copy_nature_polishing_to_run(run_dir: Path) -> list[str]:
    if not NATURE_POLISHING_ROOT.exists():
        return []
    target = run_dir / "skill" / "vendor" / "nature-polishing"
    files: list[str] = []
    for source in sorted(NATURE_POLISHING_ROOT.rglob("*")):
        if source.is_file():
            rel = source.relative_to(NATURE_POLISHING_ROOT)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            files.append(str(Path("skill") / "vendor" / "nature-polishing" / rel))
    return files


def write_cross_section_review(run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.agent_backend == "mock":
        return write_static_cross_section_review(run_dir)
    skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
    allowed_files = [
        "paper/story/paper_story_contract.yaml",
        "paper/story/paper_story_plan.yaml",
        "paper/evidence/evidence_claim_ledger.yaml",
        "audits/cross_section_evidence_ledger.yaml",
        "manuscript/abstract.tex",
        "manuscript/introduction.tex",
        "manuscript/results.tex",
        "manuscript/discussion.tex",
        "sections/results/reviews/section_review.yaml",
        "sections/discussion/reviews/section_review.yaml",
        "sections/introduction/reviews/section_review.yaml",
        "sections/abstract/reviews/section_review.yaml",
        copy_skill_file_to_run(run_dir, "prompts/cross_section_reviewer_prompt.md", skill_version),
        copy_skill_file_to_run(run_dir, "rubrics/cross_section_rubric.yaml", skill_version),
    ]
    backend = "api" if args.agent_backend in {"api", "codex+api"} else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role="cross_section_reviewer",
        run_dir=run_dir,
        prompt=build_cross_section_reviewer_prompt(),
        allowed_files=allowed_files,
        output_contract={"files": {"reviews/cross_section_review.yaml": "yaml"}},
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / "cross_section_reviewer.agent_result.yaml", result.__dict__)
    review = read_yaml(run_dir / "reviews" / "cross_section_review.yaml")
    if not isinstance(review, dict) or result.status != "done":
        review = {
            "schema_version": "nature_orchestrator.cross_section_review.v1",
            "status": "fail",
            "overall_score": 0,
            "accepted_by_reviewers": False,
            "blocking_issues": [result.error or "cross-section reviewer failed"],
            "targeted_revisions": [],
        }
        write_yaml(run_dir / "reviews" / "cross_section_review.yaml", review)
    write_yaml(run_dir / "audits" / "cross_section_score_gate.yaml", section_score_gate(review))
    return review


def snapshot_cross_section_review(run_dir: Path, round_index: int) -> None:
    review_path = run_dir / "reviews" / "cross_section_review.yaml"
    gate_path = run_dir / "audits" / "cross_section_score_gate.yaml"
    if review_path.exists():
        shutil.copyfile(review_path, run_dir / "reviews" / f"cross_section_review_round_{round_index:03d}.yaml")
    if gate_path.exists():
        shutil.copyfile(gate_path, run_dir / "audits" / f"cross_section_score_gate_round_{round_index:03d}.yaml")


def run_full_paper_polisher(run_dir: Path, args: argparse.Namespace, round_index: int) -> dict[str, Any]:
    allowed_files = [
        "paper/story/paper_story_contract.yaml",
        "paper/story/paper_story_plan.yaml",
        "paper/evidence/evidence_claim_ledger.yaml",
        "audits/cross_section_evidence_ledger.yaml",
        "audits/final_section_anchor_gate.yaml",
        "manuscript/abstract.tex",
        "manuscript/introduction.tex",
        "manuscript/results.tex",
        "manuscript/discussion.tex",
        "reviews/cross_section_review.yaml",
        "sections/results/reviews/section_review.yaml",
        "sections/discussion/reviews/section_review.yaml",
    ]
    if args.full_paper_polisher_profile == "yuan_nature_polishing":
        allowed_files.extend(copy_nature_polishing_to_run(run_dir))
        prompt = build_yuan_nature_polisher_prompt(round_index)
    elif args.full_paper_polisher_profile in FULL_PAPER_SKILL_PROFILES:
        skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
        allowed_files.append(copy_skill_file_to_run(run_dir, "prompts/full_paper_polisher_prompt.md", skill_version))
        prompt = build_full_paper_polisher_prompt(
            round_index,
            full_paper_polisher_profile=args.full_paper_polisher_profile,
        )
    else:
        allowed_files.append(copy_skill_file_to_run(run_dir, "prompts/full_paper_polisher_prompt.md"))
        prompt = build_full_paper_polisher_prompt(round_index)
    backend = "api" if args.agent_backend == "api" else "codex"
    api_config = None
    if backend == "api":
        api_config = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    result = run_agent(
        role=f"full_paper_polisher_{round_index:03d}",
        run_dir=run_dir,
        prompt=prompt,
        allowed_files=allowed_files,
        output_contract={
            "files": {
                "manuscript/abstract.tex": "latex",
                "manuscript/introduction.tex": "latex",
                "manuscript/results.tex": "latex",
                "manuscript/discussion.tex": "latex",
            }
        },
        backend=backend,
        timeout=args.api_timeout if backend == "api" else args.codex_timeout,
        codex_binary=args.codex_binary,
        api_config=api_config,
    )
    write_yaml(run_dir / "logs" / f"full_paper_polisher_{round_index:03d}.agent_result.yaml", result.__dict__)
    final_path = assemble_final(run_dir)
    return {"status": result.status, "returncode": result.returncode, "final_output": str(final_path), "error": result.error}


def run_mock(run_dir: Path, slug: str, field: str, args: argparse.Namespace) -> dict[str, Any]:
    full_profile = getattr(args, "full_paper_polisher_profile", "v2_4")
    full_skill_version = full_paper_skill_version(full_profile)
    section_profile = getattr(args, "section_skill_profile", "v2_3")
    section_skills = SECTION_SKILL_PROFILES[section_profile]
    evidence_claim_ledger = None
    if uses_evidence_claim_ledger(full_profile):
        evidence_claim_ledger = write_evidence_claim_ledger(run_dir, args, slug, field)
    if uses_paper_story_contract(full_profile):
        write_paper_story_contract(run_dir, args, slug, field)
    else:
        plan = build_mock_paper_story_plan(slug, field)
        write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", plan)
        write_yaml(run_dir / "audits" / "paper_story_plan_gate.yaml", paper_story_plan_gate(plan))
    section_records = {section: write_mock_section(run_dir, section) for section in SECTION_ORDER}
    final_path = assemble_final(run_dir)
    cross_section_evidence_ledger = None
    if uses_cross_section_evidence_ledger(full_profile):
        cross_section_evidence_ledger = write_cross_section_evidence_ledger(run_dir, args)
    cross_review = write_static_cross_section_review(run_dir)
    provenance = {
        "schema_version": "nature_orchestrator.full_paper_generation_provenance.v1",
        "skill_version": full_skill_version,
        "section_skill_profile": section_profile,
        "section_skill_versions": section_skills,
        "full_paper_polisher_profile": full_profile,
        "slug": slug,
        "field": field,
        "agent_backend": "mock",
        "section_order": SECTION_ORDER,
        "max_refiner_rounds": args.max_refiner_rounds,
        "cross_section_evidence_ledger": (
            "audits/cross_section_evidence_ledger.yaml"
            if cross_section_evidence_ledger is not None
            else None
        ),
        "evidence_claim_ledger": (
            "paper/evidence/evidence_claim_ledger.yaml"
            if evidence_claim_ledger is not None
            else None
        ),
        "final_output": str(final_path),
    }
    write_yaml(run_dir / "provenance.yaml", provenance)
    return {
        "status": "done",
        "slug": slug,
        "field": field,
        "skill_version": full_skill_version,
        "section_skill_profile": section_profile,
        "section_skill_versions": section_skills,
        "full_paper_polisher_profile": full_profile,
        "agent_backend": "mock",
        "section_order": SECTION_ORDER,
        "section_reviews": {
            key: {
                "overall_score": value["review"]["overall_score"],
                "score_gate_status": value["score_gate"]["status"],
            }
            for key, value in section_records.items()
        },
        "cross_section_review": {
            "overall_score": cross_review["overall_score"],
            "status": cross_review["status"],
        },
        "evidence_claim_ledger": evidence_claim_ledger,
        "cross_section_evidence_ledger": cross_section_evidence_ledger,
        "cross_section_repair_records": [],
        "final_output": str(final_path),
    }


def run_command(command: list[str], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, text=True)
    return int(completed.returncode)


def find_status(root: Path, slug: str) -> Path | None:
    candidates = [path for path in root.rglob("status.yaml") if slug in str(path)]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def copy_section_output(status_path: Path, section: str, run_dir: Path) -> dict[str, Any]:
    section_run = status_path.parent
    if section == "results":
        source = section_run / "final" / "results.tex"
        target = run_dir / "manuscript" / "results.tex"
        write_text(target, read_text(source))
    elif section == "discussion":
        source = section_run / "final" / "discussion.tex"
        target = run_dir / "manuscript" / "discussion.tex"
        write_text(target, read_text(source))
    else:
        source = section_run / "final" / "abstract_intro.tex"
        abstract, introduction = split_abstract_intro(read_text(source))
        write_text(run_dir / "manuscript" / "abstract.tex", abstract)
        write_text(run_dir / "manuscript" / "introduction.tex", introduction)
    status = read_yaml(status_path)
    review = normalize_section_review(status_path, section)
    gate = section_score_gate(review)
    write_yaml(run_dir / "sections" / section / "reviews" / "section_review.yaml", review)
    write_yaml(run_dir / "sections" / section / "audits" / "section_score_gate.yaml", gate)
    for story_name in ("evidence_to_story_plan.yaml", "story_contract.yaml", "story_blueprint.yaml"):
        source_story = section_run / "story" / story_name
        if source_story.exists():
            target_story = run_dir / "sections" / section / "story" / story_name
            target_story.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_story, target_story)
    if section == "abstract_intro":
        for alias in ("abstract", "introduction"):
            alias_review = {**review, "section": alias, "source_section": "abstract_intro"}
            write_yaml(run_dir / "sections" / alias / "reviews" / "section_review.yaml", alias_review)
            write_yaml(run_dir / "sections" / alias / "audits" / "section_score_gate.yaml", gate)
    return {"status": status, "review": review, "score_gate": gate, "source_status_path": str(status_path)}


def run_real_sections(args: argparse.Namespace, run_dir: Path, slug: str, field: str) -> dict[str, Any]:
    evidence_claim_ledger_path = None
    if uses_evidence_claim_ledger(args.full_paper_polisher_profile):
        ledger_path = run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml"
        existing_ledger = read_yaml(ledger_path)
        if (
            isinstance(existing_ledger, dict)
            and evidence_claim_ledger_gate(existing_ledger).get("status") == "passed"
        ):
            write_yaml(run_dir / "audits" / "evidence_claim_ledger_gate.yaml", evidence_claim_ledger_gate(existing_ledger))
        else:
            write_evidence_claim_ledger(run_dir, args, slug, field)
        if ledger_path.exists():
            evidence_claim_ledger_path = ledger_path
    if uses_paper_story_contract(args.full_paper_polisher_profile):
        paper_contract_path = run_dir / "paper" / "story" / "paper_story_contract.yaml"
        existing_contract = read_yaml(paper_contract_path)
        if (
            isinstance(existing_contract, dict)
            and paper_story_contract_gate(existing_contract).get("status") == "passed"
        ):
            paper_contract = normalize_paper_story_contract(existing_contract)
            write_yaml(paper_contract_path, paper_contract)
            write_yaml(run_dir / "audits" / "paper_story_contract_gate.yaml", paper_story_contract_gate(paper_contract))
            write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", paper_contract)
        else:
            paper_contract = write_paper_story_contract(run_dir, args, slug, field)
    else:
        paper_contract = build_mock_paper_story_plan(slug, field)
        write_yaml(run_dir / "paper" / "story" / "paper_story_plan.yaml", paper_contract)
        write_yaml(run_dir / "audits" / "paper_story_plan_gate.yaml", paper_story_plan_gate(paper_contract))
        paper_contract_path = None
    paper_story_contract_arg = (
        ["--paper-story-contract", str(paper_contract_path)]
        if paper_contract_path is not None and paper_contract_path.exists()
        else []
    )
    paper_evidence_ledger_arg = (
        ["--paper-evidence-ledger", str(evidence_claim_ledger_path)]
        if evidence_claim_ledger_path is not None and evidence_claim_ledger_path.exists()
        else []
    )
    section_root = run_dir / "section_runs"
    records: dict[str, Any] = {}
    section_skills = SECTION_SKILL_PROFILES[args.section_skill_profile]
    full_skill_version = full_paper_skill_version(args.full_paper_polisher_profile)
    commands = [
        (
            "results",
            [
                sys.executable,
                "scripts/run_results_batch.py",
                "--tasks-root",
                str(args.tasks_root),
                "--out",
                str(section_root / "results"),
                "--run-id",
                "results",
                "--skill-version",
                section_skills["results"],
                "--task-name",
                "results_figure_grounded",
                "--only-slug",
                slug,
                "--image-mode",
                args.image_mode,
                "--agent-backend",
                section_backend(args, "results"),
                "--max-refiner-rounds",
                str(args.max_refiner_rounds),
                "--api-timeout",
                str(args.api_timeout),
                "--api-max-tokens",
                str(args.api_max_tokens),
                "--codex-timeout",
                str(args.codex_timeout),
                "--codex-binary",
                args.codex_binary,
                *paper_story_contract_arg,
                *paper_evidence_ledger_arg,
            ],
        ),
        (
            "discussion",
            [
                sys.executable,
                "scripts/run_discussion_batch.py",
                "--tasks-root",
                str(args.tasks_root),
                "--out",
                str(section_root / "discussion"),
                "--run-id",
                "discussion",
                "--skill-version",
                section_skills["discussion"],
                "--task-name",
                "discussion",
                "--only-slug",
                slug,
                "--image-mode",
                args.image_mode,
                "--agent-backend",
                section_backend(args, "discussion"),
                "--max-refiner-rounds",
                str(args.max_refiner_rounds),
                "--api-timeout",
                str(args.api_timeout),
                "--api-max-tokens",
                str(args.api_max_tokens),
                "--codex-timeout",
                str(args.codex_timeout),
                "--codex-binary",
                args.codex_binary,
                *paper_story_contract_arg,
                *paper_evidence_ledger_arg,
            ],
        ),
        (
            "abstract_intro",
            [
                sys.executable,
                "scripts/run_abstract_intro_batch.py",
                "--tasks-root",
                str(args.tasks_root),
                "--out",
                str(section_root / "abstract_intro"),
                "--run-id",
                "abstract_intro",
                "--skill-version",
                section_skills["abstract_intro"],
                "--only-slug",
                slug,
                "--image-mode",
                args.image_mode,
                "--agent-backend",
                section_backend(args, "abstract_intro"),
                "--max-refiner-rounds",
                str(args.max_refiner_rounds),
                "--api-timeout",
                str(args.api_timeout),
                "--api-max-tokens",
                str(args.api_max_tokens),
                "--codex-timeout",
                str(args.codex_timeout),
                "--codex-binary",
                args.codex_binary,
                *paper_story_contract_arg,
                *paper_evidence_ledger_arg,
                "--quiet-progress",
            ],
        ),
    ]
    for section, command in commands:
        attach_paper_context_artifacts(section_root / section, run_dir)
        status_path = find_status(section_root / section, slug)
        status = read_yaml(status_path) if status_path is not None else {}
        if isinstance(status, dict) and status.get("status") == "done":
            code = 0
        else:
            code = run_command(command, ROOT)
        status_path = find_status(section_root / section, slug)
        if status_path is None:
            records[section] = {"returncode": code, "status": "missing_status"}
            return {"status": "failed", "section_records": records}
        records[section] = {"returncode": code, **copy_section_output(status_path, section, run_dir)}
        if records[section]["score_gate"]["status"] != "passed":
            return {"status": "needs_review", "section_records": records}
        if uses_paper_story_alignment(args.full_paper_polisher_profile):
            write_paper_story_alignment(run_dir, args, section)
    final_path = assemble_final(run_dir)
    cross_section_evidence_ledger = None
    if uses_cross_section_evidence_ledger(args.full_paper_polisher_profile):
        cross_section_evidence_ledger = write_cross_section_evidence_ledger(run_dir, args)
    cross_review = write_cross_section_review(run_dir, args)
    cross_review = apply_final_section_anchor_gate(run_dir, cross_review)
    cross_rounds = 1
    snapshot_cross_section_review(run_dir, 0)
    polish_records: list[dict[str, Any]] = []
    repair_records: list[dict[str, Any]] = []
    cross_repair_round_budget = effective_cross_repair_rounds(args)
    for round_index in range(1, cross_repair_round_budget + 1):
        if section_score_gate(cross_review)["status"] == "passed":
            break
        if uses_targeted_cross_section_repair(args.full_paper_polisher_profile):
            repair_plan = write_cross_section_repair_plan(run_dir, args, round_index)
            patch_records = run_targeted_cross_section_patchers(run_dir, args, round_index, repair_plan)
            repair_record = {
                "round_index": round_index,
                "repair_plan": "repairs/cross_section_repair_plan.yaml",
                "repair_plan_gate": cross_section_repair_plan_gate(repair_plan),
                "patch_records": patch_records,
            }
            repair_records.append(repair_record)
            if not patch_records or any(record.get("status") != "done" for record in patch_records):
                break
        else:
            polish_record = run_full_paper_polisher(run_dir, args, round_index)
            polish_records.append(polish_record)
            if polish_record["status"] != "done":
                break
        if uses_cross_section_evidence_ledger(args.full_paper_polisher_profile):
            cross_section_evidence_ledger = write_cross_section_evidence_ledger(run_dir, args)
        cross_review = write_cross_section_review(run_dir, args)
        cross_review = apply_final_section_anchor_gate(run_dir, cross_review)
        snapshot_cross_section_review(run_dir, round_index)
        cross_rounds += 1
    final_path = assemble_final(run_dir)
    write_yaml(
        run_dir / "provenance.yaml",
        {
            "schema_version": "nature_orchestrator.full_paper_generation_provenance.v1",
            "skill_version": full_skill_version,
            "section_skill_profile": args.section_skill_profile,
            "section_skill_versions": section_skills,
            "full_paper_polisher_profile": args.full_paper_polisher_profile,
            "slug": slug,
            "field": field,
            "agent_backend": args.agent_backend,
            "section_order": SECTION_ORDER,
            "section_status_paths": {
                section: value.get("source_status_path")
                for section, value in records.items()
            },
            "max_refiner_rounds": args.max_refiner_rounds,
            "max_cross_repair_rounds": cross_repair_round_budget,
            "cross_section_review_rounds": cross_rounds,
            "cross_section_evidence_ledger": (
                "audits/cross_section_evidence_ledger.yaml"
                if cross_section_evidence_ledger is not None
                else None
            ),
            "full_paper_polish_rounds": len(polish_records),
            "cross_section_repair_rounds": len(repair_records),
            "final_output": str(final_path),
        },
    )
    return {
        "status": "done" if cross_review["status"] == "pass" else "needs_review",
        "slug": slug,
        "field": field,
        "skill_version": full_skill_version,
        "section_skill_profile": args.section_skill_profile,
        "section_skill_versions": section_skills,
        "full_paper_polisher_profile": args.full_paper_polisher_profile,
        "agent_backend": args.agent_backend,
        "section_order": SECTION_ORDER,
        "section_records": records,
        "section_reviews": {
            "results": {"score_gate_status": records["results"]["score_gate"]["status"]},
            "discussion": {"score_gate_status": records["discussion"]["score_gate"]["status"]},
            "introduction": {"score_gate_status": records["abstract_intro"]["score_gate"]["status"]},
            "abstract": {"score_gate_status": records["abstract_intro"]["score_gate"]["status"]},
        },
        "cross_section_review": cross_review,
        "cross_section_review_rounds": cross_rounds,
        "cross_section_evidence_ledger": cross_section_evidence_ledger,
        "full_paper_polish_records": polish_records,
        "cross_section_repair_records": repair_records,
        "final_output": str(final_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a full-paper core manuscript from v2.3 section writers.")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=f"full_paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--only-slug", required=True)
    parser.add_argument("--field", default="")
    parser.add_argument("--image-mode", default="benchmark_vlm")
    parser.add_argument("--agent-backend", choices=["mock", "api", "codex", "codex+api"], default="api")
    parser.add_argument(
        "--section-agent-backends",
        type=parse_section_agent_backends,
        default={},
        dest="section_agent_backend_overrides",
        help="Optional comma-separated overrides, e.g. results=codex+api,discussion=api,abstract_intro=api.",
    )
    parser.add_argument("--section-skill-profile", choices=sorted(SECTION_SKILL_PROFILES), default="v2_3")
    parser.add_argument(
        "--full-paper-polisher-profile",
        choices=sorted([*FULL_PAPER_SKILL_PROFILES, "yuan_nature_polishing"]),
        default="v2_4",
    )
    parser.add_argument("--max-refiner-rounds", type=int, default=2)
    parser.add_argument(
        "--max-cross-repair-rounds",
        type=int,
        default=None,
        help="Optional full-paper cross-section repair round budget. Defaults to --max-refiner-rounds.",
    )
    parser.add_argument("--api-timeout", type=int, default=900)
    parser.add_argument("--api-max-tokens", type=int, default=16000)
    parser.add_argument("--codex-timeout", type=int, default=1800)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default=None)
    parser.add_argument("--quiet-progress", action="store_true")
    args = parser.parse_args(argv)

    slug = args.only_slug
    field = infer_field(args.tasks_root, slug, args.field)
    run_dir = args.out / args.run_id / field / slug
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.agent_backend == "mock":
        summary = run_mock(run_dir, slug, field, args)
    else:
        summary = run_real_sections(args, run_dir, slug, field)
    write_yaml(run_dir / "summary.yaml", summary)
    write_yaml(args.out / args.run_id / "summary.yaml", {"run_id": args.run_id, "tasks": [summary]})
    if not args.quiet_progress:
        print(run_dir / "summary.yaml")
    return 0 if summary.get("status") in {"done", "needs_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
