"""Scene v2 → HTML → PPTX foundation tests."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import unittest

from tasks.html_constitution import (
    constitution_prompt_block,
    ensure_slide_root,
    validate_slide_html,
    wrap_slide_fragment,
)
from tasks.html_flags import (
    ensure_html_dirs,
    html_sot_enabled,
    write_html_sot_marker,
)
from tasks.html_pipeline import (
    _apply_figure_host_chrome,
    format_slide_page_label,
    materialize_html_slide,
    sanitize_html_presentation_chrome,
)


class FlagAndScaffoldTests(unittest.TestCase):
    def test_html_source_of_truth_is_unconditional(self):
        self.assertTrue(html_sot_enabled())

    def test_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_html_dirs(tmp)
            for key in ("html_output", "preview"):
                self.assertTrue(os.path.isdir(paths[key]))
            self.assertNotIn("ir", paths)
            self.assertNotIn("measure", paths)
            write_html_sot_marker(tmp, enabled=True)
            self.assertTrue(html_sot_enabled(tmp))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "validation", "html_sot.json")))


class EnsureSlideRootTests(unittest.TestCase):
    def test_injects_class_on_bare_section_full_document(self):
        # Executor often omits class="slide" on an otherwise complete HTML doc.
        html = (
            "<!DOCTYPE html><html><body>"
            '<section style="width:1280px;height:720px;position:relative;">'
            "<h1>Cover</h1></section></body></html>"
        )
        out = ensure_slide_root(html)
        self.assertRegex(out, r'class=["\'][^"\']*\bslide\b')
        self.assertIn("<h1>Cover</h1>", out)
        self.assertIn("<html", out.casefold())

    def test_wraps_fragment_without_html(self):
        out = ensure_slide_root("<h1>Hi</h1>")
        self.assertIn('class="slide"', out)
        self.assertIn("<h1>Hi</h1>", out)


class ConstitutionTests(unittest.TestCase):
    def test_rejects_svg(self):
        html = wrap_slide_fragment('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        report = validate_slide_html(html)
        self.assertFalse(report.ok)
        self.assertTrue(any(i.code == "svg_forbidden" for i in report.issues))

    def test_accepts_table_host(self):
        html = wrap_slide_fragment(
            '<h1 style="font-size:32px">Title</h1>'
            '<div data-pptx="table" data-table-id="t1" '
            'style="position:absolute;left:520px;top:160px;width:700px;height:400px;"></div>'
        )
        report = validate_slide_html(html)
        self.assertTrue(report.ok, report.issues)

    def test_accepts_inert_mathml_formula_markup(self):
        html = wrap_slide_fragment(
            '<div data-pptx="formula"><math><mrow><mi>x</mi><mo>=</mo><mn>1</mn></mrow></math></div>'
        )
        report = validate_slide_html(html)
        self.assertTrue(report.ok, report.issues)

    def test_prompt_block_forbids_svg(self):
        block = constitution_prompt_block()
        self.assertIn("<svg>", block)


class PageChromeTests(unittest.TestCase):
    def test_format_slide_page_label(self):
        self.assertEqual("4/12", format_slide_page_label(4, 12))
        self.assertEqual("4", format_slide_page_label(4, None))

    def test_control_chars_become_spaces_not_glue(self):
        from tasks.html_constitution import ensure_slide_root, sanitize_html_control_chars

        raw = f"Insert\x0bhere using\x0bspatial"
        self.assertEqual(sanitize_html_control_chars(f"<p>{raw}</p>"), "<p>Insert here using spatial</p>")
        out = ensure_slide_root(f"<div>{raw}</div>")
        self.assertIn("Insert here", out)
        self.assertIn("using spatial", out)
        self.assertNotIn("Inserthere", out)

    def test_sanitize_strips_variants_and_injects_n_of_n(self):
        html = wrap_slide_fragment(
            '<div style="position:absolute;left:80px;top:500px;width:900px;'
            'height:80px;background:#EEF2F7;">'
            '<span>Why this matters: retrieval helps.</span>'
            '<span class="page-number" style="position:absolute;right:16px;bottom:12px;">04</span>'
            "</div>"
            '<div style="position:absolute;right:40px;bottom:40px;">P02</div>'
            '<footer>03</footer>'
            '<div>P03 / METHOD FRAMING</div>'
        )
        out = sanitize_html_presentation_chrome(html, slide_number=4, total_slides=12)
        self.assertIn('data-sunairum-page-number="1"', out)
        self.assertIn(">4/12<", out)
        self.assertNotIn(">04<", out)
        self.assertNotIn(">P02<", out)
        self.assertNotIn(">03<", out)
        self.assertNotIn("P03 / METHOD", out)
        self.assertIn("Why this matters", out)
        self.assertIn("line-height:18px;height:18px", out)
        # Exactly one injected marker.
        self.assertEqual(1, out.count('data-sunairum-page-number="1"'))

    def test_chrome_sanitizer_preserves_numeric_diagram_badges(self):
        html = wrap_slide_fragment(
            '<div class="loop-node"><div class="node-dot">01</div>'
            '<strong>Destroy</strong></div>'
            '<div class="loop-node"><div class="node-dot">02</div>'
            '<strong>Repair</strong></div>'
        )
        out = sanitize_html_presentation_chrome(html, slide_number=3, total_slides=14)
        self.assertIn('<div class="node-dot">01</div>', out)
        self.assertIn('<div class="node-dot">02</div>', out)

    def test_chrome_sanitizer_preserves_timeline_nodes_with_connector_rail(self):
        html = wrap_slide_fragment(
            '<style>.steps::before{content:"";position:absolute;width:1px}</style>'
            '<div class="steps">'
            '<article class="step"><div class="step-number">01</div><p>Query</p></article>'
            '<article class="step"><div class="step-number">02</div><p>Filter</p></article>'
            '<article class="step"><div class="step-number">03</div><p>Select</p></article>'
            '<article class="step"><div class="step-number">04</div><p>Update</p></article>'
            '</div>'
        )
        out = sanitize_html_presentation_chrome(html, slide_number=7, total_slides=14)
        self.assertEqual(4, out.count('class="step-number"'))
        for ordinal in ("01", "02", "03", "04"):
            self.assertIn(f'>{ordinal}</div>', out)
        self.assertIn('.steps::before', out)

    def test_page_number_lifts_above_bottom_right_callout(self):
        html = wrap_slide_fragment(
            '<div style="position:absolute;left:160px;top:620px;width:1040px;'
            'height:80px;background:#E8EEF5;border-left:6px solid #1A365D;">'
            "<span>IN THIS EQUATION</span>"
            "<p>Increasing equity weights gives workload balance more influence "
            "while preserving a single scalar objective for ALNS acceptance.</p>"
            "</div>"
        )
        out = sanitize_html_presentation_chrome(html, slide_number=3, total_slides=14)
        match = re.search(
            r'data-sunairum-page-number="1"[^>]*\bbottom:([\d.]+)px',
            out,
        )
        self.assertIsNotNone(match)
        bottom = float(match.group(1))
        # Default bottom is 22 (720-698); must lift when callout owns the corner.
        self.assertGreater(bottom, 30.0)
        self.assertIn(">3/14<", out)

    def test_audience_copy_scrubber_removes_split_provenance_cards(self):
        from tasks.html_pipeline import sanitize_html_audience_copy

        html = (
            '<html><head><style>.x{content:"ev-page-03-block-031"}</style></head><body>'
            '<section class="slide"><article class="scene-card"><p>Claim '
            '(evidence=ev-page-03-block-031</p></article>'
            '<article class="scene-card"><p>ev-page-03-block-034)</p></article>'
            '<div data-figure-id="pdf-page-3-picture-1"></div></section></body></html>'
        )
        out, meta = sanitize_html_audience_copy(html)
        self.assertTrue(meta["changed"])
        self.assertIn("Claim", out)
        self.assertNotIn("evidence=", out)
        self.assertEqual(1, out.count("scene-card"))
        self.assertIn('data-figure-id="pdf-page-3-picture-1"', out)
        self.assertIn('content:"ev-page-03-block-031"', out)


class InlineTextBoundaryTests(unittest.TestCase):
    def test_restores_spaces_around_emphasis_without_touching_punctuation(self):
        from tasks.html_pipeline import normalize_inline_text_boundaries

        html = (
            '<html><body><section class="slide"><p>'
            'through<b>n=600</b>; <strong>91.1M</strong>evaluations'
            '</p><p>(<em>kept</em>)</p></section></body></html>'
        )
        out, meta = normalize_inline_text_boundaries(html)
        self.assertEqual(2, meta["boundaries"])
        self.assertIn('through <b>n=600</b>;', out)
        self.assertIn('<strong>91.1M</strong> evaluations', out)
        self.assertIn('(<em>kept</em>)', out)

    def test_restores_space_after_sentence_punctuation_before_emphasis(self):
        from tasks.html_pipeline import normalize_inline_text_boundaries

        out, meta = normalize_inline_text_boundaries(
            '<html><body><p>scanning;<em>feasibility remains exact.</em></p></body></html>'
        )
        self.assertEqual(1, meta["boundaries"])
        self.assertIn('scanning; <em>', out)

class MaterializeTests(unittest.TestCase):
    def test_preview_from_running_asyncio_loop_skips_sync_playwright(self):
        from unittest.mock import patch

        from tasks.html_pipeline import _render_preview_png

        async def render() -> bool:
            with tempfile.TemporaryDirectory() as tmp, patch(
                "tasks.html_pipeline._render_preview_png_once",
                side_effect=AssertionError("sync Playwright must not run in asyncio loop"),
            ), patch(
                "tasks.html_pipeline._render_preview_png_subprocess",
                return_value=True,
            ) as subprocess_preview:
                result = _render_preview_png(
                    wrap_slide_fragment("<h1>Async-safe preview</h1>"),
                    os.path.join(tmp, "slide.png"),
                )
                self.assertEqual(1, subprocess_preview.call_count)
                return result

        self.assertTrue(asyncio.run(render()))

    def test_materialize_without_llm(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            write_html_sot_marker(tmp, enabled=True)
            html = wrap_slide_fragment(
                '<h1 style="position:absolute;left:60px;top:40px;width:600px;'
                'height:56px;font-size:40px;color:#0B3B6F;">Hello</h1>'
                '<span style="position:absolute;right:20px;bottom:20px;">P02</span>'
            )
            scene = {
                "version": "scene_layout_v2",
                "composition": "body",
                "regions": [
                    {"id": "title", "role": "title", "x": 60, "y": 40, "w": 600, "h": 56}
                ],
            }

            def _fake_preview(doc: str, png_path: str) -> bool:
                os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
                with open(png_path, "wb") as handle:
                    handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20_000)
                return True

            with patch(
                "tasks.html_pipeline._render_preview_png", side_effect=_fake_preview
            ), patch(
                "tasks.html_layout_qa.audit_runtime_html_layout",
                return_value={"ok": True, "issues": [], "hard": [], "inspection": {"available": True}},
            ):
                result = materialize_html_slide(
                    storage_dir=tmp,
                    slide={"slide": 2, "title": "Hello", "total_slides": 8},
                    html=html,
                    scene=scene,
                )
            self.assertNotIn("ir_path", result)
            self.assertTrue(os.path.isfile(result["html_path"]))
            self.assertTrue(os.path.isfile(result["preview_path"]))
            with open(result["html_path"], encoding="utf-8") as handle:
                authored = handle.read()
            self.assertIn(">2/8<", authored)
            self.assertNotIn(">P02<", authored)

    def test_materialize_persists_resolved_scene(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            write_html_sot_marker(tmp, enabled=True)
            html = wrap_slide_fragment('<h1 style="margin:0">Hello</h1>')
            scene = {
                "version": "scene_layout_v2",
                "composition": "body",
                "regions": [{"id": "title", "role": "title", "x": 60, "y": 60, "w": 1160, "h": 48}],
            }

            def _fake_preview(doc: str, png_path: str) -> bool:
                os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
                with open(png_path, "wb") as handle:
                    handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20_000)
                return True

            with patch("tasks.html_pipeline._render_preview_png", side_effect=_fake_preview), patch(
                "tasks.html_layout_qa.audit_runtime_html_layout",
                return_value={"ok": True, "issues": [], "hard": [], "inspection": {"available": True}},
            ):
                result = materialize_html_slide(
                    storage_dir=tmp,
                    slide={"slide": 1, "title": "Hello", "total_slides": 1},
                    html=html,
                    scene=scene,
                )

            self.assertTrue(result["scene_path"])
            self.assertTrue(os.path.isfile(result["scene_path"]))
            with open(result["scene_path"], encoding="utf-8") as handle:
                self.assertEqual("scene_layout_v2", __import__("json").load(handle)["version"])

    def test_scene_runtime_geometry_owns_validity_over_static_false_positive(self):
        from unittest.mock import patch
        from PIL import Image

        def fake_preview(_html: str, path: str) -> bool:
            Image.new("RGB", (2560, 1440), "white").save(path)
            return True

        slide = {
            "slide": 1,
            "total_slides": 1,
            "title": "Measured geometry wins",
            "core_message": "Legacy CSS inference remains advisory for Scene output.",
            "cards": [{"title": "Result", "body": "The browser-resolved plate is valid."}],
        }
        scene = {
            "version": "scene_layout_v2",
            "composition": "body",
            "regions": [
                {"id": "title", "role": "title", "x": 60, "y": 60, "w": 1160, "h": 48},
                {"id": "lede", "role": "lede", "x": 60, "y": 122, "w": 1160, "h": 27},
                {"id": "primary", "role": "primary", "x": 60, "y": 177, "w": 1160, "h": 465},
                {"id": "footer", "role": "footer", "x": 60, "y": 660, "w": 1160, "h": 24},
            ],
        }
        from tasks.scene_html_renderer import render_scene_html

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tasks.html_pipeline._render_preview_png", side_effect=fake_preview), patch(
                "tasks.html_layout_qa.audit_runtime_html_layout",
                return_value={"ok": True, "issues": [], "hard": [], "inspection": {"available": True}},
            ):
                result = materialize_html_slide(
                    storage_dir=tmp,
                    slide=slide,
                    html=render_scene_html(slide=slide, scene=scene),
                    scene=scene,
                )
        self.assertTrue(result["ok"])
        self.assertEqual([], result["layout_qa"]["hard"])
        self.assertEqual("scene_runtime_authoritative", result["layout_qa"]["skipped"])


class FigureHostChromeTests(unittest.TestCase):
    def test_apply_chrome_keeps_geometry(self):
        tag = (
            '<div data-pptx="figure" data-figure-id="x" '
            'style="position:absolute;left:640px;top:140px;width:560px;height:480px;">'
        )
        out = _apply_figure_host_chrome(tag)
        self.assertIn("border-radius:16px", out)
        self.assertIn("padding:18px", out)
        self.assertIn("left:640px", out)
        self.assertIn("box-shadow:", out)

    def test_apply_chrome_idempotent(self):
        tag = '<div data-pptx="figure" style="width:560px;height:480px;">'
        once = _apply_figure_host_chrome(tag)
        twice = _apply_figure_host_chrome(once)
        self.assertEqual(once.count("border-radius:16px"), 1)
        self.assertEqual(twice.count("border-radius:16px"), 1)

    def test_normalize_figure_hosts_chromes_filled(self):
        from tasks.html_pipeline import normalize_figure_hosts

        html = (
            '<html><head><style>.slide{width:1280px;height:720px}</style></head><body>'
            '<section class="slide">'
            '<div data-pptx="figure" data-figure-id="pdf-1" '
            'style="position:absolute;left:640px;top:140px;width:560px;height:480px;">'
            '<img data-sunairum-figure-id="pdf-1" style="width:100%;height:100%;" src="x.png"/>'
            "</div></section></body></html>"
        )
        out, meta = normalize_figure_hosts(html)
        self.assertTrue(meta.get("changed"))
        self.assertIn("border-radius:16px", out)
        self.assertIn("box-shadow:", out)
        self.assertIn("border-radius:8px", out)
        self.assertIn("data-sunairum-semantic-host-ownership=1", out)
        self.assertIn("[data-pptx]:not(:empty):not([data-pptx-keep-pseudo])::before", out)
        self.assertEqual(1, out.count("<style"))


if __name__ == "__main__":
    unittest.main()
