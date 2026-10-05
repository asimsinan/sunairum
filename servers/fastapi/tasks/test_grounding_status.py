import json
import tempfile
import unittest
from pathlib import Path

from grounding_status import build_grounding_status


class GroundingStatusTests(unittest.TestCase):
    def _write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _project(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp())
        project = root / "default_user" / "project-1"
        project.mkdir(parents=True)
        (project / "source.pdf").write_bytes(b"pdf")
        self._write(project / "validation" / "source_policy.json", {"grounding_mode": "pdf_strict"})
        self._write(project / "validation" / "run_manifest.json", {"run_id": "run-1", "grounding_mode": "pdf_strict"})
        self._write(project / "sources" / "parser_manifest.json", {
            "parser_requested": "docling", "parser_selected": "docling_ocr",
            "parser_version": "2.118.0", "fallback_used": True,
            "fallback_reason": "quality gate failed", "page_count": 2,
            "tables": {"detected": 1, "structured": 1},
            "figures": {"detected": 1, "provenance_verified": 1},
            "source_pdf_sha256": "pdf-hash",
        })
        self._write(project / "sources" / "evidence_manifest.json", {
            "source_pdf_sha256": "pdf-hash", "evidence_count": 3,
            "table_count": 1, "formula_count": 0, "asset_count": 1,
        })
        self._write(project / "sources" / "source_structure.json", {
            "pages": [{"page": 1, "blocks": [{"evidence_id": "ev-1"}]}],
        })
        self._write(project / "sources" / "source_sections.json", {
            "sections": [
                {"section_id": "sec-1", "title": "Results", "level": 1,
                 "page_start": 1, "page_end": 2, "evidence_ids": ["ev-1", "ev-2"]},
                {"section_id": "sec-2", "title": "Method", "level": 2,
                 "page_start": 2, "page_end": 2, "evidence_ids": ["ev-3"]},
            ],
        })
        self._write(project / "sources" / "source_tables.json", {
            "tables": [{"table_id": "table-1", "evidence_id": "ev-2", "page_start": 2, "page_end": 2}],
        })
        self._write(project / "sources" / "source_formulas.json", {"formulas": []})
        self._write(project / "sources" / "source_assets.json", {
            "assets": [{"asset_id": "asset-1", "page": 2}],
        })
        self._write(project / "validation" / "grounded_plan.json", {
            "run_id": "run-1", "requested_slide_count": 1, "actual_slide_count": 1,
            "coverage_compressed": True,
            "coverage_plan": [{
                "slide_id": "slide-1", "section_ids": ["sec-1"],
                "coverage_mode": "full", "required_evidence_ids": ["ev-1"],
            }],
            "slides": [{
                "slide_id": "slide-1", "title": "Results",
                "grounding": {"section_ids": ["sec-1"], "evidence_ids": ["ev-1"],
                               "claims": [], "metrics": [], "table_bindings": [],
                               "figure_bindings": [{"asset_id": "asset-1", "evidence_ids": ["ev-1"]}],
                               "formula_bindings": []},
            }],
        })
        self._write(project / "validation" / "grounding_qa.json", {"run_id": "run-1", "status": "passed", "issues": []})
        return root, project

    def test_status_exposes_fallback_counts_coverage_and_citations(self):
        root, project = self._project()
        status = build_grounding_status(project, root)
        self.assertTrue(status["available"])
        self.assertEqual("docling_ocr", status["source"]["parser_selected"])
        self.assertTrue(status["source"]["fallback_used"])
        self.assertEqual(1, status["evidence"]["table_count"])
        self.assertTrue(status["plan"]["coverage_compressed"])
        self.assertEqual([1, 2], status["plan"]["slides"][0]["citation_pages"])

    def test_sections_are_reported_before_a_plan_exists(self):
        """Coverage used to appear only once the outline landed.

        The parser knows the sections long before the plan assigns them, so the
        panel can show what was found and fill in assignments as they arrive.
        """
        root, project = self._project()
        (project / "validation" / "grounded_plan.json").unlink()
        status = build_grounding_status(project, root)

        self.assertIsNone(status["plan"])
        titles = [section["title"] for section in status["sections"]]
        self.assertEqual(["Results", "Method"], titles)
        # Nothing is assigned yet, which is what the UI renders as pending.
        self.assertEqual([[], []], [section["slide_numbers"] for section in status["sections"]])
        self.assertEqual([None, None], [section["coverage_mode"] for section in status["sections"]])
        self.assertEqual(0, status["evidence"]["covered_section_count"])
        self.assertEqual(2, status["evidence"]["section_count"])
        # Page span and evidence volume are known at this point too.
        self.assertEqual((1, 2, 2), (
            status["sections"][0]["page_start"],
            status["sections"][0]["page_end"],
            status["sections"][0]["evidence_count"],
        ))
        self.assertEqual(2, status["sections"][1]["level"])

    def test_plan_assignments_are_merged_onto_the_sections(self):
        root, project = self._project()
        status = build_grounding_status(project, root)

        by_id = {section["section_id"]: section for section in status["sections"]}
        self.assertEqual([1], by_id["sec-1"]["slide_numbers"])
        self.assertEqual("full", by_id["sec-1"]["coverage_mode"])
        # sec-2 is in the source but in no slide: the gap the panel exists to show.
        self.assertEqual([], by_id["sec-2"]["slide_numbers"])
        self.assertEqual(1, status["evidence"]["covered_section_count"])

    def test_a_slide_assignment_without_a_coverage_group_still_counts(self):
        """Plans may bind sections per slide rather than through a coverage group.

        L2 assignments still appear on the section row; the covered fraction
        remains L1-only (same contract as validate_section_coverage).
        """
        root, project = self._project()
        plan = json.loads((project / "validation" / "grounded_plan.json").read_text(encoding="utf-8"))
        plan.pop("coverage_plan")
        plan["slides"][0]["grounding"]["section_ids"] = ["sec-2"]
        self._write(project / "validation" / "grounded_plan.json", plan)
        status = build_grounding_status(project, root)

        by_id = {section["section_id"]: section for section in status["sections"]}
        self.assertEqual([1], by_id["sec-2"]["slide_numbers"])
        self.assertEqual(0, status["evidence"]["covered_section_count"])
        self.assertEqual(1, status["evidence"]["required_section_count"])

        # L1 bound only via slide grounding (no coverage_plan) still counts.
        plan["slides"][0]["grounding"]["section_ids"] = ["sec-1"]
        self._write(project / "validation" / "grounded_plan.json", plan)
        status = build_grounding_status(project, root)
        self.assertEqual(1, status["evidence"]["covered_section_count"])

    def test_a_stale_plan_reports_sections_as_unassigned(self):
        """A plan from a previous run must not be shown as current coverage."""
        root, project = self._project()
        self._write(project / "validation" / "run_manifest.json", {"run_id": "run-2", "grounding_mode": "pdf_strict"})
        status = build_grounding_status(project, root)

        self.assertEqual(2, len(status["sections"]))
        self.assertEqual(0, status["evidence"]["covered_section_count"])

    def test_old_run_artifacts_are_not_reported_as_current(self):
        root, project = self._project()
        self._write(project / "validation" / "run_manifest.json", {"run_id": "run-2", "grounding_mode": "pdf_strict"})
        status = build_grounding_status(project, root)
        self.assertIsNone(status["plan"])
        self.assertIn("grounded_plan.json", status["stale_artifacts"])
        self.assertEqual("not-released", status["release"]["status"])


if __name__ == "__main__":
    unittest.main()
