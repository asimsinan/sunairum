"""Unit tests for closed-loop PPTX visual fidelity helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image


class SsimHelpersTests(unittest.TestCase):
    def test_identical_images_high_ssim(self):
        from tasks.pptx_visual_verify import mean_absolute_error, ssim_grayscale

        a = np.zeros((64, 64, 3), dtype=np.uint8)
        a[:, :] = (40, 80, 120)
        self.assertGreaterEqual(ssim_grayscale(a, a), 0.999)
        self.assertEqual(mean_absolute_error(a, a), 0.0)

    def test_drift_lowers_ssim(self):
        from tasks.pptx_visual_verify import ssim_grayscale

        a = np.zeros((64, 64), dtype=np.uint8)
        a[:, :] = 100
        b = a.copy()
        b[10:50, 10:50] = 200
        self.assertLess(ssim_grayscale(a, b), 0.95)

    def test_compare_slide_pair_flags_drift(self):
        from tasks.pptx_visual_verify import compare_slide_pair

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = root / "ref.png"
            bad = root / "bad.png"
            Image.new("RGB", (128, 72), (255, 255, 255)).save(ref)
            Image.new("RGB", (128, 72), (0, 0, 0)).save(bad)
            finding = compare_slide_pair(
                ref, bad, ssim_floor=0.92, mae_ceil=18.0
            )
            self.assertFalse(finding["ok"])
            self.assertLess(finding["ssim"], 0.5)

    def test_attribute_failures_ranks_regions(self):
        from tasks.pptx_visual_verify import attribute_failures

        ref = np.zeros((720, 1280, 3), dtype=np.uint8)
        cand = ref.copy()
        # Drift in the right half of the slide (pptx inches 5..10).
        cand[:, 640:] = 255
        shapes = [
            {
                "slideIndex": 0,
                "elementId": "left",
                "type": "text",
                "pptx": {"x": 0.5, "y": 1.0, "w": 2.0, "h": 1.0},
            },
            {
                "slideIndex": 0,
                "elementId": "right",
                "type": "text",
                "pptx": {"x": 6.0, "y": 1.0, "w": 2.0, "h": 1.0},
            },
        ]
        ranked = attribute_failures(ref, cand, shapes, 0, top_k=2)
        self.assertEqual(ranked[0]["elementId"], "right")
        self.assertGreater(ranked[0]["mae"], ranked[1]["mae"])

    def test_semantic_geometry_flags_named_shape_drift(self):
        from tasks.pptx_visual_verify import semantic_shape_geometry_failures

        shapes = [
            {
                "slideIndex": 0,
                "elementId": "text-title",
                "type": "text",
                "html": {"x": 60, "y": 60, "w": 600, "h": 50},
                "pptx": {"x": 1.0, "y": 60 / 128, "w": 600 / 128, "h": 50 / 128},
            }
        ]
        failures = semantic_shape_geometry_failures(shapes, 0, tolerance_px=4)
        self.assertEqual("text-title", failures[0]["elementId"])

    def test_scene_requires_named_shape_for_every_region(self):
        from tasks.pptx_visual_verify import semantic_scene_missing_ids

        scene = {
            "regions": [
                {"id": "title", "role": "title", "x": 60, "y": 60, "w": 1160, "h": 56},
                {"id": "primary", "role": "primary", "x": 60, "y": 160, "w": 1160, "h": 500},
                {"id": "footer", "role": "footer"},
            ]
        }
        shapes = [{"slideIndex": 0, "elementId": "text-title", "type": "text", "html": {"x": 60, "y": 60, "w": 600, "h": 50}}]
        self.assertEqual(["scene-primary:drawable_content"], semantic_scene_missing_ids(scene, shapes, 0))

    def test_scene_accepts_native_math_as_formula_drawable(self):
        from tasks.pptx_visual_verify import semantic_scene_missing_ids

        scene = {
            "regions": [
                {"id": "formula", "role": "formula", "x": 100, "y": 160, "w": 600, "h": 120}
            ]
        }
        shapes = [
            {
                "slideIndex": 0,
                "elementId": "scene-formula__native-formula",
                "type": "math",
                "html": {"x": 100, "y": 160, "w": 600, "h": 120},
            }
        ]
        self.assertEqual([], semantic_scene_missing_ids(scene, shapes, 0))

    def test_semantic_geometry_rejects_excessive_text_shrink(self):
        from tasks.pptx_visual_verify import semantic_shape_geometry_failures

        shapes = [
            {
                "slideIndex": 0,
                "elementId": "text-lede",
                "type": "text",
                "html": {"x": 60, "y": 140, "w": 500, "h": 42},
                "pptx": {
                    "x": 60 / 128,
                    "y": 140 / 128,
                    "w": 500 / 128,
                    "h": 42 / 128,
                },
                "htmlLineCount": 2,
                "fontScale": 0.89,
            }
        ]
        failures = semantic_shape_geometry_failures(shapes, 0)
        self.assertEqual("text_font_scale", failures[0]["type"])
        self.assertEqual(2, failures[0]["html_line_count"])

    def test_contained_image_uses_painted_geometry_contract(self):
        from tasks.pptx_visual_verify import semantic_shape_geometry_failures

        image = {
            "slideIndex": 0,
            "elementId": "figure-image",
            "type": "image",
            "objectFit": "contain",
            "html": {"x": 100, "y": 100, "w": 400, "h": 300},
            # Same center, full width, letterboxed vertically.
            "pptx": {"x": 100 / 128, "y": 150 / 128, "w": 400 / 128, "h": 200 / 128},
        }
        self.assertEqual([], semantic_shape_geometry_failures([image], 0))

    def test_anonymous_fragment_is_rejected(self):
        from tasks.pptx_visual_verify import semantic_shape_geometry_failures

        fragment = {
            "slideIndex": 0,
            "elementId": None,
            "type": "text",
            "html": {"x": 60, "y": 180, "w": 500, "h": 42},
            "pptx": {"x": 60 / 128, "y": 180 / 128, "w": 500 / 128, "h": 6 / 128},
            "fontScale": 1,
        }
        failures = semantic_shape_geometry_failures([fragment], 0)
        self.assertIn("missing_stable_identity", [item["type"] for item in failures])

    def test_peer_typography_rejects_inconsistent_scale(self):
        from tasks.pptx_visual_verify import peer_typography_failures

        peers = [
            {"slideIndex": 0, "elementId": "a", "type": "text", "tag": "p.metric", "fontSize": 24, "fontScale": 1, "fontFamily": "Arial"},
            {"slideIndex": 0, "elementId": "b", "type": "text", "tag": "p.metric", "fontSize": 24, "fontScale": 0.94, "fontFamily": "Arial"},
        ]
        self.assertEqual("peer_typography_drift", peer_typography_failures(peers, 0)[0]["type"])

    def test_plain_tags_do_not_create_false_peer_groups(self):
        from tasks.pptx_visual_verify import peer_typography_failures

        unrelated = [
            {"slideIndex": 0, "elementId": "dh-auto-a", "type": "text", "tag": "p", "fontSize": 16, "fontScale": 1, "fontFamily": "Arial"},
            {"slideIndex": 0, "elementId": "dh-auto-b", "type": "text", "tag": "p", "fontSize": 16, "fontScale": 0.9, "fontFamily": "Arial"},
        ]
        self.assertEqual([], peer_typography_failures(unrelated, 0))

    def test_table_owner_rejects_cell_content_drift(self):
        from tasks.pptx_visual_verify import semantic_ownership_failures

        table = {
            "slideIndex": 0,
            "elementId": "table-native",
            "semanticOwner": "table-host",
            "semanticKind": "table",
            "type": "table",
            "tableRows": 1,
            "tableCols": 2,
            "tableCells": ["A", "B"],
            "pptxTableCells": ["A", "shifted"],
            "tableRowHeights": [30],
            "pptxTableRowHeights": [30 / 128],
            "tableColumnWidths": [100, 100],
            "pptxTableColumnWidths": [100 / 128, 100 / 128],
        }
        failures = semantic_ownership_failures([table], 0)
        self.assertIn("table_cell_content_drift", [item["type"] for item in failures])

    def test_scene_raster_requires_both_signals_to_be_bad(self):
        from tasks.pptx_visual_verify import scene_raster_is_credible

        # Strong structure carries a slide whose pixels differ (font rasterization).
        self.assertTrue(scene_raster_is_credible(0.82, 24, mae_ceil=18))
        # Low error still excuses the SSIM depression from a text-heavy raster.
        self.assertTrue(scene_raster_is_credible(0.55, 8, mae_ceil=18))
        self.assertFalse(scene_raster_is_credible(0.20, 24, mae_ceil=18))

    def test_low_structure_is_not_excused_by_low_pixel_error(self):
        """MAE averages over the canvas, so it cannot vouch for composition.

        A cover slide whose title rendered at the wrong size measured ssim 0.15
        with mae 16.3 — inside the ceiling — and shipped as a passing slide.
        """
        from tasks.pptx_visual_verify import scene_raster_is_credible

        self.assertFalse(scene_raster_is_credible(0.15447, 16.31, mae_ceil=18))
        self.assertFalse(scene_raster_is_credible(0.39, 2.0, mae_ceil=18))

    def test_failed_report_carries_object_first_remediation(self):
        from tasks.layout_findings import native_fidelity_remediation_plan

        report = {
            "failures": [{
                "stem": "slide_06",
                "semantic": {
                    "ok": False,
                    "geometry_failures": [{"type": "text_font_scale", "elementId": "body-1"}],
                    "typography_failures": [],
                    "ownership_failures": [],
                    "missing_element_ids": [],
                },
            }]
        }
        remediation = native_fidelity_remediation_plan(report)
        self.assertEqual("object", remediation["findings"][0]["repair_scope"])
        self.assertFalse(remediation["whole_slide_fallback_allowed"])


class FidelityGateWiringTests(unittest.TestCase):
    def test_compile_passes_embed_fonts(self):
        from tasks import html_to_pptx as mod

        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env") or {}

            class R:
                returncode = 0
                stderr = ""
                stdout = ""

            for i, tok in enumerate(cmd):
                if tok == "-o" and i + 1 < len(cmd):
                    Path(cmd[i + 1]).write_bytes(b"PK\x03\x04fake")
            return R()

        with mock.patch.object(mod.subprocess, "run", side_effect=fake_run):
            with tempfile.TemporaryDirectory() as tmp:
                html_dir = Path(tmp) / "html"
                html_dir.mkdir()
                (html_dir / "slide_01.html").write_text("<html></html>", encoding="utf-8")
                out = Path(tmp) / "out.pptx"
                mod.compile_html_dir_to_pptx(html_dir, out)
        self.assertIn("--embed-fonts", captured["cmd"])
        self.assertIn("DECKHTML_FONTS_DIR", captured["env"])

    def test_finalize_missing_previews_keeps_native_editable_output(self):
        from tasks import html_to_pptx as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "html_output").mkdir()
            (root / "html_output" / "slide_01.html").write_text(
                "<html></html>", encoding="utf-8"
            )
            (root / "exports").mkdir()

            def compile_staged(_html_dir, output, **_kwargs):
                Path(output).write_bytes(b"PK\x03\x04fake")
                return str(output)

            with mock.patch.object(
                mod, "compile_html_dir_to_pptx", side_effect=compile_staged
            ), mock.patch.object(
                mod,
                "validate_html_dir_runtime_layout",
                return_value={"ok": True, "hard": [], "slides": []},
            ):
                with mock.patch(
                    "tasks.release_export.write_release_manifest",
                    return_value={"ok": True},
                ):
                    result = mod.finalize_compile_html(
                        str(root), include_notes=False, fidelity_verify=True
                    )
            self.assertTrue(result["ok"])
            self.assertIn(
                "canonical_previews_unavailable_nonblocking",
                [item.get("code") for item in result.get("advisories") or []],
            )

    def test_runtime_layout_issues_do_not_replace_or_refuse_native_compile(self):
        from tasks import html_to_pptx as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_dir = root / "html_output"
            html_dir.mkdir()
            (html_dir / "slide_01.html").write_text("<html></html>", encoding="utf-8")
            with mock.patch.object(
                mod,
                "validate_html_dir_runtime_layout",
                return_value={"ok": False, "hard": ["slide_01: runtime_sibling_collision"], "slides": []},
            ):
                def compile_staged(_html_dir, output, **_kwargs):
                    Path(output).write_bytes(b"PK\x03\x04fake")
                    return str(output)

                with mock.patch.object(
                    mod, "compile_html_dir_to_pptx", side_effect=compile_staged
                ) as compile_mock, mock.patch(
                    "tasks.release_export.write_release_manifest",
                    return_value={"status": "released_with_advisories"},
                ):
                    result = mod.finalize_compile_html(
                        str(root), include_notes=False, fidelity_verify=False
                    )
            compile_mock.assert_called_once()
            self.assertTrue(result["ok"])
            self.assertIn(
                "measured_findings_preserved_for_object_repair",
                [item.get("code") for item in result.get("advisories") or []],
            )

    def test_runtime_layout_report_rejects_missing_scene_manifest(self):
        from tasks import html_to_pptx as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_dir = root / "html_output"
            html_dir.mkdir()
            (html_dir / "slide_01.html").write_text("<html></html>", encoding="utf-8")
            measured = {
                "ok": True,
                "issues": [],
                "hard": [],
                "inspection": {"available": True},
            }
            with mock.patch(
                "tasks.html_layout_qa.audit_runtime_html_layout", return_value=measured
            ):
                report = mod.validate_html_dir_runtime_layout(root, html_dir)
            self.assertFalse(report["ok"])
            self.assertEqual(1, report["summary"]["invalid_scene_manifest"])
            self.assertIn("scene_manifest_missing_or_invalid", report["slides"][0]["hard"])

    def test_runtime_layout_report_is_included_in_compile_result(self):
        from tasks import html_to_pptx as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "html_output").mkdir()
            (root / "html_output" / "slide_01.html").write_text("<html></html>", encoding="utf-8")
            (root / "exports").mkdir()
            report = {"ok": True, "hard": [], "slides": [{"stem": "slide_01", "ok": True}]}
            with mock.patch.object(mod, "validate_html_dir_runtime_layout", return_value=report):
                def compile_staged(_html_dir, output, **_kwargs):
                    Path(output).write_bytes(b"PK\x03\x04fake")
                    return str(output)

                with mock.patch.object(mod, "compile_html_dir_to_pptx", side_effect=compile_staged):
                    with mock.patch("tasks.release_export.write_release_manifest", return_value={"ok": True}):
                        result = mod.finalize_compile_html(
                            str(root), include_notes=False, fidelity_verify=False
                        )
            self.assertEqual(report, result["runtime_layout"])

    def test_compile_rebuilds_latest_when_sources_change_mid_build(self):
        from tasks import html_to_pptx as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_dir = root / "html_output"
            html_dir.mkdir()
            source = html_dir / "slide_01.html"
            source.write_text("<html>before</html>", encoding="utf-8")

            def compile_and_mutate(_html_dir, output, **_kwargs):
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"PK\x03\x04fake")
                source.write_text("<html>after</html>", encoding="utf-8")

            with mock.patch.object(
                mod,
                "validate_html_dir_runtime_layout",
                return_value={"ok": True, "hard": [], "slides": []},
            ), mock.patch.object(
                mod, "compile_html_dir_to_pptx", side_effect=compile_and_mutate
            ), mock.patch.object(
                mod,
                "build_failsafe_pptx",
                side_effect=lambda _root, output, **_kwargs: (
                    Path(output).write_bytes(b"PK\x03\x04fallback")
                    or {"mode": "editable_text_failsafe"}
                ),
            ):
                with mock.patch(
                    "tasks.release_export.write_release_manifest",
                    return_value={"status": "released_with_advisories"},
                ) as manifest_mock:
                    result = mod.finalize_compile_html(
                        str(root), include_notes=False, fidelity_verify=False
                    )
            manifest_mock.assert_called_once()
            self.assertTrue(result["ok"])
            self.assertEqual("html_deckhtml", result["mode"])
            self.assertIn(
                "changed_during_compile",
                [item.get("code") for item in result.get("advisories") or []],
            )


if __name__ == "__main__":
    unittest.main()


class ExportOverlapGate(unittest.TestCase):
    """The conversion must not put text on top of other text."""

    def _shape(self, element_id, html, pptx):
        return {
            "type": "text",
            "slideIndex": 0,
            "elementId": element_id,
            "html": dict(zip("xywh", html)),
            "pptx": dict(zip("xywh", pptx)),
        }

    def test_overlap_the_html_already_had_is_not_blamed_on_the_export(self):
        from tasks.pptx_visual_verify import export_introduced_overlaps

        # Both frames overlap identically in each space: a content problem, and
        # the layout QA owns it — reporting it here would hide the real defects.
        shapes = [
            self._shape("a", (0, 0, 128, 128), (0, 0, 1, 1)),
            self._shape("b", (64, 0, 128, 128), (0.5, 0, 1, 1)),
        ]
        self.assertEqual(export_introduced_overlaps(shapes, 0), [])

    def test_collision_created_by_the_export_is_reported(self):
        from tasks.pptx_visual_verify import export_introduced_overlaps

        # Chromium left a 64px gap; the export placed the second frame on top.
        shapes = [
            self._shape("a", (0, 0, 128, 128), (0, 0, 1, 1)),
            self._shape("b", (192, 0, 128, 128), (0.5, 0, 1, 1)),
        ]
        failures = export_introduced_overlaps(shapes, 0)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["type"], "export_introduced_overlap")
        self.assertEqual(failures[0]["html_overlap_px2"], 0.0)
        self.assertGreater(failures[0]["pptx_overlap_px2"], 20)

    def test_rounding_hairlines_are_tolerated(self):
        from tasks.pptx_visual_verify import export_introduced_overlaps

        # Adjacent frames sharing ~0.1px after inch→EMU rounding are not defects.
        shapes = [
            self._shape("a", (0, 0, 128, 128), (0, 0, 1, 1)),
            self._shape("b", (128, 0, 128, 128), (0.999, 0, 1, 1)),
        ]
        self.assertEqual(export_introduced_overlaps(shapes, 0), [])
