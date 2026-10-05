"""Library enrichment helpers for Recents / History."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class ProjectLibraryTests(unittest.TestCase):
    def _write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_display_title_prefers_paper_title(self):
        from tasks.project_library import resolve_display_title

        root = Path(tempfile.mkdtemp())
        self._write(
            root / "validation" / "run_manifest.json",
            {"source_identity": {"paper_title": "HERO Paper"}},
        )
        self._write(
            root / "validation" / "grounded_plan.json",
            {"slides": [{"title": "Slide Title"}]},
        )
        self.assertEqual(
            "HERO Paper",
            resolve_display_title(topic="generate ppt from pdf", proj_dir=root),
        )

    def test_display_title_falls_back_to_slide_then_topic(self):
        from tasks.project_library import resolve_display_title

        root = Path(tempfile.mkdtemp())
        self._write(
            root / "validation" / "grounded_plan.json",
            {"slides": [{"title": "Intro"}]},
        )
        self.assertEqual("Intro", resolve_display_title(topic="topic", proj_dir=root))
        empty = Path(tempfile.mkdtemp())
        self.assertEqual("topic", resolve_display_title(topic="topic", proj_dir=empty))
        self.assertEqual("Untitled", resolve_display_title(topic="", proj_dir=empty))

    def test_cover_and_slide_count(self):
        from tasks.project_library import resolve_cover_url, resolve_slide_count

        root = Path(tempfile.mkdtemp())
        svg = root / "svg_output"
        svg.mkdir()
        (svg / "slide_01.svg").write_text("<svg/>", encoding="utf-8")
        (svg / "slide_02.svg").write_text("<svg/>", encoding="utf-8")
        self.assertEqual(
            "/api/files/default_user/proj_x/svg_output/slide_01.svg",
            resolve_cover_url(user_id="default_user", project_id="proj_x", proj_dir=root),
        )
        self.assertEqual(2, resolve_slide_count(proj_dir=root))
        bare = Path(tempfile.mkdtemp())
        self.assertIsNone(
            resolve_cover_url(user_id="u", project_id="p", proj_dir=bare)
        )
        self._write(bare / "validation" / "run_manifest.json", {"num_slides": 7})
        self.assertEqual(7, resolve_slide_count(proj_dir=bare))

    def test_sort_nulls_last_then_created(self):
        from tasks.project_library import sort_library_projects

        items = [
            {"project_id": "a", "last_opened_at": None, "created_at": 30},
            {"project_id": "b", "last_opened_at": 10, "created_at": 10},
            {"project_id": "c", "last_opened_at": 20, "created_at": 5},
            {"project_id": "d", "last_opened_at": None, "created_at": 40},
        ]
        ordered = [p["project_id"] for p in sort_library_projects(items)]
        self.assertEqual(["c", "b", "d", "a"], ordered)

    def test_enrich_bundle(self):
        from tasks.project_library import enrich_project_library_fields

        root = Path(tempfile.mkdtemp())
        (root / "source.pdf").write_bytes(b"%PDF")
        self._write(
            root / "validation" / "run_manifest.json",
            {"source_identity": {"paper_title": "Paper"}, "num_slides": 3},
        )
        fields = enrich_project_library_fields(
            user_id="default_user",
            project_id="proj_1",
            topic="topic",
            has_pdf_flag=0,
            last_opened_at=123,
            proj_dir=root,
        )
        self.assertEqual("Paper", fields["display_title"])
        self.assertTrue(fields["has_pdf"])
        self.assertEqual(123, fields["last_opened_at"])
        self.assertEqual(3, fields["slide_count"])


if __name__ == "__main__":
    unittest.main()
