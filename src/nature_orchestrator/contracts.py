from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    path: Path
    case_root: Path
    raw: dict[str, Any]

    @property
    def task_id(self) -> str:
        return str(self.raw["task_id"])

    @property
    def target_section(self) -> str:
        return str(self.raw["target_section"])

    @property
    def case_slug(self) -> str:
        return str(self.raw["case_slug"])

    @property
    def task_variant(self) -> str:
        return str(self.raw.get("task_variant") or "full_context")

    def resolve_case_path(self, relative_path: str) -> Path:
        return (self.case_root / relative_path).resolve()


@dataclass(frozen=True)
class ContextPack:
    task: TaskSpec
    evidence: dict[str, Any]
    sections: list[dict[str, str]]

    def to_markdown(self) -> str:
        lines = [
            f"# Context Pack: {self.task.task_id}",
            "",
            f"Target section: `{self.task.target_section}`",
            "",
            "## Allowed Non-Target Sections",
            "",
        ]
        for section in self.sections:
            lines.extend(
                [
                    f"### {section['section']}",
                    "",
                    section["text"].strip(),
                    "",
                ]
            )
        lines.extend(["## Evidence Summary", ""])
        lines.append(f"- Figures: {len(self.evidence.get('figures') or [])}")
        lines.append(f"- Tables: {len(self.evidence.get('tables') or [])}")
        lines.append(f"- Source data files: {len(self.evidence.get('source_data') or [])}")
        lines.append(f"- Code records: {len(self.evidence.get('code') or [])}")
        availability = self.evidence.get("availability") or {}
        if availability.get("data"):
            lines.append(f"- Data availability: {availability['data']}")
        if availability.get("code"):
            lines.append(f"- Code availability: {availability['code']}")
        figure_evidence = self.evidence.get("figure_evidence") or []
        if figure_evidence:
            lines.extend(["", "## Figure Evidence", ""])
        for figure in figure_evidence:
            figure_id = str(figure.get("id") or "figure")
            lines.extend(
                [
                    f"### {figure_id}",
                    "",
                    f"- Kind: {figure.get('kind') or 'main'}",
                ]
            )
            image_path = figure.get("workspace_image_path") or figure.get("image_path")
            caption_path = figure.get("workspace_caption_path") or figure.get("caption_path")
            if image_path:
                lines.append(f"- Image: `{image_path}`")
            if caption_path:
                lines.append(f"- Caption file: `{caption_path}`")
            caption = str(figure.get("caption_text") or "").strip()
            if caption:
                lines.extend(["", caption, ""])
            source_data = figure.get("source_data") or []
            if source_data:
                lines.append("Source data:")
                for record in source_data:
                    path = record.get("path") or record.get("url") or record.get("label") or "source"
                    lines.append(f"- `{path}`")
                lines.append("")
            snippets = figure.get("method_snippets") or []
            if snippets:
                lines.append("Method snippets:")
                for snippet in snippets:
                    lines.append(f"- {str(snippet.get('text') or '').strip()}")
                lines.append("")
            hints = figure.get("role_hints") or []
            if hints:
                lines.append("Role hints:")
                for hint in hints:
                    section = hint.get("section") or "context"
                    lines.append(f"- {section}: {str(hint.get('text') or '').strip()}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
