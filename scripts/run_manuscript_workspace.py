#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "nature_writing" / "versions" / "v0_1_generic_full_paper"
PROMPT_FILES = {
    "writer": SKILL_DIR / "prompts" / "writer.md",
    "reviewer": SKILL_DIR / "prompts" / "reviewer.md",
    "refiner": SKILL_DIR / "prompts" / "refiner.md",
    "polisher": SKILL_DIR / "prompts" / "polisher.md",
    "orchestrator": SKILL_DIR / "prompts" / "orchestrator.md",
}
RUBRIC_FILES = [
    SKILL_DIR / "rubrics" / "evidence_grounding.yaml",
    SKILL_DIR / "rubrics" / "story_quality.yaml",
]


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_relative_path(value: str, field: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be a workspace-relative path: {value}")
    return path


def resolve_workspace_file(workspace_root: Path, value: str, field: str) -> Path:
    rel = require_relative_path(value, field)
    resolved = (workspace_root / rel).resolve()
    if workspace_root.resolve() not in [resolved, *resolved.parents]:
        raise ValueError(f"{field} resolves outside the workspace: {value}")
    if not resolved.exists():
        raise FileNotFoundError(f"{field} does not exist: {value}")
    if not resolved.is_file():
        raise ValueError(f"{field} must resolve to a file: {value}")
    return resolved


def workspace_input_files(workspace_path: Path, workspace: dict[str, Any]) -> list[tuple[str, Path]]:
    root = workspace_path.parent.resolve()
    inputs = workspace.get("inputs") or {}
    files: list[tuple[str, Path]] = []
    for key in ["research_question", "methods", "results_notes", "figures", "references", "constraints"]:
        value = inputs.get(key)
        if value:
            files.append((value, resolve_workspace_file(root, str(value), f"inputs.{key}")))
    return files


def output_paths(workspace: dict[str, Any]) -> list[str]:
    outputs = workspace.get("outputs") or {}
    values: list[str] = []
    for key, value in outputs.items():
        if value:
            require_relative_path(str(value), f"outputs.{key}")
            values.append(str(value))
    return values


def validate_workspace(workspace: dict[str, Any]) -> None:
    if workspace.get("schema_version") != "nature_orchestrator.manuscript_workspace.v1":
        raise ValueError("workspace schema_version must be nature_orchestrator.manuscript_workspace.v1")
    for section in ["project", "inputs", "outputs", "policy"]:
        if not isinstance(workspace.get(section), dict):
            raise ValueError(f"workspace missing `{section}` mapping")
    policy = workspace.get("policy") or {}
    if policy.get("oracle_available") not in (False, None):
        raise ValueError("generic runner does not allow oracle_available=true in no-oracle mode")


def build_context(workspace_path: Path, workspace: dict[str, Any], input_files: list[tuple[str, Path]]) -> str:
    project = workspace.get("project") or {}
    lines = [
        "# Manuscript Workspace Context",
        "",
        "## Project",
        "",
        f"- Title: {project.get('title', '')}",
        f"- Field: {project.get('field', '')}",
        f"- Target style: {project.get('target_style', '')}",
        "",
        "## Policy",
        "",
    ]
    for key, value in (workspace.get("policy") or {}).items():
        lines.append(f"- {key}: {value}")
    for rel, path in input_files:
        lines.extend(["", f"## Input: {rel}", ""])
        lines.append(path.read_text(encoding="utf-8"))
    return "\n".join(lines).rstrip() + "\n"


def prompt_for(stage: str, workspace: dict[str, Any], context_hash: str) -> str:
    prompt_text = PROMPT_FILES[stage].read_text(encoding="utf-8")
    outputs = workspace.get("outputs") or {}
    output_lines = "\n".join(f"- {key}: `{value}`" for key, value in outputs.items())
    return (
        f"# Nature Writing {stage.title()} Task\n\n"
        f"Use `context_pack/context.md` as the evidence source.\n"
        f"Context hash: `{context_hash}`.\n\n"
        f"Declared outputs:\n{output_lines}\n\n"
        f"{prompt_text}\n"
    )


def write_prompt_pack(workspace_path: Path, out_dir: Path, backend: str) -> dict[str, Any]:
    workspace_path = workspace_path.resolve()
    workspace = read_yaml(workspace_path)
    validate_workspace(workspace)
    input_files = workspace_input_files(workspace_path, workspace)
    outputs = output_paths(workspace)

    context = build_context(workspace_path, workspace, input_files)
    context_hash = sha256_text(context)
    write_text(out_dir / "context_pack" / "context.md", context)

    prompt_hashes: dict[str, str] = {}
    for stage in ["writer", "reviewer", "refiner", "polisher", "orchestrator"]:
        text = prompt_for(stage, workspace, context_hash)
        prompt_hashes[stage] = sha256_text(text)
        write_text(out_dir / "prompt_pack" / f"{stage}_prompt.md", text)

    master_prompt = (
        "# NatureOrchestrator Generic Manuscript Workspace\n\n"
        "Follow the staged prompts in this prompt pack. Start with "
        "`writer_prompt.md`; use the reviewer, orchestrator, refiner, and "
        "polisher prompts for subsequent passes.\n\n"
        "Allowed context is limited to `context_pack/context.md` and files "
        "listed in `prompt_pack/allowed_files.yaml`.\n"
    )
    write_text(out_dir / "prompt_pack" / "master_prompt.md", master_prompt)

    allowed_files = [rel for rel, _ in input_files]
    allowed_files.extend(
        str(path.relative_to(ROOT))
        for path in [*PROMPT_FILES.values(), *RUBRIC_FILES, SKILL_DIR / "manifest.yaml"]
    )
    forbidden_files = sorted(
        set(
            [
                ".env",
                ".env.*",
                "outputs/",
                "oracle/",
                "benchmark/oracle/",
                "reference/",
                "references/oracle/",
                *outputs,
            ]
        )
    )
    write_yaml(out_dir / "prompt_pack" / "allowed_files.yaml", {"allowed_files": allowed_files})
    write_yaml(out_dir / "prompt_pack" / "forbidden_files.yaml", {"forbidden_files": forbidden_files})
    write_yaml(
        out_dir / "prompt_pack" / "task_contract.yaml",
        {
            "schema_version": "nature_orchestrator.task_contract.v1",
            "workspace_schema": workspace["schema_version"],
            "workspace": str(workspace_path),
            "skill_version": "v0_1_generic_full_paper",
            "backend": backend,
            "allowed_context": allowed_files,
            "forbidden_context": forbidden_files,
            "outputs": workspace.get("outputs") or {},
            "policy": workspace.get("policy") or {},
        },
    )

    provenance = {
        "schema_version": "nature_orchestrator.provenance.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workspace_path": str(workspace_path),
        "workspace_hash": sha256_file(workspace_path),
        "context_hash": context_hash,
        "skill_version": "v0_1_generic_full_paper",
        "backend": backend,
        "input_hashes": {rel: sha256_file(path) for rel, path in input_files},
        "prompt_hashes": prompt_hashes,
        "output_hashes": {},
    }
    write_yaml(out_dir / "provenance.yaml", provenance)
    declared_provenance = (workspace.get("outputs") or {}).get("provenance")
    if declared_provenance:
        write_yaml(out_dir / declared_provenance, provenance)
    write_yaml(
        out_dir / "run_manifest.yaml",
        {
            "schema_version": "nature_orchestrator.generic_run.v1",
            "status": "prompt_pack_ready",
            "workspace": str(workspace_path),
            "backend": backend,
            "skill_version": "v0_1_generic_full_paper",
        },
    )
    return {"workspace": workspace, "provenance": provenance}


def run_codex(out_dir: Path, timeout: int) -> int:
    prompt = (out_dir / "prompt_pack" / "master_prompt.md").read_text(encoding="utf-8")
    command = ["codex", "-a", "never", "exec", "--ephemeral", "--sandbox", "workspace-write", "-C", str(out_dir), prompt]
    completed = subprocess.run(command, cwd=out_dir, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    write_text(out_dir / "logs" / "codex.stdout.log", completed.stdout)
    write_text(out_dir / "logs" / "codex.stderr.log", completed.stderr)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or run a generic Nature writing manuscript workspace.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--backend", choices=["prompt-pack", "codex", "api"], default="prompt-pack")
    parser.add_argument("--codex-timeout", type=int, default=1800)
    args = parser.parse_args()

    if args.backend == "api":
        raise SystemExit("The api backend is planned but not implemented in v0.1.")

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_prompt_pack(args.workspace, out_dir, args.backend)
    if args.backend == "codex":
        return run_codex(out_dir, args.codex_timeout)
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
