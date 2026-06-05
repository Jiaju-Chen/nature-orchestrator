#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_VERSION = "nature_writing_current"
SKILL_DIR = ROOT / "skills" / "nature_writing"
PROMPT_FILES = {
    "writer": SKILL_DIR / "tasks" / "full_paper_writing.md",
    "reviewer": SKILL_DIR / "prompts" / "cross_section_reviewer.md",
    "refiner": SKILL_DIR / "methods" / "write_review_and_refine.md",
    "polisher": SKILL_DIR / "prompts" / "final_polisher.md",
    "orchestrator": SKILL_DIR / "SKILL.md",
}
RUBRIC_FILES = [
    SKILL_DIR / "rubrics" / "section_reviewer_rubric.yaml",
    SKILL_DIR / "rubrics" / "cross_section_rubric.yaml",
    SKILL_DIR / "rubrics" / "supervisor_rubric.yaml",
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
            "skill_version": SKILL_VERSION,
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
        "skill_version": SKILL_VERSION,
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
            "mode": "prompt-pack",
            "skill_version": SKILL_VERSION,
        },
    )
    return {"workspace": workspace, "provenance": provenance, "context": context}


def run_codex_prompt(out_dir: Path, prompt: str, log_prefix: str, timeout: int) -> int:
    command = ["codex", "-a", "never", "exec", "--ephemeral", "--sandbox", "workspace-write", "-C", str(out_dir), prompt]
    completed = subprocess.run(command, cwd=out_dir, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    write_text(out_dir / "logs" / f"{log_prefix}.stdout.log", completed.stdout)
    write_text(out_dir / "logs" / f"{log_prefix}.stderr.log", completed.stderr)
    return completed.returncode


def run_codex(out_dir: Path, timeout: int) -> int:
    prompt = (out_dir / "prompt_pack" / "master_prompt.md").read_text(encoding="utf-8")
    return run_codex_prompt(out_dir, prompt, "codex", timeout)


def mock_story_blueprint(workspace: dict[str, Any]) -> dict[str, Any]:
    project = workspace.get("project") or {}
    return {
        "schema_version": "nature_orchestrator.story_blueprint.v1",
        "title": project.get("title", ""),
        "central_question": "Whether the provided evidence supports a coherent scientific manuscript.",
        "evidence_chain": [
            "research question establishes the manuscript problem",
            "methods define the experimental boundary",
            "results notes and figures define supported findings",
            "constraints define limitations and claim boundaries",
        ],
        "section_plan": {
            "results": "Report supported observations in figure-driven order.",
            "discussion": "State interpretation, limitations, and implications without adding new findings.",
            "abstract_intro": "Frame the problem, gap, approach, supported findings, and contribution.",
        },
    }


def mock_draft(workspace: dict[str, Any], context: str, round_index: int = 0) -> str:
    project = workspace.get("project") or {}
    title = project.get("title") or "Evidence-grounded manuscript"
    suffix = "" if round_index == 0 else "\n% Targeted refinement applied to reviewer requests.\n"
    return (
        f"% Draft round {round_index}\n"
        f"\\section{{Results}}\n"
        "Treatment A increased the normalized stability index under condition C, "
        "with the stated effect supported by Fig. 1 and the provided results notes. "
        "The failure counts remained comparable between groups as summarized in Fig. 2.\n\n"
        "\\section{Discussion}\n"
        f"These synthetic data support the claim that {title} under the tested condition. "
        "The evidence remains limited by sample size, the synthetic setting, and the absence "
        "of long-term durability testing.\n\n"
        "\\begin{abstract}\n"
        "A synthetic treatment study tested whether treatment A improves measurement B stability "
        "under condition C. Across the provided batches, treatment A increased the normalized "
        "stability index without a detectable increase in the pre-specified failure count. "
        "The findings support a constrained, evidence-grounded stability claim while leaving "
        "long-term durability and field deployment unresolved.\n"
        "\\end{abstract}\n\n"
        "\\section{Introduction}\n"
        "Stability under controlled stress is a common bottleneck in synthetic materials testing. "
        "The provided workspace motivates a focused test of whether treatment A improves measurement "
        "B under condition C while preserving failure-rate safety. This manuscript therefore builds "
        "a figure-grounded argument from the declared methods, results notes, and constraints.\n"
        f"{suffix}"
    )


def mock_review(role: str, draft: str) -> dict[str, Any]:
    return {
        "schema_version": "nature_orchestrator.review.v1",
        "reviewer": role,
        "status": "pass",
        "accepted_by_reviewers": True,
        "scores": {
            "evidence": 4,
            "story": 4,
            "citations": 4,
            "methods": 4,
            "clarity": 4,
            "finalization": 4,
        },
        "blocking_issues": [],
        "required_revisions": [],
        "optional_suggestions": [f"{role} reviewer found no blocking issue in mock mode."],
    }


def decide_from_reviews(reviews: list[dict[str, Any]], round_index: int, max_refiner_rounds: int) -> dict[str, Any]:
    blocking = [
        issue
        for review in reviews
        for issue in (review.get("blocking_issues") or review.get("required_revisions") or [])
    ]
    if blocking and round_index < max_refiner_rounds:
        decision = "revise"
    elif round_index == 0 and max_refiner_rounds > 0:
        decision = "polish"
    else:
        decision = "finalize"
    return {
        "schema_version": "nature_orchestrator.decision.v1",
        "round": round_index,
        "decision": decision,
        "reasons": ["parallel reviewers completed", "no oracle was used", "evidence-only policy remained active"],
        "required_next_actions": blocking,
    }


def write_final_audit(out_dir: Path, final_path: Path, reviews: list[dict[str, Any]], workspace: dict[str, Any]) -> dict[str, Any]:
    audit = {
        "schema_version": "nature_orchestrator.final_audit.v1",
        "status": "pass" if all(review.get("status") == "pass" for review in reviews) else "needs_review",
        "oracle_used": False,
        "evidence_only": bool((workspace.get("policy") or {}).get("evidence_only")),
        "final_path": str(final_path.relative_to(out_dir)),
        "checks": {
            "parallel_reviewers_completed": True,
            "final_manuscript_exists": final_path.exists(),
            "forbidden_oracle_mode": not bool((workspace.get("policy") or {}).get("oracle_available")),
        },
    }
    write_yaml(out_dir / "final" / "audit.yaml", audit)
    return audit


def update_output_hashes(out_dir: Path, paths: list[Path]) -> None:
    provenance_path = out_dir / "provenance.yaml"
    provenance = read_yaml(provenance_path)
    output_hashes = provenance.setdefault("output_hashes", {})
    for path in paths:
        if path.exists() and path.is_file():
            output_hashes[str(path.relative_to(out_dir))] = sha256_file(path)
    write_yaml(provenance_path, provenance)
    declared = read_yaml(out_dir / "prompt_pack" / "task_contract.yaml").get("outputs", {}).get("provenance")
    if declared:
        write_yaml(out_dir / declared, provenance)


def run_mock_auto(out_dir: Path, workspace: dict[str, Any], context: str, max_refiner_rounds: int, max_reviewer_workers: int) -> dict[str, Any]:
    blueprint = mock_story_blueprint(workspace)
    write_yaml(out_dir / "story" / "story_blueprint.yaml", blueprint)
    draft_path = out_dir / "drafts" / "draft_000.tex"
    write_text(draft_path, mock_draft(workspace, context, 0))

    reviewer_roles = ["evidence_reviewer", "story_reviewer", "citation_reviewer"]
    with ThreadPoolExecutor(max_workers=max(1, min(max_reviewer_workers, len(reviewer_roles)))) as pool:
        reviews = list(pool.map(lambda role: mock_review(role, draft_path.read_text(encoding="utf-8")), reviewer_roles))
    for review in reviews:
        write_yaml(out_dir / "reviews" / "round_000" / f"{review['reviewer']}.yaml", review)

    decision = decide_from_reviews(reviews, 0, max_refiner_rounds)
    write_yaml(out_dir / "decisions" / "decision_000.yaml", decision)

    current_draft = draft_path
    if decision["decision"] in {"revise", "polish"} and max_refiner_rounds > 0:
        refined_path = out_dir / "drafts" / "draft_001.tex"
        write_text(refined_path, mock_draft(workspace, context, 1))
        current_draft = refined_path

    final_path = out_dir / "final" / "manuscript.tex"
    write_text(final_path, current_draft.read_text(encoding="utf-8"))
    audit = write_final_audit(out_dir, final_path, reviews, workspace)
    update_output_hashes(
        out_dir,
        [
            out_dir / "story" / "story_blueprint.yaml",
            draft_path,
            current_draft,
            final_path,
            out_dir / "final" / "audit.yaml",
        ],
    )
    result = {
        "schema_version": "nature_orchestrator.generic_run.v1",
        "status": "completed",
        "mode": "auto",
        "backend": "mock",
        "skill_version": SKILL_VERSION,
        "reviewer_workers": max_reviewer_workers,
        "final_path": str(final_path),
        "audit_status": audit["status"],
    }
    write_yaml(out_dir / "run_manifest.yaml", result)
    return result


def codex_stage_prompt(stage: str, output_path: str, extra: str = "") -> str:
    return (
        f"Read `context_pack/context.md`, `prompt_pack/allowed_files.yaml`, "
        f"`prompt_pack/forbidden_files.yaml`, and `prompt_pack/{stage}_prompt.md`.\n"
        f"Write the requested {stage} artifact to `{output_path}`.\n"
        "Use no oracle/reference manuscript. Do not inspect forbidden files.\n"
        f"{extra}\n"
    )


def run_codex_auto(out_dir: Path, workspace: dict[str, Any], max_refiner_rounds: int, max_reviewer_workers: int, timeout: int) -> dict[str, Any]:
    stages = [
        ("writer", "story/story_blueprint.yaml", "First write a compact YAML story blueprint."),
        ("writer", "drafts/draft_000.tex", "Then write the full manuscript draft with Results, Discussion, Abstract, and Introduction."),
    ]
    for index, (stage, output, extra) in enumerate(stages):
        code = run_codex_prompt(out_dir, codex_stage_prompt(stage, output, extra), f"{index:02d}_{stage}", timeout)
        if code != 0:
            raise SystemExit(code)

    reviewer_roles = ["evidence_reviewer", "story_reviewer", "citation_reviewer"]

    def run_reviewer(role: str) -> dict[str, Any]:
        output = f"reviews/round_000/{role}.yaml"
        prompt = codex_stage_prompt(
            "reviewer",
            output,
            f"Act as `{role}`. Review `drafts/draft_000.tex` and write strict structured YAML.",
        )
        code = run_codex_prompt(out_dir, prompt, f"review_{role}", timeout)
        if code != 0:
            return {"reviewer": role, "status": "fail", "blocking_issues": [f"codex exited {code}"]}
        path = out_dir / output
        return read_yaml(path) if path.exists() else {"reviewer": role, "status": "fail", "blocking_issues": ["missing review output"]}

    with ThreadPoolExecutor(max_workers=max(1, min(max_reviewer_workers, len(reviewer_roles)))) as pool:
        reviews = list(pool.map(run_reviewer, reviewer_roles))
    decision = decide_from_reviews(reviews, 0, max_refiner_rounds)
    write_yaml(out_dir / "decisions" / "decision_000.yaml", decision)

    current_draft = out_dir / "drafts" / "draft_000.tex"
    if decision["decision"] in {"revise", "polish"} and max_refiner_rounds > 0:
        output = "drafts/draft_001.tex"
        code = run_codex_prompt(
            out_dir,
            codex_stage_prompt("refiner", output, "Use reviewer reports and `decisions/decision_000.yaml` for targeted refinement."),
            "refiner_001",
            timeout,
        )
        if code != 0:
            raise SystemExit(code)
        current_draft = out_dir / output

    final_path = out_dir / "final" / "manuscript.tex"
    code = run_codex_prompt(
        out_dir,
        codex_stage_prompt("polisher", "final/manuscript.tex", f"Polish `{current_draft.relative_to(out_dir)}` without adding new evidence."),
        "polisher",
        timeout,
    )
    if code != 0:
        raise SystemExit(code)
    audit = write_final_audit(out_dir, final_path, reviews, workspace)
    update_output_hashes(out_dir, [final_path, out_dir / "final" / "audit.yaml"])
    result = {
        "schema_version": "nature_orchestrator.generic_run.v1",
        "status": "completed" if final_path.exists() else "failed",
        "mode": "auto",
        "backend": "codex",
        "skill_version": SKILL_VERSION,
        "reviewer_workers": max_reviewer_workers,
        "final_path": str(final_path),
        "audit_status": audit["status"],
    }
    write_yaml(out_dir / "run_manifest.yaml", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or run a generic Nature writing manuscript workspace.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--backend", choices=["prompt-pack", "codex", "api", "mock"], default="prompt-pack")
    parser.add_argument("--mode", choices=["prepare", "auto"], default="prepare")
    parser.add_argument("--max-refiner-rounds", type=int, default=2)
    parser.add_argument("--max-reviewer-workers", type=int, default=3)
    parser.add_argument("--codex-timeout", type=int, default=1800)
    args = parser.parse_args()

    if args.backend == "api":
        raise SystemExit(
            "The generic manuscript-workspace API backend is not implemented. "
            "Use the section/full-paper NatureBench runners for API agent execution."
        )

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    prepared = write_prompt_pack(args.workspace, out_dir, args.backend)
    if args.mode == "auto":
        if args.backend == "mock":
            run_mock_auto(out_dir, prepared["workspace"], prepared["context"], args.max_refiner_rounds, args.max_reviewer_workers)
        elif args.backend == "codex":
            run_codex_auto(out_dir, prepared["workspace"], args.max_refiner_rounds, args.max_reviewer_workers, args.codex_timeout)
        else:
            raise SystemExit("--mode auto requires --backend codex or --backend mock.")
    elif args.backend == "codex":
        return run_codex(out_dir, args.codex_timeout)
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
