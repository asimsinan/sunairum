import json
import tempfile
import unittest
from pathlib import Path

from source_import import SOURCE_ACTIVE_STATUSES, source_status_summary, write_source_status


class SourceImportStatusTests(unittest.TestCase):
    def test_source_progress_summary_exposes_readiness_and_counts(self):
        project = Path(tempfile.mkdtemp())
        (project / "sources").mkdir()
        write_source_status(project, "source_grounding", 75, "Building evidence")
        (project / "sources" / "parser_manifest.json").write_text(json.dumps({
            "parser_selected": "docling",
            "parser_version": "2.6.4",
            "page_count": 6,
            "tables": {"structured": 6},
            "figures": {"detected": 2},
        }), encoding="utf-8")
        (project / "sources" / "evidence_manifest.json").write_text(json.dumps({
            "table_count": 6,
            "asset_count": 2,
            "formula_count": 3,
        }), encoding="utf-8")
        write_source_status(project, "source_ready", 100, "Ready")
        summary = source_status_summary(project)
        self.assertEqual("source_ready", summary["status"])
        self.assertTrue(summary["ready"])
        self.assertEqual(6, summary["pages"])
        self.assertEqual(6, summary["tables"])
        self.assertEqual(2, summary["figures"])
        self.assertEqual(3, summary["formulas"])

    def test_source_active_statuses_are_explicit(self):
        self.assertEqual({"source_uploading", "source_parsing", "source_grounding"}, SOURCE_ACTIVE_STATUSES)

    def test_missing_pdf_is_terminal_orphan_not_raise(self):
        from types import SimpleNamespace
        from tasks import source_import_task as sit

        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            user = "user-1"
            project_id = "proj_orphan"
            project = storage / user / project_id
            project.mkdir(parents=True)

            class FakeTask:
                request = SimpleNamespace(id="task-orphan-1")

            out = sit._parse_uploaded_source_body(
                FakeTask(),
                project_id,
                "topic",
                user,
                storage,
                project,
            )
            self.assertEqual("source_error", out["status"])
            self.assertTrue(out.get("orphan"))
            status = json.loads((project / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual("source_error", status["status"])
            self.assertIn("missing", status.get("error", ""))

    def test_source_readiness_survives_generation_status_updates(self):
        project = Path(tempfile.mkdtemp())
        (project / "sources").mkdir()
        (project / "sources" / "evidence_manifest.json").write_text(json.dumps({"table_count": 1}), encoding="utf-8")
        write_source_status(project, "source_ready", 100, "Ready")
        (project / "status.json").write_text(json.dumps({"status": "planning", "progress": 5}), encoding="utf-8")

        summary = source_status_summary(project)

        self.assertEqual("source_ready", summary["status"])
        self.assertTrue(summary["ready"])
        self.assertEqual(100, summary["progress"])


if __name__ == "__main__":
    unittest.main()
