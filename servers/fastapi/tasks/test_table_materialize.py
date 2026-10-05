"""Free-design table materialize: headers→columns and exact/ai_replica modes."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class TableMaterializeTests(unittest.TestCase):
    def test_double_materialize_parses_without_duplicate_attrs(self):
        from tasks.generate_task import materialize_source_table_svg

        carrier = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table">'
            '<metadata type="application/json">'
            '{"x":80,"y":200,"width":1120,"height":400,'
            '"source_table_id":"src-table-010",'
            '"columns":[{"text":"A"},{"text":"B"}],'
            '"rows":[[{"text":"1"},{"text":"2"}]]}'
            "</metadata>"
            '<rect x="80" y="200" width="1120" height="400" fill="#fff"/>'
            "</g></svg>"
        )
        payload = {
            "source_table_id": "src-table-010",
            "columns": [{"text": "A"}, {"text": "B"}],
            "rows": [[{"text": "1"}, {"text": "2"}]],
        }
        once = materialize_source_table_svg(carrier, payload)
        twice = materialize_source_table_svg(once, payload)
        self.assertEqual(once, twice)
        self.assertEqual(1, twice.lower().count('data-sunairum-source-table-id="src-table-010"'))
        ET.fromstring(twice)

    def test_materialize_strips_slot_transform_and_clamps(self):
        from tasks.generate_task import materialize_source_table_svg

        carrier = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table" data-sunairum-table-slot="1" '
            'transform="translate(540.0,160.0)">'
            '<metadata type="application/json">'
            '{"x":24,"y":276,"width":1232,"height":344,'
            '"source_table_id":"src-table-002",'
            '"columns":[{"text":"n"},{"text":"A"},{"text":"B"},{"text":"C"},{"text":"D"}],'
            '"rows":[[{"text":"1"},{"text":"2"},{"text":"3"},{"text":"4"},{"text":"5"}]]}'
            "</metadata>"
            '<rect x="0" y="0" width="716" height="420" fill="#fff"/>'
            "</g></svg>"
        )
        payload = {
            "source_table_id": "src-table-002",
            "columns": [{"text": "n"}, {"text": "A"}, {"text": "B"}, {"text": "C"}, {"text": "D"}],
            "rows": [[{"text": "1"}, {"text": "2"}, {"text": "3"}, {"text": "4"}, {"text": "5"}]],
            "x": 24,
            "y": 276,
            "width": 1232,
            "height": 344,
        }
        out = materialize_source_table_svg(carrier, payload)
        self.assertNotIn("transform=", out)
        ET.fromstring(out)
        # Absolute rects must stay on-canvas (no translate double-offset).
        import re

        for m in re.finditer(r'<rect\b[^>]*>', out):
            tag = m.group(0)
            xs = re.search(r'\bx="([-\d.]+)"', tag)
            ws = re.search(r'\bwidth="([-\d.]+)"', tag)
            if xs and ws:
                self.assertLessEqual(float(xs.group(1)) + float(ws.group(1)), 1280.01)

    def test_place_skips_already_materialized_table(self):
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        filled = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table" '
            'data-sunairum-source-table-id="src-table-010">'
            '<metadata type="application/json">'
            '{"source_table_id":"src-table-010","columns":[{"text":"A"}],'
            '"rows":[[{"text":"1"}]]}'
            "</metadata>"
            '<text data-sunairum-source-table-text="1">KEEP</text>'
            "</g></svg>"
        )
        path = svg_dir / "slide_04.svg"
        path.write_text(filled, encoding="utf-8")
        bundle = {
            "tables": {
                "tables": [
                    {
                        "table_id": "src-table-010",
                        "headers": [{"text": "A"}],
                        "rows": [[{"text": "CHANGED"}]],
                    }
                ]
            }
        }
        placed = place_selected_assets(
            slides=[{"slide": 4, "role": "content", "table_id": "src-table-010"}],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=bundle,
            figure_render_mode="exact",
            table_render_mode="exact",
            color_palette={},
        )
        after = path.read_text(encoding="utf-8")
        self.assertEqual("existing", placed["tables"][0]["mode"])
        self.assertIn("KEEP", after)
        self.assertNotIn("CHANGED", after)
        self.assertEqual(1, after.lower().count('data-sunairum-source-table-id="src-table-010"'))
        ET.fromstring(after)
    def test_resolve_maps_headers_to_columns(self):
        from tasks.free_design_pipeline import _resolve_table_payload

        bundle = {
            "tables": {
                "tables": [
                    {
                        "table_id": "src-table-001",
                        "headers": [{"text": "Method"}, {"text": "Cost"}],
                        "rows": [[{"text": "HERO"}, {"text": "1.0"}]],
                    }
                ]
            }
        }
        payload = _resolve_table_payload(bundle, "src-table-001")
        self.assertIsNotNone(payload)
        self.assertEqual([{"text": "Method"}, {"text": "Cost"}], payload["columns"])
        self.assertEqual("src-table-001", payload["source_table_id"])

    def test_exact_mode_materializes_headers_only_payload(self):
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_02.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#FFFFFF"/>'
            '<text x="64" y="80">Results</text></svg>',
            encoding="utf-8",
        )
        bundle = {
            "tables": {
                "tables": [
                    {
                        "table_id": "src-table-004",
                        "headers": [{"text": "Class"}, {"text": "Cost"}],
                        "rows": [[{"text": "C1"}, {"text": "100"}]],
                    }
                ]
            }
        }
        placed = place_selected_assets(
            slides=[{"slide": 2, "role": "content", "table_id": "src-table-004"}],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=bundle,
            figure_render_mode="exact",
            table_render_mode="exact",
            color_palette={"primary": "#0B3B6F", "body_text": "#0F172A"},
        )
        svg = (svg_dir / "slide_02.svg").read_text(encoding="utf-8")
        self.assertEqual(1, len(placed["tables"]))
        self.assertEqual([], placed["errors"])
        self.assertIn('data-sunairum-source-table-id="src-table-004"', svg)
        self.assertIn("C1", svg)
        self.assertIn("#0B3B6F", svg)  # Intent renderer header fill

    def test_ai_replica_mode_keeps_existing_exact_table(self):
        """ai_replica request is ignored; existing exact grid counts as placed."""
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_03.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table" '
            'data-sunairum-source-table-id="src-table-005">'
            '<metadata type="application/json">'
            '{"x":80,"y":200,"width":600,"height":120,'
            '"source_table_id":"src-table-005",'
            '"columns":[{"text":"Weight"},{"text":"Delta"}],'
            '"rows":[[{"text":"0.6"},{"text":"+2"}]]}'
            "</metadata>"
            '<rect x="80" y="200" width="600" height="40" fill="#0B3B6F"/>'
            '<text data-sunairum-source-table-text="1" x="90" y="226" fill="#FFFFFF">Weight</text>'
            '<text data-sunairum-source-table-text="1" x="220" y="226" fill="#FFFFFF">Delta</text>'
            '<text data-sunairum-source-table-text="1" x="90" y="270" fill="#0F172A">0.6</text>'
            '<text data-sunairum-source-table-text="1" x="220" y="270" fill="#0F172A">+2</text>'
            "</g></svg>",
            encoding="utf-8",
        )
        bundle = {
            "tables": {
                "tables": [
                    {
                        "table_id": "src-table-005",
                        "headers": [{"text": "Weight"}, {"text": "Delta"}],
                        "rows": [[{"text": "0.6"}, {"text": "+2"}]],
                    }
                ]
            }
        }
        placed = place_selected_assets(
            slides=[{"slide": 3, "role": "content", "table_id": "src-table-005"}],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=bundle,
            figure_render_mode="exact",
            table_render_mode="ai_replica",
            color_palette={"primary": "#0B3B6F", "body_text": "#0F172A"},
        )
        self.assertEqual(1, len(placed["tables"]))
        self.assertEqual("existing", placed["tables"][0]["mode"])
        self.assertEqual([], placed["errors"])

    def test_ai_replica_mode_falls_back_to_exact_grid(self):
        """Empty slot + ai_replica request → exact materialize (not an error)."""
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_03.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#FFFFFF"/>'
            '<g data-sunairum-table-slot="1" data-sunairum-table-id="src-table-005" '
            'data-pptx-replace-with="table" transform="translate(80,200)">'
            '<rect width="1120" height="320" fill="none"/></g></svg>',
            encoding="utf-8",
        )
        bundle = {
            "tables": {
                "tables": [
                    {
                        "table_id": "src-table-005",
                        "headers": [{"text": "Weight"}, {"text": "Delta"}],
                        "rows": [[{"text": "0.6"}, {"text": "+2"}]],
                    }
                ]
            }
        }
        placed = place_selected_assets(
            slides=[{"slide": 3, "role": "content", "table_id": "src-table-005"}],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=bundle,
            figure_render_mode="exact",
            table_render_mode="ai_replica",
            color_palette={"primary": "#0B3B6F", "body_text": "#0F172A"},
        )
        self.assertEqual(1, len(placed["tables"]))
        self.assertEqual("intent_spec", placed["tables"][0]["mode"])
        svg = (svg_dir / "slide_03.svg").read_text(encoding="utf-8")
        self.assertIn("0.6", svg)

    def test_materialize_keeps_readable_font_floor(self):
        from tasks.generate_task import materialize_source_table_svg
        import re

        carrier = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table">'
            '<metadata type="application/json">'
            '{"x":80,"y":200,"width":1120,"height":180,'
            '"source_table_id":"src-table-020",'
            '"columns":[{"text":"Class"},{"text":"ALNS CV"},{"text":"HERO CV"},'
            '{"text":"Delta CV"},{"text":"Delta Cost"}],'
            '"rows":[]}'
            "</metadata>"
            '<rect x="80" y="200" width="1120" height="180" fill="#fff"/>'
            "</g></svg>"
        )
        rows = []
        for label in ("C", "R", "RC"):
            rows.append(
                [
                    {"text": label},
                    {"text": "0.324"},
                    {"text": "0.169"},
                    {"text": "- 47 . 7 %"},
                    {"text": "+12 . 7 %"},
                ]
            )
        payload = {
            "source_table_id": "src-table-020",
            "columns": [
                {"text": "Class"},
                {"text": "ALNS CV"},
                {"text": "HERO CV"},
                {"text": "Delta CV"},
                {"text": "Delta Cost"},
            ],
            "rows": rows,
            "x": 80,
            "y": 200,
            "width": 1120,
            "height": 180,
            "style": {"font_size": 14, "header_font_size": 14},
        }
        out = materialize_source_table_svg(carrier, payload)
        sizes = [float(s) for s in re.findall(r'data-sunairum-source-table-text="1"[^>]*font-size="([\d.]+)"', out)]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 12.0)
        # OCR junk collapsed into one cell string / one text node.
        self.assertIn("-47.7%", out)
        self.assertIn("+12.7%", out)
        self.assertNotIn("- 47 . 7", out)

    def test_ocr_cell_normalize_helper(self):
        from tasks.evidence_bundle import _normalize_cell_text

        self.assertEqual("-47.7%", _normalize_cell_text("- 47 . 7 %"))
        self.assertEqual("0.6", _normalize_cell_text("0 . 6"))

    def test_painted_only_carrier_not_materialized_until_metadata(self):
        from tasks.free_design_pipeline import _table_materialized_in_svg
        from tasks.generate_task import (
            materialize_source_table_svg,
            strip_unfilled_native_table_carriers,
        )

        painted = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table" '
            'data-sunairum-source-table-id="src-table-099" '
            'transform="translate(80,200)">'
            '<rect x="0" y="0" width="400" height="120" fill="#fff"/>'
            "<text>Method</text><text>100</text>"
            "</g></svg>"
        )
        self.assertFalse(_table_materialized_in_svg(painted, "src-table-099"))
        stripped = strip_unfilled_native_table_carriers(painted)
        self.assertNotIn("Method", stripped)

        payload = {
            "source_table_id": "src-table-099",
            "columns": [{"text": "Method"}, {"text": "Cost"}],
            "rows": [[{"text": "A"}, {"text": "100"}]],
            "x": 80,
            "y": 200,
            "width": 400,
            "height": 120,
        }
        bound = materialize_source_table_svg(painted, payload)
        self.assertTrue(_table_materialized_in_svg(bound, "src-table-099"))
        self.assertIn("<metadata", bound)
        after = strip_unfilled_native_table_carriers(bound)
        self.assertIn("Method", after)
        self.assertIn("src-table-099", after)


if __name__ == "__main__":
    unittest.main()
