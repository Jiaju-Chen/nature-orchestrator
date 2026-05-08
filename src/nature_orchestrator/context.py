from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .contracts import ContextPack, TaskSpec
from .io import read_yaml


class LeakageError(RuntimeError):
    """Raised when generation context attempts to include oracle/forbidden data."""


def normalize_case_relative(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_forbidden_path(path: str, forbidden_prefixes: list[str]) -> bool:
    normalized = normalize_case_relative(path)
    if "/oracle/" in f"/{normalized}" or normalized.startswith("oracle/"):
        return True
    return any(normalized.startswith(normalize_case_relative(prefix)) for prefix in forbidden_prefixes)


def load_leakage_policy(task: TaskSpec) -> dict[str, Any]:
    policy_path = task.resolve_case_path(str(task.raw["leakage_policy"]))
    return read_yaml(policy_path)


def assert_generation_path_allowed(path: str, forbidden_prefixes: list[str]) -> None:
    if is_forbidden_path(path, forbidden_prefixes):
        raise LeakageError(f"Forbidden oracle path in generation context: {path}")


def read_allowed_section(task: TaskSpec, item: dict[str, str], forbidden_prefixes: list[str]) -> dict[str, str]:
    section = str(item.get("section") or "")
    path = str(item.get("path") or "")
    if section == task.target_section:
        raise LeakageError(f"Target section cannot be allowed context: {section}")
    assert_generation_path_allowed(path, forbidden_prefixes)
    absolute = task.resolve_case_path(path)
    text = absolute.read_text(encoding="utf-8", errors="replace") if absolute.exists() else ""
    return {"section": section, "path": path, "text": text}


def sanitized_evidence_pack(evidence: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(evidence)
    sanitized.pop("peer_review", None)
    return sanitized


def build_context(task: TaskSpec) -> ContextPack:
    policy = load_leakage_policy(task)
    forbidden_prefixes = list(policy.get("forbidden_path_prefixes") or ["benchmark/oracle/"])
    allowed = task.raw.get("allowed_context") or {}

    for path in allowed.get("evidence_artifacts") or []:
        assert_generation_path_allowed(str(path), forbidden_prefixes)

    evidence_path = task.resolve_case_path(str(task.raw["evidence_pack"]))
    assert_generation_path_allowed(str(task.raw["evidence_pack"]), forbidden_prefixes)
    evidence = sanitized_evidence_pack(read_yaml(evidence_path))
    sections = [
        read_allowed_section(task, dict(item), forbidden_prefixes)
        for item in allowed.get("non_target_sections") or []
    ]
    return ContextPack(task=task, evidence=evidence, sections=sections)


def copy_if_exists(source: Path, dest: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return True


def materialize_figure_assets(context: ContextPack, out_dir: Path) -> list[str]:
    allowed_files: list[str] = []
    figures = context.evidence.get("figure_evidence") or []
    for figure in figures:
        figure_id = str(figure.get("id") or "figure").replace("/", "-")
        image_path = str(figure.get("image_path") or "")
        if image_path:
            source = context.task.resolve_case_path(image_path)
            suffix = source.suffix or ".png"
            dest = out_dir / "evidence" / "figures" / f"{figure_id}{suffix}"
            if copy_if_exists(source, dest):
                relative = dest.relative_to(out_dir).as_posix()
                figure["workspace_image_path"] = relative
                allowed_files.append(relative)

        caption_text = str(figure.get("caption_text") or "").strip()
        caption_path = str(figure.get("caption_path") or "")
        if caption_text:
            dest = out_dir / "evidence" / "figures" / f"{figure_id}.caption.txt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(caption_text + "\n", encoding="utf-8")
            relative = dest.relative_to(out_dir).as_posix()
            figure["workspace_caption_path"] = relative
            allowed_files.append(relative)
        elif caption_path:
            source = context.task.resolve_case_path(caption_path)
            dest = out_dir / "evidence" / "figures" / f"{figure_id}.caption.txt"
            if copy_if_exists(source, dest):
                relative = dest.relative_to(out_dir).as_posix()
                figure["workspace_caption_path"] = relative
                allowed_files.append(relative)
    context.evidence["_workspace_allowed_files"] = sorted(set(allowed_files))
    return allowed_files


def write_context_pack(context: ContextPack, out_dir: Path) -> None:
    from .io import write_text, write_yaml

    materialize_figure_assets(context, out_dir)
    write_yaml(
        out_dir / "context_pack" / "context.yaml",
        {
            "task_id": context.task.task_id,
            "target_section": context.task.target_section,
            "sections": context.sections,
            "evidence": context.evidence,
        },
    )
    write_text(out_dir / "context_pack" / "context.md", context.to_markdown())
