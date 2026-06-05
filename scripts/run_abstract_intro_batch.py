from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nature_orchestrator.context import build_context, write_context_pack  # noqa: E402
from nature_orchestrator.agents import AgentResult, ApiConfig, api_config_from_env, run_agent  # noqa: E402
from nature_orchestrator.io import write_text, write_yaml  # noqa: E402
from nature_orchestrator.loader import load_task  # noqa: E402


DEFAULT_TASKS_ROOT = ROOT.parent / "nature-bench" / "data" / "downloads"
DEFAULT_SKILL_VERSION = "v1_abstract_intro_distill"
DEFAULT_OUT = Path("outputs/abstract_intro")
DEFAULT_CODEX_TIMEOUT = 1800
DEFAULT_ENV = ROOT.parent / "nature-orchestrator" / ".env"
REVIEW_SCORE_FIELDS = [
    "abstract_specificity_score",
    "intro_gap_ladder_score",
    "evidence_disclosure_score",
    "story_novelty_score",
    "claim_safety_score",
    "nature_style_score",
]
NUMERIC_ANCHOR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*"
    r"(?:%|per cent|fold|x|×|ms|MPa|GPa|Pa|µm|μm|micrometre|micrometers?|"
    r"mm|cm|nm|K|Hz|kHz|MHz|GHz|events?|papers?|researchers?|participants?|"
    r"samples?|cells?|mice|rats|patients?|datasets?)",
    re.IGNORECASE,
)
FIGURE_REF_RE = re.compile(r"\b(?:Figs?|Figures?)\.?\s*~?\s*\d+[a-z]?", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^{}]+)\}|^#{1,6}\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
STRONG_CAUSAL_RE = re.compile(
    r"\b(produces?|produced|producing|causes?|caused|causing|drives?|drove|driven|"
    r"determines?|determined|determining|results?\s+in|resulted\s+in|resulting\s+in|"
    r"leads?\s+to|led\s+to|leading\s+to)\b",
    re.IGNORECASE,
)
ASSOCIATION_CUE_RE = re.compile(r"\b(associated|association|correlat|linked|model(?:led|ed)?|estimate|observational)\b", re.IGNORECASE)
OVERREACH_CONTEXT_RE = re.compile(
    r"\b(incentives?|adoption|reward|rewards|productivity|citations?|career|collective|"
    r"scientific|science|exploration|data availability|recognized|recognizable|system-level|system)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AbstractIntroTask:
    path: Path
    field: str
    slug: str


@dataclass(frozen=True)
class SkillPackage:
    version: str
    root: Path
    current_layout: bool = False

    @property
    def writer_prompt(self) -> Path:
        return self.root / "prompts" / "writer_prompt.md"

    @property
    def reviewer_prompt(self) -> Path:
        return self.root / "prompts" / "reviewer_prompt.md"

    @property
    def refiner_prompt(self) -> Path:
        return self.root / "prompts" / "refiner_prompt.md"

    @property
    def story_prompt(self) -> Path:
        return self.root / "prompts" / "story_blueprint_prompt.md"

    @property
    def supervisor_prompt(self) -> Path:
        return self.root / "prompts" / "supervisor_prompt.md"


class ProgressReporter:
    def __init__(self, run_id: str, total: int, enabled: bool = True, stream: TextIO | None = None) -> None:
        self.run_id = run_id
        self.total = total
        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.index = 0

    def set_task_index(self, index: int) -> None:
        self.index = index

    def event(self, stage: str, status: str, task: AbstractIntroTask | None = None, **fields: Any) -> None:
        if not self.enabled:
            return
        parts = [
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
            f"run_id={self.run_id}",
            f"task={self.index}/{self.total}",
        ]
        if task:
            parts.extend([f"slug={task.slug}", f"field={task.field}"])
        parts.extend([f"stage={stage}", f"status={status}"])
        for key, value in fields.items():
            if value is not None and value != "":
                parts.append(f"{key}={value}")
        self.stream.write(" ".join(parts) + "\n")
        self.stream.flush()


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_gate_yaml(path: Path) -> tuple[Any, str | None]:
    if not path.exists():
        return {}, None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}, None
    except yaml.YAMLError as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def stream_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_anchor(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("μ", "µ").strip().lower())


def extract_numeric_anchors(text: str) -> list[str]:
    anchors: set[str] = set()
    for match in NUMERIC_ANCHOR_RE.finditer(text or ""):
        prefix = (text or "")[max(0, match.start() - 12) : match.start()]
        if re.search(r"(?:fig|figure)s?\.?\s*~?\s*$", prefix, re.IGNORECASE):
            continue
        anchors.add(normalize_anchor(match.group(0)))
    return sorted(anchors)


def extract_figure_refs(text: str) -> list[str]:
    return sorted({normalize_anchor(match.group(0).replace("~", " ")) for match in FIGURE_REF_RE.finditer(text or "")})


def base_figure_ref(ref: str) -> str:
    match = re.match(r"(fig\s+\d+)", normalize_anchor(ref))
    return match.group(1) if match else normalize_anchor(ref)


def build_evidence_manifest(context_text: str) -> dict[str, Any]:
    numeric = extract_numeric_anchors(context_text)
    figure_refs = extract_figure_refs(context_text)
    return {
        "schema_version": "nature_orchestrator.abstract_intro_evidence_manifest.v1",
        "numeric_anchors": numeric,
        "figure_refs": figure_refs,
        "context_sha256": sha256_text(context_text or ""),
    }


ABSTRACT_INTRO_SUPPORT_ARTIFACTS = (
    "paper/story/paper_story_contract.yaml",
    "story/evidence_to_story_plan.yaml",
    "story/story_contract.yaml",
)


def build_abstract_intro_support_text(run_dir: Path) -> str:
    parts = [read_text_if_exists(run_dir / "context_pack" / "context.md")]
    for rel in ABSTRACT_INTRO_SUPPORT_ARTIFACTS:
        path = run_dir / rel
        if path.exists():
            parts.append(f"\n\n# Support artifact: {rel}\n{read_text_if_exists(path)}")
    return "\n".join(part for part in parts if part)


def discover_tasks(tasks_root: Path, only_slug: str | None = None) -> list[AbstractIntroTask]:
    root = tasks_root.resolve()
    tasks: list[AbstractIntroTask] = []
    for path in root.glob("*/s41586-*/benchmark/tasks_safe_web/abstract_intro.yaml"):
        if "snapshots" in path.parts:
            continue
        rel = path.relative_to(root)
        if len(rel.parts) < 5:
            continue
        field, slug = rel.parts[0], rel.parts[1]
        if field == "nature_portfolio_subjournals":
            continue
        if only_slug and slug != only_slug:
            continue
        tasks.append(AbstractIntroTask(path=path, field=field, slug=slug))
    return sorted(tasks, key=lambda item: (item.field, item.slug))


def load_skill(version: str, repo_root: Path = ROOT) -> SkillPackage:
    if version == "nature_writing_current_abstract_intro":
        root = repo_root / "skills" / "nature_writing"
        required = [
            root / "manifest.yaml",
            root / "prompts" / "abstract_intro_planner.md",
            root / "prompts" / "abstract_intro_writer.md",
            root / "prompts" / "abstract_intro_reviewer.md",
            root / "prompts" / "abstract_intro_refiner.md",
            root / "prompts" / "supervisor.md",
            root / "rubrics" / "section_reviewer_rubric.yaml",
            root / "methods" / "abstract_patterns.md",
            root / "methods" / "intro_gap_ladders.md",
            root / "methods" / "story_blueprint_schema.yaml",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing current abstract+intro skill file(s): " + ", ".join(missing))
        return SkillPackage(version=version, root=root, current_layout=True)
    root = repo_root / "skills" / "nature_writing" / "versions" / version
    required = [
        root / "manifest.yaml",
        root / "prompts" / "writer_prompt.md",
        root / "prompts" / "reviewer_prompt.md",
        root / "prompts" / "refiner_prompt.md",
        root / "prompts" / "story_blueprint_prompt.md",
        root / "patterns" / "abstract_patterns.md",
        root / "patterns" / "intro_gap_ladders.md",
        root / "rubrics" / "abstract_intro_rubric.yaml",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing skill file(s): " + ", ".join(missing))
    return SkillPackage(version=version, root=root)


def copy_skill_package(skill: SkillPackage, run_dir: Path) -> None:
    destination = run_dir / "skill"
    if skill.current_layout:
        copy_map = [
            ("manifest.yaml", "manifest.yaml"),
            ("prompts/abstract_intro_planner.md", "prompts/story_blueprint_prompt.md"),
            ("prompts/abstract_intro_writer.md", "prompts/writer_prompt.md"),
            ("prompts/abstract_intro_reviewer.md", "prompts/reviewer_prompt.md"),
            ("prompts/abstract_intro_refiner.md", "prompts/refiner_prompt.md"),
            ("prompts/supervisor.md", "prompts/supervisor_prompt.md"),
            ("rubrics/section_reviewer_rubric.yaml", "rubrics/abstract_intro_rubric.yaml"),
            ("methods/abstract_patterns.md", "patterns/abstract_patterns.md"),
            ("methods/intro_gap_ladders.md", "patterns/intro_gap_ladders.md"),
            ("methods/story_blueprint_schema.yaml", "patterns/story_blueprint_schema.yaml"),
            ("methods/distilled_writing_rules.md", "patterns/distilled_writing_rules.md"),
            ("methods/evidence_to_story.md", "methods/evidence_to_story.md"),
            ("methods/write_review_and_refine.md", "methods/write_review_and_refine.md"),
            ("tasks/section_writing.md", "tasks/section_writing.md"),
        ]
        for source_rel, target_rel in copy_map:
            source = skill.root / source_rel
            target = destination / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return
    for source in skill.root.rglob("*"):
        relative_parts = source.relative_to(skill.root).parts
        if (
            not source.is_file()
            or source.name.endswith(".pyc")
            or "__pycache__" in source.parts
            or relative_parts[0] in {"cases", "splits", "dev"}
            or relative_parts[:2] in {("patterns", "by_field"), ("patterns", "by_story_type")}
        ):
            continue
        target = destination / source.relative_to(skill.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def load_target_fingerprint(spec: Any) -> dict[str, Any]:
    candidates: list[str] = []
    network = spec.raw.get("network") or {}
    if isinstance(network, dict) and network.get("target_fingerprint"):
        candidates.append(str(network["target_fingerprint"]))
    candidates.append("benchmark/control/target_fingerprint.yaml")
    for relative in candidates:
        path = spec.resolve_case_path(relative)
        if path.exists():
            data = read_yaml(path)
            return data if isinstance(data, dict) else {}
    return {}


def fingerprint_blocklist(slug: str, fingerprint: dict[str, Any] | None = None) -> list[str]:
    fingerprint = fingerprint or {}
    candidates = [slug]
    for key in ["doi", "doi_suffix", "article_url", "title"]:
        value = fingerprint.get(key)
        if value:
            candidates.append(str(value))
    candidates.extend(str(item) for item in fingerprint.get("title_ngrams") or [] if item)
    return sorted({item.strip() for item in candidates if item and len(item.strip()) >= 5})


def write_task_contract(run_dir: Path, task: AbstractIntroTask, spec: Any, skill: SkillPackage, image_mode: str, allowed_files: list[str]) -> None:
    write_yaml(
        run_dir / "prompt_pack" / "task_contract.yaml",
        {
            "schema_version": "nature_orchestrator.abstract_intro_task_contract.v1",
            "task_slug": task.slug,
            "field": task.field,
            "task_id": spec.task_id,
            "target_section": spec.target_section,
            "skill_version": skill.version,
            "image_mode": image_mode,
            "allowed_files": allowed_files,
            "forbidden_context": spec.raw.get("forbidden_context") or {},
            "outputs": {
                "story": "story/story_blueprint.yaml",
                "evidence_to_story_plan": "story/evidence_to_story_plan.yaml",
                "story_contract": "story/story_contract.yaml",
                "final": "final/abstract_intro.tex",
                "reviews": "reviews/abstract_intro_review_round_*.yaml",
                "revisions": "revisions/refine_round_*.md",
                "drafts": "drafts/draft_*.tex",
                "audits": "audits/*.yaml",
            },
            "deterministic_gates": [
                "abstract_intro_format_gate",
                "evidence_anchor_gate",
                "reviewer_acceptance_gate",
            ],
        },
    )


def write_or_update_provenance(
    run_dir: Path,
    task: AbstractIntroTask,
    skill: SkillPackage,
    image_mode: str,
    codex_binary: str = "codex",
    status: str | None = None,
) -> None:
    existing = read_yaml(run_dir / "provenance.yaml")
    if not isinstance(existing, dict):
        existing = {}
    provenance = {
        **existing,
        "schema_version": "nature_orchestrator.abstract_intro_provenance.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "task_slug": task.slug,
        "field": task.field,
        "task_path": str(task.path),
        "skill_version": skill.version,
        "image_mode": image_mode,
        "codex_binary": codex_binary,
        "task_yaml_sha256": sha256_file(task.path),
        "context_md_sha256": sha256_file(run_dir / "context_pack" / "context.md"),
        "context_yaml_sha256": sha256_file(run_dir / "context_pack" / "context.yaml"),
        "writer_prompt_sha256": sha256_file(run_dir / "skill" / "prompts" / "writer_prompt.md"),
        "reviewer_prompt_sha256": sha256_file(run_dir / "skill" / "prompts" / "reviewer_prompt.md"),
        "refiner_prompt_sha256": sha256_file(run_dir / "skill" / "prompts" / "refiner_prompt.md"),
        "command_prompt_sha256": sha256_file(run_dir / "prompt_pack" / "prompt.md"),
        "final_output_sha256": sha256_file(run_dir / "final" / "abstract_intro.tex"),
        "latest_review_sha256": sha256_file(run_dir / "reviews" / "abstract_intro_review.yaml"),
    }
    if status is not None:
        provenance["status"] = status
    write_yaml(run_dir / "provenance.yaml", provenance)


def write_abstract_intro_prompt_pack(
    run_dir: Path,
    task: AbstractIntroTask,
    skill: SkillPackage,
    image_mode: str = "benchmark_vlm",
) -> None:
    spec = load_task(task.path)
    context = build_context(spec)
    write_context_pack(context, run_dir)
    copy_skill_package(skill, run_dir)
    allowed_files = [
        "context_pack/context.md",
        "context_pack/context.yaml",
        *[f"skill/{path}" for path in relative_files(run_dir / "skill")],
    ]
    if (run_dir / "paper" / "story" / "paper_story_contract.yaml").exists():
        allowed_files.append("paper/story/paper_story_contract.yaml")
    write_yaml(run_dir / "prompt_pack" / "allowed_files.yaml", {"allowed_files": allowed_files})
    write_yaml(run_dir / "prompt_pack" / "forbidden_files.yaml", spec.raw.get("forbidden_context") or {})
    write_text(run_dir / "prompt_pack" / "writer_prompt.md", (run_dir / "skill" / "prompts" / "writer_prompt.md").read_text(encoding="utf-8"))
    write_text(run_dir / "prompt_pack" / "reviewer_prompt.md", (run_dir / "skill" / "prompts" / "reviewer_prompt.md").read_text(encoding="utf-8"))
    write_text(run_dir / "prompt_pack" / "prompt.md", build_story_planner_command_prompt(task, skill.version))
    write_oracle_supervisor_pack(run_dir, task, spec, skill)
    write_task_contract(run_dir, task, spec, skill, image_mode, allowed_files)
    support_text = build_abstract_intro_support_text(run_dir)
    write_yaml(run_dir / "context_pack" / "evidence_manifest.yaml", build_evidence_manifest(support_text))
    write_yaml(
        run_dir / "run_manifest.yaml",
        {
            "schema_version": "nature_orchestrator.abstract_intro_run.v1",
            "task_slug": task.slug,
            "field": task.field,
            "task_path": str(task.path),
            "skill_version": skill.version,
            "image_mode": image_mode,
            "outputs": [
                "story/story_blueprint.yaml",
                "story/evidence_to_story_plan.yaml",
                "story/story_contract.yaml",
                "final/abstract_intro.tex",
                "reviews/abstract_intro_review.yaml",
                "reviews/abstract_intro_review_round_*.yaml",
                "revisions/refine_round_*.md",
                "drafts/draft_*.tex",
            ],
        },
    )
    write_or_update_provenance(run_dir, task, skill, image_mode, status="prepared")


def copy_paper_story_contract(run_dir: Path, source: Path | None) -> None:
    if source is None or not source.exists() or not source.is_file():
        return
    target = run_dir / "paper" / "story" / "paper_story_contract.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def write_oracle_supervisor_pack(run_dir: Path, task: AbstractIntroTask, spec: Any, skill: SkillPackage) -> None:
    allowed_files = [
        "prompt_pack/supervisor_allowed_files.yaml",
        "supervision/oracle/ground_truth_sections.yaml",
        "story/story_blueprint.yaml",
        "final/abstract_intro.tex",
        "reviews/abstract_intro_review.yaml",
        "reviews/abstract_intro_review_round_*.yaml",
        "audits/abstract_intro_format_gate.yaml",
        "audits/evidence_anchor_gate.yaml",
        "audits/claim_safety_gate.yaml",
        "audits/reviewer_acceptance_gate.yaml",
        "drafts/draft_*.tex",
        "revisions/refine_round_*.md",
        "provenance.yaml",
        "run_manifest.yaml",
        "prompt_pack/task_contract.yaml",
        "skill/prompts/writer_prompt.md",
        "skill/prompts/reviewer_prompt.md",
        "skill/prompts/refiner_prompt.md",
        "skill/prompts/supervisor_prompt.md",
        "skill/rubrics/abstract_intro_rubric.yaml",
    ]
    write_yaml(run_dir / "prompt_pack" / "supervisor_allowed_files.yaml", {"allowed_files": allowed_files})
    write_text(run_dir / "prompt_pack" / "oracle_supervisor_prompt.md", build_oracle_supervisor_command_prompt(task, skill.version))


def build_oracle_supervisor_command_prompt(task: AbstractIntroTask, skill_version: str) -> str:
    return f"""# Abstract + Introduction Oracle Supervisor Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`

You are a development-time oracle supervisor. You may inspect the original
target section only through `supervision/oracle/ground_truth_sections.yaml`.
Writer, reviewer, refiner and deterministic gates must never inspect oracle
files.

Use only files listed in `prompt_pack/supervisor_allowed_files.yaml`.

Compare the generated abstract+introduction against the oracle abstract+intro,
but do not rewrite the manuscript and do not copy long oracle passages. Diagnose
prompt, writer, reviewer and refiner behavior in reusable terms.

Read:
- `supervision/oracle/ground_truth_sections.yaml`
- `story/story_blueprint.yaml`
- `final/abstract_intro.tex`
- `reviews/abstract_intro_review.yaml`
- `reviews/abstract_intro_review_round_*.yaml`
- `audits/*.yaml`
- `drafts/draft_*.tex`
- `revisions/refine_round_*.md`
- `skill/prompts/supervisor_prompt.md`
- `skill/rubrics/abstract_intro_rubric.yaml`

Write:
- `supervision/supervisor_report.yaml`
- `supervision/story_gap_report.yaml`
- `supervision/textual_gradient.yaml`
- `supervision/optimization_score.yaml`

`optimization_score.yaml` must use this schema:
- `schema_version: nature_orchestrator.abstract_intro_optimization_score.v1`
- `overall.final_weighted_score`
- `overall.oracle_fidelity`
- `overall.evidence_fidelity`
- `overall.story_quality`
- `overall.nature_style`
- `overall.prompt_pipeline_performance`
- `component_scores.abstract_intro`
- `dimension_breakdown.quantitative_anchor_coverage`
- `dimension_breakdown.abstract_progression`
- `dimension_breakdown.intro_gap_ladder`
- `decision`
- `recommended_optimization_actions`
- `failure_attribution.must_mention_anchor_recall`
- `failure_attribution.direction_comparator_errors`
- `failure_attribution.unsupported_or_unrecoverable_details`
- `failure_attribution.over_conservatism`
- `failure_attribution.context_gap`
- `failure_attribution.planner_failure`
- `failure_attribution.writer_failure`
- `failure_attribution.reviewer_false_pass`
"""


def prepare_oracle_supervision(run_dir: Path, task: AbstractIntroTask) -> bool:
    spec = load_task(task.path)
    source = spec.case_root / "benchmark" / "oracle" / "ground_truth_sections.yaml"
    if not source.exists():
        return False
    target = run_dir / "supervision" / "oracle" / "ground_truth_sections.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def run_oracle_supervisor(
    task: AbstractIntroTask,
    run_dir: Path,
    skill: SkillPackage,
    codex_timeout: int,
    codex_binary: str,
    ignore_user_config: bool = False,
    agent_backend: str = "codex",
    api_config: ApiConfig | None = None,
) -> tuple[int | None, str]:
    if not prepare_oracle_supervision(run_dir, task):
        return None, "missing_oracle"
    prompt = build_oracle_supervisor_command_prompt(task, skill.version)
    result = run_role_agent(
        run_dir,
        prompt,
        "oracle_supervisor_final",
        role_backend("supervisor", agent_backend),
        codex_timeout,
        codex_binary=codex_binary,
        ignore_user_config=ignore_user_config,
        api_config=api_config,
        allowed_files=read_allowed_files(run_dir / "prompt_pack" / "supervisor_allowed_files.yaml"),
        output_files=[
            "supervision/supervisor_report.yaml",
            "supervision/story_gap_report.yaml",
            "supervision/textual_gradient.yaml",
            "supervision/optimization_score.yaml",
        ],
    )
    required = [
        run_dir / "supervision" / "supervisor_report.yaml",
        run_dir / "supervision" / "story_gap_report.yaml",
        run_dir / "supervision" / "textual_gradient.yaml",
        run_dir / "supervision" / "optimization_score.yaml",
    ]
    if result.returncode != 0 or any(not path.exists() for path in required):
        return result.returncode, "failed"
    return result.returncode, "done"


def run_oracle_supervisor_only(
    task: AbstractIntroTask,
    run_dir: Path,
    skill: SkillPackage,
    codex_timeout: int,
    codex_binary: str,
    ignore_user_config: bool = False,
    agent_backend: str = "codex",
    api_config: ApiConfig | None = None,
) -> dict[str, Any]:
    record = read_yaml(run_dir / "status.yaml") or {
        "slug": task.slug,
        "field": task.field,
        "skill_version": skill.version,
        "status": "missing_run",
    }
    if not (run_dir / "final" / "abstract_intro.tex").exists():
        record["supervision_status"] = "missing_final_output"
        write_yaml(run_dir / "status.yaml", record)
        return record
    write_oracle_supervisor_pack(run_dir, task, load_task(task.path), skill)
    supervisor_code, supervisor_status = run_oracle_supervisor(
        task,
        run_dir,
        skill,
        codex_timeout,
        codex_binary,
        ignore_user_config=ignore_user_config,
        agent_backend=agent_backend,
        api_config=api_config,
    )
    record["supervision_status"] = supervisor_status
    if supervisor_code is not None:
        record["oracle_supervisor_returncode"] = supervisor_code
    write_yaml(run_dir / "status.yaml", record)
    return record


def build_story_planner_command_prompt(task: AbstractIntroTask, skill_version: str) -> str:
    return f"""# Abstract + Introduction Story Planning Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`

Use only files listed in `prompt_pack/allowed_files.yaml`.
Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the evidence source.
Use the skill files under `skill/` as writing-pattern guidance only; do not treat any distilled development material as facts about this paper.

Read:
- `paper/story/paper_story_contract.yaml` if present. Treat it as a soft paper-level contract: use its selected manuscript route, section role and claim boundaries as prior context, but report corrections in `paper_contract_alignment` if the Abstract+Introduction opening story needs a narrower or clearer framing.
- `skill/prompts/story_blueprint_prompt.md`
- `skill/patterns/abstract_patterns.md`
- `skill/patterns/intro_gap_ladders.md`
- `skill/patterns/distilled_writing_rules.md` if present
- `skill/rubrics/abstract_intro_rubric.yaml`

Write:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`

Do not write `final/abstract_intro.tex` in this step.
`story/evidence_to_story_plan.yaml` must contain `central_headline_claim`, `must_mention_anchors`, `paired_observables`, `figure_role_map`, `method_contribution_map`, `direction_comparator_table`, `claim_boundary_table`, `weak_or_missing_context`, and `section_compression_plan`.
If `paper/story/paper_story_contract.yaml` is present, `story/evidence_to_story_plan.yaml` must also contain `paper_contract_alignment`.
`section_compression_plan` must contain `paragraph_count_target`, `paragraph_roles`, `abstract_must_include`, `intro_must_include`, `mention_once_only`, and `omit_or_defer`.
Before exiting, reopen the YAML files you wrote and verify they parse and contain the required keys above.
"""


def uses_story_contract(skill_version: str) -> bool:
    return skill_version == "nature_writing_current_abstract_intro" or any(token in skill_version for token in ("v2_1", "v2_2", "v2_3", "v2_6", "v2_8", "story_refined", "payoff_refined"))


def uses_payoff_contract(skill_version: str) -> bool:
    return skill_version == "nature_writing_current_abstract_intro" or any(token in skill_version for token in ("v2_2", "v2_3", "v2_6", "v2_8", "payoff_refined"))


def build_story_refiner_command_prompt(task: AbstractIntroTask, skill_version: str, round_index: int = 0) -> str:
    review_hint = (
        f"\nAlso read `reviews/abstract_intro_review_round_{round_index - 1:03d}.yaml` "
        "and repair story-level issues before prose is refined."
        if round_index > 0
        else ""
    )
    return f"""# Abstract + Introduction Story Contract Refinement Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`
Story refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`

Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the only paper-specific evidence source.

Goal:
Convert the raw story plan into a compact writing contract. Do not write the
manuscript. Compare candidate story routes when present; if only one route is
present, construct two plausible alternatives from the evidence and explain why
they are weaker. The final contract should make the writer choose, rank, and
compress evidence rather than checklist every anchor.

Read:
- `context_pack/context.md`
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `skill/prompts/story_blueprint_prompt.md`
- `skill/prompts/writer_prompt.md`
- `skill/rubrics/abstract_intro_rubric.yaml`
- `skill/patterns/distilled_writing_rules.md` if present
{review_hint}

Write:
- `story/story_critic.yaml`
- `story/story_contract.yaml`

`story/story_critic.yaml` must include:
- `candidate_assessments`
- `selected_candidate`
- `rejected_or_downweighted_routes`
- `story_level_risks`

`story/story_contract.yaml` must include:
- `schema_version: nature_orchestrator.story_contract.v1`
- `selected_story`
- `story_route`
- `central_thesis`
- `hero_evidence`
- `support_evidence`
- `boundary_evidence`
- `omit_or_defer`
- `figure_writing_actions`
- `section_strategy`
- `claim_boundaries`
- `reviewer_story_level_triggers`
- for v2.2, v2.3, or payoff-refined skills: `high_impact_payoff_anchors`,
  `abstract_closing_payoff`, and `intro_final_payoff`

Rules:
- For v2.3/story-tournament skills, compare at least three plausible story
  routes before selecting one. Record why rejected candidates lost under
  `story/story_critic.yaml`.
- `hero_evidence` should contain only contribution-defining anchors.
- `support_evidence` should contain anchors that strengthen the story but should
  not dominate the abstract or opening Introduction.
- `boundary_evidence` should contain limitations, failure cases, null/no-effect
  evidence, subgroup boundaries, or claim-safety qualifiers.
- `figure_writing_actions` must turn each important figure role into a prose
  instruction: expand, compress, use as transition, use as validation, use as
  boundary close, or omit/defer.
- `section_strategy` must separately describe abstract disclosure and
  Introduction paragraph strategy.
- For v2.2, v2.3, or payoff-refined skills, identify at least one recoverable high-impact
  payoff anchor: a quantitative constraint, mechanistic parameter,
  detectability/transfer implication, or bounded cross-scale/generalization
  claim. If present and central, it must be protected for the abstract close or
  final Introduction paragraph.
- For v2.2, v2.3, or payoff-refined skills, do a context payoff-candidate sweep before trusting
  the raw plan. Search `context_pack/context.md` for contribution cues such as
  "allow", "infer", "constraint", "range", "detect", "revisit", "reasonable
  ranges", "state-evolution slip distance", "dynamic rupture", "parameter",
  "transfer", "natural", and numeric ranges. Promote a candidate only if it is
  recoverable and central; otherwise list it under boundary or omit/defer.
- Before exiting, reopen both YAML files and verify they parse.
"""


def build_writer_command_prompt(task: AbstractIntroTask, skill_version: str) -> str:
    return f"""# Abstract + Introduction Drafting Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated file:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present

Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the evidence source.
Use the selected story blueprint as the plan. Do not regenerate story candidates unless the blueprint is internally inconsistent.
Use `story/evidence_to_story_plan.yaml` as the must-mention anchor and claim-boundary contract. Do not omit recoverable `must_mention_anchors`.
If `story/story_contract.yaml` exists, treat it as the final story-selection and
evidence-hierarchy contract. Follow its `hero_evidence`, `support_evidence`,
`boundary_evidence`, `omit_or_defer`, `figure_writing_actions`, and
`section_strategy` over the raw anchor list.
When story files include `high_impact_payoff_anchors`, use them to decide
whether the abstract close or final Introduction paragraph must state a
recoverable quantitative constraint, mechanistic parameter, detectability
implication, or bounded transfer payoff.
Use `section_compression_plan` to compress evidence selectively. Do not expand every anchor into a separate sentence or paragraph.

Read:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `skill/prompts/writer_prompt.md`
- `skill/patterns/abstract_patterns.md`
- `skill/patterns/intro_gap_ladders.md`
- `skill/patterns/distilled_writing_rules.md` if present
- `skill/rubrics/abstract_intro_rubric.yaml`

Write:
- `final/abstract_intro.tex`

`final/abstract_intro.tex` must contain one `\\begin{{abstract}}...\\end{{abstract}}` block followed by Introduction prose. Omit `\\section{{Introduction}}`.
"""


def build_reviewer_command_prompt(task: AbstractIntroTask, skill_version: str, round_index: int = 0) -> str:
    review_path = f"reviews/abstract_intro_review_round_{round_index:03d}.yaml"
    return f"""# Abstract + Introduction Review Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`
Review round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/abstract_intro.tex`

Read `skill/prompts/reviewer_prompt.md`, `skill/rubrics/abstract_intro_rubric.yaml`, and `skill/patterns/distilled_writing_rules.md` if present.
Also read `context_pack/context.md` before passing a v2.2, v2.3, or payoff-refined skill.
Be strict. Do not rewrite the manuscript.
The review YAML must include `must_mention_anchor_recall`, `missing_recoverable_anchors`, `direction_comparator_errors`, `over_conservatism`, `unrecoverable_detail_risk`, and an explicit audit of `section_compression_plan`.
If `story/story_contract.yaml` exists, separately audit whether the draft follows
its `central_thesis`, `hero_evidence`, `figure_writing_actions`, and
`omit_or_defer` choices. Put story-contract failures under `story_level_issues`;
put local prose, formatting, or minor anchor issues under `text_level_issues`.
For payoff-enabled skills including v2.2, v2.3, v2.6, v2.8, or payoff-refined
skills, the review YAML must include `payoff_anchor_audit` and
`safe_underclaiming_risk: low | medium | high`. Do not pass a safe, fluent draft if it omits a
recoverable high-impact payoff anchor that would materially strengthen the
Nature-level contribution; mark it as `revise` and put the omission under
`story_level_issues` and `required_revisions`.
For payoff-enabled skills including v2.2, v2.3, v2.6, v2.8, or payoff-refined
skills, do a context payoff-candidate sweep before pass:
look for contribution cues such as "allow", "infer", "constraint", "range",
"detect", "revisit", "reasonable ranges", "state-evolution slip distance",
"dynamic rupture", "parameter", "transfer", "natural", and numeric ranges.
It must also include top-level `status`, `accepted_by_reviewers`, `blocking_issues`, `required_revisions`, `abstract_specificity_score`, `intro_gap_ladder_score`, `evidence_disclosure_score`, `story_novelty_score`, `claim_safety_score`, and `nature_style_score`.
For every review, separately score the abstract and Introduction:
- `abstract_component_score`: 1-5, based on evidence disclosure, contribution specificity, claim calibration and compact writing flow.
- `introduction_component_score`: 1-5, based on gap ladder, article-specific bottleneck, contribution framing, paragraph flow and avoidance of Results-preview inventory.
Also include `abstract_component_diagnosis` and `introduction_component_diagnosis` as concise lists of targeted issues or strengths.
Do not pass a draft whose Introduction exceeds the plan by more than one paragraph or reads like a Results preview.
Before exiting, reopen `{review_path}` and verify it parses as YAML and contains all required top-level fields.

Write only:
- `{review_path}`
"""


def build_reviewer_schema_repair_prompt(task: AbstractIntroTask, skill_version: str, round_index: int = 0) -> str:
    review_path = f"reviews/abstract_intro_review_round_{round_index:03d}.yaml"
    return f"""# Abstract + Introduction Reviewer YAML Schema Repair

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`
Review round: `{round_index:03d}`

The manuscript review has already been written, but `reviewer_acceptance_gate`
found schema-level omissions in `{review_path}`. Do not rewrite the manuscript
and do not change the review decision unless the existing YAML is internally
contradictory. Repair only the review YAML schema.

Read:
- `{review_path}`
- `audits/reviewer_acceptance_gate.yaml`
- `final/abstract_intro.tex`
- `skill/prompts/reviewer_prompt.md`
- `skill/rubrics/abstract_intro_rubric.yaml`

The repaired YAML must include all top-level score fields:
- `abstract_specificity_score`
- `intro_gap_ladder_score`
- `abstract_component_score`
- `introduction_component_score`
- `evidence_disclosure_score`
- `story_novelty_score`
- `claim_safety_score`
- `nature_style_score`

Preserve existing detailed audits such as `must_mention_anchor_recall`,
`missing_recoverable_anchors`, `direction_comparator_errors`,
`over_conservatism`, and `unrecoverable_detail_risk`.
Before exiting, reopen `{review_path}` and verify it parses as YAML and contains all required top-level fields.

Write only:
- `{review_path}`
"""


def build_refiner_command_prompt(task: AbstractIntroTask, skill_version: str, round_index: int) -> str:
    previous_round = round_index - 1
    return f"""# Abstract + Introduction Targeted Refinement Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`
Refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/abstract_intro.tex`
- `reviews/abstract_intro_review_round_{previous_round:03d}.yaml`
- `audits/abstract_intro_format_gate.yaml`
- `audits/evidence_anchor_gate.yaml`
- `audits/reviewer_acceptance_gate.yaml`

Read:
- `skill/prompts/refiner_prompt.md`
- `skill/prompts/writer_prompt.md`
- `skill/rubrics/abstract_intro_rubric.yaml`
- `skill/patterns/distilled_writing_rules.md` if present

Revise only the blocking or required issues raised by the previous review or deterministic gate reports.
Preserve supported quantitative evidence, causal direction, comparator language
and the selected central story. If `story/story_contract.yaml` exists, follow its
evidence hierarchy and figure-writing actions; do not re-expand omitted/deferred
anchors unless the reviewer explicitly identifies a story-level failure.
Do not inspect forbidden paths. Do not use oracle files.

Write:
- updated `final/abstract_intro.tex`
- `revisions/refine_round_{round_index:03d}.md`
"""


def build_gate_refiner_command_prompt(task: AbstractIntroTask, skill_version: str, round_index: int) -> str:
    return f"""# Abstract + Introduction Gate-Driven Refinement Task

Task: `{task.slug}` / `{task.field}`
Skill version: `{skill_version}`
Refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/story_blueprint.yaml`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/abstract_intro.tex`
- `audits/abstract_intro_format_gate.yaml`
- `audits/evidence_anchor_gate.yaml`
- `audits/claim_safety_gate.yaml`
- `audits/nature_style_compression_gate.yaml`

The previous draft failed deterministic gates before reviewer review. Revise only
the blocking gate issues. Preserve supported evidence and the central story.
Do not inspect forbidden paths. Do not use oracle files.

Write:
- updated `final/abstract_intro.tex`
- `revisions/refine_round_{round_index:03d}.md`
"""


def can_refine_after_failure(rounds_used: int, max_refiner_rounds: int) -> bool:
    return rounds_used < max_refiner_rounds


def read_allowed_files(path: Path) -> list[str]:
    data = read_yaml(path) or {}
    return [str(item) for item in data.get("allowed_files") or []]


def role_backend(role: str, agent_backend: str) -> str:
    if agent_backend in {"codex", "api"}:
        return agent_backend
    if agent_backend == "codex+api":
        return "api" if role in {"reviewer", "supervisor"} else "codex"
    raise ValueError(f"Unsupported agent backend: {agent_backend}")


def abstract_intro_role_allowed(role: str, round_index: int = 0) -> list[str]:
    base = [
        "context_pack/context.md",
        "context_pack/context.yaml",
        "context_pack/evidence_manifest.yaml",
        "paper/story/paper_story_contract.yaml",
        "skill/rubrics/abstract_intro_rubric.yaml",
    ]
    patterns = [
        "skill/patterns/abstract_patterns.md",
        "skill/patterns/intro_gap_ladders.md",
        "skill/patterns/story_blueprint_schema.yaml",
        "skill/patterns/distilled_writing_rules.md",
    ]
    if role == "planner":
        return base + patterns + ["skill/prompts/story_blueprint_prompt.md", "skill/prompts/writer_prompt.md"]
    if role == "story_refiner":
        return base + patterns + [
            "story/story_blueprint.yaml",
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            f"reviews/abstract_intro_review_round_{max(0, round_index - 1):03d}.yaml",
            "skill/prompts/story_blueprint_prompt.md",
            "skill/prompts/writer_prompt.md",
        ]
    if role == "writer":
        return base + patterns + [
            "story/story_blueprint.yaml",
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "skill/prompts/writer_prompt.md",
        ]
    if role == "reviewer":
        return base + patterns + [
            "story/story_blueprint.yaml",
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "final/abstract_intro.tex",
            "skill/prompts/reviewer_prompt.md",
        ]
    if role == "refiner":
        return base + patterns + [
            "story/story_blueprint.yaml",
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "final/abstract_intro.tex",
            f"reviews/abstract_intro_review_round_{round_index:03d}.yaml",
            "audits/abstract_intro_format_gate.yaml",
            "audits/evidence_anchor_gate.yaml",
            "audits/claim_safety_gate.yaml",
            "audits/nature_style_compression_gate.yaml",
            "audits/reviewer_acceptance_gate.yaml",
            "skill/prompts/refiner_prompt.md",
            "skill/prompts/writer_prompt.md",
        ]
    return base


def run_role_agent(
    run_dir: Path,
    prompt: str,
    log_prefix: str,
    backend: str,
    timeout: int,
    codex_binary: str = "codex",
    ignore_user_config: bool = False,
    api_config: ApiConfig | None = None,
    allowed_files: list[str] | None = None,
    output_files: list[str] | None = None,
) -> AgentResult:
    result = run_agent(
        role=log_prefix,
        run_dir=run_dir,
        prompt=prompt,
        allowed_files=allowed_files or read_allowed_files(run_dir / "prompt_pack" / "allowed_files.yaml"),
        output_contract={"files": output_files or []},
        backend=backend,
        timeout=timeout,
        codex_binary=codex_binary,
        ignore_user_config=ignore_user_config,
        api_config=api_config,
    )
    write_yaml(
        run_dir / "logs" / f"{log_prefix}.agent_result.yaml",
        {
            "role": result.role,
            "backend": result.backend,
            "returncode": result.returncode,
            "status": result.status,
            "elapsed_sec": result.elapsed_sec,
            "files_written": result.files_written,
            "error": result.error,
        },
    )
    return result


def run_codex(run_dir: Path, prompt: str, log_prefix: str, timeout: int, codex_binary: str = "codex", ignore_user_config: bool = False) -> int:
    return run_role_agent(
        run_dir,
        prompt,
        log_prefix,
        "codex",
        timeout,
        codex_binary=codex_binary,
        ignore_user_config=ignore_user_config,
    ).returncode


def abstract_intro_format_gate(text: str, slug: str, fingerprint: dict[str, Any] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    begin_count = len(re.findall(r"\\begin\{abstract\}", text or ""))
    end_count = len(re.findall(r"\\end\{abstract\}", text or ""))
    if begin_count != 1 or end_count != 1:
        issues.append("expected exactly one abstract block")
    end_match = re.search(r"\\end\{abstract\}", text or "")
    if end_match and not (text[end_match.end() :].strip()):
        issues.append("missing Introduction prose after abstract")
    for match in SECTION_HEADING_RE.finditer(text or ""):
        heading = (match.group(1) or match.group(2) or "").strip()
        normalized = re.sub(r"\s+", " ", heading).lower()
        if normalized in {"introduction", "results", "discussion", "methods"}:
            issues.append(f"forbidden section heading: {heading}")
    lower = (text or "").lower()
    leaked = [item for item in fingerprint_blocklist(slug, fingerprint) if item.lower() in lower]
    for item in leaked:
        issues.append(f"forbidden target fingerprint leakage: {item}")
    return {
        "schema_version": "nature_orchestrator.abstract_intro_format_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": sorted(set(issues)),
    }


def payoff_audit_has_missing_or_underclaimed_anchor(review: dict[str, Any]) -> bool:
    audit = review.get("payoff_anchor_audit")
    if isinstance(audit, dict):
        missing = audit.get("missing") or audit.get("missing_payoff_anchors") or audit.get("missing_required_payoff_anchors") or []
        if isinstance(missing, dict):
            missing = [key for key, value in missing.items() if value]
        if missing:
            return True
        if audit.get("pass_allowed") is False:
            return True
    risk = safe_underclaiming_risk_level(review)
    return risk in {"medium", "high"}


def safe_underclaiming_risk_level(review: dict[str, Any]) -> str:
    risk = review.get("safe_underclaiming_risk")
    if isinstance(risk, dict):
        risk = risk.get("risk_level") or risk.get("level") or risk.get("status") or risk.get("risk")
    return str(risk or "").strip().lower()


def reviewer_acceptance_gate(review: dict[str, Any], require_payoff_audit: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    status = review.get("status")
    if status not in {"pass", "revise", "fail"}:
        issues.append("status must be pass, revise, or fail")
    if not isinstance(review.get("accepted_by_reviewers"), bool):
        issues.append("accepted_by_reviewers must be boolean")
    for field in REVIEW_SCORE_FIELDS:
        score = review.get(field)
        if score is None:
            issues.append(f"missing score: {field}")
            continue
        if not isinstance(score, (int, float)) or not 1 <= float(score) <= 5:
            issues.append(f"score must be between 1 and 5: {field}")
    blocking = review.get("blocking_issues") or []
    required = review.get("required_revisions") or []
    has_blocking = bool(blocking)
    has_required = bool(required)
    if status == "pass" and has_blocking:
        issues.append("pass review cannot contain blocking_issues")
    if status in {"revise", "fail"} and not (has_blocking or has_required):
        issues.append("revise/fail review must include blocking_issues or required_revisions")
    if status == "pass" and isinstance(review.get("nature_style_score"), (int, float)) and float(review["nature_style_score"]) < 4:
        issues.append("pass review requires nature_style_score >= 4")
    if require_payoff_audit:
        audit = review.get("payoff_anchor_audit")
        risk = safe_underclaiming_risk_level(review)
        if not isinstance(audit, dict):
            issues.append("missing payoff_anchor_audit")
        if risk not in {"low", "medium", "high"}:
            issues.append("safe_underclaiming_risk must be low, medium, or high")
        if status == "pass" and payoff_audit_has_missing_or_underclaimed_anchor(review):
            issues.append("pass review cannot omit high-impact payoff anchors or carry medium/high safe_underclaiming_risk")
    return {
        "schema_version": "nature_orchestrator.reviewer_acceptance_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": sorted(set(issues)),
    }


def is_schema_only_reviewer_gate_failure(report: dict[str, Any]) -> bool:
    issues = report.get("blocking_issues") or []
    if not issues:
        return False
    schema_prefixes = (
        "missing score:",
        "score must be between 1 and 5:",
        "accepted_by_reviewers must be boolean",
        "status must be pass, revise, or fail",
    )
    return all(any(str(issue).startswith(prefix) for prefix in schema_prefixes) for issue in issues)


def evidence_anchor_gate(generated: str, manifest: dict[str, Any], context_text: str) -> dict[str, Any]:
    allowed_numeric = {normalize_anchor(item) for item in manifest.get("numeric_anchors") or []}
    allowed_figures = {normalize_anchor(item) for item in manifest.get("figure_refs") or []}
    allowed_base_figures = {base_figure_ref(item) for item in allowed_figures}
    context_lower = (context_text or "").lower().replace("μ", "µ")
    generated_numeric = extract_numeric_anchors(generated)
    generated_figures = extract_figure_refs(generated)
    unsupported_numeric = [
        item for item in generated_numeric if item not in allowed_numeric and item not in context_lower
    ]
    unsupported_figures = [
        item
        for item in generated_figures
        if item not in allowed_figures and base_figure_ref(item) not in allowed_base_figures and item not in context_lower
    ]
    issues = []
    if unsupported_numeric:
        issues.append("unsupported numeric anchors")
    if unsupported_figures:
        issues.append("unsupported figure references")
    return {
        "schema_version": "nature_orchestrator.evidence_anchor_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
        "generated_numeric_anchors": generated_numeric,
        "generated_figure_refs": generated_figures,
        "unsupported_numeric_anchors": unsupported_numeric,
        "unsupported_figure_refs": unsupported_figures,
    }


def claim_safety_gate(text: str) -> dict[str, Any]:
    flagged: list[dict[str, Any]] = []
    for line_number, line in enumerate((text or "").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for match in STRONG_CAUSAL_RE.finditer(stripped):
            window_start = max(0, match.start() - 100)
            window_end = min(len(stripped), match.end() + 100)
            context = stripped[window_start:window_end]
            if not OVERREACH_CONTEXT_RE.search(context):
                continue
            if ASSOCIATION_CUE_RE.search(context) and match.group(0).lower() not in {"produce", "produces", "produced", "producing"}:
                continue
            flagged.append(
                {
                    "phrase": match.group(0).lower(),
                    "line": line_number,
                    "context": context,
                    "risk": "strong causal mechanism language",
                }
            )
    issues = ["strong causal mechanism language"] if flagged else []
    return {
        "schema_version": "nature_orchestrator.claim_safety_gate.v1",
        "status": "warning" if flagged else "passed",
        "blocking_issues": issues,
        "flagged_phrases": flagged,
    }


def abstract_intro_parts(text: str) -> tuple[str, str]:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text or "", re.DOTALL | re.IGNORECASE)
    if not match:
        return "", text or ""
    return match.group(1).strip(), (text or "")[match.end() :].strip()


def prose_paragraphs(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"\n\s*\n", text or "")
        if item.strip() and not item.strip().startswith("\\")
    ]


def compression_target(plan: dict[str, Any]) -> int:
    compression = plan.get("section_compression_plan") if isinstance(plan, dict) else {}
    if not isinstance(compression, dict):
        return 4
    value = compression.get("paragraph_count_target")
    try:
        target = int(value)
    except (TypeError, ValueError):
        return 4
    return max(3, min(target, 5))


def nature_style_compression_gate(text: str, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = plan or {}
    abstract, intro = abstract_intro_parts(text)
    paragraphs = prose_paragraphs(intro)
    target = compression_target(plan)
    max_intro_paragraphs = max(5, target + 1)
    issues: list[str] = []
    if len(paragraphs) > max_intro_paragraphs:
        issues.append(f"too many Introduction paragraphs: {len(paragraphs)} > {max_intro_paragraphs}")
    if len(abstract.split()) > 330:
        issues.append("abstract is too long for a compressed Nature-style summary")
    intro_figure_refs = extract_figure_refs(intro)
    intro_numeric = extract_numeric_anchors(intro)
    if len(intro_figure_refs) >= 5 or len(intro_numeric) >= 10:
        issues.append("Introduction reads like an overloaded Results preview")
    return {
        "schema_version": "nature_orchestrator.nature_style_compression_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": sorted(set(issues)),
        "intro_paragraph_count": len(paragraphs),
        "paragraph_count_target": target,
        "intro_numeric_anchor_count": len(intro_numeric),
        "intro_figure_ref_count": len(intro_figure_refs),
    }


def write_gate_report(run_dir: Path, gate_name: str, round_index: int, report: dict[str, Any]) -> None:
    audits = run_dir / "audits"
    audits.mkdir(parents=True, exist_ok=True)
    payload = {**report, "round_index": round_index, "gate": gate_name}
    write_yaml(audits / f"{gate_name}_round_{round_index:03d}.yaml", payload)
    write_yaml(audits / f"{gate_name}.yaml", payload)


def draft_gates_pass(run_dir: Path, task: AbstractIntroTask, round_index: int) -> tuple[bool, list[str]]:
    text = read_text_if_exists(run_dir / "final" / "abstract_intro.tex")
    support_text = build_abstract_intro_support_text(run_dir)
    manifest = build_evidence_manifest(support_text)
    write_yaml(run_dir / "context_pack" / "evidence_manifest.yaml", manifest)
    fingerprint: dict[str, Any] = {}
    if task.path.exists():
        try:
            fingerprint = load_target_fingerprint(load_task(task.path))
        except Exception:
            fingerprint = {}
    format_report = abstract_intro_format_gate(text, task.slug, fingerprint=fingerprint)
    evidence_report = evidence_anchor_gate(text, manifest, support_text)
    claim_report = claim_safety_gate(text)
    plan = read_yaml(run_dir / "story" / "evidence_to_story_plan.yaml")
    style_report = nature_style_compression_gate(text, plan if isinstance(plan, dict) else {})
    write_gate_report(run_dir, "abstract_intro_format_gate", round_index, format_report)
    write_gate_report(run_dir, "evidence_anchor_gate", round_index, evidence_report)
    write_gate_report(run_dir, "claim_safety_gate", round_index, claim_report)
    write_gate_report(run_dir, "nature_style_compression_gate", round_index, style_report)
    failed = [
        "abstract_intro_format_gate" if format_report["status"] != "passed" else "",
        "evidence_anchor_gate" if evidence_report["status"] != "passed" else "",
        "nature_style_compression_gate" if style_report["status"] != "passed" else "",
    ]
    return not any(failed), [item for item in failed if item]


def reviewer_gate_pass(run_dir: Path, review: dict[str, Any], round_index: int, require_payoff_audit: bool = False) -> tuple[bool, list[str]]:
    report = reviewer_acceptance_gate(review, require_payoff_audit=require_payoff_audit)
    write_gate_report(run_dir, "reviewer_acceptance_gate", round_index, report)
    return report["status"] == "passed", ([] if report["status"] == "passed" else ["reviewer_acceptance_gate"])


def evidence_to_story_plan_gate(run_dir: Path) -> tuple[bool, list[str]]:
    required = [
        "central_headline_claim",
        "must_mention_anchors",
        "paired_observables",
        "figure_role_map",
        "method_contribution_map",
        "direction_comparator_table",
        "claim_boundary_table",
        "weak_or_missing_context",
        "section_compression_plan",
    ]
    plan, parse_error = read_gate_yaml(run_dir / "story" / "evidence_to_story_plan.yaml")
    issues = [f"missing evidence_to_story_plan key: {key}" for key in required if key not in plan]
    if parse_error:
        issues.insert(0, f"malformed evidence_to_story_plan.yaml: {parse_error}")
    anchors = plan.get("must_mention_anchors") if isinstance(plan, dict) else None
    if not isinstance(anchors, (list, dict)):
        issues.append("must_mention_anchors must be a list or mapping")
    compression = plan.get("section_compression_plan") if isinstance(plan, dict) else None
    if not isinstance(compression, dict):
        issues.append("section_compression_plan must be a mapping")
    else:
        for key in ("paragraph_count_target", "paragraph_roles", "abstract_must_include", "intro_must_include", "mention_once_only", "omit_or_defer"):
            if key not in compression:
                issues.append(f"missing section_compression_plan key: {key}")
    report = {
        "schema_version": "nature_orchestrator.evidence_to_story_plan_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }
    write_gate_report(run_dir, "evidence_to_story_plan_gate", 0, report)
    return report["status"] == "passed", ([] if report["status"] == "passed" else ["evidence_to_story_plan_gate"])


def story_contract_gate(run_dir: Path, require_payoff_contract: bool = False) -> tuple[bool, list[str]]:
    required = [
        "selected_story",
        "story_route",
        "central_thesis",
        "hero_evidence",
        "support_evidence",
        "boundary_evidence",
        "omit_or_defer",
        "figure_writing_actions",
        "section_strategy",
        "claim_boundaries",
        "reviewer_story_level_triggers",
    ]
    contract, parse_error = read_gate_yaml(run_dir / "story" / "story_contract.yaml")
    issues = [f"missing story_contract key: {key}" for key in required if key not in contract]
    if parse_error:
        issues.insert(0, f"malformed story_contract.yaml: {parse_error}")
    for key in ("hero_evidence", "support_evidence", "boundary_evidence", "omit_or_defer", "figure_writing_actions"):
        value = contract.get(key) if isinstance(contract, dict) else None
        if not isinstance(value, (list, dict)):
            issues.append(f"{key} must be a list or mapping")
    section_strategy = contract.get("section_strategy") if isinstance(contract, dict) else None
    if not isinstance(section_strategy, (list, dict)) or not section_strategy:
        issues.append("section_strategy must be a non-empty list or mapping")
    thesis = contract.get("central_thesis") if isinstance(contract, dict) else None
    if not isinstance(thesis, str) or len(thesis.strip()) < 20:
        issues.append("central_thesis must be a specific non-empty sentence")
    if require_payoff_contract:
        payoff = contract.get("high_impact_payoff_anchors") if isinstance(contract, dict) else None
        if not isinstance(payoff, (list, dict)) or not payoff:
            issues.append("high_impact_payoff_anchors must be a non-empty list or mapping")
    report = {
        "schema_version": "nature_orchestrator.story_contract_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }
    write_gate_report(run_dir, "story_contract_gate", 0, report)
    return report["status"] == "passed", ([] if report["status"] == "passed" else ["story_contract_gate"])


def review_has_story_level_issues(review: dict[str, Any]) -> bool:
    if payoff_audit_has_missing_or_underclaimed_anchor(review):
        return True
    issues = review.get("story_level_issues")
    if isinstance(issues, list) and issues:
        return True
    if isinstance(issues, dict) and any(issues.values()):
        return True
    blocking = " ".join(str(item).lower() for item in (review.get("blocking_issues") or []))
    return any(
        cue in blocking
        for cue in (
            "central story",
            "central thesis",
            "story contract",
            "figure hierarchy",
            "evidence hierarchy",
            "payoff",
            "underclaim",
            "underclaiming",
            "story-level",
            "story level",
        )
    )


def run_task(
    task: AbstractIntroTask,
    run_dir: Path,
    skill: SkillPackage,
    image_mode: str,
    prepare_only: bool,
    codex_timeout: int,
    codex_binary: str,
    max_refiner_rounds: int = 0,
    ignore_user_config: bool = False,
    oracle_supervisor: bool = False,
    agent_backend: str = "codex",
    api_config: ApiConfig | None = None,
    paper_story_contract: Path | None = None,
) -> dict[str, Any]:
    copy_paper_story_contract(run_dir, paper_story_contract)
    write_abstract_intro_prompt_pack(run_dir, task, skill, image_mode=image_mode)
    record: dict[str, Any] = {
        "slug": task.slug,
        "field": task.field,
        "skill_version": skill.version,
        "status": "prepared",
        "max_refiner_rounds": max_refiner_rounds,
        "refiner_rounds_used": 0,
        "review_rounds": 0,
    }
    if prepare_only:
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    planner_result = run_role_agent(
        run_dir,
        build_story_planner_command_prompt(task, skill.version),
        "story_planner",
        role_backend("planner", agent_backend),
        codex_timeout,
        codex_binary=codex_binary,
        ignore_user_config=ignore_user_config,
        api_config=api_config,
        allowed_files=abstract_intro_role_allowed("planner"),
        output_files=["story/story_blueprint.yaml", "story/evidence_to_story_plan.yaml"],
    )
    planner_code = planner_result.returncode
    record["story_planner_returncode"] = planner_code
    record["story_planner_backend"] = planner_result.backend
    record["story_planner_elapsed_sec"] = planner_result.elapsed_sec
    if planner_code != 0 or not (run_dir / "story" / "story_blueprint.yaml").exists():
        record["status"] = "story_planner_failed"
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    plan_ok, plan_failed_gates = evidence_to_story_plan_gate(run_dir)
    if not plan_ok:
        record["status"] = "gate_failed"
        record["failed_gates"] = plan_failed_gates
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    if uses_story_contract(skill.version):
        story_refiner_result = run_role_agent(
            run_dir,
            build_story_refiner_command_prompt(task, skill.version, 0),
            "story_refiner",
            role_backend("planner", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            ignore_user_config=ignore_user_config,
            api_config=api_config,
            allowed_files=abstract_intro_role_allowed("story_refiner"),
            output_files=["story/story_critic.yaml", "story/story_contract.yaml"],
        )
        record["story_refiner_returncode"] = story_refiner_result.returncode
        record["story_refiner_backend"] = story_refiner_result.backend
        record["story_refiner_elapsed_sec"] = story_refiner_result.elapsed_sec
        if story_refiner_result.returncode != 0 or not (run_dir / "story" / "story_contract.yaml").exists():
            record["status"] = "story_refiner_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        contract_ok, contract_failed_gates = story_contract_gate(run_dir, require_payoff_contract=uses_payoff_contract(skill.version))
        if not contract_ok:
            record["status"] = "gate_failed"
            record["failed_gates"] = contract_failed_gates
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
    writer_allowed = abstract_intro_role_allowed("writer")
    writer_result = run_role_agent(
        run_dir,
        build_writer_command_prompt(task, skill.version),
        "writer",
        role_backend("writer", agent_backend),
        codex_timeout,
        codex_binary=codex_binary,
        ignore_user_config=ignore_user_config,
        api_config=api_config,
        allowed_files=writer_allowed,
        output_files=["final/abstract_intro.tex"],
    )
    writer_code = writer_result.returncode
    record["writer_returncode"] = writer_code
    record["writer_backend"] = writer_result.backend
    record["writer_elapsed_sec"] = writer_result.elapsed_sec
    if writer_code != 0 or not (run_dir / "final" / "abstract_intro.tex").exists():
        record["status"] = "writer_failed"
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    save_draft(run_dir, 0)
    gates_ok, failed_gates = draft_gates_pass(run_dir, task, 0)
    while not gates_ok and can_refine_after_failure(record["refiner_rounds_used"], max_refiner_rounds):
        next_round = record["refiner_rounds_used"] + 1
        refiner_result = run_role_agent(
            run_dir,
            build_gate_refiner_command_prompt(task, skill.version, round_index=next_round),
            f"gate_refiner_{next_round:03d}",
            role_backend("refiner", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            ignore_user_config=ignore_user_config,
            api_config=api_config,
            allowed_files=abstract_intro_role_allowed("refiner", 0),
            output_files=["final/abstract_intro.tex", f"revisions/refine_round_{next_round:03d}.md"],
        )
        record[f"refiner_{next_round:03d}_returncode"] = refiner_result.returncode
        record[f"refiner_{next_round:03d}_backend"] = refiner_result.backend
        record[f"refiner_{next_round:03d}_elapsed_sec"] = refiner_result.elapsed_sec
        if refiner_result.returncode != 0 or not (run_dir / "final" / "abstract_intro.tex").exists():
            record["status"] = "refiner_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        record["refiner_rounds_used"] = next_round
        save_draft(run_dir, next_round)
        gates_ok, failed_gates = draft_gates_pass(run_dir, task, next_round)
    if not gates_ok:
        record["status"] = "gate_failed"
        record["failed_gates"] = failed_gates
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    for round_index in range(max_refiner_rounds + 1):
        review_path_rel = f"reviews/abstract_intro_review_round_{round_index:03d}.yaml"
        reviewer_allowed = abstract_intro_role_allowed("reviewer", round_index)
        reviewer_result = run_role_agent(
            run_dir,
            build_reviewer_command_prompt(task, skill.version, round_index=round_index),
            f"reviewer_{round_index:03d}",
            role_backend("reviewer", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            ignore_user_config=ignore_user_config,
            api_config=api_config,
            allowed_files=reviewer_allowed,
            output_files=[review_path_rel],
        )
        reviewer_code = reviewer_result.returncode
        review_path = run_dir / "reviews" / f"abstract_intro_review_round_{round_index:03d}.yaml"
        record[f"reviewer_{round_index:03d}_returncode"] = reviewer_code
        record[f"reviewer_{round_index:03d}_backend"] = reviewer_result.backend
        record[f"reviewer_{round_index:03d}_elapsed_sec"] = reviewer_result.elapsed_sec
        record["review_rounds"] = round_index + 1
        if reviewer_code != 0 or not review_path.exists():
            record["status"] = "reviewer_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        canonical_review = run_dir / "reviews" / "abstract_intro_review.yaml"
        canonical_review.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(review_path, canonical_review)
        review = read_yaml(review_path) or {}
        reviewer_ok, reviewer_failed_gates = reviewer_gate_pass(
            run_dir,
            review,
            round_index,
            require_payoff_audit=uses_payoff_contract(skill.version),
        )
        if not reviewer_ok:
            repair_report = read_yaml(run_dir / "audits" / "reviewer_acceptance_gate.yaml") or {}
            if is_schema_only_reviewer_gate_failure(repair_report):
                repair_allowed = abstract_intro_role_allowed("reviewer", round_index) + [
                    review_path_rel,
                    "audits/reviewer_acceptance_gate.yaml",
                    f"audits/reviewer_acceptance_gate_round_{round_index:03d}.yaml",
                ]
                repair_result = run_role_agent(
                    run_dir,
                    build_reviewer_schema_repair_prompt(task, skill.version, round_index=round_index),
                    f"reviewer_schema_repair_{round_index:03d}",
                    role_backend("reviewer", agent_backend),
                    codex_timeout,
                    codex_binary=codex_binary,
                    ignore_user_config=ignore_user_config,
                    api_config=api_config,
                    allowed_files=repair_allowed,
                    output_files=[review_path_rel],
                )
                record[f"reviewer_schema_repair_{round_index:03d}_returncode"] = repair_result.returncode
                record[f"reviewer_schema_repair_{round_index:03d}_backend"] = repair_result.backend
                record[f"reviewer_schema_repair_{round_index:03d}_elapsed_sec"] = repair_result.elapsed_sec
                if repair_result.returncode == 0 and review_path.exists():
                    shutil.copy2(review_path, canonical_review)
                    review = read_yaml(review_path) or {}
                    reviewer_ok, reviewer_failed_gates = reviewer_gate_pass(
                        run_dir,
                        review,
                        round_index,
                        require_payoff_audit=uses_payoff_contract(skill.version),
                    )
            if reviewer_ok:
                pass
            elif is_schema_only_reviewer_gate_failure(read_yaml(run_dir / "audits" / "reviewer_acceptance_gate.yaml") or {}):
                record["reviewer_returncode"] = reviewer_code
                record["status"] = "reviewer_failed"
                record["failed_gates"] = reviewer_failed_gates
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
        if not reviewer_ok:
            if round_index >= max_refiner_rounds:
                record["reviewer_returncode"] = reviewer_code
                record["status"] = "gate_failed"
                record["failed_gates"] = reviewer_failed_gates
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
            review["status"] = "revise"
            review["accepted_by_reviewers"] = False
        if review_accepts(review):
            record["reviewer_returncode"] = reviewer_code
            record["status"] = "done"
            if oracle_supervisor:
                supervisor_code, supervisor_status = run_oracle_supervisor(
                    task,
                    run_dir,
                    skill,
                    codex_timeout,
                    codex_binary,
                    ignore_user_config=ignore_user_config,
                    agent_backend=agent_backend,
                    api_config=api_config,
                )
                record["supervision_status"] = supervisor_status
                if supervisor_code is not None:
                    record["oracle_supervisor_returncode"] = supervisor_code
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        if round_index >= max_refiner_rounds:
            record["reviewer_returncode"] = reviewer_code
            record["status"] = "revise"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        next_round = round_index + 1
        if uses_story_contract(skill.version) and review_has_story_level_issues(review):
            story_refiner_result = run_role_agent(
                run_dir,
                build_story_refiner_command_prompt(task, skill.version, next_round),
                f"story_refiner_{next_round:03d}",
                role_backend("planner", agent_backend),
                codex_timeout,
                codex_binary=codex_binary,
                ignore_user_config=ignore_user_config,
                api_config=api_config,
                allowed_files=abstract_intro_role_allowed("story_refiner", next_round),
                output_files=["story/story_critic.yaml", "story/story_contract.yaml"],
            )
            record[f"story_refiner_{next_round:03d}_returncode"] = story_refiner_result.returncode
            record[f"story_refiner_{next_round:03d}_backend"] = story_refiner_result.backend
            record[f"story_refiner_{next_round:03d}_elapsed_sec"] = story_refiner_result.elapsed_sec
            if story_refiner_result.returncode != 0 or not (run_dir / "story" / "story_contract.yaml").exists():
                record["status"] = "story_refiner_failed"
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
            contract_ok, contract_failed_gates = story_contract_gate(run_dir, require_payoff_contract=uses_payoff_contract(skill.version))
            if not contract_ok:
                record["status"] = "gate_failed"
                record["failed_gates"] = contract_failed_gates
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
        refiner_allowed = abstract_intro_role_allowed("refiner", round_index)
        refiner_result = run_role_agent(
            run_dir,
            build_refiner_command_prompt(task, skill.version, round_index=next_round),
            f"refiner_{next_round:03d}",
            role_backend("refiner", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            ignore_user_config=ignore_user_config,
            api_config=api_config,
            allowed_files=refiner_allowed,
            output_files=["final/abstract_intro.tex", f"revisions/refine_round_{next_round:03d}.md"],
        )
        refiner_code = refiner_result.returncode
        record[f"refiner_{next_round:03d}_returncode"] = refiner_code
        record[f"refiner_{next_round:03d}_backend"] = refiner_result.backend
        record[f"refiner_{next_round:03d}_elapsed_sec"] = refiner_result.elapsed_sec
        if refiner_code != 0 or not (run_dir / "final" / "abstract_intro.tex").exists():
            record["status"] = "refiner_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        record["refiner_rounds_used"] = next_round
        save_draft(run_dir, next_round)
        gates_ok, failed_gates = draft_gates_pass(run_dir, task, next_round)
        if not gates_ok:
            record["status"] = "gate_failed"
            record["failed_gates"] = failed_gates
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
    write_yaml(run_dir / "status.yaml", record)
    write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
    return record


def review_accepts(review: dict[str, Any]) -> bool:
    return review.get("status") == "pass" or review.get("accepted_by_reviewers") is True


def save_draft(run_dir: Path, round_index: int) -> None:
    source = run_dir / "final" / "abstract_intro.tex"
    if not source.exists():
        return
    target = run_dir / "drafts" / f"draft_{round_index:03d}.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _status_paths(run_root: Path) -> list[Path]:
    return sorted(path for path in run_root.glob("*/*/status.yaml") if path.is_file())


def _word_count(path: Path) -> int:
    text = read_text_if_exists(path)
    return len(re.findall(r"\S+", text))


def _gate_statuses(run_dir: Path) -> list[str]:
    rows: list[str] = []
    for name in ("evidence_to_story_plan_gate", "abstract_intro_format_gate", "evidence_anchor_gate", "claim_safety_gate", "reviewer_acceptance_gate"):
        path = run_dir / "audits" / f"{name}.yaml"
        if not path.exists():
            continue
        data = read_yaml(path) or {}
        status = data.get("status", "unknown")
        issues = data.get("blocking_issues") or []
        suffix = f" ({'; '.join(str(item) for item in issues)})" if issues else ""
        rows.append(f"{name}: {status}{suffix}")
    return rows


def _review_issue_ids(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for path in sorted((run_dir / "reviews").glob("abstract_intro_review_round_*.yaml")):
        data = read_yaml(path) or {}
        for item in data.get("blocking_issues") or []:
            if isinstance(item, dict):
                issues.append(str(item.get("id") or item.get("issue") or item.get("detail") or item))
            else:
                issues.append(str(item))
    return issues


def _supervision_summary(run_dir: Path) -> str:
    score = read_yaml(run_dir / "supervision" / "optimization_score.yaml") or {}
    overall = score.get("overall") if isinstance(score, dict) else {}
    components = score.get("component_scores") if isinstance(score, dict) else {}
    parts: list[str] = []
    if isinstance(overall, dict):
        if overall.get("final_weighted_score") is not None:
            parts.append(f"final={overall.get('final_weighted_score')}")
        if overall.get("oracle_fidelity") is not None:
            parts.append(f"oracle={overall.get('oracle_fidelity')}")
    if isinstance(components, dict):
        abstract_intro = components.get("abstract_intro")
        if isinstance(abstract_intro, dict):
            component_score = abstract_intro.get("weighted_score", abstract_intro.get("score"))
            if component_score is not None:
                parts.append(f"abstract_intro={component_score}")
        elif abstract_intro is not None:
            parts.append(f"abstract_intro={abstract_intro}")
    decision = score.get("decision") if isinstance(score, dict) else None
    if isinstance(decision, dict):
        label = decision.get("label") or decision.get("status") or decision.get("decision")
        if label:
            parts.append(f"decision={label}")
    elif decision:
        parts.append(f"decision={decision}")
    return "<br>".join(parts) or "none"


def write_comparison_report(run_root: Path) -> Path:
    rows: list[str] = [
        "# Abstract + Introduction Run Comparison",
        "",
        f"Run: `{run_root.name}`",
        "",
        "| Field | Slug | Status | Review rounds | Refiner rounds | Words | Gates | Review issues | Oracle supervisor |",
        "|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for status_path in _status_paths(run_root):
        run_dir = status_path.parent
        record = read_yaml(status_path) or {}
        field = str(record.get("field") or run_dir.parent.name)
        slug = str(record.get("slug") or run_dir.name)
        status = str(record.get("status", "unknown"))
        review_rounds = record.get("review_rounds", 0)
        refiner_rounds = record.get("refiner_rounds_used", 0)
        words = _word_count(run_dir / "final" / "abstract_intro.tex")
        gates = "<br>".join(_gate_statuses(run_dir)) or "none"
        issues = "<br>".join(_review_issue_ids(run_dir)) or "none"
        supervision = _supervision_summary(run_dir)
        rows.append(f"| {field} | `{slug}` | {status} | {review_rounds} | {refiner_rounds} | {words} | {gates} | {issues} | {supervision} |")
    rows.extend(
        [
            "",
            "## Notes",
            "",
            "- `claim_safety_gate` is advisory: warning status is reported but does not fail the run.",
            "- Gate details remain in each paper's `audits/` directory.",
        ]
    )
    report_path = run_root / "comparison_report.md"
    write_text(report_path, "\n".join(rows) + "\n")
    return report_path


def summary_path_for_run(run_root: Path, slug: str | None, shard_summary: bool = False) -> Path:
    if shard_summary:
        safe_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug or "all")
        return run_root / f"summary_{safe_slug}.yaml"
    return run_root / "summary.yaml"


def build_aggregate_summary(run_root: Path, skill_version: str) -> dict[str, Any]:
    records = [read_yaml(path) or {} for path in _status_paths(run_root)]
    return {
        "run_id": run_root.name,
        "skill_version": skill_version,
        "total": len(records),
        "completed": sum(1 for item in records if item.get("status") in {"prepared", "done"}),
        "failed": sum(1 for item in records if item.get("status") not in {"prepared", "done"}),
        "supervision_done": sum(1 for item in records if item.get("supervision_status") == "done"),
    }


def write_aggregate_summary(run_root: Path, skill_version: str) -> dict[str, Any]:
    summary = build_aggregate_summary(run_root, skill_version)
    write_yaml(run_root / "summary.yaml", summary)
    write_comparison_report(run_root)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run abstract+intro generation with a versioned nature_writing skill.")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--skill-version", default=DEFAULT_SKILL_VERSION)
    parser.add_argument("--only-slug", default=None)
    parser.add_argument("--image-mode", choices=["copy", "text_summary", "external_vlm", "benchmark_vlm"], default="benchmark_vlm")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--max-refiner-rounds", type=int, default=0)
    parser.add_argument("--codex-timeout", type=int, default=DEFAULT_CODEX_TIMEOUT)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--agent-backend", choices=["codex", "api", "codex+api"], default="codex")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-timeout", type=int, default=600)
    parser.add_argument("--api-max-tokens", type=int, default=16000)
    parser.add_argument("--ignore-user-config", action="store_true")
    parser.add_argument("--oracle-supervisor", action="store_true", help="Run post-hoc oracle supervision after reviewer acceptance.")
    parser.add_argument("--oracle-supervisor-only", action="store_true", help="Run post-hoc oracle supervision for existing outputs under --out/--run-id without regenerating.")
    parser.add_argument("--shard-summary", action="store_true", help="Write summary_<slug>.yaml instead of shared summary.yaml for parallel one-slug workers.")
    parser.add_argument("--aggregate-only", action="store_true", help="Only aggregate existing status.yaml files into summary.yaml and comparison_report.md.")
    parser.add_argument("--paper-story-contract", type=Path, default=None)
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill = load_skill(args.skill_version)
    api_cfg = None
    if args.agent_backend in {"api", "codex+api"}:
        api_cfg = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    run_root = args.out / args.run_id
    if args.aggregate_only:
        summary = write_aggregate_summary(run_root, args.skill_version)
        comparison_report = run_root / "comparison_report.md"
        if not args.quiet_progress:
            print(comparison_report)
            print(yaml.safe_dump(summary, sort_keys=False).strip())
        return 0 if summary.get("failed") == 0 else 1
    tasks = discover_tasks(args.tasks_root, only_slug=args.only_slug)
    progress = ProgressReporter(args.run_id, len(tasks), enabled=not args.quiet_progress)
    progress.event("batch", "started", total=len(tasks), skill=args.skill_version)
    completed = failed = 0
    for index, task in enumerate(tasks, start=1):
        progress.set_task_index(index)
        progress.event("task", "started", task)
        run_dir = args.out / args.run_id / task.field / task.slug
        if args.oracle_supervisor_only:
            record = run_oracle_supervisor_only(
                task,
                run_dir,
                skill,
                args.codex_timeout,
                args.codex_binary,
                ignore_user_config=args.ignore_user_config,
                agent_backend=args.agent_backend,
                api_config=api_cfg,
            )
        else:
            record = run_task(
                task,
                run_dir,
                skill,
                args.image_mode,
                args.prepare_only,
                args.codex_timeout,
                args.codex_binary,
                max_refiner_rounds=args.max_refiner_rounds,
                ignore_user_config=args.ignore_user_config,
                oracle_supervisor=args.oracle_supervisor,
                agent_backend=args.agent_backend,
                api_config=api_cfg,
                paper_story_contract=args.paper_story_contract,
            )
        if record["status"] in {"prepared", "done"}:
            completed += 1
        else:
            failed += 1
        progress.event("task", record["status"], task)
    summary = {"run_id": args.run_id, "skill_version": args.skill_version, "total": len(tasks), "completed": completed, "failed": failed}
    summary_path = summary_path_for_run(run_root, args.only_slug, shard_summary=args.shard_summary)
    write_yaml(summary_path, summary)
    comparison_report = write_comparison_report(run_root)
    progress.event("batch", "done", completed=completed, failed=failed, report=summary_path, comparison=comparison_report)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
