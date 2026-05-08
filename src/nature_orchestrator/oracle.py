from __future__ import annotations

import re
from pathlib import Path

from .contracts import TaskSpec
from .io import read_yaml, write_text, write_yaml


STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "because",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "only",
    "section",
    "shown",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "using",
    "were",
    "where",
    "which",
    "with",
}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
LATEX_HEADING_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{[^{}]+\}")
MARKER_HEADING_RE = re.compile(r"@@(?:SECTION|SUBSECTION|SUBSUBSECTION):[^@]+@@")


def content_tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def keyword_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for token in content_tokens(text):
        if token in STOPWORDS or len(token) < 5 or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


def token_recall(reference: str, generated: str) -> float:
    reference_tokens = set(content_tokens(reference))
    if not reference_tokens:
        return 0.0
    generated_tokens = set(content_tokens(generated))
    return round(len(reference_tokens & generated_tokens) / len(reference_tokens), 4)


def token_precision(reference: str, generated: str) -> float:
    generated_tokens = set(content_tokens(generated))
    if not generated_tokens:
        return 0.0
    reference_tokens = set(content_tokens(reference))
    return round(len(reference_tokens & generated_tokens) / len(generated_tokens), 4)


def oracle_metrics(ground_truth: str, generated: str) -> dict[str, object]:
    ground_truth_keywords = keyword_tokens(ground_truth)
    generated_keywords = keyword_tokens(generated)
    generated_keyword_set = set(generated_keywords)
    ground_truth_keyword_set = set(ground_truth_keywords)
    return {
        "ground_truth_token_recall": token_recall(ground_truth, generated),
        "generated_token_precision": token_precision(ground_truth, generated),
        "missing_keywords": [token for token in ground_truth_keywords if token not in generated_keyword_set][:30],
        "unsupported_generated_keywords": [token for token in generated_keywords if token not in ground_truth_keyword_set][:30],
        "ground_truth_heading_count": len(LATEX_HEADING_RE.findall(ground_truth)) + len(MARKER_HEADING_RE.findall(ground_truth)),
        "generated_heading_count": len(LATEX_HEADING_RE.findall(generated)) + len(MARKER_HEADING_RE.findall(generated)),
    }


def figure_ids_from_evidence(evidence: dict[str, object]) -> list[str]:
    records = evidence.get("figure_evidence") or evidence.get("figures") or []
    ids: list[str] = []
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict) and record.get("id"):
                ids.append(str(record["id"]))
    return ids


def main_figure_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    pattern = re.compile(r"(?<!Extended Data\s)\bFigs?\.?\s*~?([0-9]+)(?:[a-z])?(?:\s*(?:,|and|-)\s*([0-9]+)(?:[a-z])?)*", re.IGNORECASE)
    for match in pattern.finditer(text):
        numbers.add(match.group(1))
        if match.group(2):
            numbers.add(match.group(2))
    return numbers


def filter_expected_figures_by_ground_truth(figures: list[str], ground_truth: str) -> list[str]:
    mentioned_numbers = main_figure_numbers(ground_truth)
    if not mentioned_numbers:
        return figures
    expected: list[str] = []
    for figure_id in figures:
        match = re.search(r"(\d+)", figure_id)
        if match and match.group(1) in mentioned_numbers:
            expected.append(figure_id)
    return expected


def figure_records_from_evidence(evidence: dict[str, object]) -> list[dict[str, object]]:
    records = evidence.get("figure_evidence") or evidence.get("figures") or []
    return [record for record in records if isinstance(record, dict)]


def figure_is_mentioned(generated: str, figure_id: str) -> bool:
    match = re.search(r"(\d+)", figure_id)
    if not match:
        return figure_id.lower() in generated.lower()
    number = re.escape(match.group(1))
    patterns = [
        rf"(?<!Extended Data\s)\bFigs?\.?\s*~?{number}[a-z]?\b",
        rf"(?<!Extended Data\s)\bFigures?\.?\s*~?{number}[a-z]?\b",
        rf"\bfigure-{number}\b",
    ]
    return any(re.search(pattern, generated, re.IGNORECASE) for pattern in patterns)


def expected_panels(caption: str) -> list[str]:
    letters: set[str] = set()
    for match in re.finditer(r"\b([a-z])\s*,", caption):
        letters.add(match.group(1))
    for match in re.finditer(r"\bpanels?\s+([a-z])(?:\s*(?:and|,)\s*([a-z]))?", caption, re.IGNORECASE):
        letters.add(match.group(1).lower())
        if match.group(2):
            letters.add(match.group(2).lower())
    return sorted(letters)


def mentioned_panels(generated: str, figure_id: str, panels: list[str]) -> list[str]:
    if not panels:
        return []
    match = re.search(r"(\d+)", figure_id)
    number = re.escape(match.group(1)) if match else re.escape(figure_id)
    found: list[str] = []
    for panel in panels:
        patterns = [
            rf"(?<!Extended Data\s)\bFigs?\.?\s*~?{number}[a-z]*(?:\s*,\s*{panel}|{panel})\b",
            rf"(?<!Extended Data\s)\bFigures?\.?\s*~?{number}[a-z]*(?:\s*,\s*{panel}|{panel})\b",
            rf"\bpanel\s+{panel}\b",
            rf"\bpanels?[^.:\n;]*\b{panel}\b",
        ]
        if any(re.search(pattern, generated, re.IGNORECASE) for pattern in patterns):
            found.append(panel)
    return found


def panel_coverage(generated: str, evidence: dict[str, object], expected_figures: list[str]) -> dict[str, object]:
    expected_total = 0
    mentioned_total = 0
    by_figure: dict[str, dict[str, object]] = {}
    expected_set = set(expected_figures)
    for record in figure_records_from_evidence(evidence):
        figure_id = str(record.get("id") or "")
        if not figure_id or figure_id not in expected_set:
            continue
        panels = expected_panels(str(record.get("caption_text") or record.get("caption") or ""))
        mentioned = mentioned_panels(generated, figure_id, panels)
        expected_total += len(panels)
        mentioned_total += len(mentioned)
        by_figure[figure_id] = {"expected": panels, "mentioned": mentioned}
    return {
        "expected_panel_count": expected_total,
        "mentioned_panel_count": mentioned_total,
        "panel_mention_coverage": score_fraction(mentioned_total / expected_total) if expected_total else 0.0,
        "panels_by_figure": by_figure,
    }


def score_fraction(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def claim_role_metrics(generated: str) -> dict[str, object]:
    text = generated.lower()
    roles = {
        "empirical": bool(re.search(r"\b(fig|figure|table|panel|observed|showed|measured|revealed)\b", text)),
        "design": bool(re.search(r"\b(control|dataset|benchmark|model|training|method|evaluation|experiment)\b", text)),
        "interpretive": bool(re.search(r"\b(suggest|indicat|reveal|support|consistent|imply|demonstrat)\w*\b", text)),
        "narrative": bool(re.search(r"\b(next|therefore|together|to test|we then|we asked|we further)\b", text)),
    }
    return {
        "roles_present": [role for role, present in roles.items() if present],
        "score": score_fraction(sum(1 for present in roles.values() if present) / len(roles)),
    }


def leakage_hits(task: TaskSpec, generated: str) -> list[str]:
    network = task.raw.get("network") or {}
    fingerprint_path = network.get("target_fingerprint")
    if not fingerprint_path:
        return []
    path = task.resolve_case_path(str(fingerprint_path))
    fingerprint = read_yaml(path) if path.exists() else {}
    candidates: list[str] = []
    for key in ["doi", "doi_suffix", "slug", "article_url", "title"]:
        value = fingerprint.get(key)
        if value:
            candidates.append(str(value))
    candidates.extend(str(item) for item in fingerprint.get("known_preprints") or [] if item)
    lower = generated.lower()
    return [candidate for candidate in candidates if candidate and candidate.lower() in lower]


def results_quality_metrics(task: TaskSpec, ground_truth: str, generated: str, base_metrics: dict[str, object]) -> dict[str, object]:
    evidence_path = task.resolve_case_path(str(task.raw.get("evidence_pack") or ""))
    evidence = read_yaml(evidence_path) if evidence_path.exists() else {}
    all_figures = figure_ids_from_evidence(evidence if isinstance(evidence, dict) else {})
    figures = filter_expected_figures_by_ground_truth(all_figures, ground_truth)
    mentioned = [figure_id for figure_id in figures if figure_is_mentioned(generated, figure_id)]
    claim_roles = claim_role_metrics(generated)
    panel_metrics = panel_coverage(generated, evidence if isinstance(evidence, dict) else {}, figures)
    ground_truth_heading_count = int(base_metrics.get("ground_truth_heading_count") or 0)
    generated_heading_count = int(base_metrics.get("generated_heading_count") or 0)
    structure_denominator = max(1, ground_truth_heading_count)
    structure_score = score_fraction(generated_heading_count / structure_denominator)
    figure_grounding_score = score_fraction(len(mentioned) / len(figures)) if figures else 0.0
    leaks = leakage_hits(task, generated)
    nature_narrative_score = score_fraction(
        0.35 * structure_score
        + 0.35 * float(claim_roles["score"])
        + 0.30 * (figure_grounding_score if figures else 0.5)
    )
    return {
        "structure_score": structure_score,
        "figure_grounding_score": figure_grounding_score,
        "claim_role_score": claim_roles["score"],
        "claim_roles_present": claim_roles["roles_present"],
        "nature_narrative_score": nature_narrative_score,
        "leakage_score": 0.0 if leaks else 1.0,
        "leakage_hits": leaks,
        "figures": figures,
        "mentioned_figures": mentioned,
        "missing_figures": [figure_id for figure_id in figures if figure_id not in mentioned],
        "panel_mention_coverage": panel_metrics["panel_mention_coverage"],
        "expected_panel_count": panel_metrics["expected_panel_count"],
        "mentioned_panel_count": panel_metrics["mentioned_panel_count"],
        "panels_by_figure": panel_metrics["panels_by_figure"],
        "evidence_coverage": {
            "expected_figures": len(figures),
            "mentioned_figures": len(mentioned),
            "missing_figures": len(figures) - len(mentioned),
        },
        "oracle_similarity": {
            "ground_truth_token_recall": base_metrics.get("ground_truth_token_recall", 0.0),
            "generated_token_precision": base_metrics.get("generated_token_precision", 0.0),
        },
    }


def write_results_quality_report(task: TaskSpec, generated_path: Path, audit: dict[str, object], out_dir: Path) -> None:
    del task, generated_path
    metrics = ((audit.get("metrics") or {}).get("results_quality") or {}) if isinstance(audit, dict) else {}
    expected = len(metrics.get("figures") or [])
    mentioned = len(metrics.get("mentioned_figures") or [])
    missing = metrics.get("missing_figures") or []
    leaks = metrics.get("leakage_hits") or []
    oracle_similarity = metrics.get("oracle_similarity") or {}
    lines = [
        "# Results Quality Report",
        "",
        f"Expected figures: `{expected}`",
        f"Mentioned figures: `{mentioned}`",
        f"Missing figures: {', '.join(f'`{item}`' for item in missing) if missing else 'none'}",
        f"Panel mention coverage: `{metrics.get('panel_mention_coverage', 0.0)}`",
        "",
        "## Scores",
        "",
        f"- Structure score: `{metrics.get('structure_score', 0.0)}`",
        f"- Figure grounding score: `{metrics.get('figure_grounding_score', 0.0)}`",
        f"- Claim role score: `{metrics.get('claim_role_score', 0.0)}`",
        f"- Nature narrative score: `{metrics.get('nature_narrative_score', 0.0)}`",
        f"- Leakage score: `{metrics.get('leakage_score', 0.0)}`",
        f"- Oracle recall: `{oracle_similarity.get('ground_truth_token_recall', 0.0)}`",
        f"- Oracle precision: `{oracle_similarity.get('generated_token_precision', 0.0)}`",
        "",
        "## Claim Roles",
        "",
        ", ".join(f"`{role}`" for role in metrics.get("claim_roles_present") or []) or "none",
        "",
        "## Leakage Hits",
        "",
    ]
    lines.extend(f"- `{item}`" for item in leaks) if leaks else lines.append("- none")
    lines.extend(["", "## Panel Mentions", ""])
    panels_by_figure = metrics.get("panels_by_figure") or {}
    if panels_by_figure:
        lines.extend(["| Figure | Expected panels | Mentioned panels |", "| --- | --- | --- |"])
        for figure_id, panels in panels_by_figure.items():
            expected_panels_text = ", ".join(f"`{item}`" for item in panels.get("expected") or []) or "none"
            mentioned_panels_text = ", ".join(f"`{item}`" for item in panels.get("mentioned") or []) or "none"
            lines.append(f"| `{figure_id}` | {expected_panels_text} | {mentioned_panels_text} |")
    else:
        lines.append("- none")
    write_text(out_dir / "reports" / "results_quality_report.md", "\n".join(lines) + "\n")


def run_oracle_audit(task: TaskSpec, generated_path: Path, out_path: Path) -> dict[str, object]:
    oracle_path = task.case_root / "benchmark" / "oracle" / "ground_truth_sections.yaml"
    oracle = read_yaml(oracle_path) if oracle_path.exists() else {}
    target = task.target_section
    section = ((oracle.get("sections") or {}).get(target) or {}) if isinstance(oracle, dict) else {}
    ground_truth = str(section.get("text") or "")
    generated = generated_path.read_text(encoding="utf-8", errors="replace") if generated_path.exists() else ""
    metrics = oracle_metrics(ground_truth, generated)
    if task.target_section == "results":
        metrics["results_quality"] = results_quality_metrics(task, ground_truth, generated, metrics)
    audit = {
        "schema_version": "nature_orchestrator.oracle_audit.v1",
        "target_section": target,
        "ground_truth_available": bool(ground_truth),
        "generated_character_count": len(generated),
        "ground_truth_character_count": len(ground_truth),
        "metrics": metrics,
        "ground_truth_excerpt": ground_truth[:1000],
        "generated_excerpt": generated[:1000],
        "notes": [
            "Oracle audit is post-generation only; do not feed this artifact back into generation context.",
        ],
    }
    write_yaml(out_path, audit)
    if task.target_section == "results":
        write_results_quality_report(task, generated_path, audit, out_path.parent)
    return audit
