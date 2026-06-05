#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import run_section_skill_eval as section_eval  # noqa: E402


DEFAULT_FULL_PAPER_ROOT = ROOT / "outputs" / "full_paper_generation"


def read_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except yaml.YAMLError:
        return {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def copy_file_if_exists(source: Path, destination: Path) -> None:
    if source.exists() and source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def copy_tree_if_exists(source: Path, destination: Path) -> None:
    if source.exists() and source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def section_status_path(summary: dict[str, Any], section: str) -> Path | None:
    record = (summary.get("section_records") or {}).get(section)
    if not isinstance(record, dict):
        return None
    path = Path(record.get("source_status_path") or "")
    if path.exists():
        return path
    return None


def final_manuscript_text(paper_dir: Path, section: str) -> str:
    manuscript_dir = paper_dir / "manuscript"
    if section == "abstract_intro":
        abstract = read_text(manuscript_dir / "abstract.tex").strip()
        introduction = read_text(manuscript_dir / "introduction.tex").strip()
        if abstract and "\\begin{abstract}" not in abstract:
            abstract = f"\\begin{{abstract}}{abstract}\\end{{abstract}}"
        return "\n\n".join(item for item in [abstract, introduction] if item)
    return read_text(manuscript_dir / f"{section}.tex")


def full_paper_context_text(paper_dir: Path) -> str:
    context_dir = paper_dir / "paper" / "context"
    parts: list[str] = []
    for name in ("full_paper_task_safe_web.yaml", "full_paper_task.yaml", "evidence_pack.yaml", "vlm_figure_evidence.md"):
        path = context_dir / name
        text = read_text(path).strip()
        if text:
            parts.append(f"# {name}\n\n{text}")
    return "\n\n".join(parts)


def prepare_final_manuscript_eval_run(
    paper_dir: Path,
    summary: dict[str, Any],
    section: str,
    eval_dir: Path,
) -> Path | None:
    text = final_manuscript_text(paper_dir, section)
    if not text.strip():
        return None
    field = paper_dir.parent.name
    slug = str(summary.get("slug") or paper_dir.name)
    run_dir = eval_dir / "final_manuscript_runs" / field / slug / section
    final_rel = {
        "abstract_intro": "abstract_intro.tex",
        "results": "results.tex",
        "discussion": "discussion.tex",
    }.get(section, f"{section}.tex")
    write_text(run_dir / "final" / final_rel, text)

    source_status = section_status_path(summary, section)
    if source_status is not None:
        source_run_dir = source_status.parent
        for dirname in ("context_pack", "story", "reviews", "audits", "prompt_pack", "skill"):
            copy_tree_if_exists(source_run_dir / dirname, run_dir / dirname)
    if not (run_dir / "context_pack" / "context.md").exists():
        context = full_paper_context_text(paper_dir)
        if context.strip():
            write_text(run_dir / "context_pack" / "context.md", context)

    for path in sorted((paper_dir / "reviews").glob("cross_section_review*.yaml")):
        copy_file_if_exists(path, run_dir / "reviews" / f"full_paper_{path.name}")
    for path in sorted((paper_dir / "audits").glob("cross_section*.yaml")):
        copy_file_if_exists(path, run_dir / "audits" / f"full_paper_{path.name}")
    for path in sorted((paper_dir / "paper" / "story").glob("paper_story*.yaml")):
        copy_file_if_exists(path, run_dir / "story" / path.name)
    copy_file_if_exists(paper_dir / "provenance.yaml", run_dir / "provenance.yaml")

    status = read_yaml(source_status) if source_status is not None else {}
    status.update(
        {
            "status": "done",
            "text_source": "final-manuscript",
            "full_paper_run_dir": str(paper_dir),
            "source_status_path": str(source_status) if source_status is not None else "",
        }
    )
    write_yaml(run_dir / "status.yaml", status)
    return run_dir / "status.yaml"


def collect_full_paper_records(
    run_root: Path,
    skill_label: str | None = None,
    text_source: str = "section-source",
    eval_dir: Path | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for summary_path in sorted(run_root.glob("*/*/summary.yaml")):
        summary = read_yaml(summary_path)
        if not isinstance(summary, dict) or summary.get("status") not in {"done", "needs_review"}:
            continue
        slug = str(summary.get("slug") or summary_path.parent.name)
        backend = str(summary.get("agent_backend") or "api")
        run_id = run_root.name
        label = skill_label or str(summary.get("section_skill_profile") or summary.get("skill_version") or run_id)
        section_versions = summary.get("section_skill_versions") if isinstance(summary.get("section_skill_versions"), dict) else {}
        for section in ("results", "discussion", "abstract_intro"):
            if text_source == "section-source":
                status_path = section_status_path(summary, section)
            elif text_source == "final-manuscript":
                if eval_dir is None:
                    raise ValueError("eval_dir is required when text_source='final-manuscript'")
                status_path = prepare_final_manuscript_eval_run(summary_path.parent, summary, section, eval_dir)
            else:
                raise ValueError(f"Unsupported text_source: {text_source}")
            if status_path is None:
                continue
            job = section_eval.EvalJob(
                section=section,
                skill_label=label,
                skill_version=str(section_versions.get(section) or ""),
                backend=backend,
                slug=slug,
                run_id=run_id,
            )
            run_result = {
                "job": job.__dict__,
                "skipped": True,
                "returncode": 0,
                "status_path": str(status_path),
                "task_status": read_yaml(status_path).get("status"),
            }
            records.append(section_eval.collect_record(job, run_result))
            records[-1]["text_source"] = text_source
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate full-paper generation section outputs with Supervisor V2/V2.1.")
    parser.add_argument("--full-paper-run-id", required=True)
    parser.add_argument("--full-paper-root", type=Path, default=DEFAULT_FULL_PAPER_ROOT)
    parser.add_argument("--eval-id", default=None)
    parser.add_argument("--skill-label", default=None)
    parser.add_argument(
        "--text-source",
        default="section-source",
        choices=["section-source", "final-manuscript"],
        help="Score original section outputs or the final polished full-paper manuscript sections.",
    )
    parser.add_argument("--supervisor-backend", default="api", choices=section_eval.SUPERVISOR_V2_BACKENDS)
    parser.add_argument("--supervisor-version", default="v2_1", choices=["v2", "v2_1"])
    parser.add_argument("--supervisor-workers", type=int, default=4)
    parser.add_argument("--supervisor-timeout", type=int, default=900)
    parser.add_argument("--api-max-tokens", type=int, default=16000)
    parser.add_argument("--env", type=Path, default=section_eval.DEFAULT_ENV)
    parser.add_argument("--model", default=None)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--force-supervisor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    run_root = args.full_paper_root / args.full_paper_run_id
    if not run_root.exists():
        print(f"missing full-paper run root: {run_root}", file=sys.stderr)
        return 2
    eval_id = args.eval_id or f"full_paper_{args.full_paper_run_id}_{args.supervisor_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    eval_dir = ROOT / "outputs" / "section_skill_eval" / eval_id
    eval_dir.mkdir(parents=True, exist_ok=True)

    records = collect_full_paper_records(
        run_root,
        skill_label=args.skill_label,
        text_source=args.text_source,
        eval_dir=eval_dir,
    )
    section_eval.write_report(eval_dir, records)
    print(f"eval_dir={eval_dir}")
    print(f"records={len(records)}")
    print(f"text_source={args.text_source}")
    if args.dry_run:
        return 0
    records = section_eval.run_supervisor_v2_for_records(
        records,
        args.supervisor_backend,
        args.supervisor_workers,
        args.supervisor_timeout,
        args.api_max_tokens,
        args.env,
        args.model,
        args.codex_binary,
        args.force_supervisor,
        eval_dir,
        args.supervisor_version,
    )
    section_eval.write_report(eval_dir, records)
    print(eval_dir / "supervisor_v2_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
