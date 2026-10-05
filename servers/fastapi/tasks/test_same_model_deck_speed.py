"""Same-model deck speed: dialect, brain-worthy QA, cache fail-open, dedupe."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class SvgDialectTests(unittest.TestCase):
    def test_expand_data_font_and_missing_family(self):
        from tasks.svg_dialect import expand_font_dialect

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="60" y="76" font-size="36" font-weight="700" '
            'data-sunairum-font="title">Title</text>'
            '<text x="60" y="200" font-size="16">Body</text>'
            "</svg>"
        )
        out = expand_font_dialect(svg, lock_title="Georgia", lock_body="Arial")
        self.assertIn('font-family="Georgia, serif"', out)
        self.assertIn('font-family="Arial, sans-serif"', out)
        self.assertNotIn("data-sunairum-font", out)

    def test_rewrite_drift_faces_only(self):
        from tasks.svg_dialect import rewrite_font_drift

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="60" y="76" font-size="36" font-weight="700" '
            'font-family="Inter, sans-serif">Title</text>'
            '<text x="60" y="200" font-size="16" '
            'font-family="Georgia, serif">Keep</text>'
            "</svg>"
        )
        out = rewrite_font_drift(svg, lock_title="Georgia", lock_body="Arial")
        self.assertIn('font-family="Georgia, serif"', out)
        # Titleish Inter → Georgia; body Georgia already allowed stays.
        self.assertEqual(2, out.count("Georgia"))


class BrainWorthyTests(unittest.TestCase):
    def test_allowlist(self):
        from tasks.free_design_pipeline import (
            _brain_worthy_issues,
            _is_brain_worthy_issue,
        )

        self.assertTrue(_is_brain_worthy_issue("missing_svg: no document"))
        self.assertTrue(_is_brain_worthy_issue("export_gate: />xt debris"))
        self.assertFalse(_is_brain_worthy_issue("font_drift: use lock faces"))
        self.assertFalse(_is_brain_worthy_issue("text_overlaps:3: collide"))
        self.assertEqual(
            ["missing_svg: x"],
            _brain_worthy_issues(["font_drift: a", "missing_svg: x", "text_overlaps:1"]),
        )


class PromptCacheTests(unittest.TestCase):
    def test_openrouter_extra_body_and_fail_open(self):
        import llm_client as lc

        lc._prompt_cache_disabled = False
        settings = mock.Mock(
            provider="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test",
            model_name="test/model",
        )
        captured: dict = {}

        class _Resp:
            class _Usage:
                prompt_tokens_details = mock.Mock(cached_tokens=12)

            usage = _Usage()
            choices = [mock.Mock(message=mock.Mock(content="ok"))]

        def _create(**kwargs):
            captured.update(kwargs)
            return _Resp()

        client = mock.Mock()
        client.chat.completions.create = _create
        with mock.patch.object(lc, "get_active_settings", return_value=settings):
            with mock.patch.object(lc, "_openai_client", return_value=client):
                with lc.llm_session_context("run-abc"):
                    out = lc.call_llm_text("sys", "user")
        self.assertEqual("ok", out)
        self.assertIn("extra_body", captured)
        self.assertEqual(
            {"type": "ephemeral"}, captured["extra_body"].get("cache_control")
        )
        self.assertEqual("run-abc", captured["extra_body"].get("session_id"))
        self.assertTrue(lc.last_prompt_cache_hit())

    def test_non_openrouter_skips_cache(self):
        import llm_client as lc

        lc._prompt_cache_disabled = False
        settings = mock.Mock(
            provider="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model_name="gpt-4o",
        )
        captured: dict = {}

        class _Resp:
            usage = None
            choices = [mock.Mock(message=mock.Mock(content="ok"))]

        def _create(**kwargs):
            captured.update(kwargs)
            return _Resp()

        client = mock.Mock()
        client.chat.completions.create = _create
        with mock.patch.object(lc, "get_active_settings", return_value=settings):
            with mock.patch.object(lc, "_openai_client", return_value=client):
                lc.call_llm_text("sys", "user")
        self.assertNotIn("extra_body", captured)


class DedupePlanTests(unittest.TestCase):
    def test_precomputed_plan_skips_planner(self):
        from tasks.free_design_pipeline import author_free_slide_svg

        calls: list[str] = []

        def _call(system: str, prompt: str) -> str:
            calls.append(system[:60])
            return (
                '<svg viewBox="0 0 1280 720">'
                '<text x="60" y="76" font-size="36">Hello</text></svg>'
            )

        class _GT:
            def sanitize_flat_structure_metadata(self, s: str) -> str:
                return s

            def finalize_svg_document(self, s: str) -> str:
                return s

            def sanitize_presentation_chrome(self, s: str, **_kw) -> str:
                return s

        slide = {
            "slide": 1,
            "role": "content",
            "title": "Hello",
            "content": {"BODY": "Body"},
            "_layout_plan": {
                "job": "pre",
                "composition": "x",
                "regions": [
                    {"id": "t", "role": "title", "x": 60, "y": 60, "w": 1000, "h": 60}
                ],
            },
            "_craft_block": "",
            "_art_direction_block": "",
            "_executor_paints": 0,
        }
        svg, source = author_free_slide_svg(
            slide=slide,
            design_spec_md="",
            spec_lock_md="Primary #000",
            prior_summary="",
            color_palette={"body_text": "#000", "_heading_family": "Georgia"},
            call_text=_call,
            gt=_GT(),
            allow_fallback=False,
        )
        self.assertIn("<svg", svg)
        self.assertEqual("model", source)
        self.assertFalse(any("Layout Planner" in c for c in calls))


class ResumeSkipTests(unittest.TestCase):
    def test_keep_existing_skips_call_text(self):
        from tasks.authoring_budget import AuthoringBudget
        from tasks.free_design_pipeline import materialize_free_design_slides

        calls: list[str] = []

        def _call(system: str, prompt: str) -> str:
            calls.append("hit")
            raise AssertionError("should not call LLM for kept slide")

        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp) / "svg_output"
            svg_dir.mkdir()
            (svg_dir / "slide_01.svg").write_text(
                '<svg viewBox="0 0 1280 720"><text x="60" y="76">Kept</text></svg>',
                encoding="utf-8",
            )
            slides = [
                {
                    "slide": 1,
                    "role": "content",
                    "title": "Kept",
                    "content": {"BODY": "x"},
                    "total_slides": 1,
                }
            ]
            result = materialize_free_design_slides(
                slides=slides,
                design_spec_md="",
                spec_lock_md="lock",
                storage_dir=tmp,
                svg_dir=str(svg_dir),
                color_palette={"background": "#fff"},
                budget=AuthoringBudget(limit=8),
                call_text=_call,
                gt=None,
                keep_existing=True,
            )
        self.assertEqual([], calls)
        self.assertEqual([], result.get("authored") or [])


class ParallelContextTests(unittest.TestCase):
    def test_no_shared_context_run_in_source(self):
        src = Path(__file__).with_name("free_design_pipeline.py").read_text(
            encoding="utf-8"
        )
        # Regression: shared Context.run across Art‖Plan raises "already entered".
        self.assertNotIn("pool.submit(_ctx.run", src)
        self.assertNotIn("copy_context()", src)


class FontDriftPaintCountTests(unittest.TestCase):
    def test_font_drift_not_brain_worthy(self):
        from tasks.free_design_pipeline import _brain_worthy_issues

        issues = ["font_drift: use lock faces (Georgia/Arial)", "text_overlaps:1"]
        self.assertEqual([], _brain_worthy_issues(issues))


if __name__ == "__main__":
    unittest.main()
