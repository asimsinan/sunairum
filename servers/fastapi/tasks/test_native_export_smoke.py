import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class NativeExportSmokeTests(unittest.TestCase):
    def test_grounded_table_without_template_carrier_gets_native_source_marker(self):
        try:
            from tasks.generate_task import materialize_source_table_svg
            from tasks.grounding_qa import validate_rendered_grounding
        except ModuleNotFoundError:
            from generate_task import materialize_source_table_svg
            from grounding_qa import validate_rendered_grounding

        root = Path(tempfile.mkdtemp())
        (root / "svg_output").mkdir()
        payload = {
            "source_table_id": "src-table-001",
            "columns": [{"text": "Method"}, {"text": "Cost"}],
            "rows": [[{"text": "HERO"}, {"text": "1403.6"}]],
        }
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#FFFFFF"/>'
            '<text x="64" y="100">Results</text></svg>'
        )
        rendered = materialize_source_table_svg(svg, payload)
        (root / "svg_output" / "slide_01.svg").write_text(rendered, encoding="utf-8")

        self.assertIn('data-sunairum-source-table-id="src-table-001"', rendered)
        self.assertIn("HERO", rendered)
        report = validate_rendered_grounding(
            str(root),
            [{"grounding": {"table_bindings": [{"table_id": "src-table-001"}]}}],
            "pdf_strict",
        )
        self.assertEqual("passed", report["status"])

    def test_materialized_table_row_heights_match_native_resolved_rows(self):
        import html
        import json
        import re
        import sys

        try:
            from tasks.generate_task import materialize_source_table_svg
        except ModuleNotFoundError:
            from generate_task import materialize_source_table_svg

        scripts = str(Path(__file__).resolve().parents[1] / "sunairum_scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from svg_to_pptx.native_objects.table import (  # noqa: E402
            _table_rows,
            _validate_table_payload,
        )

        payload = {
            "source_table_id": "src-table-axis",
            "columns": [{"text": "Method"}, {"text": "Cost"}],
            "rows": [
                [{"text": "HERO"}, {"text": "1"}],
                [{"text": "Baseline"}, {"text": "2"}],
            ],
        }
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#FFFFFF"/></svg>'
        )
        rendered = materialize_source_table_svg(svg, payload)
        match = re.search(
            r'<metadata\b[^>]*>(.*?)</metadata>',
            rendered,
            re.S | re.I,
        )
        self.assertIsNotNone(match)
        meta = json.loads(html.unescape(match.group(1)).strip())
        resolved = _table_rows(meta)
        self.assertEqual(len(resolved), len(meta["row_heights"]))
        _validate_table_payload(meta)  # must not raise
        # Stale short heights (the old bug) must also compile-validate.
        broken = {**meta, "row_heights": [1] * len(payload["rows"])}
        _validate_table_payload(broken)
        self.assertEqual(len(_table_rows(broken)), len(broken["row_heights"]))
    def test_table_template_compiles_to_native_pptx(self):
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        notes_dir = root / "notes"
        exports_dir = root / "exports"
        svg_dir.mkdir()
        notes_dir.mkdir()
        exports_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="0" y="0" width="1280" height="720" fill="#FFFFFF"/>'
            '<text x="64" y="100" font-family="Arial" font-size="48">Native export smoke</text>'
            '</svg>',
            encoding="utf-8",
        )
        (notes_dir / "slide_01.md").write_text("Table smoke test.", encoding="utf-8")
        (root / "spec_lock.md").write_text(
            "## communication\n- primary_language: en\n\n## canvas\n- viewBox: 0 0 1280 720\n\n## colors\n- bg: #FFFFFF\n- primary: #1E3A8A\n- accent: #3B82F6\n- text: #0F172A\n\n## typography\n- font_family: Arial\n- title_family: Arial\n- body_family: Arial\n- title: 48\n- body: 24\n- title_min: 28\n- body_min: 16\n\n## pptx_structure\n- mode: flat\n",
            encoding="utf-8",
        )
        script = Path(__file__).parents[1] / "sunairum_scripts" / "svg_to_pptx.py"
        subprocess.run([sys.executable, str(script), str(root)], check=True, timeout=120)
        self.assertTrue(list(exports_dir.glob("*.pptx")))


if __name__ == "__main__":
    unittest.main()
