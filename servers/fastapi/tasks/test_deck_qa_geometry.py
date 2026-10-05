import tempfile
import unittest
from pathlib import Path

from deck_qa import check_svg_text, check_text_geometry


class TransformedTableGeometryTests(unittest.TestCase):
    def _write_svg(self, text_y: float) -> Path:
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(
            f'''<svg viewBox="0 0 1280 720">
  <g transform="translate(60,160)">
    <rect x="0" y="0" width="1160" height="68" fill="#fff"/>
    <text x="24" y="{text_y}" font-size="9.72">Approximate retrieval result</text>
  </g>
</svg>''',
            encoding="utf-8",
        )
        return svg_dir

    def test_transformed_cell_coordinates_are_resolved(self):
        issues = check_text_geometry(str(self._write_svg(40)))
        self.assertEqual([], issues)

    def test_transformed_cell_overflow_is_blocked(self):
        issues = check_text_geometry(str(self._write_svg(67)))
        self.assertEqual("text-overflow", issues[0]["category"])


class CertifiedFrameGeometryTests(unittest.TestCase):
    def test_framed_copy_is_judged_by_reflow_not_its_raw_svg_line(self):
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(
            '''<svg viewBox="0 0 1280 720">
  <g data-pptx-bounds="888 184 296 360">
    <text x="888" y="206" font-size="24" font-weight="700"
      font-family="Arial, sans-serif" data-pptx-frame="888 184 296 360"
      data-sunairum-original-text="AI edit; authors checked">AI edit; authors checked</text>
  </g>
</svg>''',
            encoding="utf-8",
        )

        self.assertEqual([], check_text_geometry(str(svg_dir)))


class PlaceholderRoleTests(unittest.TestCase):
    def test_title_content_object_copy_is_a_body_role(self):
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(
            '''<svg viewBox="0 0 1280 720" data-pptx-layout="title_content">
  <g data-pptx-placeholder="object">
    <text x="100" y="200" font-size="22">Body copy in the content object.</text>
  </g>
  <g id="left-title-slot" data-pptx-placeholder="body">
    <text id="left-title-carrier" x="100" y="260" font-size="24">Card heading</text>
  </g>
</svg>''',
            encoding="utf-8",
        )

        issues = check_svg_text(str(svg_dir))

        self.assertFalse(any(
            issue["category"] == "font-too-small"
            and "role title" in issue["detail"]
            for issue in issues
        ))


if __name__ == "__main__":
    unittest.main()
