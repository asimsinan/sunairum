"""Densify + painter fill from proj_83kef-like Strategist IR."""

from __future__ import annotations

import re
import unittest


_SLIDE3_BODY = """\
- **Title:** HERO separates retrieval from scoring
- **Core message:** The index determines which insertion positions are examined; the objective determines which feasible position is selected.
- **Layout:** process_steps — centered conceptual split with two large blocks
- **Content:**
  - **Candidate retrieval:** HNSW returns a compact set of promising insertion positions.
  - **Candidate scoring:** Feasible positions are evaluated with distance and, when enabled, equity terms.
  - The same mechanism supports cost-only and equity-guided repair.
- **Visual job:** Make the paper's central design separation immediately legible.
"""


class ContentDensifyTests(unittest.TestCase):
    def test_extract_multiline_content_from_body_md(self):
        from tasks.content_densify import extract_content_bullets_from_body_md

        bullets = extract_content_bullets_from_body_md(_SLIDE3_BODY)
        self.assertGreaterEqual(len(bullets), 3)
        self.assertTrue(any("HNSW" in b for b in bullets))
        self.assertFalse(any("**" in b for b in bullets))

    def test_densify_fills_thin_content_blocks(self):
        from tasks.content_densify import densify_slide_ir

        slide = {
            "role": "content",
            "title": "HERO separates retrieval from scoring",
            "core_message": "The index determines which insertion positions are examined.",
            "content_blocks": "- **Candidate retrieval:** HNSW returns a compact set.",
            "content": {
                "BODY": "- **Candidate retrieval:** HNSW returns a compact set.",
            },
            "body_md": _SLIDE3_BODY,
            "cards": [],
            "steps": [],
        }
        densify_slide_ir(slide)
        body = str(slide["content"]["BODY"])
        self.assertGreaterEqual(len([ln for ln in body.splitlines() if ln.strip()]), 3)
        self.assertNotIn("**", body)


class EnrichDoesNotStealExecutorTests(unittest.TestCase):
    def test_two_column_compare_does_not_invent_painter_cards(self):
        from tasks.content_densify import densify_slide_ir
        from tasks.slide_renderer import resolve_content_owner

        slide = {
            "slide": 2,
            "role": "content",
            "title": "Why repair becomes the bottleneck",
            "layout_intent": (
                "two_column_compare — computational bottleneck on the left "
                "and operational objective on the right"
            ),
            "content_blocks": (
                "- Search burden: O(r n) evaluations\n"
                "- Feasibility burden: capacity checks\n"
                "- Cost limitation: unbalanced workloads\n"
                "- Research gap: equity-aware repair"
            ),
            "content": {
                "BODY": (
                    "- Search burden: O(r n) evaluations\n"
                    "- Feasibility burden: capacity checks\n"
                    "- Cost limitation: unbalanced workloads\n"
                    "- Research gap: equity-aware repair"
                )
            },
            "cards": [],
            "steps": [],
        }
        densify_slide_ir(slide)
        self.assertEqual(slide.get("cards") or [], [])
        self.assertEqual("executor", resolve_content_owner(slide))


class ExecutorBrainContractTests(unittest.TestCase):
    def test_executor_system_authors_svg(self):
        from tasks.free_design_pipeline import EXECUTOR_SYSTEM

        self.assertIn("Author ONE complete SVG", EXECUTOR_SYSTEM)
        self.assertIn("## Hard", EXECUTOR_SYSTEM)
        self.assertIn("## Defaults", EXECUTOR_SYSTEM)
        self.assertNotIn("Infographic DSL", EXECUTOR_SYSTEM)
        self.assertNotIn("Exclusive regions", EXECUTOR_SYSTEM)

    def test_design_reference_allows_freehand(self):
        from tasks import design_reference as dr

        src = open(dr.__file__, encoding="utf-8").read()
        self.assertIn("Author original freehand SVG", src)
        self.assertNotIn("slide_shell + Infographic own", src)
        self.assertNotIn("region_painter owns", src)

    def test_strategist_prompt_executor_ir(self):
        from tasks.strategist_agent import SYSTEM_PROMPT

        self.assertIn("Executor", SYSTEM_PROMPT)
        self.assertIn("process_steps", SYSTEM_PROMPT)
        self.assertIn("Cards:", SYSTEM_PROMPT)
        self.assertNotIn("region_painter", SYSTEM_PROMPT)
        self.assertNotIn("**Infographic template:**", SYSTEM_PROMPT)
        self.assertIn("Never invent AntV", SYSTEM_PROMPT)

    def test_slide_renderer_no_antv_import(self):
        import tasks.slide_renderer as sr

        src = open(sr.__file__, encoding="utf-8").read()
        self.assertNotIn("infographic_bridge", src)
        self.assertNotIn("@antv", src)
        self.assertEqual("executor", sr.resolve_content_owner({"role": "content"}))


if __name__ == "__main__":
    unittest.main()
