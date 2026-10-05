"""Evidence-first section coverage for free-design."""

from __future__ import annotations

import unittest


class DeriveSectionCoverageTests(unittest.TestCase):
    def _bundle(self):
        return {
            "sections": {
                "sections": [
                    {
                        "section_id": "sec-title-001",
                        "title": "Paper Title",
                        "level": 1,
                        "evidence_ids": ["ev-page-01-block-001"],
                        "page_start": 1,
                    },
                    {
                        "section_id": "sec-related-002",
                        "title": "II. RELATED WORK",
                        "level": 1,
                        "evidence_ids": ["ev-page-02-block-001", "ev-page-02-block-002"],
                        "page_start": 2,
                    },
                    {
                        "section_id": "sec-problem-003",
                        "title": "III. PROBLEM FORMULATION",
                        "level": 1,
                        "evidence_ids": ["ev-page-03-block-001", "ev-page-03-block-002"],
                        "page_start": 3,
                    },
                    {
                        "section_id": "sec-refs-004",
                        "title": "REFERENCES",
                        "level": 1,
                        "evidence_ids": ["ev-page-10-block-001"],
                        "page_start": 10,
                    },
                ]
            }
        }

    def test_coverage_follows_evidence_not_document_index(self):
        from tasks.grounded_planner import (
            apply_coverage_plan_section_ids,
            derive_section_coverage_from_slides,
        )

        slides = [
            {
                "slide_id": "slide-1",
                "title": "Paper Title",
                "grounding": {
                    "section_ids": ["sec-title-001"],
                    "evidence_ids": ["ev-page-01-block-001"],
                },
            },
            {
                "slide_id": "slide-2",
                "title": "Problem Formulation",
                "grounding": {
                    "section_ids": ["sec-title-001"],
                    "evidence_ids": ["ev-page-03-block-001", "ev-page-03-block-002"],
                },
            },
            {
                "slide_id": "slide-3",
                "title": "Related Work",
                "grounding": {
                    "section_ids": ["sec-title-001"],
                    "evidence_ids": ["ev-page-02-block-001"],
                },
            },
        ]
        plan = derive_section_coverage_from_slides(slides, self._bundle())
        self.assertEqual(["sec-title-001"], plan[0]["section_ids"])
        self.assertIn("sec-problem-003", plan[1]["section_ids"])
        self.assertIn("sec-related-002", plan[2]["section_ids"])
        stamped = apply_coverage_plan_section_ids({"slides": slides}, plan, replace=True)
        self.assertEqual(
            ["sec-problem-003"],
            stamped["slides"][1]["grounding"]["section_ids"],
        )
        # Title section must not pollute every content slide after replace.
        self.assertNotIn("sec-title-001", stamped["slides"][1]["grounding"]["section_ids"])

    def test_extract_asset_ids_prefer_canonical(self):
        from tasks.strategist_agent import _extract_asset_id

        self.assertEqual(
            "src-table-004",
            _extract_asset_id("TABLE IV (src-table-004)", kind="table"),
        )
        self.assertEqual("", _extract_asset_id("TABLE IV", kind="table"))
        self.assertEqual(
            "pdf-page-3-picture-1",
            _extract_asset_id("Figure 1 pdf-page-3-picture-1", kind="figure"),
        )

    def test_caption_labels_resolve_via_catalog(self):
        from tasks.strategist_agent import resolve_asset_id_from_catalog, resolve_parsed_slide_assets

        tables = [
            {"table_id": "src-table-004", "caption": "TABLE IV. HERO recall@10"},
            {"table_id": "src-table-001", "caption": "Table I Overview"},
        ]
        self.assertEqual(
            "src-table-004",
            resolve_asset_id_from_catalog("TABLE IV", kind="table", catalog=tables),
        )
        slides = resolve_parsed_slide_assets(
            [{"table_id": "", "table_field": "TABLE IV", "figure_id": "", "body": ""}],
            tables=tables,
            figures=[],
        )
        self.assertEqual("src-table-004", slides[0]["table_id"])


if __name__ == "__main__":
    unittest.main()
