from __future__ import annotations

from pathlib import Path

from .contracts import TaskSpec
from .io import read_yaml


def infer_case_root(task_path: Path) -> Path:
    task_path = task_path.resolve()
    if task_path.parent.name in {"tasks", "tasks_safe_web"} and task_path.parent.parent.name == "benchmark":
        return task_path.parents[2]
    raise ValueError(f"Task path must be under <case>/benchmark/tasks/: {task_path}")


def load_task(task_path: Path | str) -> TaskSpec:
    path = Path(task_path).resolve()
    raw = read_yaml(path)
    required = ["schema_version", "task_id", "case_slug", "target_section", "allowed_context", "forbidden_context"]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Task file {path} is missing required key(s): {', '.join(missing)}")
    if raw["schema_version"] != "naturebench.task.v1":
        raise ValueError(f"Unsupported task schema: {raw['schema_version']}")
    return TaskSpec(path=path, case_root=infer_case_root(path), raw=raw)
