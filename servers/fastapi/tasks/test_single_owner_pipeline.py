"""Contract tests: Executor owns content; Intent owns table/formula; no AntV."""

from __future__ import annotations

import unittest
from unittest import mock


def _mock_gt():
    gt = mock.Mock()
    gt.sanitize_flat_structure_metadata.side_effect = lambda s: s
    gt.sanitize_presentation_chrome.side_effect = lambda s, **_kw: s
    gt.sanitize_project_geometry_lengths.side_effect = lambda s: s
    gt.finalize_svg_document.side_effect = lambda s: s
    gt.minimal_slide_svg.return_value = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
        "<text>fallback</text></svg>"
    )
    return gt


class SlideShellTests(unittest.TestCase):
    def test_shell_has_no_title_text(self):
        from tasks.slide_shell import build_slide_shell

        slide = {
            "slide": 1,
            "role": "title",
            "title": "Hello World Deck",
            "layout_recipe": "title_plate",
        }
        svg, layout = build_slide_shell(slide, {"surface": "#FFF"}, slide_number=1, total_slides=10)
        self.assertIn("data-sunairum-content-host", svg)
        self.assertIn("data-sunairum-page-number", svg)
        self.assertNotIn("Hello World Deck", svg)
        self.assertTrue(layout.regions)


class RenderSlideOwnerTests(unittest.TestCase):
    def test_structured_cards_owner_executor(self):
        from tasks.slide_renderer import resolve_content_owner, slide_has_structured_paint_ir

        slide = {
            "slide": 2,
            "role": "content",
            "title": "Routing quality has two dimensions",
            "core_message": "Feasibility and efficiency both matter",
            "layout_recipe": "title_stack_cards",
            "executor_mode": "stack_cards",
            "cards": [
                {"title": "Feasibility", "body": "Serve every customer"},
                {"title": "Efficiency", "body": "Minimize travel distance"},
            ],
            "content": {"BODY": "Feasibility\nEfficiency"},
        }
        # Brain = LLM. Cards/steps are prompt IR, not a painter job.
        self.assertFalse(slide_has_structured_paint_ir(slide))
        self.assertEqual("executor", resolve_content_owner(slide))

    def test_process_steps_owner_executor(self):
        from tasks.slide_renderer import resolve_content_owner

        self.assertEqual(
            "executor",
            resolve_content_owner(
                {
                    "role": "content",
                    "layout_intent": "process_steps — three stages",
                    "layout_recipe": "title_process_steps",
                    "executor_mode": "process_flow",
                    "steps": [
                        {"title": "A", "body": "one"},
                        {"title": "B", "body": "two"},
                        {"title": "C", "body": "three"},
                    ],
                }
            ),
        )

    def test_free_canvas_owner_executor(self):
        from tasks.slide_renderer import resolve_content_owner

        self.assertEqual(
            "executor",
            resolve_content_owner(
                {
                    "role": "content",
                    "title": "Open canvas",
                    "layout_recipe": "title_body_bullets",
                    "executor_mode": "free_canvas",
                    "cards": [],
                    "steps": [],
                }
            ),
        )

    def test_table_owner(self):
        from tasks.slide_renderer import resolve_content_owner

        self.assertEqual(
            "table",
            resolve_content_owner({"table_id": "src-table-001", "role": "content"}),
        )

    def test_formula_owner_injects_into_executor_host(self):
        from tasks.slide_renderer import render_slide, resolve_content_owner

        slide = {
            "slide": 6,
            "role": "content",
            "title": "Equity-Aware Insertion Scoring",
            "core_message": "Positive equity weights favor balanced insertions.",
            "formula": "J(R) = D + beta * CV + gamma * Jain",
            "formula_terms": "beta=equity weight; gamma=Jain weight",
            "formula_gloss": "beta = gamma = 0 is distance-only insertion.",
            "content": {},
        }
        base = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="84" y="80" font-size="28">Equity-Aware Insertion Scoring</text>'
            '<text x="84" y="140" font-size="16">Workload definition</text>'
            '<g id="formula-band" data-sunairum-formula-host="1" '
            'transform="translate(60,160)">'
            '<rect width="1160" height="160" fill="none"/></g>'
            "</svg>"
        )
        self.assertEqual("formula", resolve_content_owner(slide))
        svg, owner, dsl = render_slide(
            slide,
            theme={"primary": "#0B3B6F", "accent": "#E07A2F", "ink": "#0F172A"},
            slide_number=6,
            total_slides=14,
            call_text=None,
            base_svg=base,
        )
        self.assertEqual("formula", owner)
        self.assertIn("Equity-Aware Insertion Scoring", svg)
        self.assertIn("Workload definition", svg)
        self.assertTrue(
            ("beta=equity weight" in svg)
            or ("β = equity weight" in svg)
            or ("β=equity weight" in svg)
            or ("equity weight" in svg.casefold()),
            "expected equity-weight term callout in formula legend",
        )
        self.assertIn("distance-only", svg.casefold())
        self.assertTrue(
            "data-sunairum-formula-host" in svg
            or 'id="formula-band"' in svg
            or "formula" in svg.casefold()
        )

    def test_table_owner_injects_into_executor_host(self):
        from tasks.intent_hosts import TABLE_HOST
        from tasks.slide_renderer import render_slide

        payload = {
            "source_table_id": "src-table-001",
            "columns": [{"text": "n"}, {"text": "Brute"}, {"text": "HNSW"}],
            "rows": [
                [{"text": "200"}, {"text": "8.6M"}, {"text": "2.8M"}],
                [{"text": "400"}, {"text": "33.5M"}, {"text": "23.5M"}],
            ],
        }

        def _resolve(_bundle, tid: str):
            return payload if tid == "src-table-001" else None

        slide = {
            "slide": 9,
            "role": "content",
            "title": "HNSW Reduces Repair Evaluations",
            "core_message": "Reduction is not monotonic with size.",
            "table_id": "src-table-001",
            "content": {},
        }
        tx, ty, tw, th = TABLE_HOST
        base = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="84" y="80" font-size="28">HNSW Reduces Repair Evaluations</text>'
            '<text x="84" y="200" font-size="16">Clustered instances</text>'
            '<text x="84" y="240" font-size="16">Cost ratio</text>'
            f'<g data-sunairum-table-slot="1" data-sunairum-table-id="src-table-001" '
            f'data-pptx-replace-with="table" transform="translate({tx:g},{ty:g})">'
            f'<rect width="{tw:g}" height="{th:g}" fill="none"/></g>'
            "</svg>"
        )
        svg, owner, dsl = render_slide(
            slide,
            theme={"primary": "#0B3B6F", "accent": "#E07A2F", "ink": "#0F172A"},
            slide_number=9,
            total_slides=14,
            call_text=None,
            resolve_table_payload=_resolve,
            base_svg=base,
        )
        self.assertEqual("table", owner)
        self.assertIn("HNSW Reduces Repair Evaluations", svg)
        self.assertIn("Clustered instances", svg)
        self.assertIn("data-sunairum-source-table-id", svg)
        self.assertGreater(tx, 500.0)

    def test_materialize_executor_owns_svg_no_painter_module(self):
        import tempfile
        from pathlib import Path
        import importlib.util

        import tasks.free_design_pipeline as fdp
        from tasks.authoring_budget import AuthoringBudget

        self.assertIsNone(importlib.util.find_spec("tasks.slide_painter"))

        slides = [
            {
                "slide": 1,
                "role": "title",
                "title": "Cover",
                "content": {},
            }
        ]

        def _executor(system: str, _user: str) -> str:
            s = system.casefold()
            if "tablevisualintent" in s or "formulavisualintent" in s:
                return "{}"
            if "executor for free-design" in s or "author one complete svg" in s:
                return (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                    '<text x="80" y="120" font-size="36">Cover</text>'
                    '<text data-sunairum-page-number="1" x="1220" y="698">1</text>'
                    "</svg>"
                )
            raise AssertionError(f"unexpected LLM system: {system[:80]}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            out = fdp.materialize_free_design_slides(
                slides=slides,
                design_spec_md="",
                spec_lock_md="",
                storage_dir=str(root),
                svg_dir=str(svg_dir),
                color_palette={"primary": "#0B3B6F", "body_text": "#0F172A"},
                budget=AuthoringBudget(limit=8),
                call_text=_executor,
                gt=_mock_gt(),
            )
            self.assertFalse(out.get("cancelled"))
            svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
            self.assertIn("data-sunairum-page-number", svg)
            self.assertEqual("model", out["authored"][0]["source"])


class TableIntentStackTests(unittest.TestCase):
    def test_analyzer_and_render_spec(self):
        from tasks.table_analyzer import analyze_table, template_insight
        from tasks.table_render_spec import build_table_render_spec
        from tasks.table_renderer import render_table_spec_svg
        from tasks.table_visual_intent import default_table_intent, validate_table_intent

        table = {
            "table_id": "src-table-001",
            "caption": "Results",
            "headers": [{"text": "Method"}, {"text": "Cost"}, {"text": "Jain"}],
            "rows": [
                [{"text": "A"}, {"text": "100"}, {"text": "0.9"}],
                [{"text": "B"}, {"text": "80"}, {"text": "0.8"}],
            ],
        }
        analysis = analyze_table(table)
        self.assertIn("Cost", analysis["numeric_columns"])
        intent = default_table_intent(analysis, "src-table-001")
        intent = validate_table_intent(intent, analysis, "src-table-001")
        insight = template_insight(analysis, intent)
        self.assertIn("B", insight)  # lowest Cost
        self.assertIn("80", insight)
        spec = build_table_render_spec(
            analysis, intent, aabb=(100, 200, 1000, 400), theme={"primary": "#0B3B6F"}
        )
        self.assertEqual("src-table-001", spec["table_id"])
        frag = render_table_spec_svg(spec)
        self.assertIn("data-sunairum-source-table-id", frag)
        self.assertIn("<metadata", frag)
        self.assertIn('"columns"', frag)
        self.assertIn("80", frag)
        self.assertIn("100", frag)
        from tasks.generate_task import strip_unfilled_native_table_carriers

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            f"{frag}</svg>"
        )
        after = strip_unfilled_native_table_carriers(svg)
        self.assertIn("data-sunairum-source-table-id", after)
        self.assertIn("Method", after)
        self.assertIn("80", after)

    def test_intent_cannot_invent_columns(self):
        from tasks.table_analyzer import analyze_table
        from tasks.table_visual_intent import validate_table_intent

        table = {
            "table_id": "src-table-001",
            "headers": [{"text": "Method"}, {"text": "Cost"}],
            "rows": [[{"text": "A"}, {"text": "100"}]],
        }
        analysis = analyze_table(table)
        bad = {
            "table_id": "src-table-001",
            "content": {"columns": ["Invented", "Cost"], "show_all_columns": False},
            "emphasis": {"rules": [{"column": "Invented", "direction": "min"}]},
        }
        fixed = validate_table_intent(bad, analysis, "src-table-001")
        cols = fixed.get("content", {}).get("columns") or []
        self.assertNotIn("Invented", cols)
        for rule in fixed.get("emphasis", {}).get("rules") or []:
            self.assertNotEqual("Invented", rule.get("column"))


if __name__ == "__main__":
    unittest.main()
