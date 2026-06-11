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
from nature_orchestrator.oracle import run_oracle_audit  # noqa: E402
from nature_orchestrator.review_validation import final_text_quote_issues  # noqa: E402


DEFAULT_TASKS_ROOT = ROOT.parent / "nature-bench" / "data" / "downloads"
DEFAULT_SKILL_VERSION = "v2_deep_evidence_discussion"
DEFAULT_OUT = Path("outputs/discussion")
DEFAULT_CODEX_TIMEOUT = 1800
DEFAULT_ENV = ROOT.parent / "nature-orchestrator" / ".env"
NUMERIC_ANCHOR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*"
    r"(?:%|per cent|fold|x|×|ms|MPa|GPa|Pa|µm|μm|micrometre|micrometers?|"
    r"mm|cm|nm|K|Hz|kHz|MHz|GHz|events?|papers?|researchers?|participants?|"
    r"samples?|cells?|mice|rats|patients?|datasets?)",
    re.IGNORECASE,
)
SHARED_UNIT_SERIES_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*(?:,|and|or|to|--|–|—|-)\s*"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)+)"
    r"\s*(%|per cent|fold|x|×|ms|MPa|GPa|Pa|µm|μm|micrometre|micrometers?|"
    r"mm|cm|nm|K|Hz|kHz|MHz|GHz)(?![A-Za-z])",
    re.IGNORECASE,
)
NUMBER_IN_SERIES_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
FIGURE_REF_RE = re.compile(r"\b(?:Figs?|Figures?)\.?\s*~?\s*\d+[a-z]?", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^{}]+)\}|^#{1,6}\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class DiscussionTask:
    path: Path
    field: str
    slug: str
    task_name: str


@dataclass(frozen=True)
class DiscussionSkill:
    version: str
    root: Path
    current_layout: bool = False


class ProgressReporter:
    def __init__(self, run_id: str, total: int, enabled: bool = True, stream: TextIO | None = None) -> None:
        self.run_id = run_id
        self.total = total
        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.index = 0

    def set_task_index(self, index: int) -> None:
        self.index = index

    def event(self, stage: str, status: str, task: DiscussionTask | None = None, **fields: Any) -> None:
        if not self.enabled:
            return
        parts = [
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
            f"run_id={self.run_id}",
            f"task={self.index}/{self.total}",
        ]
        if task:
            parts.extend([f"slug={task.slug}", f"field={task.field}", f"task_name={task.task_name}"])
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


def normalize_figure_ref(value: str) -> str:
    normalized = normalize_anchor(value.replace("~", " "))
    normalized = normalized.replace("figures", "fig").replace("figure", "fig").replace("figs.", "fig").replace("figs", "fig").replace("fig.", "fig")
    return re.sub(r"\s+", " ", normalized).strip()


def extract_numeric_anchors(text: str) -> list[str]:
    anchors: set[str] = set()
    for match in NUMERIC_ANCHOR_RE.finditer(text or ""):
        prefix = (text or "")[max(0, match.start() - 12) : match.start()]
        if re.search(r"(?:fig|figure)s?\.?\s*~?\s*$", prefix, re.IGNORECASE):
            continue
        anchors.add(normalize_anchor(match.group(0)))
    for match in SHARED_UNIT_SERIES_RE.finditer(text or ""):
        prefix = (text or "")[max(0, match.start() - 12) : match.start()]
        if re.search(r"(?:fig|figure)s?\.?\s*~?\s*$", prefix, re.IGNORECASE):
            continue
        unit = normalize_anchor(match.group(2))
        for number in NUMBER_IN_SERIES_RE.findall(match.group(1)):
            anchors.add(normalize_anchor(f"{number} {unit}"))
    return sorted(anchors)


def extract_figure_refs(text: str) -> list[str]:
    return sorted({normalize_figure_ref(match.group(0)) for match in FIGURE_REF_RE.finditer(text or "")})


def base_figure_ref(ref: str) -> str:
    match = re.match(r"(fig\s+\d+)", normalize_figure_ref(ref))
    return match.group(1) if match else normalize_figure_ref(ref)


def build_discussion_evidence_manifest(context_text: str) -> dict[str, Any]:
    return {
        "schema_version": "nature_orchestrator.discussion_evidence_manifest.v1",
        "numeric_anchors": extract_numeric_anchors(context_text),
        "figure_refs": extract_figure_refs(context_text),
        "context_sha256": sha256_text(context_text or ""),
    }


DISCUSSION_SUPPORT_ARTIFACTS = (
    "paper/story/paper_story_contract.yaml",
    "story/evidence_to_story_plan.yaml",
    "story/story_contract.yaml",
)


def build_discussion_support_text(run_dir: Path) -> str:
    parts = [read_text_if_exists(run_dir / "context_pack" / "context.md")]
    for rel in DISCUSSION_SUPPORT_ARTIFACTS:
        path = run_dir / rel
        if path.exists():
            parts.append(f"\n\n# Support artifact: {rel}\n{read_text_if_exists(path)}")
    return "\n".join(part for part in parts if part)


def discover_tasks(tasks_root: Path, only_slug: str | None = None, task_name: str = "discussion") -> list[DiscussionTask]:
    root = tasks_root.resolve()
    tasks: list[DiscussionTask] = []
    for path in root.glob(f"*/s41586-*/benchmark/tasks_safe_web/{task_name}.yaml"):
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
        tasks.append(DiscussionTask(path=path, field=field, slug=slug, task_name=path.stem))
    return sorted(tasks, key=lambda item: (item.field, item.slug, item.task_name))


def load_skill(version: str, repo_root: Path = ROOT) -> DiscussionSkill:
    if version == "nature_writing_current_discussion":
        root = repo_root / "skills" / "nature_writing"
        required = [
            root / "manifest.yaml",
            root / "prompts" / "discussion_planner.md",
            root / "prompts" / "discussion_writer.md",
            root / "prompts" / "discussion_reviewer.md",
            root / "prompts" / "discussion_refiner.md",
            root / "rubrics" / "section_reviewer_rubric.yaml",
            root / "methods" / "discussion_story_patterns.md",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing current discussion skill file(s): " + ", ".join(missing))
        return DiscussionSkill(version=version, root=root, current_layout=True)
    root = repo_root / "skills" / "nature_writing" / "versions" / version
    required = [
        root / "manifest.yaml",
        root / "prompts" / "writer_prompt.md",
        root / "rubrics" / "discussion_rubric.yaml",
        root / "patterns" / "discussion_story_patterns.md",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing discussion skill file(s): " + ", ".join(missing))
    return DiscussionSkill(version=version, root=root)


def copy_skill_package(skill: DiscussionSkill, run_dir: Path) -> None:
    destination = run_dir / "skill"
    if skill.current_layout:
        copy_map = [
            ("manifest.yaml", "manifest.yaml"),
            ("prompts/discussion_planner.md", "prompts/planner_prompt.md"),
            ("prompts/discussion_writer.md", "prompts/writer_prompt.md"),
            ("prompts/discussion_reviewer.md", "prompts/reviewer_prompt.md"),
            ("prompts/discussion_refiner.md", "prompts/refiner_prompt.md"),
            ("rubrics/section_reviewer_rubric.yaml", "rubrics/discussion_rubric.yaml"),
            ("methods/discussion_story_patterns.md", "patterns/discussion_story_patterns.md"),
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
        if not source.is_file() or source.name.endswith(".pyc") or "__pycache__" in source.parts:
            continue
        target = destination / source.relative_to(skill.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def write_task_contract(run_dir: Path, task: DiscussionTask, spec: Any, skill: DiscussionSkill, image_mode: str, allowed_files: list[str]) -> None:
    write_yaml(
        run_dir / "prompt_pack" / "task_contract.yaml",
        {
            "schema_version": "nature_orchestrator.discussion_task_contract.v1",
            "task_slug": task.slug,
            "field": task.field,
            "task_id": spec.task_id,
            "task_name": task.task_name,
            "target_section": spec.target_section,
            "task_variant": getattr(spec, "task_variant", ""),
            "skill_version": skill.version,
            "image_mode": image_mode,
            "allowed_files": allowed_files,
            "forbidden_context": spec.raw.get("forbidden_context") or {},
            "outputs": {
                "story": "story/evidence_to_story_plan.yaml",
                "story_contract": "story/story_contract.yaml",
                "final": "final/discussion.tex",
                "reviews": "reviews/discussion_review_round_*.yaml",
                "revisions": "revisions/refine_round_*.md",
                "drafts": "drafts/draft_*.tex",
                "audits": "audits/*.yaml",
                "oracle_audit": "oracle_audit.yaml",
            },
            "deterministic_gates": [
                "discussion_format_gate",
                "evidence_anchor_gate",
                "discussion_synthesis_gate",
            ],
        },
    )


def write_or_update_provenance(run_dir: Path, task: DiscussionTask, skill: DiscussionSkill, image_mode: str, codex_binary: str = "codex", status: str | None = None) -> None:
    existing = read_yaml(run_dir / "provenance.yaml")
    if not isinstance(existing, dict):
        existing = {}
    provenance = {
        **existing,
        "schema_version": "nature_orchestrator.discussion_provenance.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "task_slug": task.slug,
        "field": task.field,
        "task_path": str(task.path),
        "task_name": task.task_name,
        "skill_version": skill.version,
        "image_mode": image_mode,
        "codex_binary": codex_binary,
        "task_yaml_sha256": sha256_file(task.path),
        "context_md_sha256": sha256_file(run_dir / "context_pack" / "context.md"),
        "writer_prompt_sha256": sha256_file(run_dir / "skill" / "prompts" / "writer_prompt.md"),
        "final_output_sha256": sha256_file(run_dir / "final" / "discussion.tex"),
    }
    if status is not None:
        provenance["status"] = status
    write_yaml(run_dir / "provenance.yaml", provenance)


def write_discussion_prompt_pack(run_dir: Path, task: DiscussionTask, skill: DiscussionSkill, image_mode: str = "benchmark_vlm") -> None:
    spec = load_task(task.path)
    if spec.target_section != "discussion":
        raise ValueError(f"Expected discussion target, got {spec.target_section}")
    context = build_context(spec)
    write_context_pack(context, run_dir)
    copy_skill_package(skill, run_dir)
    allowed_files = [
        "context_pack/context.md",
        "context_pack/context.yaml",
        "context_pack/evidence_manifest.yaml",
        *[f"skill/{path}" for path in relative_files(run_dir / "skill")],
    ]
    if (run_dir / "paper" / "story" / "paper_story_contract.yaml").exists():
        allowed_files.append("paper/story/paper_story_contract.yaml")
    if (run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml").exists():
        allowed_files.append("paper/evidence/evidence_claim_ledger.yaml")
    write_yaml(run_dir / "prompt_pack" / "allowed_files.yaml", {"allowed_files": allowed_files})
    write_yaml(run_dir / "prompt_pack" / "forbidden_files.yaml", spec.raw.get("forbidden_context") or {})
    write_text(run_dir / "prompt_pack" / "prompt.md", build_writer_command_prompt(task, skill.version))
    support_text = build_discussion_support_text(run_dir)
    write_yaml(run_dir / "context_pack" / "evidence_manifest.yaml", build_discussion_evidence_manifest(support_text))
    write_task_contract(run_dir, task, spec, skill, image_mode, allowed_files)
    write_yaml(
        run_dir / "run_manifest.yaml",
        {
            "schema_version": "nature_orchestrator.discussion_run.v1",
            "task_slug": task.slug,
            "field": task.field,
            "task_path": str(task.path),
            "task_name": task.task_name,
            "skill_version": skill.version,
            "image_mode": image_mode,
            "outputs": [
                "story/evidence_to_story_plan.yaml",
                "story/story_contract.yaml",
                "final/discussion.tex",
                "reviews/discussion_review_round_*.yaml",
                "revisions/refine_round_*.md",
                "drafts/draft_*.tex",
                "audits/*.yaml",
                "oracle_audit.yaml",
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


def copy_paper_evidence_ledger(run_dir: Path, source: Path | None) -> None:
    if source is None or not source.exists() or not source.is_file():
        return
    target = run_dir / "paper" / "evidence" / "evidence_claim_ledger.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def build_planner_command_prompt(task: DiscussionTask, skill_version: str) -> str:
    return f"""# Discussion Evidence-to-Story Planning Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`

Use only files listed in `prompt_pack/allowed_files.yaml`.
Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the evidence source.

Read:
- `paper/story/paper_story_contract.yaml` if present. Treat it as a soft paper-level contract: preserve the central thesis, claim boundaries and section role when evidence supports them, but report corrections in `paper_contract_alignment` when Discussion evidence requires narrower interpretation.
- `paper/evidence/evidence_claim_ledger.yaml` if present. Treat it as the evidence-confidence ledger; Discussion may synthesize supported implications but cannot upgrade low-confidence or VLM-only observations beyond Results support.
- `skill/prompts/planner_prompt.md` if present
- `skill/prompts/writer_prompt.md`
- `skill/patterns/discussion_story_patterns.md`
- `skill/rubrics/discussion_rubric.yaml`

Write:
- `story/evidence_to_story_plan.yaml`

The plan must include:
- `central_contribution`
- `must_mention_anchors`
- `results_to_synthesize`
- `mechanistic_interpretation`
- `boundary_conditions`
- `limitations`
- `implications`
- `future_or_next_questions`
- `discussion_payoff_anchors`
- `method_contribution_map`
- `direction_comparator_table`
- `claim_boundary_table`
- `paper_contract_alignment` if `paper/story/paper_story_contract.yaml` is present
- `weak_or_missing_context`
Before exiting, reopen `story/evidence_to_story_plan.yaml` and verify it parses as YAML and contains all required keys above.
"""


def uses_story_contract(skill_version: str) -> bool:
    return skill_version == "nature_writing_current_discussion" or "v2" in skill_version or "story_refined" in skill_version or "payoff_refined" in skill_version


def uses_payoff_contract(skill_version: str) -> bool:
    return skill_version == "nature_writing_current_discussion" or any(token in skill_version for token in ("v2_2", "v2_3", "v2_6", "payoff_refined"))


def build_story_refiner_command_prompt(task: DiscussionTask, skill_version: str, round_index: int = 0) -> str:
    review_hint = (
        f"\nAlso read `reviews/discussion_review_round_{round_index - 1:03d}.yaml` "
        "and repair story-level issues before prose is refined."
        if round_index > 0
        else ""
    )
    return f"""# Discussion Story Contract Refinement Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`
Story refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated file:
- `story/evidence_to_story_plan.yaml`
Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the only paper-specific evidence source.

Goal:
Convert the raw Discussion evidence plan into a compact story contract that
ranks what the Discussion should synthesize, what it should bound, and what it
should leave to future work. Do not write Discussion prose. The contract should
prevent a second Results section and prevent a generic limitation/outlook ending.

Read:
- `context_pack/context.md`
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `skill/prompts/writer_prompt.md`
- `skill/patterns/discussion_story_patterns.md`
- `skill/rubrics/discussion_rubric.yaml`
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
- for v2.3 or payoff-refined skills: `high_impact_payoff_anchors`
- `discussion_payoff_anchors`

Rules:
- For v2.3/story-tournament skills, compare at least three plausible Discussion
  routes before selecting one. Record why rejected candidates lost under
  `story/story_critic.yaml`.
- `hero_evidence` should contain the few results whose interpretation changes
  the paper's meaning.
- `support_evidence` should contain validation, controls and secondary anchors
  that explain why the interpretation is credible.
- `boundary_evidence` should contain null/no-effect, failure, subgroup,
  uncertainty, design limits, transfer limits or claim-safety anchors.
- `figure_writing_actions` must turn each important result/figure role into a
  Discussion instruction: synthesize, use as mechanism, use as boundary, use as
  limitation, use as implication, or omit/defer.
- `section_strategy` must define Discussion paragraph order by reader question:
  what changed, why it is credible, where it applies, what remains limited, and
  what follows.
- Identify recoverable Discussion payoff anchors: mechanism shift, parameter or
  quantitative constraint, boundary-changing comparison, practical implication,
  transfer relation, or next-question framing. Protect these from being softened
  into a generic outlook.
- For v2.3 or payoff-refined skills, identify high-impact payoff anchors whose
  omission would make the Discussion generic or over-conservative.
- Before exiting, reopen both YAML files and verify they parse.
"""


def build_writer_command_prompt(task: DiscussionTask, skill_version: str) -> str:
    return f"""# Discussion Generation Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated file:
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
Do not inspect `prompt_pack/forbidden_files.yaml` paths.
Use `context_pack/context.md` as the evidence source.
Use the skill files under `skill/` as writing-pattern guidance only.
Use `story/evidence_to_story_plan.yaml` as the synthesis, implication,
limitation and claim-boundary contract.
If `story/story_contract.yaml` exists, treat it as the final story-selection and
evidence-hierarchy contract. Follow its `hero_evidence`, `support_evidence`,
`boundary_evidence`, `omit_or_defer`, `figure_writing_actions`, and
`section_strategy` over the raw anchor list.
Use `discussion_payoff_anchors` to decide which interpretation, implication,
boundary, or next-question payoff deserves the strongest paragraph emphasis.

Read:
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `skill/prompts/writer_prompt.md`
- `skill/patterns/discussion_story_patterns.md`
- `skill/rubrics/discussion_rubric.yaml`

Write:
- `final/discussion.tex`

`final/discussion.tex` must contain Discussion body prose and optional
subsection headings. Omit a leading `\\section{{Discussion}}`. Do not introduce
new Results claims that are absent from allowed context.
"""


def build_reviewer_command_prompt(task: DiscussionTask, skill_version: str, round_index: int) -> str:
    review_path = f"reviews/discussion_review_round_{round_index:03d}.yaml"
    return f"""# Discussion Review Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`
Review round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/discussion.tex`
- `audits/discussion_format_gate.yaml`
- `audits/evidence_anchor_gate.yaml`
- `audits/discussion_synthesis_gate.yaml`

Read `skill/prompts/reviewer_prompt.md` if present, `skill/rubrics/discussion_rubric.yaml`, and the relevant Discussion pattern files.
Also read `context_pack/context.md` before passing.
Be strict. Do not rewrite the manuscript.

The YAML must include:
- `status: pass | revise | fail`
- `accepted_by_reviewers: true | false`
- `scores`
- `blocking_issues`
- `required_revisions`
- `must_mention_anchor_recall`
- `missing_recoverable_anchors`
- `direction_comparator_errors`
- `over_conservatism`
- `unrecoverable_detail_risk`
- `discussion_synthesis_audit`
- `boundary_limitation_audit`
- `implication_calibration_audit`
- `payoff_anchor_audit`
- `safe_underclaiming_risk`
If `story/story_contract.yaml` exists, separately audit whether the draft follows
its `central_thesis`, `hero_evidence`, `figure_writing_actions`, and
`omit_or_defer` choices. Put story-contract failures under `story_level_issues`;
put local prose, formatting, or minor anchor issues under `text_level_issues`.
Do not pass a Discussion draft that is merely a second Results summary, lacks a
clear claim boundary, hides recoverable limitations, or ends with a generic
outlook instead of a paper-specific implication or next question.
Before exiting, reopen `{review_path}` and verify it parses as YAML and contains all required top-level fields.

Write only:
- `{review_path}`
"""


def build_reviewer_schema_repair_prompt(task: DiscussionTask, skill_version: str, round_index: int) -> str:
    review_path = f"reviews/discussion_review_round_{round_index:03d}.yaml"
    return f"""# Discussion Reviewer YAML Schema Repair

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`
Review round: `{round_index:03d}`

The Discussion review has already been written, but `reviewer_acceptance_gate`
found schema-level omissions in `{review_path}`. Do not rewrite Discussion prose
and do not change the review decision unless the existing YAML is internally
contradictory. Repair only the review YAML schema.

Read:
- `{review_path}`
- `audits/reviewer_acceptance_gate.yaml`
- `final/discussion.tex`
- `skill/prompts/reviewer_prompt.md`
- `skill/rubrics/discussion_rubric.yaml`

The repaired YAML must include:
- `status: pass | revise | fail`
- `accepted_by_reviewers: true | false`
- `scores`
- `blocking_issues`
- `required_revisions`
- `must_mention_anchor_recall`
- `missing_recoverable_anchors`
- `direction_comparator_errors`
- `over_conservatism`
- `unrecoverable_detail_risk`
Before exiting, reopen `{review_path}` and verify it parses as YAML and contains all required top-level fields.

Write only:
- `{review_path}`
"""


def build_refiner_command_prompt(task: DiscussionTask, skill_version: str, round_index: int) -> str:
    previous_round = round_index - 1
    return f"""# Discussion Targeted Refinement Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`
Refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/discussion.tex`
- `reviews/discussion_review_round_{previous_round:03d}.yaml`
- `audits/discussion_format_gate.yaml`
- `audits/evidence_anchor_gate.yaml`
- `audits/discussion_synthesis_gate.yaml`
- `audits/reviewer_acceptance_gate.yaml`

Revise only blocking or required issues raised by the reviewer or deterministic gates.
Preserve supported quantitative evidence, figure references, comparator
direction, limitations, implications and claim boundaries. If `story/story_contract.yaml`
exists, follow its evidence hierarchy and figure-writing actions; do not
re-expand omitted/deferred anchors unless the reviewer explicitly identifies a
story-level failure.
Do not inspect forbidden paths. Do not use oracle files.

Write:
- updated `final/discussion.tex`
- `revisions/refine_round_{round_index:03d}.md`
"""


def build_gate_refiner_command_prompt(task: DiscussionTask, skill_version: str, round_index: int) -> str:
    return f"""# Discussion Gate-Driven Refinement Task

Task: `{task.slug}` / `{task.field}` / `{task.task_name}`
Skill version: `{skill_version}`
Refinement round: `{round_index:03d}`

Use only files listed in `prompt_pack/allowed_files.yaml`, plus generated files:
- `story/evidence_to_story_plan.yaml`
- `story/story_contract.yaml` if present
- `final/discussion.tex`
- `audits/discussion_format_gate.yaml`
- `audits/evidence_anchor_gate.yaml`
- `audits/discussion_synthesis_gate.yaml`

The previous Discussion draft failed deterministic gates before reviewer review.
Revise only the blocking gate issues. Preserve supported quantitative evidence,
figure references, comparator direction, limitations, implications and claim boundaries.
Do not inspect forbidden paths. Do not use oracle files.

Write:
- updated `final/discussion.tex`
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


def discussion_role_allowed(role: str, round_index: int = 0) -> list[str]:
    base = [
        "context_pack/context.md",
        "context_pack/context.yaml",
        "context_pack/evidence_manifest.yaml",
        "paper/story/paper_story_contract.yaml",
        "paper/evidence/evidence_claim_ledger.yaml",
        "skill/rubrics/discussion_rubric.yaml",
        "skill/patterns/discussion_story_patterns.md",
    ]
    if role == "planner":
        return base + ["skill/prompts/planner_prompt.md", "skill/prompts/writer_prompt.md"]
    if role == "story_refiner":
        return base + [
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            f"reviews/discussion_review_round_{max(0, round_index - 1):03d}.yaml",
            "skill/prompts/planner_prompt.md",
            "skill/prompts/writer_prompt.md",
        ]
    if role == "writer":
        return base + [
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "skill/prompts/writer_prompt.md",
        ]
    if role == "reviewer":
        return base + [
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "final/discussion.tex",
            "audits/discussion_format_gate.yaml",
            "audits/evidence_anchor_gate.yaml",
            "audits/discussion_synthesis_gate.yaml",
            "skill/prompts/reviewer_prompt.md",
        ]
    if role == "refiner":
        return base + [
            "story/evidence_to_story_plan.yaml",
            "story/story_contract.yaml",
            "final/discussion.tex",
            f"reviews/discussion_review_round_{round_index:03d}.yaml",
            "audits/discussion_format_gate.yaml",
            "audits/evidence_anchor_gate.yaml",
            "audits/discussion_synthesis_gate.yaml",
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


def run_codex(run_dir: Path, prompt: str, log_prefix: str, timeout: int, codex_binary: str = "codex") -> int:
    return run_role_agent(run_dir, prompt, log_prefix, "codex", timeout, codex_binary=codex_binary).returncode


def discussion_format_gate(text: str) -> dict[str, Any]:
    issues: list[str] = []
    if not (text or "").strip():
        issues.append("missing Discussion prose")
    for match in SECTION_HEADING_RE.finditer(text or ""):
        heading = (match.group(1) or match.group(2) or "").strip()
        normalized = re.sub(r"\s+", " ", heading).lower()
        if normalized in {"discussion", "results", "methods", "abstract", "introduction"}:
            issues.append(f"forbidden section heading: {heading}")
    return {
        "schema_version": "nature_orchestrator.discussion_format_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": sorted(set(issues)),
    }


def evidence_anchor_gate(generated: str, manifest: dict[str, Any], context_text: str) -> dict[str, Any]:
    allowed_numeric = {normalize_anchor(item) for item in manifest.get("numeric_anchors") or []}
    allowed_figures = {normalize_anchor(item) for item in manifest.get("figure_refs") or []}
    allowed_base_figures = {base_figure_ref(item) for item in allowed_figures}
    context_lower = (context_text or "").lower().replace("μ", "µ")
    generated_numeric = extract_numeric_anchors(generated)
    generated_figures = extract_figure_refs(generated)
    unsupported_numeric = [item for item in generated_numeric if item not in allowed_numeric and item not in context_lower]
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
        "schema_version": "nature_orchestrator.discussion_evidence_anchor_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
        "generated_numeric_anchors": generated_numeric,
        "generated_figure_refs": generated_figures,
        "unsupported_numeric_anchors": unsupported_numeric,
        "unsupported_figure_refs": unsupported_figures,
    }


def discussion_synthesis_gate(text: str) -> dict[str, Any]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text or "") if item.strip()]
    prose_paragraphs = [item for item in paragraphs if not item.startswith("\\")]
    lower = "\n".join(prose_paragraphs).lower()
    issues: list[str] = []
    if len(prose_paragraphs) < 2:
        issues.append("Discussion should have at least two prose paragraphs")
    synthesis_cues = ("together", "overall", "collectively", "these findings", "our findings", "this work", "demonstrate", "show", "suggest")
    boundary_cues = ("limit", "limitation", "boundary", "caveat", "although", "whereas", "while", "only", "not", "uncertain", "remain")
    implication_cues = ("implication", "enable", "provide", "support", "suggest", "could", "may", "future", "next", "opens", "points to")
    if not any(cue in lower for cue in synthesis_cues):
        issues.append("missing synthesis cue tying results to the paper-level contribution")
    if not any(cue in lower for cue in boundary_cues):
        issues.append("missing boundary, limitation, caveat or uncertainty cue")
    if not any(cue in lower for cue in implication_cues):
        issues.append("missing implication, transfer or next-question cue")
    return {
        "schema_version": "nature_orchestrator.discussion_synthesis_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }


def write_gate_report(run_dir: Path, gate_name: str, report: dict[str, Any], round_index: int | None = None) -> None:
    payload = {**report, "gate": gate_name}
    if round_index is not None:
        payload["round_index"] = round_index
        write_yaml(run_dir / "audits" / f"{gate_name}_round_{round_index:03d}.yaml", payload)
    write_yaml(run_dir / "audits" / f"{gate_name}.yaml", payload)


def evidence_to_story_plan_gate(run_dir: Path) -> tuple[bool, list[str]]:
    required = [
        "central_contribution",
        "must_mention_anchors",
        "results_to_synthesize",
        "mechanistic_interpretation",
        "boundary_conditions",
        "limitations",
        "implications",
        "future_or_next_questions",
        "discussion_payoff_anchors",
        "method_contribution_map",
        "direction_comparator_table",
        "claim_boundary_table",
        "weak_or_missing_context",
    ]
    plan, parse_error = read_gate_yaml(run_dir / "story" / "evidence_to_story_plan.yaml")
    issues = [f"missing evidence_to_story_plan key: {key}" for key in required if key not in plan]
    if parse_error:
        issues.insert(0, f"malformed evidence_to_story_plan.yaml: {parse_error}")
    anchors = plan.get("must_mention_anchors") if isinstance(plan, dict) else None
    if not isinstance(anchors, (list, dict)):
        issues.append("must_mention_anchors must be a list or mapping")
    report = {
        "schema_version": "nature_orchestrator.discussion_evidence_to_story_plan_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }
    write_gate_report(run_dir, "evidence_to_story_plan_gate", report, 0)
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
    discussion_payoff = contract.get("discussion_payoff_anchors") if isinstance(contract, dict) else None
    if not isinstance(discussion_payoff, (list, dict)) or not discussion_payoff:
        issues.append("discussion_payoff_anchors must be a non-empty list or mapping")
    report = {
        "schema_version": "nature_orchestrator.discussion_story_contract_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }
    write_gate_report(run_dir, "story_contract_gate", report, 0)
    return report["status"] == "passed", ([] if report["status"] == "passed" else ["story_contract_gate"])


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


def gates_pass(run_dir: Path, round_index: int = 0) -> tuple[bool, list[str]]:
    text = read_text_if_exists(run_dir / "final" / "discussion.tex")
    support_text = build_discussion_support_text(run_dir)
    manifest = build_discussion_evidence_manifest(support_text)
    write_yaml(run_dir / "context_pack" / "evidence_manifest.yaml", manifest)
    reports = {
        "discussion_format_gate": discussion_format_gate(text),
        "evidence_anchor_gate": evidence_anchor_gate(text, manifest, support_text),
        "discussion_synthesis_gate": discussion_synthesis_gate(text),
    }
    failed: list[str] = []
    for gate_name, report in reports.items():
        write_gate_report(run_dir, gate_name, report, round_index)
        if report["status"] != "passed":
            failed.append(gate_name)
    return not failed, failed


def reviewer_acceptance_gate(
    review: dict[str, Any],
    require_payoff_audit: bool = False,
    final_text: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    status = review.get("status")
    if status not in {"pass", "revise", "fail"}:
        issues.append("status must be pass, revise, or fail")
    if not isinstance(review.get("accepted_by_reviewers"), bool):
        issues.append("accepted_by_reviewers must be boolean")
    if status == "pass" and review.get("blocking_issues"):
        issues.append("pass review cannot contain blocking_issues")
    if status in {"revise", "fail"} and not (review.get("blocking_issues") or review.get("required_revisions")):
        issues.append("revise/fail review must include blocking_issues or required_revisions")
    for field in ["must_mention_anchor_recall", "missing_recoverable_anchors", "direction_comparator_errors", "over_conservatism", "unrecoverable_detail_risk", "discussion_synthesis_audit", "boundary_limitation_audit", "implication_calibration_audit"]:
        if field not in review:
            issues.append(f"missing reviewer audit field: {field}")
    if require_payoff_audit:
        audit = review.get("payoff_anchor_audit")
        risk = safe_underclaiming_risk_level(review)
        if not isinstance(audit, dict):
            issues.append("missing payoff_anchor_audit")
        if risk not in {"low", "medium", "high"}:
            issues.append("safe_underclaiming_risk must be low, medium, or high")
        if status == "pass" and payoff_audit_has_missing_or_underclaimed_anchor(review):
            issues.append("pass review cannot omit high-impact payoff anchors or carry medium/high safe_underclaiming_risk")
    issues.extend(final_text_quote_issues(review, final_text, label="final Discussion"))
    return {
        "schema_version": "nature_orchestrator.discussion_reviewer_acceptance_gate.v1",
        "status": "passed" if not issues else "failed",
        "blocking_issues": issues,
    }


def is_schema_only_reviewer_gate_failure(report: dict[str, Any]) -> bool:
    issues = report.get("blocking_issues") or []
    if not issues:
        return False
    schema_issues = (
        "status must be pass, revise, or fail",
        "accepted_by_reviewers must be boolean",
        "missing reviewer audit field:",
        "$.",
    )
    return all(
        any(str(issue).startswith(prefix) for prefix in schema_issues)
        and ("final_text_quote" in str(issue) or not str(issue).startswith("$."))
        for issue in issues
    )


def reviewer_gate_pass(run_dir: Path, review: dict[str, Any], round_index: int, require_payoff_audit: bool = False) -> tuple[bool, list[str]]:
    final_text = read_text_if_exists(run_dir / "final" / "discussion.tex")
    report = reviewer_acceptance_gate(review, require_payoff_audit=require_payoff_audit, final_text=final_text)
    write_gate_report(run_dir, "reviewer_acceptance_gate", report, round_index)
    return report["status"] == "passed", ([] if report["status"] == "passed" else ["reviewer_acceptance_gate"])


def review_accepts(review: dict[str, Any]) -> bool:
    return review.get("status") == "pass" or review.get("accepted_by_reviewers") is True


def save_draft(run_dir: Path, round_index: int) -> None:
    final_path = run_dir / "final" / "discussion.tex"
    if final_path.exists():
        target = run_dir / "drafts" / f"draft_{round_index:03d}.tex"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final_path, target)


def run_task(
    task: DiscussionTask,
    run_dir: Path,
    skill: DiscussionSkill,
    image_mode: str,
    prepare_only: bool,
    codex_timeout: int,
    codex_binary: str,
    oracle_audit: bool = False,
    agent_backend: str = "codex",
    api_config: ApiConfig | None = None,
    max_refiner_rounds: int = 0,
    paper_story_contract: Path | None = None,
    paper_evidence_ledger: Path | None = None,
) -> dict[str, Any]:
    copy_paper_story_contract(run_dir, paper_story_contract)
    copy_paper_evidence_ledger(run_dir, paper_evidence_ledger)
    write_discussion_prompt_pack(run_dir, task, skill, image_mode=image_mode)
    record: dict[str, Any] = {
        "slug": task.slug,
        "field": task.field,
        "task_name": task.task_name,
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
        build_planner_command_prompt(task, skill.version),
        "planner",
        role_backend("planner", agent_backend),
        codex_timeout,
        codex_binary=codex_binary,
        api_config=api_config,
        allowed_files=discussion_role_allowed("planner"),
        output_files=["story/evidence_to_story_plan.yaml"],
    )
    record["planner_returncode"] = planner_result.returncode
    record["planner_backend"] = planner_result.backend
    record["planner_elapsed_sec"] = planner_result.elapsed_sec
    if planner_result.returncode != 0 or not (run_dir / "story" / "evidence_to_story_plan.yaml").exists():
        record["status"] = "planner_failed"
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
            api_config=api_config,
            allowed_files=discussion_role_allowed("story_refiner"),
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
    writer_allowed = discussion_role_allowed("writer")
    writer_result = run_role_agent(
        run_dir,
        build_writer_command_prompt(task, skill.version),
        "writer",
        role_backend("writer", agent_backend),
        codex_timeout,
        codex_binary=codex_binary,
        api_config=api_config,
        allowed_files=writer_allowed,
        output_files=["final/discussion.tex"],
    )
    writer_code = writer_result.returncode
    record["writer_returncode"] = writer_code
    record["writer_backend"] = writer_result.backend
    record["writer_elapsed_sec"] = writer_result.elapsed_sec
    if writer_code != 0 or not (run_dir / "final" / "discussion.tex").exists():
        record["status"] = "writer_failed"
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    save_draft(run_dir, 0)
    gates_ok, failed_gates = gates_pass(run_dir, 0)
    while not gates_ok and can_refine_after_failure(record["refiner_rounds_used"], max_refiner_rounds):
        next_round = record["refiner_rounds_used"] + 1
        refiner_result = run_role_agent(
            run_dir,
            build_gate_refiner_command_prompt(task, skill.version, next_round),
            f"gate_refiner_{next_round:03d}",
            role_backend("refiner", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            api_config=api_config,
            allowed_files=discussion_role_allowed("refiner", 0),
            output_files=["final/discussion.tex", f"revisions/refine_round_{next_round:03d}.md"],
        )
        record[f"refiner_{next_round:03d}_returncode"] = refiner_result.returncode
        record[f"refiner_{next_round:03d}_backend"] = refiner_result.backend
        record[f"refiner_{next_round:03d}_elapsed_sec"] = refiner_result.elapsed_sec
        if refiner_result.returncode != 0 or not (run_dir / "final" / "discussion.tex").exists():
            record["status"] = "refiner_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        record["refiner_rounds_used"] = next_round
        save_draft(run_dir, next_round)
        gates_ok, failed_gates = gates_pass(run_dir, next_round)
    if not gates_ok:
        record["status"] = "gate_failed"
        record["failed_gates"] = failed_gates
        write_yaml(run_dir / "status.yaml", record)
        write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
        return record
    for round_index in range(max_refiner_rounds + 1):
        review_rel = f"reviews/discussion_review_round_{round_index:03d}.yaml"
        reviewer_allowed = discussion_role_allowed("reviewer", round_index)
        reviewer_result = run_role_agent(
            run_dir,
            build_reviewer_command_prompt(task, skill.version, round_index),
            f"reviewer_{round_index:03d}",
            role_backend("reviewer", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            api_config=api_config,
            allowed_files=reviewer_allowed,
            output_files=[review_rel],
        )
        record[f"reviewer_{round_index:03d}_returncode"] = reviewer_result.returncode
        record[f"reviewer_{round_index:03d}_backend"] = reviewer_result.backend
        record[f"reviewer_{round_index:03d}_elapsed_sec"] = reviewer_result.elapsed_sec
        record["review_rounds"] = round_index + 1
        review_path = run_dir / review_rel
        if reviewer_result.returncode != 0 or not review_path.exists():
            record["status"] = "reviewer_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        canonical_review = run_dir / "reviews" / "discussion_review.yaml"
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
                repair_allowed = discussion_role_allowed("reviewer", round_index) + [
                    review_rel,
                    "audits/reviewer_acceptance_gate.yaml",
                    f"audits/reviewer_acceptance_gate_round_{round_index:03d}.yaml",
                ]
                repair_result = run_role_agent(
                    run_dir,
                    build_reviewer_schema_repair_prompt(task, skill.version, round_index),
                    f"reviewer_schema_repair_{round_index:03d}",
                    role_backend("reviewer", agent_backend),
                    codex_timeout,
                    codex_binary=codex_binary,
                    api_config=api_config,
                    allowed_files=repair_allowed,
                    output_files=[review_rel],
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
                record["status"] = "reviewer_failed"
                record["failed_gates"] = reviewer_failed_gates
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
        if not reviewer_ok:
            if round_index >= max_refiner_rounds:
                record["status"] = "gate_failed"
                record["failed_gates"] = reviewer_failed_gates
                write_yaml(run_dir / "status.yaml", record)
                write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
                return record
            review["status"] = "revise"
            review["accepted_by_reviewers"] = False
        if review_accepts(review):
            break
        if round_index >= max_refiner_rounds:
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
                api_config=api_config,
                allowed_files=discussion_role_allowed("story_refiner", next_round),
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
        refiner_allowed = discussion_role_allowed("refiner", round_index)
        refiner_result = run_role_agent(
            run_dir,
            build_refiner_command_prompt(task, skill.version, next_round),
            f"refiner_{next_round:03d}",
            role_backend("refiner", agent_backend),
            codex_timeout,
            codex_binary=codex_binary,
            api_config=api_config,
            allowed_files=refiner_allowed,
            output_files=["final/discussion.tex", f"revisions/refine_round_{next_round:03d}.md"],
        )
        record[f"refiner_{next_round:03d}_returncode"] = refiner_result.returncode
        record[f"refiner_{next_round:03d}_backend"] = refiner_result.backend
        record[f"refiner_{next_round:03d}_elapsed_sec"] = refiner_result.elapsed_sec
        if refiner_result.returncode != 0 or not (run_dir / "final" / "discussion.tex").exists():
            record["status"] = "refiner_failed"
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
        record["refiner_rounds_used"] = next_round
        save_draft(run_dir, next_round)
        gates_ok, failed_gates = gates_pass(run_dir, next_round)
        if not gates_ok:
            record["status"] = "gate_failed"
            record["failed_gates"] = failed_gates
            write_yaml(run_dir / "status.yaml", record)
            write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
            return record
    if oracle_audit:
        run_oracle_audit(load_task(task.path), run_dir / "final" / "discussion.tex", run_dir / "oracle_audit.yaml")
        record["oracle_audit"] = True
    record["status"] = "done"
    write_yaml(run_dir / "status.yaml", record)
    write_or_update_provenance(run_dir, task, skill, image_mode, codex_binary=codex_binary, status=record["status"])
    return record


def successful_statuses(prepare_only: bool = False) -> set[str]:
    statuses = {"done"}
    if prepare_only:
        statuses.add("prepared")
    return statuses


def write_summary(out_root: Path, run_id: str, skill_version: str, records: list[dict[str, Any]], prepare_only: bool = False) -> Path:
    success = successful_statuses(prepare_only=prepare_only)
    summary = {
        "run_id": run_id,
        "skill_version": skill_version,
        "total": len(records),
        "completed": sum(1 for item in records if item.get("status") in success),
        "failed": sum(1 for item in records if item.get("status") not in success),
        "records": records,
    }
    path = out_root / run_id / "summary.yaml"
    write_yaml(path, summary)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run section-wise Discussion generation with lightweight gates.")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=f"discussion_v1_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--skill-version", default=DEFAULT_SKILL_VERSION)
    parser.add_argument("--task-name", default="discussion")
    parser.add_argument("--only-slug", default="")
    parser.add_argument("--image-mode", default="benchmark_vlm", choices=["copy", "text_summary", "external_vlm", "benchmark_vlm"])
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--oracle-audit", action="store_true")
    parser.add_argument("--max-refiner-rounds", type=int, default=0)
    parser.add_argument("--agent-backend", choices=["codex", "api", "codex+api"], default="codex")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-timeout", type=int, default=600)
    parser.add_argument("--api-max-tokens", type=int, default=16000)
    parser.add_argument("--codex-timeout", type=int, default=DEFAULT_CODEX_TIMEOUT)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--paper-story-contract", type=Path, default=None)
    parser.add_argument("--paper-evidence-ledger", type=Path, default=None)
    parser.add_argument("--progress-plain", action="store_true")
    args = parser.parse_args(argv)

    tasks = discover_tasks(args.tasks_root, only_slug=args.only_slug or None, task_name=args.task_name)
    skill = load_skill(args.skill_version)
    api_cfg = None
    if args.agent_backend in {"api", "codex+api"}:
        api_cfg = api_config_from_env(args.env, args.model, args.api_timeout, args.api_max_tokens)
    progress = ProgressReporter(args.run_id, len(tasks), enabled=True)
    progress.event("batch", "started", total=len(tasks), skill=args.skill_version)
    records: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        progress.set_task_index(index)
        progress.event("task", "started", task=task)
        run_dir = args.out / args.run_id / task.field / task.slug / task.task_name
        record = run_task(
            task,
            run_dir,
            skill,
            image_mode=args.image_mode,
            prepare_only=args.prepare_only,
            codex_timeout=args.codex_timeout,
            codex_binary=args.codex_binary,
            oracle_audit=args.oracle_audit,
            agent_backend=args.agent_backend,
            api_config=api_cfg,
            max_refiner_rounds=args.max_refiner_rounds,
            paper_story_contract=args.paper_story_contract,
            paper_evidence_ledger=args.paper_evidence_ledger,
        )
        records.append({**record, "run_dir": str(run_dir)})
        progress.event("task", "done", task=task, task_status=record.get("status"))
    summary_path = write_summary(args.out, args.run_id, args.skill_version, records, prepare_only=args.prepare_only)
    success = successful_statuses(prepare_only=args.prepare_only)
    completed = sum(1 for item in records if item.get("status") in success)
    failed = len(records) - completed
    progress.event("batch", "done", completed=completed, failed=failed, report=summary_path)
    print(summary_path)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
