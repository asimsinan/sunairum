"""SVG XML repair + well-formed gate."""

from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

try:
    from tasks.svg_xml import ensure_well_formed_svg, repair_svg_xml
except ModuleNotFoundError:  # pragma: no cover
    from svg_xml import ensure_well_formed_svg, repair_svg_xml  # type: ignore


class SvgXmlRepairTests(unittest.TestCase):
    def test_self_close_glitch_and_orphan_g(self):
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<rect x="1" y="1" width="2" height="2" stroke-width="3"//>'
            "<g><text>ok</text></g></g>"
            "</svg>"
        )
        repaired = repair_svg_xml(broken)
        self.assertNotIn("//>", repaired)
        self.assertIn('stroke-width="3"/>', repaired)
        # One orphan </g> removed; remaining markup parses.
        ET.fromstring(repaired)

    def test_clamp_shapes_does_not_reintroduce_double_slash(self):
        """Geometry rebuilds must strip attrs' trailing / before appending />."""
        from tasks.table_layout import clamp_shapes_inside_cards
        from tasks.svg_geometry import sanitize_self_closing_markup

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="100" y="100" width="200" height="100" rx="8" fill="#fff"/>'
            '<line x1="280" y1="120" x2="280" y2="220" stroke="#C53030" '
            'stroke-width="2"//>'
            "</svg>"
        )
        cleaned = sanitize_self_closing_markup(svg)
        out = clamp_shapes_inside_cards(cleaned)
        self.assertNotIn("//>", out)
        ET.fromstring(out)

    def test_ensure_well_formed_after_repair(self):
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<circle cx="1" cy="1" r="1"//>'
            "</svg>"
        )
        out = ensure_well_formed_svg(broken)
        ET.fromstring(out)

    def test_still_broken_raises(self):
        # Not an SVG root — recover must refuse and the gate must still raise.
        with self.assertRaises(ET.ParseError):
            ensure_well_formed_svg("<div><p>not svg</p></div>")

    def test_bare_amp_escaped(self):
        raw = '<svg xmlns="http://www.w3.org/2000/svg"><text>A & B</text></svg>'
        repaired = repair_svg_xml(raw)
        self.assertIn("A &amp; B", repaired)
        ET.fromstring(repaired)

    def test_unclosed_text_before_sibling_does_not_drop_svg(self):
        """P06-style: missing </text> must not cause </svg> to be treated as orphan."""
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="100" y="82" font-family="Georgia, \'Microsoft YaHei\', serif" '
            'font-size="36" font-weight="700" fill="#1A202C">'
            "The feature space carries routing and equity"
            '<text x="100" y="140" font-size="18">body line</text>'
            "</svg>"
        )
        out = ensure_well_formed_svg(broken)
        ET.fromstring(out)
        self.assertEqual(out.count("<text"), out.count("</text>"))
        self.assertTrue(out.rstrip().endswith("</svg>"))

    def test_nested_double_quotes_in_font_family(self):
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<text x="1" y="2" font-family="Georgia, "Microsoft YaHei", serif" '
            'font-size="36">Title</text></svg>'
        )
        out = ensure_well_formed_svg(broken)
        ET.fromstring(out)
        self.assertIn("font-family=\"Georgia, 'Microsoft YaHei', serif\"", out)

    def test_bare_lt_in_text_escaped(self):
        raw = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="1" y="2" font-size="16">when n < 10 or x<y</text></svg>'
        )
        out = ensure_well_formed_svg(raw)
        ET.fromstring(out)
        self.assertIn("n &lt; 10", out)
        self.assertIn("x&lt;y", out)

    def test_lxml_recover_keeps_title_when_tags_mismatch(self):
        """formula_hero-style damage: unclosed text + stray closer — keep content."""
        broken = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="0" y="0" width="1280" height="720" fill="#fff"/>'
            '<text x="100" y="88" font-family="Georgia, \'Microsoft YaHei\', serif" '
            'font-size="36" font-weight="700" fill="#1A202C">'
            "Search control keeps comparisons consistent"
            "<g><text x=\"100\" y=\"200\" font-size=\"18\">body copy here</text>"
            "</svg>"
        )
        out = ensure_well_formed_svg(broken)
        ET.fromstring(out)
        self.assertIn("Search control keeps comparisons consistent", out)
        self.assertIn("body copy here", out)


if __name__ == "__main__":
    unittest.main()
