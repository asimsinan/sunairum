"""Decorative shapes and full-bleed backgrounds must stay inside the canvas."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

TASKS = Path(__file__).resolve().parent
FASTAPI = TASKS.parent
if str(FASTAPI) not in sys.path:
    sys.path.insert(0, str(FASTAPI))

from tasks.generate_task import sanitize_shapes_inside_canvas  # noqa: E402


class CanvasSanitizeTests(unittest.TestCase):
    def test_spilling_circle_is_pulled_inside(self):
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <circle cx="1200" cy="40" r="80" fill="#DBEAFE" opacity="0.5"/>
</svg>"""
        out = sanitize_shapes_inside_canvas(svg)
        root = ET.fromstring(out)
        circle = next(e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "circle")
        cx = float(circle.get("cx"))
        cy = float(circle.get("cy"))
        r = float(circle.get("r"))
        self.assertGreaterEqual(cx - r, 16 - 0.01)
        self.assertGreaterEqual(cy - r, 16 - 0.01)
        self.assertLessEqual(cx + r, 1280 - 16 + 0.01)
        self.assertLessEqual(cy + r, 720 - 16 + 0.01)

    def test_dragged_full_bleed_background_is_pinned(self):
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#FFFFFF" id="edit_rect_1"
        x="223.1" y="-293.6"/>
</svg>"""
        out = sanitize_shapes_inside_canvas(svg)
        root = ET.fromstring(out)
        rect = next(e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "rect")
        self.assertEqual(rect.get("x"), "0")
        self.assertEqual(rect.get("y"), "0")
        self.assertEqual(rect.get("width"), "1280")
        self.assertEqual(rect.get("height"), "720")


if __name__ == "__main__":
    unittest.main()
