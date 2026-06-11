import sys
import tempfile
import unittest
import urllib.error
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def write_yaml(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


class EvidenceLedgerAndReviewValidationTests(unittest.TestCase):
    def test_evidence_claim_ledger_gate_accepts_structured_general_ledger(self):
        from nature_orchestrator.evidence_ledger import evidence_claim_ledger_gate

        ledger = {
            "schema_version": "nature_orchestrator.evidence_claim_ledger.v1",
            "evidence_items": [
                {
                    "anchor": "Fig. 1a-b",
                    "observation": "Treatment reduced the measured readout versus control.",
                    "comparator": "treatment versus control",
                    "direction": "reduced",
                    "confidence_source": "caption_supported",
                    "evidence_role": "primary_claim",
                    "must_write_detail": "name the comparator and direction",
                    "can_compress": "setup details",
                    "cannot_claim": "do not claim rescue",
                    "downstream_section_use": ["results", "discussion", "abstract"],
                },
                {
                    "anchor": "Fig. 2c",
                    "observation": "Visual evidence suggests a possible morphology change.",
                    "comparator": "condition A versus condition B",
                    "direction": "unclear",
                    "confidence_source": "vlm_only",
                    "evidence_role": "boundary",
                    "must_write_detail": "describe as measured or compared, not as a signed effect",
                    "can_compress": "panel setup",
                    "cannot_claim": "definite increase, rescue, prevention or no-effect",
                    "downstream_section_use": ["results"],
                },
            ],
            "story_use_rules": [
                "Story plans may order and weight evidence but must not replace this ledger.",
            ],
        }

        gate = evidence_claim_ledger_gate(ledger)

        self.assertEqual(gate["status"], "passed")
        self.assertEqual(gate["blocking_issues"], [])

    def test_evidence_claim_ledger_gate_blocks_vlm_only_definitive_direction(self):
        from nature_orchestrator.evidence_ledger import evidence_claim_ledger_gate

        ledger = {
            "schema_version": "nature_orchestrator.evidence_claim_ledger.v1",
            "evidence_items": [
                {
                    "anchor": "Fig. 3d",
                    "observation": "VLM-only panel reading was used for a perturbation endpoint.",
                    "comparator": "perturbation versus control",
                    "direction": "prevented",
                    "confidence_source": "vlm_only",
                    "evidence_role": "primary_claim",
                    "must_write_detail": "write a prevented decrease",
                    "can_compress": "",
                    "cannot_claim": "",
                    "downstream_section_use": ["results", "discussion"],
                }
            ],
            "story_use_rules": [],
        }

        gate = evidence_claim_ledger_gate(ledger)

        self.assertEqual(gate["status"], "failed")
        self.assertTrue(
            any("vlm_only" in issue and "definitive direction" in issue for issue in gate["blocking_issues"]),
            gate["blocking_issues"],
        )

    def test_final_text_quote_validation_recurses_through_review_issues(self):
        from nature_orchestrator.review_validation import final_text_quote_issues

        final_text = (
            "The treatment reduced the measured readout versus control. "
            "A separate validation experiment bounded the interpretation."
        )
        review = {
            "status": "revise",
            "blocking_issues": [
                {
                    "issue_type": "fact_conflict",
                    "final_text_quote": "The treatment reduced the measured readout versus control",
                    "suggested_repair": "keep the comparator explicit",
                },
                {
                    "issue_type": "unsupported_claim",
                    "final_text_quote": "This exact sentence is not in the manuscript",
                    "suggested_repair": "remove the unsupported claim",
                },
            ],
            "reader_experience_audit": {
                "issues": [
                    {
                        "final_text_quote": "A separate validation experiment bounded the interpretation",
                        "reader_problem": "pass",
                    }
                ]
            },
        }

        issues = final_text_quote_issues(review, final_text, label="final manuscript")

        self.assertEqual(len(issues), 1)
        self.assertIn("This exact sentence is not in the manuscript", issues[0])

    def test_full_paper_mock_evidence_claim_ledger_is_valid_and_general(self):
        from scripts import run_full_paper_generation as full_paper
        from nature_orchestrator.evidence_ledger import evidence_claim_ledger_gate

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_yaml(
                run_dir / "paper" / "context" / "evidence_pack.yaml",
                {
                    "schema_version": "naturebench.evidence_pack.figure_grounded.v1",
                    "figure_evidence": [
                        {
                            "id": "figure-1",
                            "caption_text": "Fig. 1 | A measured response is compared across conditions.",
                            "method_snippets": [{"text": "Assay details define the measured readout."}],
                            "role_hints": [
                                {"section": "abstract_intro", "text": "This figure motivates the study entry."}
                            ],
                        }
                    ],
                },
            )
            (run_dir / "paper" / "context" / "vlm_figure_evidence.md").write_text(
                "Visual model note: possible panel-level morphology differences.",
                encoding="utf-8",
            )

            ledger = full_paper.build_mock_evidence_claim_ledger(run_dir, field="general_science")
            gate = evidence_claim_ledger_gate(ledger)

            self.assertEqual(gate["status"], "passed", gate["blocking_issues"])
            self.assertEqual(ledger["schema_version"], "nature_orchestrator.evidence_claim_ledger.v1")
            self.assertTrue(ledger["evidence_items"])
            self.assertNotIn("s41586", yaml.safe_dump(ledger))
            self.assertIn("results", ledger["evidence_items"][0]["downstream_section_use"])

    def test_full_paper_attaches_evidence_claim_ledger_to_section_run(self):
        from scripts import run_full_paper_generation as full_paper

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            full_run = tmp_path / "full"
            section_run = tmp_path / "section"
            write_yaml(
                full_run / "paper" / "story" / "paper_story_contract.yaml",
                {"schema_version": "nature_orchestrator.paper_story_contract.v2"},
            )
            write_yaml(
                full_run / "paper" / "evidence" / "evidence_claim_ledger.yaml",
                {
                    "schema_version": "nature_orchestrator.evidence_claim_ledger.v1",
                    "evidence_items": [],
                },
            )

            full_paper.attach_paper_context_artifacts(section_run, full_run)

            self.assertTrue((section_run / "paper" / "story" / "paper_story_contract.yaml").exists())
            self.assertTrue((section_run / "paper" / "evidence" / "evidence_claim_ledger.yaml").exists())

    def test_cross_repair_round_budget_defaults_to_section_refiner_budget(self):
        from scripts import run_full_paper_generation as full_paper

        args = Namespace(max_refiner_rounds=3, max_cross_repair_rounds=None)

        self.assertEqual(full_paper.effective_cross_repair_rounds(args), 3)

    def test_cross_repair_round_budget_can_be_set_independently(self):
        from scripts import run_full_paper_generation as full_paper

        args = Namespace(max_refiner_rounds=2, max_cross_repair_rounds=5)

        self.assertEqual(full_paper.effective_cross_repair_rounds(args), 5)

    def test_section_role_allowed_files_include_optional_evidence_claim_ledger(self):
        from scripts import run_abstract_intro_batch, run_discussion_batch, run_results_batch

        expected = "paper/evidence/evidence_claim_ledger.yaml"

        self.assertIn(expected, run_results_batch.results_role_allowed("writer"))
        self.assertIn(expected, run_results_batch.results_role_allowed("reviewer"))
        self.assertIn(expected, run_discussion_batch.discussion_role_allowed("writer"))
        self.assertIn(expected, run_discussion_batch.discussion_role_allowed("reviewer"))
        self.assertIn(expected, run_abstract_intro_batch.abstract_intro_role_allowed("writer"))
        self.assertIn(expected, run_abstract_intro_batch.abstract_intro_role_allowed("reviewer"))

    def test_section_reviewer_gates_reject_invented_final_text_quotes(self):
        from scripts import run_abstract_intro_batch, run_discussion_batch, run_results_batch

        results_review = {
            "status": "revise",
            "accepted_by_reviewers": False,
            "blocking_issues": [
                {"issue": "invented quote", "final_text_quote": "not present in results"}
            ],
            "required_revisions": ["repair quote"],
            "must_mention_anchor_recall": {},
            "missing_recoverable_anchors": [],
            "direction_comparator_errors": [],
            "over_conservatism": [],
            "unrecoverable_detail_risk": "low",
        }
        discussion_review = {
            **results_review,
            "discussion_synthesis_audit": {},
            "boundary_limitation_audit": {},
            "implication_calibration_audit": {},
        }
        abstract_intro_review = {
            "status": "revise",
            "accepted_by_reviewers": False,
            "blocking_issues": [
                {"issue": "invented quote", "final_text_quote": "not present in abstract intro"}
            ],
            "required_revisions": ["repair quote"],
            "abstract_specificity_score": 4,
            "intro_gap_ladder_score": 4,
            "evidence_disclosure_score": 4,
            "story_novelty_score": 4,
            "claim_safety_score": 4,
            "nature_style_score": 4,
        }

        self.assertEqual(
            run_results_batch.reviewer_acceptance_gate(
                results_review,
                final_text="The Results text contains a real sentence.",
            )["status"],
            "failed",
        )
        self.assertEqual(
            run_discussion_batch.reviewer_acceptance_gate(
                discussion_review,
                final_text="The Discussion text contains a real sentence.",
            )["status"],
            "failed",
        )
        self.assertEqual(
            run_abstract_intro_batch.reviewer_acceptance_gate(
                abstract_intro_review,
                final_text="The Abstract and Introduction contain a real sentence.",
            )["status"],
            "failed",
        )

    def test_full_paper_final_anchor_gate_catches_polisher_numeric_anchor_loss(self):
        from scripts import run_full_paper_generation as full_paper

        review = {
            "section": "discussion",
            "must_mention_anchor_recall": {
                "individual_advantage": (
                    "Recalled: '98.70% higher annual citations', "
                    "'3.02 times more papers' and '4.84 times more citations'."
                ),
                "downstream": (
                    "Recalled: '3.46% expanded paper families', "
                    "'22% less follow-on engagement' and "
                    "'Gini coefficient 0.754 versus 0.690'."
                ),
            },
        }
        final_discussion = (
            "AI papers receive higher annual citations, and AI-adopting researchers "
            "publish more papers and receive more citations. Paper families are more "
            "expanded and follow-on engagement is lower."
        )

        gate = full_paper.final_section_anchor_gate(
            section="discussion",
            review=review,
            final_text=final_discussion,
        )

        self.assertEqual(gate["status"], "failed")
        self.assertIn("98.70%", gate["missing_numeric_anchors"])
        self.assertIn("3.02 times", gate["missing_numeric_anchors"])
        self.assertIn("0.754", gate["missing_numeric_anchors"])

    def test_full_paper_final_anchor_gate_accepts_preserved_numeric_anchors(self):
        from scripts import run_full_paper_generation as full_paper

        review = {
            "section": "discussion",
            "must_mention_anchor_recall": {
                "individual_advantage": (
                    "Recalled: '98.70% higher annual citations', "
                    "'3.02 times more papers' and '4.84 times more citations'."
                ),
                "downstream": (
                    "Recalled: '3.46% expanded paper families', "
                    "'22% less follow-on engagement' and "
                    "'Gini coefficient 0.754 versus 0.690'."
                ),
            },
        }
        final_discussion = (
            "AI papers receive 98.70\\% higher annual citations, and AI-adopting "
            "researchers publish 3.02 times more papers and receive 4.84 times "
            "more citations. Paper families are 3.46\\% more expanded, follow-on "
            "engagement is 22\\% lower, and citation concentration is higher "
            "(Gini coefficient 0.754 versus 0.690)."
        )

        gate = full_paper.final_section_anchor_gate(
            section="discussion",
            review=review,
            final_text=final_discussion,
        )

        self.assertEqual(gate["status"], "passed", gate["missing_numeric_anchors"])

    def test_full_paper_final_anchor_gate_accepts_multiplier_unit_equivalence(self):
        from scripts import run_full_paper_generation as full_paper

        review = {
            "section": "results",
            "must_mention_anchor_recall": {
                "visibility": "recalled with 4.84x researcher citations and 3.02x annual papers",
            },
        }
        final_results = (
            "AI-adopting researchers received 4.84 times more citations and "
            "published 3.02 times more papers annually than non-adopters."
        )

        gate = full_paper.final_section_anchor_gate(
            section="results",
            review=review,
            final_text=final_results,
        )

        self.assertEqual(gate["status"], "passed", gate["missing_numeric_anchors"])

    def test_full_paper_final_anchor_gate_accepts_more_exact_metric_values(self):
        from scripts import run_full_paper_generation as full_paper

        review = {
            "section": "results",
            "must_mention_anchor_recall": {
                "classifier": "recalled with BERT classifier, kappa >= 0.93 and F1-score >= 0.85",
            },
        }
        final_results = (
            "Expert validation showed high agreement among annotators "
            "(Fleiss $\\kappa=0.964$) and strong classifier agreement "
            "(F1-score $=0.875$)."
        )

        gate = full_paper.final_section_anchor_gate(
            section="results",
            review=review,
            final_text=final_results,
        )

        self.assertEqual(gate["status"], "passed", gate["missing_numeric_anchors"])

    def test_full_paper_final_anchor_gate_rejects_deleted_metric_thresholds(self):
        from scripts import run_full_paper_generation as full_paper

        review = {
            "section": "results",
            "must_mention_anchor_recall": {
                "classifier": "recalled with BERT classifier, kappa >= 0.93 and F1-score >= 0.85",
            },
        }
        final_results = "Expert validation showed high agreement between annotators and classifier labels."

        gate = full_paper.final_section_anchor_gate(
            section="results",
            review=review,
            final_text=final_results,
        )

        self.assertEqual(gate["status"], "failed")
        self.assertIn("0.93", gate["missing_numeric_anchors"])
        self.assertIn("0.85", gate["missing_numeric_anchors"])

    def test_repair_plan_defers_external_softening_when_results_support_is_recoverable(self):
        from scripts import run_full_paper_generation as full_paper

        ledger = {
            "recoverable_results_repairs": [
                {
                    "anchor": "classifier exact values",
                    "suggested_results_line": "Fleiss kappa=0.964 and F1-score=0.875.",
                }
            ]
        }
        plan = {
            "schema_version": "nature_orchestrator.cross_section_repair_plan.v1",
            "round_index": 1,
            "repair_actions": [
                {
                    "issue_id": "recoverable_results_repair_001",
                    "source": "audits/cross_section_evidence_ledger.yaml:recoverable_results_repairs",
                    "edit_type": "add_results_support",
                    "affected_sections": ["results"],
                    "target_files": ["manuscript/results.tex"],
                    "problem": "Results is missing classifier exact values.",
                    "desired_outcome": "Add classifier exact values to Results.",
                    "evidence_basis": "story contract",
                    "blocking": True,
                },
                {
                    "issue_id": "exact_value_mismatch_001",
                    "source": "audits/cross_section_evidence_ledger.yaml:exact_value_mismatches",
                    "edit_type": "soften_external_claim",
                    "affected_sections": ["abstract", "introduction", "results"],
                    "target_files": ["manuscript/abstract.tex", "manuscript/introduction.tex", "manuscript/results.tex"],
                    "problem": "Classifier exact validation values outside Results.",
                    "desired_outcome": "Remove unsupported exact values outside Results.",
                    "evidence_basis": "exact_value_mismatches",
                    "blocking": True,
                },
                {
                    "issue_id": "missing_support_001",
                    "source": "audits/cross_section_evidence_ledger.yaml:missing_support",
                    "edit_type": "soften_external_claim",
                    "affected_sections": ["abstract", "introduction", "discussion"],
                    "target_files": [
                        "manuscript/abstract.tex",
                        "manuscript/introduction.tex",
                        "manuscript/discussion.tex",
                    ],
                    "problem": "Outside Results exact validation values are not visible in current Results.",
                    "desired_outcome": "Remove unsupported exact values outside Results.",
                    "evidence_basis": "missing_support",
                    "blocking": True,
                },
                {
                    "issue_id": "missing_support_002",
                    "source": "audits/cross_section_evidence_ledger.yaml:missing_support",
                    "edit_type": "remove_unsupported_claim",
                    "affected_sections": ["discussion"],
                    "target_files": ["manuscript/discussion.tex"],
                    "problem": "Discussion adds an unsupported mechanism.",
                    "desired_outcome": "Remove unsupported discussion-only mechanism.",
                    "evidence_basis": "missing_support",
                    "blocking": True,
                },
            ],
            "unresolved_or_deferred": [],
        }

        sanitized = full_paper.sanitize_repair_plan_for_recoverable_results(plan, ledger)

        action_ids = [action["issue_id"] for action in sanitized["repair_actions"]]
        self.assertEqual(action_ids, ["recoverable_results_repair_001", "missing_support_002"])
        deferred_ids = [item["issue_id"] for item in sanitized["unresolved_or_deferred"]]
        self.assertIn("exact_value_mismatch_001", deferred_ids)
        self.assertIn("missing_support_001", deferred_ids)

    def test_results_evidence_anchor_gate_accepts_descriptor_compressed_counts(self):
        from scripts import run_results_batch

        context_text = "Data are from n = 3 (lesion analysis) and n = 4 (IO analysis) rats."
        manifest = run_results_batch.build_results_evidence_manifest(context_text)
        generated = "Representative DBiT-seq readouts used n = 3 rats and n = 4 rats."

        gate = run_results_batch.evidence_anchor_gate(generated, manifest, context_text)

        self.assertEqual(gate["status"], "passed", gate["unsupported_numeric_anchors"])

    def test_results_evidence_anchor_gate_accepts_metric_decimal_with_validation_context(self):
        from scripts import run_results_batch

        context_text = (
            "Accuracy evaluation by human experts reported strong validation against "
            "expert-labelled data, with an F1-score ≥0.85."
        )
        manifest = run_results_batch.build_results_evidence_manifest(context_text)
        generated = "The model achieved an F1-score of at least 0.85 against expert-labelled papers."

        gate = run_results_batch.evidence_anchor_gate(generated, manifest, context_text)

        self.assertEqual(gate["status"], "passed", gate["unsupported_numeric_anchors"])

    def test_results_evidence_anchor_gate_rejects_metric_decimal_without_context_support(self):
        from scripts import run_results_batch

        context_text = "Accuracy evaluation by human experts reported strong validation."
        manifest = run_results_batch.build_results_evidence_manifest(context_text)
        generated = "The model achieved an F1-score of at least 0.85 against expert-labelled papers."

        gate = run_results_batch.evidence_anchor_gate(generated, manifest, context_text)

        self.assertEqual(gate["status"], "failed")
        self.assertIn("0.85 against expert-labelled papers", gate["unsupported_numeric_anchors"])

    def test_api_chat_completion_retries_transient_http_error(self):
        from nature_orchestrator import agents

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices": [{"message": {"content": "ok"}}]}'

        transient = urllib.error.HTTPError(
            "https://api.example.test/chat/completions",
            503,
            "Service Unavailable",
            {"Retry-After": "0"},
            None,
        )
        config = agents.ApiConfig(
            api_key="test-key",
            base_url="https://api.example.test",
            model="test-model",
            timeout=30,
            max_tokens=100,
        )

        with patch("nature_orchestrator.agents.urllib.request.urlopen", side_effect=[transient, FakeResponse()]) as urlopen:
            with patch("nature_orchestrator.agents.time.sleep") as sleep:
                result = agents._post_chat_completion(config, {"messages": []})

        self.assertEqual(result["choices"][0]["message"]["content"], "ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_api_retry_sleep_uses_retry_after_with_cap(self):
        from nature_orchestrator import agents

        exc = urllib.error.HTTPError(
            "https://api.example.test/chat/completions",
            503,
            "Service Unavailable",
            {"Retry-After": "90"},
            None,
        )

        self.assertEqual(agents._api_retry_sleep_seconds(0, exc), 30.0)
        self.assertEqual(agents._api_retry_sleep_seconds(2), 4.0)


if __name__ == "__main__":
    unittest.main()
