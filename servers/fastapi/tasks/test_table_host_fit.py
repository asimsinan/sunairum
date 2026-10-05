"""Table host fit: dense tables must not clip the last row."""

from __future__ import annotations

import re
import unittest

from tasks.html_pipeline import (
    _estimate_table_natural_height,
    _render_table_html,
    _table_density_for_host,
    inject_table_into_html,
)


def _solomon_payload() -> dict:
    return {
        "columns": ["Method", "Cost", "CV", "Gini", "Jain", "Time (s)"],
        "rows": [
            ["ALNS (cost-only)", "1261.9", "0.3439", "0.1855", "0.8886", "6.10"],
            ["ALNS+HNSW (cost-only)", "1244.3", "0.3373", "0.1826", "0.8923", "4.25"],
            ["ALNS (equity)", "1450.1", "0.1226", "0.0664", "0.9813", "5.52"],
            ["HERO (equity+HNSW)", "1403.6", "0.1331", "0.0717", "0.9787", "4.37"],
            ["OR-Tools", "940.1", "0.2844", "0.1529", "0.9155", "30.00"],
            ["OR-Tools (balanced)", "1251.6", "0.1568", "0.0826", "0.9725", "30.00"],
            ["PyVRP (HGS)", "1066.4", "0.2840", "0.1549", "0.9175", "30.01"],
            ["PyVRP (balanced)", "1078.8", "0.2356", "0.1236", "0.9430", "30.01"],
        ],
    }


class TableHostFitTests(unittest.TestCase):
    def test_density_shrinks_when_natural_exceeds_host(self):
        payload = _solomon_payload()
        natural = _estimate_table_natural_height(
            payload["columns"],
            payload["rows"],
            host_w=580.0,
            pad_y=14.0,
            pad_x=18.0,
            fs_body=15.0,
            fs_head=12.0,
        )
        self.assertGreater(natural, 440.0)
        dens = _table_density_for_host(
            payload["columns"], payload["rows"], host_w=580.0, host_h=440.0
        )
        self.assertLess(dens["scale"], 1.0)
        self.assertLessEqual(dens["fs_body"], 15.0)
        html = _render_table_html(payload, host_w=580.0, host_h=440.0)
        self.assertIn("font-size:", html)
        # Compact mode must use smaller body type than the default 15px.
        sizes = [int(x) for x in re.findall(r"font-size:(\d+)px", html)]
        self.assertTrue(any(s < 15 for s in sizes), sizes)

    def test_inject_fits_eight_row_table_without_mutating_scene_geometry(self):
        payload = _solomon_payload()
        html = (
            '<section class="slide" style="position:relative;width:1280px;height:720px">'
            '<div data-pptx="table" data-table-id="solomon-results-table" '
            'style="position:absolute;left:640px;top:160px;width:580px;height:440px;"></div>'
            "</section>"
        )
        out, meta = inject_table_into_html(
            html,
            storage_dir="/tmp",
            slide={"slide": 10, "table_id": "solomon-results-table", "table": payload},
            native_payloads={"solomon-results-table": payload},
        )
        self.assertEqual(meta.get("status"), "filled")
        self.assertEqual(440.0, float(meta.get("host_h") or 0))
        self.assertIn("PyVRP (balanced)", out)
        # Scene geometry remains authoritative; density adapts inside the host.
        m = re.search(
            r'data-pptx=["\']table["\'][^>]*style="([^"]*)"',
            out,
            flags=re.I,
        )
        self.assertIsNotNone(m)
        hm = re.search(r"height\s*:\s*([\d.]+)px", m.group(1), flags=re.I)
        self.assertIsNotNone(hm)
        self.assertEqual(440.0, float(hm.group(1)))


if __name__ == "__main__":
    unittest.main()
