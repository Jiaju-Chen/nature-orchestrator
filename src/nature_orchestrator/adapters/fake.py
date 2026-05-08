from __future__ import annotations

from ..contracts import ContextPack


def draft(context: ContextPack, plan: list[dict[str, str]]) -> str:
    target = context.task.target_section
    figure_count = len(context.evidence.get("figures") or [])
    table_count = len(context.evidence.get("tables") or [])
    source_count = len(context.evidence.get("source_data") or [])
    return (
        f"\\section{{{target.replace('_', ' ').title()}}}\n"
        f"Draft {target} section generated from allowed context only. "
        f"It references {figure_count} figures, {table_count} tables, and {source_count} source-data records.\n"
    )


def review(context: ContextPack, draft_text: str) -> dict[str, object]:
    return {
        "status": "reviewed",
        "target_section": context.task.target_section,
        "findings": [
            {
                "severity": "note",
                "message": "Fake adapter does not evaluate scientific quality; use a model-backed reviewer later.",
            }
        ],
    }


def rewrite(context: ContextPack, draft_text: str, review_result: dict[str, object]) -> str:
    return draft_text + "\n% Fake reviewer note recorded; no semantic rewrite applied.\n"
