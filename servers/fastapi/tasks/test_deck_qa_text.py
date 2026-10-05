import tempfile
import unittest
from pathlib import Path

from deck_qa import (
    check_native_tables,
    check_number_marker_geometry,
    check_duplicate_visible_text,
    check_svg_text,
    check_text_geometry,
)


class TextQaTests(unittest.TestCase):
    def _write_svg(self, content: str) -> str:
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(
            f'<svg viewBox="0 0 400 240">{content}</svg>', encoding="utf-8"
        )
        return str(svg_dir)

    def test_checked_in_overlap_fixture_is_blocked(self):
        fixture = Path(__file__).parent / "fixtures" / "text_overlap.svg"
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / fixture.name).write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        issues = check_text_geometry(str(svg_dir))
        self.assertTrue(any(issue["category"] == "text-overlap" for issue in issues))

    def test_scaled_text_bounds_are_used_for_overflow(self):
        svg_dir = self._write_svg(
            '<g transform="translate(20,30) scale(2)">'
            '<rect x="0" y="0" width="100" height="60"/>'
            '<text x="5" y="25" font-size="12">'
            'A very long transformed line</text></g>'
        )
        issues = check_text_geometry(svg_dir)
        self.assertTrue(any(issue["category"] == "text-overflow" for issue in issues))

    def test_role_minimum_is_configurable(self):
        svg_dir = self._write_svg(
            '<g data-role="title"><text x="10" y="30" font-size="10">Small title</text></g>'
        )
        issues = check_svg_text(svg_dir, min_font_px=8)
        minimum = [issue for issue in issues if issue["category"] == "font-too-small"]
        self.assertEqual(1, len(minimum))
        self.assertIn("role title", minimum[0]["detail"])

    def test_duplicate_visible_text_is_reported(self):
        svg_dir = self._write_svg(
            '<text x="10" y="30" font-size="12">Repeated label</text>'
            '<text x="10" y="80" font-size="12">Repeated label</text>'
        )
        issues = check_duplicate_visible_text(svg_dir)
        self.assertEqual("duplicate-text", issues[0]["category"])

    def test_hidden_duplicate_is_not_visible_text(self):
        svg_dir = self._write_svg(
            '<text x="10" y="30" font-size="12">Repeated label</text>'
            '<text x="10" y="80" font-size="12" visibility="hidden">Repeated label</text>'
        )
        self.assertEqual([], check_duplicate_visible_text(svg_dir))

    def test_same_baseline_partial_overlap_is_reported(self):
        svg_dir = self._write_svg(
            '<text x="10" y="40" font-size="12">First label</text>'
            '<text x="35" y="40" font-size="12">Second label</text>'
        )
        issues = check_text_geometry(svg_dir)
        self.assertTrue(any(issue["category"] == "text-overlap" for issue in issues))

    def test_text_leaving_a_declared_cell_is_reported(self):
        svg_dir = self._write_svg(
            '<g id="table" data-pptx-replace-with="table">'
            '<rect data-pptx-cell="0-0" x="20" y="20" width="120" height="60" fill="none"/>'
            '<rect data-pptx-cell="0-1" x="140" y="20" width="120" height="60" fill="none"/>'
            '<text x="25" y="55" font-size="16">This text runs out of its own cell</text>'
            '</g>'
        )
        issues = check_text_geometry(svg_dir)
        self.assertTrue(any(issue["category"] == "table-cell-overlap" for issue in issues))

    def test_a_grid_drawn_only_with_rules_is_not_audited_on_a_guess(self):
        """Inferring cells from drawn rules invented boundaries the renderer never had.

        A decorative divider added a phantom column, and text sitting perfectly
        inside its real cell was reported as crossing an imaginary one.
        """
        svg_dir = self._write_svg(
            '<g id="table" data-pptx-replace-with="table">'
            '<rect x="20" y="20" width="240" height="120"/>'
            '<line x1="140" y1="20" x2="140" y2="140"/>'
            '<line x1="20" y1="80" x2="260" y2="80"/>'
            '<text x="25" y="55" font-size="16">This text crosses the cell</text>'
            '</g>'
        )
        issues = check_text_geometry(svg_dir)
        self.assertFalse(any(issue["category"] == "table-cell-overlap" for issue in issues))

    def test_native_table_metadata_is_required(self):
        svg_dir = self._write_svg(
            '<g data-pptx-replace-with="table"><rect x="20" y="20" width="240" height="120"/></g>'
        )
        issues = check_native_tables(svg_dir)
        self.assertEqual("table-metadata-missing", issues[0]["category"])

    def test_checked_in_table_fixture_is_blocked(self):
        fixture = Path(__file__).parent / "fixtures" / "table_overflow.svg"
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        issues = check_native_tables(str(svg_dir))
        self.assertTrue(any(issue["category"] == "table-grid-mismatch" for issue in issues))

    def test_number_marker_center_is_checked(self):
        svg_dir = self._write_svg(
            '<circle cx="80" cy="80" r="24" fill="#123"/>'
            '<text x="96" y="86" text-anchor="middle" font-size="16">01</text>'
        )
        issues = check_number_marker_geometry(svg_dir)
        self.assertIn("marker-not-centered", {issue["category"] for issue in issues})


if __name__ == "__main__":
    unittest.main()
