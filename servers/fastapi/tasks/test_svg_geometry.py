"""Layout regression tests for svg_geometry + related QA detectors."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from tasks.deck_qa import check_figure_title_and_icon_overlap, check_text_geometry
    from tasks.svg_geometry import (
        clear_left_accent_rail,
        flatten_nested_text,
        normalize_slide_geometry,
        pack_icon_label_pairs,
        resolve_text_collisions,
    )
except ImportError:  # pragma: no cover
    from deck_qa import check_figure_title_and_icon_overlap, check_text_geometry
    from svg_geometry import (
        clear_left_accent_rail,
        flatten_nested_text,
        normalize_slide_geometry,
        pack_icon_label_pairs,
        resolve_text_collisions,
    )


FIXTURES = Path(__file__).parent / "fixtures" / "layout_regressions"


def _stage(name: str) -> Path:
    root = Path(tempfile.mkdtemp())
    svg_dir = root / "svg_output"
    svg_dir.mkdir()
    src = FIXTURES / name
    (svg_dir / "slide_01.svg").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return svg_dir


class SvgGeometryKernelTests(unittest.TestCase):
    def test_flatten_nested_furniture_text(self):
        svg = (FIXTURES / "cover_accent_byline.svg").read_text(encoding="utf-8")
        flat = flatten_nested_text(svg)
        self.assertEqual(flat.count("<text"), 3)
        self.assertNotIn("</text></text>", flat.replace(" ", ""))

    def test_cover_rail_collision_detected_and_cleared(self):
        svg_dir = _stage("cover_accent_byline.svg")
        before = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertTrue(any(i["category"] == "text-rail-collision" for i in before))
        svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
        fixed = clear_left_accent_rail(flatten_nested_text(svg))
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        after = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertFalse(any(i["category"] == "text-rail-collision" for i in after))
        self.assertIn('x="84"', fixed)  # rail_right 68 + 16

    def test_caption_stack_overlap_resolved(self):
        svg_dir = _stage("chart_caption_stack.svg")
        before = check_text_geometry(str(svg_dir))
        self.assertTrue(any(i["category"] == "text-overlap" for i in before))
        svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
        fixed = resolve_text_collisions(svg)
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        after = check_text_geometry(str(svg_dir))
        self.assertFalse(any(i["category"] == "text-overlap" for i in after))

    def test_icon_label_overlap_detected_and_packed(self):
        svg_dir = _stage("icon_label_overlap.svg")
        before = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertTrue(any(i["category"] == "text-icon-overlap" for i in before))
        svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
        fixed = pack_icon_label_pairs(svg)
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        after = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertFalse(any(i["category"] == "text-icon-overlap" for i in after))

    def test_divider_gutter_detected_and_normalized(self):
        svg_dir = _stage("divider_gutter.svg")
        before = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertTrue(any(i["category"] == "text-divider-collision" for i in before))
        svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
        fixed = normalize_slide_geometry(svg)
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        after = check_figure_title_and_icon_overlap(str(svg_dir))
        self.assertFalse(any(i["category"] == "text-divider-collision" for i in after))

    def test_ablation_chaos_normalize_clears_overlap(self):
        svg_dir = _stage("ablation_grid_chaos.svg")
        before = check_text_geometry(str(svg_dir))
        self.assertTrue(any(i["category"] == "text-overlap" for i in before))
        svg = (svg_dir / "slide_01.svg").read_text(encoding="utf-8")
        fixed = normalize_slide_geometry(svg)
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        after = check_text_geometry(str(svg_dir))
        self.assertFalse(any(i["category"] == "text-overlap" for i in after))

    def test_normalize_orchestrator_on_cover(self):
        svg = (FIXTURES / "cover_accent_byline.svg").read_text(encoding="utf-8")
        out = normalize_slide_geometry(svg)
        self.assertLess(out.count("<text"), svg.count("<text") + 1)
        # Presenter line should not remain at x=60
        self.assertNotIn('x="60" y="520"', out)



class FigureColumnReservationTests(unittest.TestCase):
    def test_left_cards_clamped_clear_of_placed_figure(self):
        try:
            from tasks.svg_geometry import reserve_figure_column
        except ImportError:  # pragma: no cover
            from svg_geometry import reserve_figure_column

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="0" y="0" width="1280" height="720" fill="#FFFFFF"/>'
            '<image href="../images/f.png" x="640" y="160" width="600" height="390" '
            'data-sunairum-figure-id="fig1"/>'
            '<rect x="40" y="170" width="1050" height="354" rx="12" fill="#F8FAFC"/>'
            '<rect x="58" y="188" width="900" height="124" rx="9" fill="#FFFFFF"/>'
            '<text x="128" y="218" font-size="22">Keep left</text>'
            '<text x="700" y="220" font-size="18">Drop right</text>'
            "</svg>"
        )
        out = reserve_figure_column(svg)
        self.assertIn('width="1280"', out)  # canvas fill untouched
        self.assertIn('width="584"', out)  # 640 - 16 - 40
        self.assertIn("Keep left", out)
        self.assertNotIn("Drop right", out)
        self.assertIn('data-sunairum-figure-id="fig1"', out)



class FontSizeSanitizerTests(unittest.TestCase):
    def test_word_font_size_with_leading_space(self):
        try:
            from tasks.generate_task import sanitize_project_geometry_lengths
        except ImportError:  # pragma: no cover
            from generate_task import sanitize_project_geometry_lengths

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
            '<text x="10" y="20" font-size=" thirty">Hi</text>'
            "</svg>"
        )
        out = sanitize_project_geometry_lengths(svg)
        self.assertIn('font-size="30"', out)
        self.assertNotIn("thirty", out)


if __name__ == "__main__":
    unittest.main()
