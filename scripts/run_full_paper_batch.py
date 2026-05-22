#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nature_orchestrator.runner import run_task  # noqa: E402


def write_yaml(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def find_task(tasks_root: Path, slug: str) -> Path:
    candidates = [
        "benchmark/tasks_safe_web/results_figure_grounded.yaml",
        "benchmark/tasks_safe_web/results.yaml",
        "benchmark/tasks/results.yaml",
    ]
    for case_dir in tasks_root.rglob(slug):
        if not case_dir.is_dir():
            continue
        for rel in candidates:
            path = case_dir / rel
            if path.exists():
                return path
    raise FileNotFoundError(f"Could not find a supported NatureBench task for slug `{slug}` under {tasks_root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a NatureBench task through the public NatureOrchestrator adapter.")
    parser.add_argument("--prepare-only", action="store_true", help="Generate prompt-pack artifacts without model execution.")
    parser.add_argument("--tasks-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--only-slug", required=True)
    parser.add_argument("--generators", default="nature-orchestrator")
    parser.add_argument("--image-mode", default="benchmark_vlm")
    parser.add_argument("--quiet-progress", action="store_true")
    args = parser.parse_args()

    if not args.prepare_only:
        raise SystemExit("This public compatibility script supports --prepare-only in v0.1.")
    if args.generators != "nature-orchestrator":
        raise SystemExit("Only --generators nature-orchestrator is supported in v0.1.")

    task_path = find_task(args.tasks_root, args.only_slug)
    out_dir = args.out / args.run_id / "nature-orchestrator" / args.only_slug
    result = run_task(task_path, out_dir, adapter_name="prompt-pack", oracle_audit=False, network_mode="safe_web")
    summary = {
        "run_id": args.run_id,
        "completed": 1,
        "failed": 0,
        "tasks": [result],
        "image_mode": args.image_mode,
    }
    write_yaml(args.out / args.run_id / "summary.yaml", summary)
    if not args.quiet_progress:
        print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
