"""Intent table/formula texts must not be shredded by collision restack."""

from __future__ import annotations

import unittest


class NativeProtectOverlapTests(unittest.TestCase):
    def test_table_cells_marked_and_skipped(self):
        from tasks.svg_geometry import parse_texts, resolve_same_baseline_overlaps

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table">'
            '<text data-sunairum-source-table-text="1" x="40" y="200" font-size="14">A</text>'
            '<text data-sunairum-source-table-text="1" x="50" y="200" font-size="14">B</text>'
            '<text data-sunairum-source-table-text="1" x="60" y="200" font-size="14">C</text>'
            '<text data-sunairum-source-table-text="1" x="70" y="200" font-size="14">D</text>'
            "</g>"
            '<text x="100" y="400" font-size="16">Freehand note</text>'
            "</svg>"
        )
        items = parse_texts(svg)
        self.assertEqual(1, len(items))
        self.assertEqual("Freehand note", items[0]["plain"])
        out = resolve_same_baseline_overlaps(svg)
        self.assertNotIn("</text>>", out)
        self.assertNotIn(">t>", out)
        self.assertIn('data-sunairum-source-table-text="1"', out)

    def test_formula_host_texts_skipped(self):
        from tasks.svg_geometry import parse_texts, resolve_text_collisions

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-host="1">'
            '<text x="100" y="200" font-size="18">beta = equity weight</text>'
            '<text x="100" y="210" font-size="18">gamma = Jain weight</text>'
            "</g>"
            '<text x="100" y="500" font-size="16">Outside claim</text>'
            "</svg>"
        )
        items = parse_texts(svg)
        self.assertEqual(1, len(items))
        out = resolve_text_collisions(svg)
        self.assertNotIn("</text>>", out)
        self.assertIn("beta = equity weight", out)

    def test_multi_edit_same_span_does_not_corrupt(self):
        from tasks.svg_geometry import _apply_text_edits

        svg = '<svg><text x="10" y="20">Hello</text><text x="30" y="20">World</text></svg>'
        # Same-start edits last-win; adjacent non-overlapping edit also applies.
        hello = '<text x="10" y="20">Hello</text>'
        hello2 = '<text x="12" y="20">Hello</text>'
        world = '<text x="30" y="20">World</text>'
        world2 = '<text x="80" y="20">World</text>'
        h0 = svg.index(hello)
        w0 = svg.index(world)
        edits = [
            (h0, h0 + len(hello), hello),
            (h0, h0 + len(hello), hello2),
            (w0, w0 + len(world), world2),
        ]
        out = _apply_text_edits(svg, edits)
        self.assertEqual(out.count("<text"), 2)
        self.assertNotIn("</text>>", out)
        self.assertIn('x="12"', out)
        self.assertIn('x="80"', out)


if __name__ == "__main__":
    unittest.main()
