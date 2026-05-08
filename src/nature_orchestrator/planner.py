from __future__ import annotations

from .contracts import ContextPack


def plan_section(context: ContextPack) -> list[dict[str, str]]:
    target = context.task.target_section
    return [
        {"stage": "ingest_task", "purpose": "Load task contract and leakage policy."},
        {"stage": "map_evidence", "purpose": "Identify figures, tables, source data, code, and availability evidence."},
        {"stage": "draft_section", "purpose": f"Draft the masked {target} section from allowed context only."},
        {"stage": "review_section", "purpose": "Check unsupported claims, missing evidence, and section-specific structure."},
        {"stage": "rewrite_section", "purpose": "Apply reviewer findings to produce a final section draft."},
        {"stage": "oracle_audit", "purpose": "Compare against ground truth only after generation is complete."},
    ]
