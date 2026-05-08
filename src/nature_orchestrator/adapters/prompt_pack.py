from __future__ import annotations

from pathlib import Path

from ..contracts import ContextPack
from ..io import write_text, write_yaml


def results_specific_instructions(context: ContextPack) -> list[str]:
    if context.task.target_section != "results":
        return []
    variant = context.task.task_variant
    lines = [
        "",
        "## Results-Specific Writing Requirements",
        "",
        "- Organize the section as a Nature-style chain of findings, not as a flat data summary.",
        "- Each subsection should state the experiment purpose, key observation, control or boundary condition, and why it advances the paper-level question.",
        "- Use claim roles explicitly while drafting: empirical claims must be tied to figure/table/source evidence; design claims to methods or code metadata; interpretive claims to observed patterns; narrative claims to the section logic.",
        "- Explain the main figures and panels at the level supported by captions and source data; do not invent panels or numerical claims.",
        "- Prefer concise mechanistic transitions such as what was tested next and why the next experiment follows.",
    ]
    if variant == "full_context":
        lines.append("- This is a `results.full_context` upper-bound/debug task; do not copy the hidden target section even if non-target sections summarize it.")
    elif variant == "figure_grounded":
        lines.append("- This is a `results.figure_grounded` task; prioritize `Figure Evidence` over broad non-target prose and do not rely on full Methods text.")
    elif variant == "evidence_only":
        lines.append("- This is a `results.evidence_only` task; infer the argument from figure/caption/source/code evidence without non-target prose.")
    return lines


def write_prompt_pack(out_dir: Path, context: ContextPack, plan: list[dict[str, str]], network_mode: str = "official_offline") -> None:
    task = context.task
    prompt = [
        f"# NatureOrchestrator Prompt Pack: {task.task_id}",
        "",
        f"Write the masked `{task.target_section}` section as editable LaTeX.",
        "",
        "Use only the allowed context in `../context_pack/context.md` and the files listed in `allowed_files.yaml`.",
        "Do not inspect any path listed in `forbidden_files.yaml`; oracle files are for post-generation audit only.",
        "Do not use direct web access. If literature is needed, write query requests for the orchestrator-controlled retrieval layer.",
        "",
        "## Pipeline Stages",
        "",
    ]
    for item in plan:
        prompt.append(f"- `{item['stage']}`: {item['purpose']}")
    prompt.extend(results_specific_instructions(context))
    prompt.extend(
        [
            "",
            "## Expected Output",
            "",
            "- Write the final section to `final/target_section.tex`.",
            "- Keep claims tied to figures, tables, source data, code metadata, or allowed non-target sections.",
            "- Do not imitate or quote the hidden target section.",
        ]
    )
    allowed_files = [
        item["path"]
        for item in (task.raw.get("allowed_context") or {}).get("non_target_sections") or []
        if item.get("path")
    ]
    allowed_files.extend((task.raw.get("allowed_context") or {}).get("evidence_artifacts") or [])
    allowed_files.extend(context.evidence.get("_workspace_allowed_files") or [])
    forbidden_files = list((task.raw.get("forbidden_context") or {}).get("paths") or [])

    write_text(out_dir / "prompt_pack" / "prompt.md", "\n".join(prompt) + "\n")
    write_yaml(out_dir / "prompt_pack" / "allowed_files.yaml", {"allowed_files": allowed_files})
    write_yaml(out_dir / "prompt_pack" / "forbidden_files.yaml", {"forbidden_files": forbidden_files})
    write_yaml(
        out_dir / "prompt_pack" / "network_policy.yaml",
        {
            "mode": network_mode,
            "direct_web_access": network_mode == "open_web",
            "query_request_path": "../retrieval/query_requests.yaml" if network_mode == "safe_web" else "",
            "literature_pack_path": "../retrieval/literature_pack.yaml",
        },
    )
