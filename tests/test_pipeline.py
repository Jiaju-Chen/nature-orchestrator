import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def write_yaml(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class NatureOrchestratorPipelineTests(unittest.TestCase):
    def test_generic_workspace_contract_loads(self):
        contract = yaml.safe_load(
            (ROOT / "skills" / "nature_writing" / "contracts" / "manuscript_workspace.yaml").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(contract["schema_version"], "nature_orchestrator.manuscript_workspace.v1")
        self.assertEqual(contract["policy"]["evidence_only"], True)
        self.assertEqual(contract["policy"]["oracle_available"], False)
        self.assertIn("results_notes", contract["inputs"])

    def test_generic_workspace_prompt_pack_excludes_outputs_and_oracle(self):
        out_dir = Path(tempfile.mkdtemp()) / "generic-run"
        workspace = ROOT / "examples" / "minimal_manuscript_workspace" / "workspace.yaml"

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_manuscript_workspace.py"),
                "--workspace",
                str(workspace),
                "--out",
                str(out_dir),
                "--backend",
                "prompt-pack",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn(str(out_dir), completed.stdout)
        allowed = yaml.safe_load((out_dir / "prompt_pack" / "allowed_files.yaml").read_text(encoding="utf-8"))
        forbidden = yaml.safe_load((out_dir / "prompt_pack" / "forbidden_files.yaml").read_text(encoding="utf-8"))

        allowed_text = json.dumps(allowed)
        self.assertNotIn("oracle", allowed_text)
        self.assertNotIn("manuscript/results.tex", allowed_text)
        self.assertIn("oracle/", forbidden["forbidden_files"])
        self.assertIn("manuscript/results.tex", forbidden["forbidden_files"])

    def test_generic_workspace_prompt_pack_lists_only_allowed_files(self):
        out_dir = Path(tempfile.mkdtemp()) / "generic-run"
        workspace = ROOT / "examples" / "minimal_manuscript_workspace" / "workspace.yaml"

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_manuscript_workspace.py"),
                "--workspace",
                str(workspace),
                "--out",
                str(out_dir),
                "--backend",
                "prompt-pack",
            ],
            cwd=ROOT,
            check=True,
        )
        allowed = yaml.safe_load((out_dir / "prompt_pack" / "allowed_files.yaml").read_text(encoding="utf-8"))

        self.assertIn("inputs/research_question.md", allowed["allowed_files"])
        self.assertIn("inputs/figures.yaml", allowed["allowed_files"])
        self.assertIn(
            "skills/nature_writing/versions/v0_2_generic_full_paper_pipeline/prompts/writer.md",
            allowed["allowed_files"],
        )
        for value in allowed["allowed_files"]:
            self.assertFalse(Path(value).is_absolute(), value)
            self.assertNotIn("..", Path(value).parts, value)

    def test_generic_workspace_prompt_pack_writes_provenance(self):
        out_dir = Path(tempfile.mkdtemp()) / "generic-run"
        workspace = ROOT / "examples" / "minimal_manuscript_workspace" / "workspace.yaml"

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_manuscript_workspace.py"),
                "--workspace",
                str(workspace),
                "--out",
                str(out_dir),
                "--backend",
                "prompt-pack",
            ],
            cwd=ROOT,
            check=True,
        )
        provenance = yaml.safe_load((out_dir / "provenance.yaml").read_text(encoding="utf-8"))

        self.assertEqual(provenance["schema_version"], "nature_orchestrator.provenance.v1")
        self.assertEqual(provenance["skill_version"], "v0_2_generic_full_paper_pipeline")
        self.assertIn("workspace_hash", provenance)
        self.assertIn("writer", provenance["prompt_hashes"])

    def test_minimal_example_workspace_prepare_only(self):
        out_dir = Path(tempfile.mkdtemp()) / "minimal-workspace"
        workspace = ROOT / "examples" / "minimal_manuscript_workspace" / "workspace.yaml"

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_manuscript_workspace.py"),
                "--workspace",
                str(workspace),
                "--out",
                str(out_dir),
                "--backend",
                "prompt-pack",
            ],
            cwd=ROOT,
            check=True,
        )

        self.assertTrue((out_dir / "prompt_pack" / "writer_prompt.md").exists())
        self.assertTrue((out_dir / "context_pack" / "context.md").exists())
        self.assertTrue((out_dir / "run_manifest.yaml").exists())

    def test_minimal_example_workspace_auto_mock_writes_full_pipeline_artifacts(self):
        out_dir = Path(tempfile.mkdtemp()) / "minimal-workspace-auto"
        workspace = ROOT / "examples" / "minimal_manuscript_workspace" / "workspace.yaml"

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_manuscript_workspace.py"),
                "--workspace",
                str(workspace),
                "--out",
                str(out_dir),
                "--backend",
                "mock",
                "--mode",
                "auto",
                "--max-refiner-rounds",
                "1",
                "--max-reviewer-workers",
                "3",
            ],
            cwd=ROOT,
            check=True,
        )

        run_manifest = yaml.safe_load((out_dir / "run_manifest.yaml").read_text(encoding="utf-8"))
        decision = yaml.safe_load((out_dir / "decisions" / "decision_000.yaml").read_text(encoding="utf-8"))
        final_text = (out_dir / "final" / "manuscript.tex").read_text(encoding="utf-8")
        provenance = yaml.safe_load((out_dir / "provenance.yaml").read_text(encoding="utf-8"))

        self.assertEqual(run_manifest["status"], "completed")
        self.assertEqual(run_manifest["mode"], "auto")
        self.assertEqual(decision["decision"], "polish")
        self.assertTrue((out_dir / "story" / "story_blueprint.yaml").exists())
        self.assertTrue((out_dir / "drafts" / "draft_000.tex").exists())
        self.assertTrue((out_dir / "drafts" / "draft_001.tex").exists())
        self.assertTrue((out_dir / "reviews" / "round_000" / "evidence_reviewer.yaml").exists())
        self.assertTrue((out_dir / "reviews" / "round_000" / "story_reviewer.yaml").exists())
        self.assertTrue((out_dir / "reviews" / "round_000" / "citation_reviewer.yaml").exists())
        self.assertTrue((out_dir / "final" / "audit.yaml").exists())
        self.assertIn("\\section{Results}", final_text)
        self.assertIn("\\section{Discussion}", final_text)
        self.assertIn("\\begin{abstract}", final_text)
        self.assertIn("final/manuscript.tex", provenance["output_hashes"])

    def test_nature_writing_skill_mentions_auto_pipeline_command(self):
        skill_text = (ROOT / "skills" / "nature_writing" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("run_manuscript_workspace.py", skill_text)
        self.assertIn("--mode auto", skill_text)
        self.assertIn("--max-reviewer-workers", skill_text)

    def test_naturebench_full_paper_adapter_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            task_path = self.make_results_figure_grounded_task(tmp_path)
            tasks_root = task_path.parents[3]
            out_dir = tmp_path / "outputs"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_full_paper_batch.py"),
                    "--prepare-only",
                    "--tasks-root",
                    str(tasks_root),
                    "--out",
                    str(out_dir),
                    "--run-id",
                    "adapter-smoke",
                    "--only-slug",
                    "case",
                    "--generators",
                    "nature-orchestrator",
                    "--image-mode",
                    "benchmark_vlm",
                    "--quiet-progress",
                ],
                cwd=ROOT,
                check=True,
            )

            summary = yaml.safe_load((out_dir / "adapter-smoke" / "summary.yaml").read_text(encoding="utf-8"))
            self.assertEqual(summary["completed"], 1)
            self.assertTrue(
                (out_dir / "adapter-smoke" / "nature-orchestrator" / "case" / "prompt_pack" / "prompt.md").exists()
            )

    def make_task(self, root: Path) -> Path:
        case = root / "case"
        benchmark = case / "benchmark"
        write_text(case / "renderers" / "custom_nature_template" / "sections" / "abstract_intro.tex", "Allowed abstract and intro.")
        write_text(case / "renderers" / "custom_nature_template" / "sections" / "discussion.tex", "Allowed discussion.")
        write_text(case / "renderers" / "custom_nature_template" / "sections" / "methods.tex", "Allowed methods.")
        write_text(case / "renderers" / "custom_nature_template" / "sections" / "results.tex", "HIDDEN TARGET RESULTS.")
        write_text(case / "inputs" / "figures" / "figure-1.caption.txt", "Fig. 1 | A measured result with panels a and b.")
        write_text(case / "inputs" / "figures" / "figure-1.png", "fake png bytes")
        write_yaml(
            benchmark / "evidence_pack.yaml",
            {
                "case_slug": "s41586-test",
                "figures": [{"id": "figure-1", "caption": "Figure evidence"}],
                "source_data": [{"path": "inputs/source_data/source.xlsx"}],
                "availability": {"data": "Data are available."},
            },
        )
        write_yaml(
            benchmark / "leakage_policy.yaml",
            {
                "forbidden_path_prefixes": ["benchmark/oracle/"],
                "oracle_only": ["benchmark/oracle/ground_truth_sections.yaml"],
            },
        )
        write_yaml(
            benchmark / "oracle" / "ground_truth_sections.yaml",
            {"sections": {"results": {"text": "HIDDEN TARGET RESULTS."}}},
        )
        task = {
            "schema_version": "naturebench.task.v1",
            "task_id": "s41586-test.results",
            "case_slug": "s41586-test",
            "target_section": "results",
            "task_family": "section_masking",
            "evidence_pack": "benchmark/evidence_pack.yaml",
            "leakage_policy": "benchmark/leakage_policy.yaml",
            "allowed_context": {
                "non_target_sections": [
                    {"section": "abstract_intro", "path": "renderers/custom_nature_template/sections/abstract_intro.tex"},
                    {"section": "discussion", "path": "renderers/custom_nature_template/sections/discussion.tex"},
                    {"section": "methods", "path": "renderers/custom_nature_template/sections/methods.tex"},
                ],
                "evidence_artifacts": ["benchmark/evidence_pack.yaml"],
            },
            "forbidden_context": {
                "target_section": "results",
                "paths": [
                    "renderers/custom_nature_template/sections/results.tex",
                    "benchmark/oracle/ground_truth_sections.yaml",
                ],
            },
            "output": {"format": "latex_section", "path_hint": "target_section.tex"},
        }
        write_yaml(benchmark / "tasks" / "results.yaml", task)
        return benchmark / "tasks" / "results.yaml"

    def make_safe_web_task(self, root: Path) -> Path:
        task_path = self.make_task(root)
        case = task_path.parents[2]
        benchmark = case / "benchmark"
        write_yaml(
            benchmark / "control" / "target_fingerprint.yaml",
            {
                "schema_version": "naturebench.target_fingerprint.v1",
                "doi": "10.1038/s41586-test",
                "doi_suffix": "s41586-test",
                "slug": "s41586-test",
                "article_url": "https://www.nature.com/articles/s41586-test",
                "title": "Hidden Nature Result Title",
                "title_ngrams": ["hidden nature result title"],
                "authors": ["Ada Example", "Grace Benchmark"],
                "author_surnames": ["example", "benchmark"],
                "publication_date": "2026-04-22",
                "known_preprints": ["https://arxiv.org/abs/2601.00001"],
            },
        )
        write_yaml(
            benchmark / "evidence_pack.sanitized.yaml",
            {
                "schema_version": "naturebench.evidence_pack.sanitized.v1",
                "blind_case_id": "case-0001",
                "figures": [{"id": "figure-1", "caption": "Figure evidence"}],
                "source_data": [{"path": "inputs/source_data/source.xlsx"}],
                "availability": {"data": "Data are available."},
            },
        )
        write_yaml(
            benchmark / "evidence_pack.figure_grounded.yaml",
            {
                "schema_version": "naturebench.evidence_pack.figure_grounded.v1",
                "blind_case_id": "case-0001",
                "figure_evidence": [
                    {
                        "id": "figure-1",
                        "kind": "main",
                        "image_path": "inputs/figures/figure-1.png",
                        "caption_path": "inputs/figures/figure-1.caption.txt",
                        "caption_text": "Fig. 1 | A measured result with panels a and b.",
                        "source_data": [{"path": "inputs/source_data/source.xlsx"}],
                        "method_snippets": [
                            {
                                "section": "methods",
                                "path": "renderers/custom_nature_template/sections/methods.tex",
                                "text": "A method snippet tied to Fig. 1.",
                            }
                        ],
                        "role_hints": [
                            {
                                "section": "abstract_intro",
                                "path": "renderers/custom_nature_template/sections/abstract_intro.tex",
                                "text": "The introduction explains why Fig. 1 matters.",
                            }
                        ],
                    }
                ],
                "availability": {"data": "Data are available."},
            },
        )
        task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        task.update(
            {
                "task_id": "case-0001.results",
                "case_slug": "case-0001",
                "blind_case_id": "case-0001",
                "evidence_pack": "benchmark/evidence_pack.sanitized.yaml",
                "network": {
                    "mode": "safe_web",
                    "target_fingerprint": "benchmark/control/target_fingerprint.yaml",
                },
            }
        )
        task["allowed_context"]["evidence_artifacts"] = ["benchmark/evidence_pack.sanitized.yaml"]
        task["forbidden_context"]["paths"].append("benchmark/control/")
        write_yaml(benchmark / "tasks_safe_web" / "results.yaml", task)
        return benchmark / "tasks_safe_web" / "results.yaml"

    def make_results_figure_grounded_task(self, root: Path) -> Path:
        task_path = self.make_safe_web_task(root)
        benchmark = task_path.parents[1]
        task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        task.update(
            {
                "task_id": "case-0001.results.figure_grounded",
                "task_variant": "figure_grounded",
                "evidence_pack": "benchmark/evidence_pack.figure_grounded.yaml",
            }
        )
        task["allowed_context"]["non_target_sections"] = [
            {"section": "abstract_intro", "path": "renderers/custom_nature_template/sections/abstract_intro.tex"}
        ]
        task["allowed_context"]["evidence_artifacts"] = ["benchmark/evidence_pack.figure_grounded.yaml"]
        write_yaml(benchmark / "tasks_safe_web" / "results_figure_grounded.yaml", task)
        return benchmark / "tasks_safe_web" / "results_figure_grounded.yaml"

    def test_fake_adapter_runs_without_reading_oracle(self):
        from nature_orchestrator.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_task(Path(tmp))
            out_dir = Path(tmp) / "run"

            result = run_task(task_path, out_dir, adapter_name="fake", oracle_audit=False)

            final_text = (out_dir / "final" / "target_section.tex").read_text(encoding="utf-8")
            context_text = (out_dir / "context_pack" / "context.md").read_text(encoding="utf-8")

        self.assertEqual(result["status"], "completed")
        self.assertIn("Draft results section", final_text)
        self.assertIn("Allowed abstract and intro.", context_text)
        self.assertNotIn("HIDDEN TARGET RESULTS", context_text)
        self.assertFalse((out_dir / "oracle_audit.yaml").exists())

    def test_prompt_pack_adapter_writes_allowed_and_forbidden_files(self):
        from nature_orchestrator.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_task(Path(tmp))
            out_dir = Path(tmp) / "prompt-run"

            run_task(task_path, out_dir, adapter_name="prompt-pack", oracle_audit=False)

            prompt = (out_dir / "prompt_pack" / "prompt.md").read_text(encoding="utf-8")
            forbidden = yaml.safe_load((out_dir / "prompt_pack" / "forbidden_files.yaml").read_text(encoding="utf-8"))

        self.assertIn("Write the masked `results` section", prompt)
        self.assertIn("benchmark/oracle/ground_truth_sections.yaml", forbidden["forbidden_files"])
        self.assertIn("renderers/custom_nature_template/sections/results.tex", forbidden["forbidden_files"])

    def test_run_task_module_exposes_cli_main(self):
        from nature_orchestrator.run_task import main

        self.assertTrue(callable(main))

    def test_context_builder_rejects_oracle_allowed_context(self):
        from nature_orchestrator.context import LeakageError, build_context
        from nature_orchestrator.loader import load_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_task(Path(tmp))
            task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
            task["allowed_context"]["non_target_sections"].append(
                {"section": "leak", "path": "benchmark/oracle/ground_truth_sections.yaml"}
            )
            write_yaml(task_path, task)

            with self.assertRaises(LeakageError):
                build_context(load_task(task_path))

    def test_oracle_audit_runs_only_when_requested(self):
        from nature_orchestrator.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_task(Path(tmp))
            out_dir = Path(tmp) / "oracle-run"

            run_task(task_path, out_dir, adapter_name="fake", oracle_audit=True)
            audit = yaml.safe_load((out_dir / "oracle_audit.yaml").read_text(encoding="utf-8"))

        self.assertEqual(audit["target_section"], "results")
        self.assertTrue(audit["ground_truth_available"])
        self.assertIn("HIDDEN TARGET RESULTS", json.dumps(audit))

    def test_oracle_audit_reports_v1_metrics(self):
        from nature_orchestrator.loader import load_task
        from nature_orchestrator.oracle import run_oracle_audit

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_task(Path(tmp))
            task = load_task(task_path)
            generated = Path(tmp) / "generated.tex"
            generated.write_text("\\section{Results}\nAlpha beta supported claim.\n", encoding="utf-8")
            oracle_path = task.case_root / "benchmark" / "oracle" / "ground_truth_sections.yaml"
            oracle = yaml.safe_load(oracle_path.read_text(encoding="utf-8"))
            oracle["sections"]["results"]["text"] = "@@SUBSECTION:Findings@@\nAlpha beta gamma delta evidence claim.\n"
            write_yaml(oracle_path, oracle)

            audit = run_oracle_audit(task, generated, Path(tmp) / "oracle_audit.yaml")

        self.assertEqual(audit["schema_version"], "nature_orchestrator.oracle_audit.v1")
        self.assertLess(audit["metrics"]["ground_truth_token_recall"], 1.0)
        self.assertIn("gamma", audit["metrics"]["missing_keywords"])
        self.assertIn("supported", audit["metrics"]["unsupported_generated_keywords"])
        self.assertEqual(audit["metrics"]["ground_truth_heading_count"], 1)
        self.assertEqual(audit["metrics"]["generated_heading_count"], 1)

    def test_safe_web_query_result_and_fetch_guards_block_target_leaks(self):
        from nature_orchestrator.retrieval import (
            filter_fetched_document,
            filter_query,
            filter_search_result,
        )

        fingerprint = {
            "doi": "10.1038/s41586-test",
            "doi_suffix": "s41586-test",
            "slug": "s41586-test",
            "article_url": "https://www.nature.com/articles/s41586-test",
            "title": "Hidden Nature Result Title",
            "title_ngrams": ["hidden nature result title"],
            "authors": ["Ada Example", "Grace Benchmark"],
            "author_surnames": ["example", "benchmark"],
            "publication_date": "2026-04-22",
            "known_preprints": ["https://arxiv.org/abs/2601.00001"],
        }

        self.assertFalse(filter_query("10.1038/s41586-test related work", fingerprint)["allowed"])
        self.assertFalse(filter_query("Hidden Nature Result Title arxiv", fingerprint)["allowed"])
        self.assertFalse(filter_query("Example Benchmark hidden result title", fingerprint)["allowed"])

        blocked_result = filter_search_result(
            {
                "title": "Hidden Nature Result Title",
                "url": "https://www.nature.com/articles/s41586-test",
                "snippet": "Nature paper summary",
                "date": "2026-04-22",
            },
            fingerprint,
        )
        self.assertFalse(blocked_result["allowed"])

        late_result = filter_search_result(
            {
                "title": "Safe looking commentary",
                "url": "https://example.org/commentary",
                "snippet": "Commentary after publication",
                "date": "2026-05-01",
            },
            fingerprint,
        )
        self.assertFalse(late_result["allowed"])

        fetched = filter_fetched_document(
            {
                "title": "Safe looking page",
                "url": "https://example.org/page",
                "text": "This page reveals Hidden Nature Result Title and 10.1038/s41586-test.",
            },
            fingerprint,
        )
        self.assertFalse(fetched["allowed"])
        self.assertNotIn("text", fetched)

    def test_safe_search_writes_literature_pack_without_blocked_body_text(self):
        from nature_orchestrator.retrieval import safe_search

        fingerprint = {
            "slug": "s41586-test",
            "title": "Hidden Nature Result Title",
            "title_ngrams": ["hidden nature result title"],
            "publication_date": "2026-04-22",
        }
        pack = safe_search(
            [{"query": "earlier general benchmark literature"}],
            fingerprint,
            search_backend=lambda query: [
                {
                    "title": "Allowed prior work",
                    "url": "https://example.org/prior",
                    "snippet": "A prior method.",
                    "date": "2025-01-01",
                    "text": "A safe excerpt about prior work.",
                },
                {
                    "title": "Hidden Nature Result Title",
                    "url": "https://example.org/leak",
                    "snippet": "Leak",
                    "date": "2025-01-01",
                    "text": "Hidden Nature Result Title leak.",
                },
            ],
        )

        self.assertEqual(pack["schema_version"], "nature_orchestrator.literature_pack.v1")
        self.assertEqual(len(pack["kept_documents"]), 1)
        self.assertEqual(len(pack["blocked_documents"]), 1)
        self.assertEqual(pack["kept_documents"][0]["title"], "Allowed prior work")
        self.assertNotIn("Hidden Nature Result Title leak", json.dumps(pack))

    def test_safe_web_prompt_pack_uses_blind_context_and_sanitized_evidence(self):
        from nature_orchestrator.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_safe_web_task(Path(tmp))
            out_dir = Path(tmp) / "safe-web-run"

            run_task(task_path, out_dir, adapter_name="prompt-pack", oracle_audit=False, network_mode="safe_web")

            context_text = (out_dir / "context_pack" / "context.md").read_text(encoding="utf-8")
            prompt_text = (out_dir / "prompt_pack" / "prompt.md").read_text(encoding="utf-8")
            allowed = yaml.safe_load((out_dir / "prompt_pack" / "allowed_files.yaml").read_text(encoding="utf-8"))
            network_policy = yaml.safe_load((out_dir / "prompt_pack" / "network_policy.yaml").read_text(encoding="utf-8"))

        combined = context_text + prompt_text + yaml.safe_dump(allowed, sort_keys=False)
        self.assertIn("case-0001.results", combined)
        self.assertIn("benchmark/evidence_pack.sanitized.yaml", allowed["allowed_files"])
        self.assertEqual(network_policy["mode"], "safe_web")
        for forbidden in [
            "s41586-test",
            "10.1038/s41586-test",
            "Hidden Nature Result Title",
            "https://www.nature.com/articles/s41586-test",
        ]:
            self.assertNotIn(forbidden, combined)

    def test_results_figure_grounded_context_expands_caption_and_copies_assets(self):
        from nature_orchestrator.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_results_figure_grounded_task(Path(tmp))
            out_dir = Path(tmp) / "figure-grounded-run"

            run_task(task_path, out_dir, adapter_name="prompt-pack", oracle_audit=False, network_mode="safe_web")

            context_text = (out_dir / "context_pack" / "context.md").read_text(encoding="utf-8")
            prompt_text = (out_dir / "prompt_pack" / "prompt.md").read_text(encoding="utf-8")
            allowed = yaml.safe_load((out_dir / "prompt_pack" / "allowed_files.yaml").read_text(encoding="utf-8"))

        self.assertIn("## Figure Evidence", context_text)
        self.assertIn("Fig. 1 | A measured result with panels a and b.", context_text)
        self.assertIn("A method snippet tied to Fig. 1.", context_text)
        self.assertIn("experiment purpose", prompt_text)
        self.assertIn("claim roles", prompt_text)
        self.assertIn("evidence/figures/figure-1.png", allowed["allowed_files"])
        self.assertIn("evidence/figures/figure-1.caption.txt", allowed["allowed_files"])

    def test_results_oracle_audit_reports_results_specific_metrics(self):
        from nature_orchestrator.loader import load_task
        from nature_orchestrator.oracle import run_oracle_audit

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_results_figure_grounded_task(Path(tmp))
            task = load_task(task_path)
            generated = Path(tmp) / "generated.tex"
            generated.write_text(
                "\\section{Results}\n\\subsection{Measured pattern}\n"
                "Figure~1 shows the empirical observation and a control, suggesting a broader mechanism.\n",
                encoding="utf-8",
            )
            oracle_path = task.case_root / "benchmark" / "oracle" / "ground_truth_sections.yaml"
            oracle = yaml.safe_load(oracle_path.read_text(encoding="utf-8"))
            oracle["sections"]["results"]["text"] = "\\section{Results}\n\\subsection{Measured pattern}\nFigure 1 shows alpha beta."
            write_yaml(oracle_path, oracle)

            audit = run_oracle_audit(task, generated, Path(tmp) / "oracle_audit.yaml")
            report = (Path(tmp) / "reports" / "results_quality_report.md").read_text(encoding="utf-8")

        metrics = audit["metrics"]["results_quality"]
        self.assertIn("structure_score", metrics)
        self.assertIn("figure_grounding_score", metrics)
        self.assertIn("claim_role_score", metrics)
        self.assertIn("nature_narrative_score", metrics)
        self.assertIn("leakage_score", metrics)
        self.assertIn("oracle_similarity", metrics)
        self.assertIn("panel_mention_coverage", metrics)
        self.assertEqual(metrics["mentioned_figures"], ["figure-1"])
        self.assertIn("Expected figures: `1`", report)
        self.assertIn("Mentioned figures: `1`", report)
        self.assertIn("Missing figures: none", report)
        self.assertIn("Panel mention coverage", report)

    def test_results_metrics_use_ground_truth_figures_and_panel_refs(self):
        from nature_orchestrator.loader import load_task
        from nature_orchestrator.oracle import run_oracle_audit

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_results_figure_grounded_task(Path(tmp))
            task = load_task(task_path)
            generated = Path(tmp) / "generated.tex"
            generated.write_text(
                "\\section{Results}\n"
                "Fig. 1a,b shows the empirical observation and the control condition.\n"
                "Extended Data Fig. 2 is only supporting material.\n",
                encoding="utf-8",
            )
            oracle_path = task.case_root / "benchmark" / "oracle" / "ground_truth_sections.yaml"
            oracle = yaml.safe_load(oracle_path.read_text(encoding="utf-8"))
            oracle["sections"]["results"]["text"] = (
                "\\section{Results}\n"
                "The main result appears in Fig. 1a,b. Extended Data Fig. 2 is not a main figure requirement.\n"
            )
            write_yaml(oracle_path, oracle)

            audit = run_oracle_audit(task, generated, Path(tmp) / "oracle_audit.yaml")

        metrics = audit["metrics"]["results_quality"]
        self.assertEqual(metrics["figures"], ["figure-1"])
        self.assertEqual(metrics["mentioned_figures"], ["figure-1"])
        self.assertEqual(metrics["missing_figures"], [])
        self.assertEqual(metrics["expected_panel_count"], 2)
        self.assertEqual(metrics["mentioned_panel_count"], 2)
        self.assertEqual(metrics["panel_mention_coverage"], 1.0)

    def test_results_quality_report_records_identifier_leakage(self):
        from nature_orchestrator.loader import load_task
        from nature_orchestrator.oracle import run_oracle_audit

        with tempfile.TemporaryDirectory() as tmp:
            task_path = self.make_results_figure_grounded_task(Path(tmp))
            task = load_task(task_path)
            generated = Path(tmp) / "generated.tex"
            generated.write_text(
                "\\section{Results}\nFigure 1 shows a result from 10.1038/s41586-test.\n",
                encoding="utf-8",
            )

            audit = run_oracle_audit(task, generated, Path(tmp) / "oracle_audit.yaml")
            report = (Path(tmp) / "reports" / "results_quality_report.md").read_text(encoding="utf-8")

        metrics = audit["metrics"]["results_quality"]
        self.assertEqual(metrics["leakage_score"], 0.0)
        self.assertIn("10.1038/s41586-test", metrics["leakage_hits"])
        self.assertIn("Leakage score: `0.0`", report)
        self.assertIn("10.1038/s41586-test", report)


if __name__ == "__main__":
    unittest.main()
