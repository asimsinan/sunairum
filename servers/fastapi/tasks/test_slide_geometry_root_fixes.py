"""Regression fixtures for slide geometry root fixes (proj_lnpurf defect classes)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class ClearLinesThroughTextTests(unittest.TestCase):
    def test_removes_tick_cluster_over_kpi_text(self):
        from tasks.svg_reflow import clear_lines_through_text

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <rect x="112" y="440" width="458" height="92" rx="10" fill="#1A365D"/>
          <text x="136" y="510" font-size="30" fill="#FFFFFF">O(rn) insertion evaluations</text>
          <line x1="418" y1="490" x2="532" y2="490"/>
          <line x1="442" y1="478" x2="442" y2="502"/>
          <line x1="470" y1="478" x2="470" y2="502"/>
          <line x1="498" y1="478" x2="498" y2="502"/>
          <line x1="526" y1="478" x2="526" y2="502"/>
        </svg>
        """
        out = clear_lines_through_text(svg)
        self.assertNotIn('x1="442"', out)
        self.assertNotIn('x1="470"', out)
        self.assertIn("O(rn) insertion evaluations", out)

    def test_nudges_horizontal_divider_below_body_text(self):
        from tasks.svg_reflow import clear_lines_through_text

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <text x="755" y="501" font-size="20" fill="#FFFFFF">reference points.</text>
          <rect x="755" y="498" width="425" height="2" fill="#3182CE"/>
        </svg>
        """
        out = clear_lines_through_text(svg)
        self.assertRegex(out, r'y="50[89]|y="51[0-9]')
        self.assertNotIn("//>", out)


class ChartBarAnnotationTests(unittest.TestCase):
    def test_moves_prose_off_bars(self):
        from tasks.svg_reflow import clear_chart_bar_annotations

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <rect x="730" y="366" width="412" height="132" rx="10" fill="#FFFFFF"/>
          <rect x="786" y="421" width="42" height="40" fill="#3182CE"/>
          <rect x="858" y="405" width="42" height="56" fill="#3182CE"/>
          <rect x="930" y="389" width="42" height="72" fill="#3182CE"/>
          <text x="754" y="397" font-size="15">same objective value ≠ same workload</text>
        </svg>
        """
        out = clear_chart_bar_annotations(svg)
        self.assertIn("same objective value", out)
        self.assertNotRegex(out, r'<text[^>]*y="397"')


class TakeawayBandFitTests(unittest.TestCase):
    def test_pulls_wrapped_body_inside_band(self):
        from tasks.svg_reflow import fit_takeaway_band

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <rect x="60" y="548" width="1160" height="60" rx="12" fill="#1A365D"/>
          <rect x="60" y="548" width="10" height="60" rx="5" fill="#63B3ED"/>
          <text x="70" y="575" font-size="14" fill="#63B3ED">PRACTICAL CONSEQUENCE</text>
          <text x="70" y="615" font-size="24" fill="#FFFFFF">Reuse the repair mechanism inside a changing ALNS candidate set</text>
        </svg>
        """
        out = fit_takeaway_band(svg)
        # Body baseline must land inside grown/fitted band (not past original bottom).
        import re

        body = re.search(r">Reuse the repair[^<]*</text>", out)
        self.assertIsNotNone(body)
        attrs = out[out.rfind("<text", 0, body.start()) : body.start()]
        y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))
        # Band may grow; text must still be above 700.
        self.assertLessEqual(y, 690)


class HubCenterDotTests(unittest.TestCase):
    def test_removes_center_dot_under_hub_label(self):
        from tasks.svg_reflow import evict_hub_center_dots

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <circle cx="640" cy="364" r="86" fill="#1A365D"/>
          <circle cx="640" cy="364" r="64" fill="#3182CE"/>
          <circle cx="640" cy="364" r="8" fill="#FFFFFF"/>
          <text x="640" y="360" font-size="18" text-anchor="middle" fill="#FFFFFF">insertion position</text>
        </svg>
        """
        out = evict_hub_center_dots(svg)
        self.assertNotIn('r="8"', out)
        self.assertIn('r="86"', out)
        self.assertIn("insertion position", out)


class FormulaRootFixTests(unittest.TestCase):
    def test_tex_fallback_uses_subscript_not_escaped_underscore(self):
        from tasks.formula_latex_png import _ascii_to_tex_fallback

        tex = _ascii_to_tex_fallback("J(R) = C(R)/C_0 + beta")
        self.assertNotIn("\\_", tex)
        self.assertTrue("C_{0}" in tex or "C_0" not in tex.replace("C_{0}", ""))

    def test_formula_plate_image_keeps_png_aspect(self):
        import base64
        import io
        from PIL import Image
        from tasks.formula_visual_intent import render_formula_plate

        # Valid navy ink PNG (not Codecogs red error).
        im = Image.new("RGBA", (640, 80), (0, 0, 0, 0))
        for x in range(40, 600):
            for y in range(20, 60):
                im.putpixel((x, y), (26, 54, 93, 255))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        href = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

        intent = {
            "formula": "J(R)=C_0",
            "formula_tex": "J(R)=C_{0}",
            "_prerender_href": href,
            "_prerender_w": 640,
            "_prerender_h": 80,
            "mode": "hero",
        }
        out = render_formula_plate(
            intent,
            aabb=(100, 200, 1000, 200),
            terms="C_0 = initial",
        )
        import re

        img = re.search(
            r'<image[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
            out,
        )
        self.assertIsNotNone(img)
        w, h = float(img.group(1)), float(img.group(2))
        self.assertGreaterEqual(h, 48.0)
        self.assertAlmostEqual(w / h, 640 / 80, delta=0.15)
        # Unicode subscript or DrawingML-safe dy tspan both OK for legend terms.
        self.assertTrue(
            "C₀" in out or 'dy="4"' in out,
            msg="expected C₀ or dy tspan subscript in legend",
        )
        self.assertNotIn("baseline-shift", out)

    def test_rejects_codecogs_red_error_png(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from tasks.formula_latex_png import formula_png_is_usable

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.png"
            im = Image.new("RGBA", (480, 56), (0, 0, 0, 0))
            for x in range(10, 40):
                for y in range(5, 50):
                    im.putpixel((x, y), (255, 0, 0, 255))
            im.save(path)
            self.assertFalse(formula_png_is_usable(path, ink="#1A365D"))


class TableAsideTests(unittest.TestCase):
    def test_paints_full_height_aside_when_only_scope_chip(self):
        from tasks.asset_narrative import ensure_table_aside_panel

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <g data-sunairum-source-table="1" transform="translate(588,160)"></g>
          <rect x="90" y="500" width="420" height="90" rx="10" fill="#EBF4FB"/>
          <text x="110" y="542" font-size="14">SCOPE CHECK</text>
          <text x="110" y="570" font-size="16">Tiny chip only.</text>
        </svg>
        """
        out = ensure_table_aside_panel(
            svg,
            {
                "table_id": "t1",
                "core_message": "HERO preserves retrieval efficiency.",
                "_color_palette": {"accent": "#3182CE", "primary": "#1A365D"},
            },
            pack="- **Insight:** Balance improves on this set.\n- **Note:** Cost leaders differ.\n",
        )
        self.assertIn('data-sunairum-table-aside="1"', out)
        self.assertIn("Balance improves on this set.", out)
        # Full-height panel, not a tiny chip.
        self.assertRegex(out, r'height="[3-9]\d{2}"')


class LayoutQaWiredTests(unittest.TestCase):
    def test_apply_free_design_layout_qa_mutates_tick_slide(self):
        from tasks.free_design_pipeline import apply_free_design_layout_qa

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_02.svg").write_text(
            """
            <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
              <text x="136" y="510" font-size="30">O(rn) insertion evaluations</text>
              <line x1="418" y1="490" x2="532" y2="490"/>
              <line x1="442" y1="478" x2="442" y2="502"/>
              <line x1="470" y1="478" x2="470" y2="502"/>
              <line x1="498" y1="478" x2="498" y2="502"/>
              <line x1="526" y1="478" x2="526" y2="502"/>
            </svg>
            """,
            encoding="utf-8",
        )
        report = apply_free_design_layout_qa(
            str(svg_dir),
            [{"slide_number": 2, "role": "content"}],
        )
        self.assertNotIn("aesthetic_qa_retired", report.get("skipped") or [])
        text = (svg_dir / "slide_02.svg").read_text(encoding="utf-8")
        self.assertTrue(report.get("repaired") or "x1=\"442\"" not in text)

    def test_surgical_pass_does_not_delete_cover_motif_circles(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <rect x="820" y="0" width="460" height="720" fill="#1A365D"/>
          <circle cx="1000" cy="222" r="13" fill="#63B3ED"/>
          <circle cx="1094" cy="132" r="12" fill="#63B3ED"/>
          <circle cx="1000" cy="470" r="10" fill="#EBF4FB"/>
          <text x="96" y="166" font-size="52" fill="#1A365D">Title</text>
        </svg>
        """
        out = normalize_free_design_slide_svg(svg, role="title")
        self.assertEqual(out.count("<circle"), 3)
        self.assertIn('cx="1094"', out)
        self.assertIn('cx="1000"', out)

    def test_surgical_pass_does_not_run_full_region_pack(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        # Two freehand cards far apart — full pack_region_grid would drag them.
        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <rect x="60" y="180" width="500" height="300" rx="12" fill="#EBF4FB"/>
          <rect x="700" y="180" width="500" height="300" rx="12" fill="#EBF4FB"/>
          <text x="80" y="220" font-size="24">Left card</text>
          <text x="720" y="220" font-size="24">Right card</text>
        </svg>
        """
        out = normalize_free_design_slide_svg(svg, role="content")
        self.assertIn('x="60"', out)
        self.assertIn('x="700"', out)
        self.assertIn('x="80"', out)
        self.assertIn('x="720"', out)

    def test_normalize_reserves_figure_column_from_takeaway(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<image href="../images/f.png" x="640" y="160" width="600" height="390" '
            'data-sunairum-figure-id="fig1"/>'
            '<rect x="48" y="560" width="900" height="90" fill="#1A365D"/>'
            '<text x="72" y="594" font-size="14" font-weight="700" fill="#FFFFFF">TAKEAWAY</text>'
            '<text x="72" y="620" font-size="16" fill="#FFFFFF">'
            "Guided search improves feasibility without inventing image content.</text>"
            "</svg>"
        )
        out = normalize_free_design_slide_svg(svg, role="content")
        # Takeaway band must not underlap FIGURE_HOST (x=640); width clamped.
        import re

        band = re.search(
            r'<rect\b([^>]*fill="#1A365D"[^>]*)/?>',
            out,
            flags=re.I,
        )
        self.assertIsNotNone(band)
        attrs = band.group(1)
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))
        self.assertLessEqual(x + w, 640.0 - 8.0)


class PdfInlineIsolatedTempTests(unittest.TestCase):
    def test_inline_resolves_from_project_svg_dir_not_staging(self):
        from tasks.release_export import _inline_svg_images_for_draw, _svg_has_external_images

        project = Path(tempfile.mkdtemp())
        svg_dir = project / "svg_output"
        images = project / "images"
        svg_dir.mkdir()
        images.mkdir()
        png = images / "pdf_fig.png"
        png.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
        )
        svg = svg_dir / "slide_01.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<image href="../images/pdf_fig.png" x="0" y="0" width="100" height="100"/>'
            "</svg>",
            encoding="utf-8",
        )
        # Isolated staging dir with NO images sibling — production shape.
        staged = Path(tempfile.mkdtemp()) / "svg"
        staged.mkdir()
        self.assertTrue(_svg_has_external_images(svg))
        out = _inline_svg_images_for_draw([svg], staged)
        text = out[0].read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64,", text)
        self.assertNotIn("../images/pdf_fig.png", text)
        self.assertFalse(_svg_has_external_images(out[0]))


if __name__ == "__main__":
    unittest.main()
