"""Export-safe SVG contract: gate + DOM-safe edits."""

from __future__ import annotations

import unittest
from pathlib import Path

from tasks.svg_export_gate import assert_export_svg, validate_export_svg
from tasks.svg_geometry import apply_svg_edits


_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "layout_regressions"
    / "ss_table_midtag_orphan_tspan.svg"
)


class TestSvgExportGate(unittest.TestCase):
    def test_rejects_mid_tag_debris_and_orphan_tspan(self):
        svg = _FIXTURE.read_text(encoding="utf-8")
        result = validate_export_svg(svg)
        self.assertFalse(result.ok)
        joined = " ".join(result.errors)
        self.assertTrue(
            "mid_tag_debris" in joined or "orphan_tspan" in joined or "xml_parse" in joined,
            msg=result.errors,
        )
        with self.assertRaises(ValueError):
            assert_export_svg(svg)

    def test_accepts_legal_wrapped_tspans(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="40" y="80" font-size="18">'
            '<tspan x="40" dy="0">Hello</tspan>'
            '<tspan x="40" dy="22">World</tspan>'
            "</text></svg>"
        )
        result = validate_export_svg(svg)
        self.assertTrue(result.ok, msg=result.errors)

    def test_rejects_bare_tspan_under_g(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            "<g><tspan>Class</tspan></g></svg>"
        )
        result = validate_export_svg(svg)
        self.assertFalse(result.ok)
        self.assertTrue(any("orphan_tspan" in e for e in result.errors), msg=result.errors)

    def test_accepts_mathjax_local_use_glyphs(self):
        """Formula MathJax SVGs use <defs><path id> + <use href="#id">; gate must expand."""
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 1280 720">'
            '<g data-sunairum-formula="1" data-sunairum-formula-math="1">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="28" viewBox="0 0 100 40">'
            '<defs><path id="MJX-1-TEX-N-43" d="M10 10h20v20h-20z"/></defs>'
            '<g><use href="#MJX-1-TEX-N-43" x="0" y="0"/></g>'
            "</svg></g></svg>"
        )
        result = validate_export_svg(svg)
        self.assertTrue(result.ok, msg=result.errors)
        self.assertFalse(any("unsupported_visual" in e for e in result.errors))

    def test_rejects_unresolvable_local_use(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<use href="#missing-glyph" x="0" y="0"/>'
            "</svg>"
        )
        result = validate_export_svg(svg)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("local_use_expansion" in e or "unsupported_visual" in e for e in result.errors),
            msg=result.errors,
        )

    def test_dom_safe_edits_reject_mid_text_splice(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="10" y="20" fill="#1A365D">Class</text>'
            "</svg>"
        )
        # Mid-tag: start inside attributes (after fill=") — must be ignored.
        start = svg.index('fill="#1A365D"') + len('fill="')
        end = svg.index("</text>")
        out = apply_svg_edits(svg, [(start, end, "")])
        self.assertEqual(out, svg)
        # Whole-element delete is allowed.
        t0 = svg.index("<text")
        t1 = svg.index("</text>") + len("</text>")
        out2 = apply_svg_edits(svg, [(t0, t1, "")])
        self.assertNotIn("<text", out2)

    def test_ensure_well_formed_fail_closed_on_orphan(self):
        from tasks.svg_xml import ensure_well_formed_svg
        from xml.etree import ElementTree as ET

        # Recoverable XML that would leave orphan tspan under g after "repair".
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect x="0" y="0" width="10" height="10" fill="#1A365D"/>'
            'xt data-sunairum-source-table-text="1" x="1" y="2">'
            "<tspan>Class</tspan></svg>"
        )
        with self.assertRaises((ET.ParseError, ValueError)):
            ensure_well_formed_svg(broken)


if __name__ == "__main__":
    unittest.main()
