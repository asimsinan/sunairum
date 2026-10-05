"""Strategist IR sanitize + CO-STAR prompt markers."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path


class StrategistIRTests(unittest.TestCase):
    def test_scratch_bookends_preserve_authored_title_and_localize_closing(self):
        from tasks.strategist_agent import ensure_bookend_slides

        slides = [
            {"slide": 1, "role": "title", "title": "Büyük Dil Modellerine Giriş"},
            {"slide": 2, "role": "content", "title": "Temel Kavramlar"},
            {"slide": 3, "role": "closing", "title": "Thank you"},
        ]
        result = ensure_bookend_slides(
            slides,
            content_count=1,
            topic="generate a ppt about introduction to large language models",
            result={"primary_language": "tr"},
            grounding_mode="scratch",
        )
        self.assertEqual("Büyük Dil Modellerine Giriş", result[0]["title"])
        self.assertEqual("Teşekkürler", result[-1]["title"])
        self.assertNotIn("Questions", result[-1]["core_message"])

    def test_scratch_title_fallback_strips_prompt_command(self):
        from tasks.strategist_agent import ensure_bookend_slides

        result = ensure_bookend_slides(
            [{"slide": 2, "role": "content", "title": "Architecture"}],
            content_count=1,
            topic="generate a ppt about introduction to large language models",
            result={"primary_language": "en"},
            grounding_mode="scratch",
        )
        self.assertEqual("Introduction to large language models", result[0]["title"])
        self.assertNotIn("generate a ppt", result[0]["title"].casefold())

    def test_scratch_bookend_rejects_model_echo_of_prompt(self):
        from tasks.strategist_agent import ensure_bookend_slides

        result = ensure_bookend_slides(
            [
                {
                    "slide": 1,
                    "role": "title",
                    "title": "generate a ppt about introduction to large language models",
                },
                {"slide": 2, "role": "content", "title": "Architecture"},
            ],
            content_count=1,
            topic="generate a ppt about introduction to large language models",
            result={"primary_language": "en"},
            grounding_mode="scratch",
        )
        self.assertEqual("Introduction to large language models", result[0]["title"])

    def test_costar_sections_in_system_prompt(self):
        from tasks.strategist_agent import SYSTEM_PROMPT

        for marker in (
            "# CONTEXT",
            "# OBJECTIVE",
            "# STYLE",
            "# TONE",
            "# AUDIENCE",
            "# RESPONSE",
        ):
            self.assertIn(marker, SYSTEM_PROMPT)
        self.assertIn("Do NOT write marketing flourish", SYSTEM_PROMPT)
        self.assertIn("NEVER inside **Content**", SYSTEM_PROMPT)
        self.assertIn("Title plate (P01)", SYSTEM_PROMPT)
        self.assertIn("Closing plate", SYSTEM_PROMPT)
        # Style/Tone must not ask for persuasive marketing density.
        style_tone = SYSTEM_PROMPT.split("# STYLE", 1)[1].split("# AUDIENCE", 1)[0]
        self.assertNotRegex(style_tone, r"(?i)\bbe persuasive\b")
        self.assertIn("executor", style_tone.casefold())
        self.assertIn("intent", style_tone.casefold())
        self.assertNotIn("region_painter", style_tone.casefold())
        self.assertIn("whitespace on plates", style_tone.casefold())

    def test_costar_sections_in_user_brief(self):
        from tasks.strategist_agent import author_design_spec

        captured: dict[str, str] = {}

        def _capture(system: str, user: str) -> str:
            captured["system"] = system
            captured["user"] = user
            return ""

        author_design_spec(
            topic="HERO routing",
            result={
                "content_page_count": 3,
                "grounding_mode": "pdf_strict",
                "audience": "exec",
            },
            grounding_mode="pdf_strict",
            call_text=_capture,
            allow_fallback=True,
            evidence_catalog="ev-1 claim",
            asset_catalog="pdf-page-1-picture-1",
        )
        user = captured.get("user") or ""
        for marker in (
            "# CONTEXT",
            "# OBJECTIVE",
            "# STYLE",
            "# TONE",
            "# AUDIENCE",
            "# RESPONSE",
        ):
            self.assertIn(marker, user)
        self.assertIn("<evidence_catalog>", user)
        self.assertIn("<asset_catalog>", user)
        self.assertNotIn("marketing persuasion", user.split("# STYLE", 1)[0])

    def test_p09_table_id_stripped_from_content(self):
        from tasks.strategist_ir import (
            StrategistDeckIR,
            validate_and_sanitize_deck,
        )

        deck = StrategistDeckIR.from_parsed(
            [
                {
                    "slide": 1,
                    "role": "title",
                    "title": "Paper",
                    "content_blocks": "Cover",
                },
                {
                    "slide": 9,
                    "role": "content",
                    "title": "Results table",
                    "content_blocks": (
                        "- HERO beats baselines on CV\n"
                        "- **Table:** `src-table-002`\n"
                        "- Equity improves under load"
                    ),
                    "table_id": "",
                },
                {
                    "slide": 10,
                    "role": "closing",
                    "title": "Thanks",
                    "core_message": "Questions welcome",
                    "content_blocks": "",
                },
            ]
        )
        out, report = validate_and_sanitize_deck(deck)
        slide9 = next(s for s in out.slides if s.slide == 9)
        self.assertEqual("src-table-002", slide9.table_id)
        self.assertNotIn("src-table-002", slide9.content_blocks)
        self.assertNotIn("Table:", slide9.content_blocks)
        codes = {item["code"] for item in report["sanitizations"]}
        self.assertIn("strip_asset_from_content", codes)

    def test_title_contribution_dump_stripped(self):
        from tasks.strategist_ir import StrategistDeckIR, validate_and_sanitize_deck

        deck = StrategistDeckIR.from_parsed(
            [
                {
                    "slide": 1,
                    "role": "title",
                    "title": "HERO",
                    "authors": "A. Author",
                    "affiliations": "Uni",
                    "content_blocks": (
                        "- HERO: equity-aware repair\n"
                        "- Our contributions\n"
                        "- Key contribution: balanced routes"
                    ),
                },
                {
                    "slide": 2,
                    "role": "closing",
                    "title": "Thanks",
                    "content_blocks": "",
                },
            ]
        )
        out, report = validate_and_sanitize_deck(deck)
        title = out.slides[0]
        self.assertEqual("A. Author", title.authors)
        self.assertNotIn("contribution", title.content_blocks.casefold())
        self.assertNotIn("HERO:", title.content_blocks)
        codes = {item["code"] for item in report["sanitizations"]}
        self.assertIn("strip_title_contribution_dump", codes)

    def test_closing_bullet_dump_collapsed(self):
        from tasks.strategist_ir import StrategistDeckIR, validate_and_sanitize_deck

        deck = StrategistDeckIR.from_parsed(
            [
                {"slide": 1, "role": "title", "title": "T", "content_blocks": ""},
                {
                    "slide": 2,
                    "role": "closing",
                    "title": "Thanks",
                    "core_message": "",
                    "content_blocks": (
                        "- Recap point one\n"
                        "- Recap point two\n"
                        "- Recap point three"
                    ),
                },
            ]
        )
        out, report = validate_and_sanitize_deck(deck)
        closing = out.slides[-1]
        self.assertEqual("", closing.content_blocks)
        self.assertTrue(closing.core_message)
        codes = {item["code"] for item in report["sanitizations"]}
        self.assertIn("collapse_closing_content", codes)

    def test_persist_strategist_ir_artifacts(self):
        from tasks.strategist_ir import sanitize_parsed_slides

        with tempfile.TemporaryDirectory() as tmp:
            sanitize_parsed_slides(
                [
                    {"slide": 1, "role": "title", "title": "T", "content_blocks": ""},
                    {
                        "slide": 2,
                        "role": "content",
                        "title": "C",
                        "content_blocks": "- **Figure:** `pdf-page-3-picture-1`",
                    },
                    {"slide": 3, "role": "closing", "title": "Thanks", "content_blocks": ""},
                ],
                storage_dir=tmp,
            )
            root = Path(tmp) / "validation"
            self.assertTrue((root / "strategist_ir.json").is_file())
            self.assertTrue((root / "strategist_ir_report.json").is_file())


def _mock_gt():
    from unittest import mock

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


class FirstPassGeometryTests(unittest.TestCase):
    """Executor brain owns SVG; no aesthetic harness second author."""


    def test_materialize_stack_uses_executor_brain(self):
        import tempfile
        from pathlib import Path
        from tasks import free_design_pipeline as fdp
        from tasks.authoring_budget import AuthoringBudget

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        slides = [
            {
                "slide": 3,
                "role": "content",
                "title": "Hard feasibility gates",
                "executor_mode": "stack_cards",
                "layout_recipe": "title_stack_cards",
                "cards": [
                    {"title": "A", "body": "Alpha claim about capacity."},
                    {"title": "B", "body": "Beta claim about windows."},
                    {"title": "C", "body": "Gamma claim about once."},
                ],
                "content": {"BODY": "lede"},
            }
        ]
        calls = {"n": 0}

        def _executor(system: str, _user: str) -> str:
            s = system.casefold()
            if "executor for free-design" in s or "author one complete svg" in s:
                calls["n"] += 1
                return (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                    '<text x="60" y="80" font-size="28">Hard feasibility gates</text>'
                    '<text x="60" y="200" font-size="16">Alpha claim about capacity.</text>'
                    '<text x="60" y="320" font-size="16">Beta claim about windows.</text>'
                    '<text x="60" y="440" font-size="16">Gamma claim about once.</text>'
                    "</svg>"
                )
            raise AssertionError(f"unexpected LLM system: {system[:80]!r}")

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
        self.assertTrue(out)
        self.assertGreaterEqual(calls["n"], 1)
        sources = {item["source"] for item in out["authored"]}
        self.assertEqual({"model"}, sources)
        painted = (svg_dir / "slide_03.svg").read_text(encoding="utf-8")
        self.assertNotIn("data-sunairum-infographic", painted)
        self.assertIn("Hard feasibility gates", painted)
        self.assertIn("Alpha claim about capacity.", painted)

    def test_two_column_calls_executor_brain(self):
        import tempfile
        from pathlib import Path
        from tasks import free_design_pipeline as fdp
        from tasks.authoring_budget import AuthoringBudget

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        slides = [
            {
                "slide": 2,
                "role": "content",
                "title": "Why Vehicle Routing Needs Both Scale and Balance",
                "layout_intent": (
                    "Two-column composition; left frames VRPTW, right contrasts "
                    "exhaustive insertion with balanced workload."
                ),
                "executor_mode": "two_column_takeaway",
                "layout_recipe": "title_two_column_takeaway",
                "cards": [
                    {"title": "VRPTW", "body": "Must respect windows."},
                    {"title": "ALNS", "body": "Repair evaluates candidates."},
                ],
                "callout": "Cost alone leaves uneven workloads.",
                "content": {"BODY": "VRPTW must respect windows."},
            }
        ]
        calls = {"n": 0}

        def _executor(system: str, _user: str) -> str:
            s = system.casefold()
            if "executor for free-design" in s or "author one complete svg" in s:
                calls["n"] += 1
                return (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                    '<text x="60" y="80" font-size="28">Why Vehicle Routing</text>'
                    '<text x="60" y="200" font-size="16">VRPTW</text>'
                    '<text x="700" y="200" font-size="16">ALNS</text>'
                    "</svg>"
                )
            raise AssertionError(f"unexpected LLM system: {system[:80]!r}")

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
        self.assertGreaterEqual(calls["n"], 1)
        sources = {item["source"] for item in out["authored"]}
        self.assertEqual({"model"}, sources)




if __name__ == "__main__":
    unittest.main()
