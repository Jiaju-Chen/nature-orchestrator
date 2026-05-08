from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from .adapters import fake, prompt_pack
from .context import build_context, write_context_pack
from .io import read_yaml, write_text, write_yaml
from .loader import load_task
from .oracle import run_oracle_audit
from .planner import plan_section
from .retrieval import offline_literature_pack, safe_search, write_literature_artifacts


def build_literature_pack(task: Any, network_mode: str, query_requests_path: Path | None = None) -> dict[str, Any]:
    if network_mode == "official_offline":
        return offline_literature_pack()
    if network_mode == "safe_web":
        network = task.raw.get("network") or {}
        fingerprint_path = network.get("target_fingerprint")
        fingerprint = read_yaml(task.resolve_case_path(str(fingerprint_path))) if fingerprint_path else {}
        query_requests = read_yaml(query_requests_path) if query_requests_path and query_requests_path.exists() else []
        if isinstance(query_requests, dict):
            query_requests = query_requests.get("queries") or query_requests.get("query_requests") or []
        return safe_search(list(query_requests or []), fingerprint)
    if network_mode == "open_web":
        pack = offline_literature_pack()
        pack["mode"] = "open_web"
        return pack
    raise ValueError(f"Unsupported network mode: {network_mode}")


def run_task(
    task_path: Path | str,
    out_dir: Path | str,
    adapter_name: str = "fake",
    oracle_audit: bool = False,
    network_mode: str = "official_offline",
    query_requests_path: Path | None = None,
) -> dict[str, Any]:
    out = Path(out_dir).resolve()
    task = load_task(Path(task_path))
    context = build_context(task)
    plan = plan_section(context)
    literature_pack = build_literature_pack(task, network_mode, query_requests_path)

    write_context_pack(context, out)
    write_literature_artifacts(out, literature_pack)
    write_yaml(out / "run_manifest.yaml", {
        "schema_version": "nature_orchestrator.run.v1",
        "task_id": task.task_id,
        "case_slug": task.case_slug,
        "target_section": task.target_section,
        "adapter": adapter_name,
        "network_mode": network_mode,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "oracle_audit_requested": oracle_audit,
    })
    write_yaml(out / "plan.yaml", {"stages": plan})

    if adapter_name == "fake":
        draft_text = fake.draft(context, plan)
        review_result = fake.review(context, draft_text)
        final_text = fake.rewrite(context, draft_text, review_result)
    elif adapter_name == "prompt-pack":
        prompt_pack.write_prompt_pack(out, context, plan, network_mode=network_mode)
        draft_text = (
            f"% Prompt pack generated for {task.task_id}.\n"
            f"% A model-backed agent should write the `{task.target_section}` section here.\n"
        )
        review_result = {"status": "not_run", "reason": "prompt-pack adapter only prepares model instructions"}
        final_text = draft_text
    else:
        raise ValueError(f"Unsupported adapter: {adapter_name}")

    write_text(out / "drafts" / "target_section.tex", draft_text)
    write_yaml(out / "reviews" / "reviewer_round_1.yaml", review_result)
    final_path = out / "final" / "target_section.tex"
    write_text(final_path, final_text)

    if oracle_audit:
        run_oracle_audit(task, final_path, out / "oracle_audit.yaml")

    result = {
        "status": "completed",
        "task_id": task.task_id,
        "target_section": task.target_section,
        "out_dir": str(out),
        "adapter": adapter_name,
        "network_mode": network_mode,
        "oracle_audit": oracle_audit,
    }
    write_yaml(out / "run_result.yaml", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a NatureOrchestrator section task.")
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--adapter", choices=["fake", "prompt-pack"], default="fake")
    parser.add_argument("--network-mode", choices=["official_offline", "safe_web", "open_web"], default="official_offline")
    parser.add_argument("--query-requests", type=Path, default=None)
    parser.add_argument("--oracle-audit", action="store_true")
    args = parser.parse_args()
    result = run_task(
        args.task,
        args.out,
        adapter_name=args.adapter,
        oracle_audit=args.oracle_audit,
        network_mode=args.network_mode,
        query_requests_path=args.query_requests,
    )
    print(result["out_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
