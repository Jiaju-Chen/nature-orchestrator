from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NatureWritingCurrentReleaseTests(unittest.TestCase):
    def test_current_skill_is_self_contained_and_clean(self):
        skill_root = ROOT / "skills" / "nature_writing"
        required = [
            "SKILL.md",
            "README.md",
            "manifest.yaml",
            "tasks/full_paper_writing.md",
            "tasks/section_writing.md",
            "methods/evidence_to_story.md",
            "methods/write_review_and_refine.md",
            "prompts/results_writer.md",
            "prompts/discussion_writer.md",
            "prompts/abstract_intro_writer.md",
            "prompts/cross_section_reviewer.md",
            "rubrics/section_reviewer_rubric.yaml",
            "rubrics/supervisor_rubric.yaml",
        ]
        for rel in required:
            self.assertTrue((skill_root / rel).exists(), rel)

        searchable = [
            skill_root / "SKILL.md",
            skill_root / "README.md",
            skill_root / "manifest.yaml",
            *sorted((skill_root / "tasks").glob("*")),
            *sorted((skill_root / "methods").glob("*")),
            *sorted((skill_root / "prompts").glob("*")),
            *sorted((skill_root / "rubrics").glob("*")),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in searchable if path.is_file())
        forbidden = ("versions/", "v2_", "source_version", "s41586", "PLX5622")
        for token in forbidden:
            self.assertNotIn(token, combined)
        versions_root = skill_root / "versions"
        self.assertFalse(any(path.is_file() for path in versions_root.rglob("*")) if versions_root.exists() else False)

    def test_current_profiles_load_from_root_skill(self):
        abstract_intro = load_module("abstract_intro_current_release", "scripts/run_abstract_intro_batch.py")
        results = load_module("results_current_release", "scripts/run_results_batch.py")
        discussion = load_module("discussion_current_release", "scripts/run_discussion_batch.py")

        self.assertEqual(
            abstract_intro.load_skill("nature_writing_current_abstract_intro").version,
            "nature_writing_current_abstract_intro",
        )
        self.assertEqual(
            results.load_skill("nature_writing_current_results").version,
            "nature_writing_current_results",
        )
        self.assertEqual(
            discussion.load_skill("nature_writing_current_discussion").version,
            "nature_writing_current_discussion",
        )

    def test_supervisor_v21_and_holdout_report_are_present(self):
        rubric = yaml.safe_load(
            (ROOT / "skills" / "scientific_writing_supervisor" / "rubrics" / "supervisor_v2_1.yaml").read_text(
                encoding="utf-8"
            )
        )
        scores = rubric.get("scores") or {}
        self.assertIn("writing_flow", scores)
        self.assertIn("evidence_to_writing_grounding", scores)
        self.assertIn("claim_calibration", scores)

        report = ROOT / "docs" / "holdout_review_report_nature_writing_current.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("15 pass / 0 needs_revision / 0 fail", text)
        self.assertIn("overall mean | 4.553", text)


if __name__ == "__main__":
    unittest.main()
