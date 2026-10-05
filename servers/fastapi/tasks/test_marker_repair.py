"""Native line-end marker color drift must be auto-repaired, not fatal."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / "sunairum_scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from svg_to_pptx.drawingml.utils import (  # noqa: E402
    project_marker_errors,
    repair_project_line_end_markers,
)


_MISMATCH_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <marker id="arrowBlue" markerWidth="10" markerHeight="10" refX="8" refY="3"
            orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L8,3 L0,6 Z" fill="#1E3A8A"/>
    </marker>
  </defs>
  <line x1="100" y1="100" x2="400" y2="100" stroke="#3B82F6" stroke-width="2"
        marker-end="url(#arrowBlue)"/>
</svg>
"""


class MarkerRepairTests(unittest.TestCase):
    def test_color_mismatch_is_reported_before_repair(self):
        root = ET.fromstring(_MISMATCH_SVG)
        errors = project_marker_errors(root)
        self.assertTrue(any("does not match" in err for err in errors))

    def test_repair_clears_color_mismatch(self):
        root = ET.fromstring(_MISMATCH_SVG)
        repairs = repair_project_line_end_markers(root)
        self.assertGreater(repairs, 0)
        errors = project_marker_errors(root)
        self.assertEqual(errors, [])
        line = root.find(".//{http://www.w3.org/2000/svg}line")
        self.assertIsNotNone(line)
        self.assertIn("__s3b82f6", line.get("marker-end", "").lower())

    def test_shared_marker_keeps_original_for_matching_stroke(self):
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <marker id="arrowBlue" markerWidth="10" markerHeight="10" refX="8" refY="3"
            orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L8,3 L0,6 Z" fill="#1E3A8A"/>
    </marker>
  </defs>
  <line id="a" x1="0" y1="0" x2="10" y2="0" stroke="#1E3A8A" stroke-width="2"
        marker-end="url(#arrowBlue)"/>
  <line id="b" x1="0" y1="20" x2="10" y2="20" stroke="#3B82F6" stroke-width="2"
        marker-end="url(#arrowBlue)"/>
</svg>"""
        root = ET.fromstring(svg)
        repair_project_line_end_markers(root)
        self.assertEqual(project_marker_errors(root), [])
        lines = {
            elem.get("id"): elem.get("marker-end")
            for elem in root.iter()
            if (elem.tag.rsplit("}", 1)[-1] == "line")
        }
        self.assertEqual(lines["a"], "url(#arrowBlue)")
        self.assertIn("3b82f6", (lines["b"] or "").lower())


if __name__ == "__main__":
    unittest.main()
