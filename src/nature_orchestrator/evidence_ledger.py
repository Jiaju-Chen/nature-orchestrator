from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "nature_orchestrator.evidence_claim_ledger.v1"

CONFIDENCE_SOURCES = {
    "caption_supported",
    "source_data_supported",
    "method_supported",
    "allowed_context_supported",
    "vlm_only",
    "unclear",
}

EVIDENCE_ROLES = {
    "primary_claim",
    "support",
    "boundary",
    "control",
    "negative_result",
    "validation",
    "limitation",
}

DOWNSTREAM_SECTIONS = {"results", "discussion", "abstract", "introduction", "abstract_intro"}

REQUIRED_ITEM_KEYS = [
    "anchor",
    "observation",
    "comparator",
    "direction",
    "confidence_source",
    "evidence_role",
    "must_write_detail",
    "can_compress",
    "cannot_claim",
    "downstream_section_use",
]

DEFINITIVE_DIRECTION_RE = re.compile(
    r"\b("
    r"increas(?:e|ed|es|ing)|decreas(?:e|ed|es|ing)|reduc(?:e|ed|es|ing)|"
    r"lower(?:ed|s|ing)?|higher|elevat(?:e|ed|es|ing)|enhanc(?:e|ed|es|ing)|"
    r"suppress(?:ed|es|ing)?|impair(?:ed|s|ing)?|worsen(?:ed|s|ing)?|"
    r"prevent(?:ed|s|ing)?|rescu(?:e|ed|es|ing)|maintain(?:ed|s|ing)?|"
    r"preserv(?:e|ed|es|ing)|block(?:ed|s|ing)?|abolish(?:ed|es|ing)?|"
    r"fail(?:ed|s)?\s+to|no\s+effect|unchanged"
    r")\b",
    re.IGNORECASE,
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_definitive_direction(*values: Any) -> bool:
    return any(DEFINITIVE_DIRECTION_RE.search(_text(value)) for value in values)


def evidence_claim_ledger_gate(ledger: dict[str, Any]) -> dict[str, Any]:
    """Validate the general evidence-to-claim ledger used before story planning."""

    issues: list[str] = []
    if not isinstance(ledger, dict):
        return {
            "schema_version": "nature_orchestrator.evidence_claim_ledger_gate.v1",
            "status": "failed",
            "blocking_issues": ["ledger must be a mapping"],
        }

    if ledger.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")

    items = ledger.get("evidence_items")
    if not isinstance(items, list) or not items:
        issues.append("evidence_items must be a non-empty list")
        items = []

    story_use_rules = ledger.get("story_use_rules")
    if story_use_rules is not None and not isinstance(story_use_rules, list):
        issues.append("story_use_rules must be a list when present")

    for index, item in enumerate(items):
        prefix = f"evidence_items[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be a mapping")
            continue
        for key in REQUIRED_ITEM_KEYS:
            if key not in item:
                issues.append(f"{prefix}.{key} is required")

        for key in ["anchor", "observation", "confidence_source", "evidence_role"]:
            if key in item and not _text(item.get(key)):
                issues.append(f"{prefix}.{key} must be non-empty")

        confidence = _text(item.get("confidence_source"))
        if confidence and confidence not in CONFIDENCE_SOURCES:
            issues.append(f"{prefix}.confidence_source must be one of {sorted(CONFIDENCE_SOURCES)}")

        role = _text(item.get("evidence_role"))
        if role and role not in EVIDENCE_ROLES:
            issues.append(f"{prefix}.evidence_role must be one of {sorted(EVIDENCE_ROLES)}")

        downstream = _as_list(item.get("downstream_section_use"))
        if not downstream:
            issues.append(f"{prefix}.downstream_section_use must be non-empty")
        for section in downstream:
            if _text(section) not in DOWNSTREAM_SECTIONS:
                issues.append(f"{prefix}.downstream_section_use contains unsupported section: {section}")

        if confidence == "vlm_only" and _contains_definitive_direction(
            item.get("direction"),
            item.get("must_write_detail"),
        ):
            issues.append(
                f"{prefix} is vlm_only but carries a definitive direction; "
                "use unclear/measured/compared wording until text or source-data support exists"
            )

    return {
        "schema_version": "nature_orchestrator.evidence_claim_ledger_gate.v1",
        "status": "failed" if issues else "passed",
        "blocking_issues": issues,
    }
