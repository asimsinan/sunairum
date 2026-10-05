import json
import tempfile
import unittest
from pathlib import Path

try:
    from tasks.evidence_bundle import build_evidence_bundle
    from tasks.grounded_planner import evidence_catalog, load_evidence_bundle
except ModuleNotFoundError:
    from evidence_bundle import build_evidence_bundle
    from grounded_planner import evidence_catalog, load_evidence_bundle


class EvidenceBundleTests(unittest.TestCase):
    def test_persisted_evidence_is_reloaded_into_the_planner_catalog(self):
        project = Path(tempfile.mkdtemp())
        sources = project / "sources"
        sources.mkdir()
        (project / "source.pdf").write_bytes(b"source")
        (sources / "parser_manifest.json").write_text(json.dumps({
            "parser_selected": "docling",
            "parser_version": "test",
            "source_pdf_sha256": "source-hash",
        }), encoding="utf-8")
        (sources / "source_structure.json").write_text(json.dumps({
            "pages": [{"page": 1, "blocks": [{
                "type": "paragraph",
                "text": "A 14-dimensional vector is evaluated for 500 iterations with 300 customers.",
            }]}],
        }), encoding="utf-8")
        (sources / "source_tables.json").write_text(json.dumps({"tables": []}), encoding="utf-8")
        (sources / "pdf_images").mkdir()
        (sources / "pdf_images" / "source_asset_manifest.json").write_text(json.dumps({"figures": []}), encoding="utf-8")

        build_evidence_bundle(project)
        loaded = load_evidence_bundle(project)
        catalog = evidence_catalog(loaded)

        self.assertTrue((sources / "source_evidence.json").is_file())
        self.assertTrue(loaded["evidence"])
        self.assertIn("14-dimensional", catalog)
        self.assertIn("500 iterations", catalog)
        self.assertIn("300 customers", catalog)


if __name__ == "__main__":
    unittest.main()
