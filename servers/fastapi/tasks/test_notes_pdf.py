"""Speaker-notes handout PDF generation and release binding."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class NotesPdfTests(unittest.TestCase):
    def _project(self) -> Path:
        from PIL import Image

        root = Path(tempfile.mkdtemp())
        for dirname in ("html_output", "notes", "preview", "exports", "validation"):
            (root / dirname).mkdir()
        for index, title in ((1, "Opening decision"), (2, "Measured result")):
            stem = f"slide_{index:02d}"
            (root / "html_output" / f"{stem}.html").write_text(
                f"<!doctype html><section class='slide'><h1>{title}</h1></section>\n",
                encoding="utf-8",
            )
            Image.new("RGB", (4000, 2250), (244, 248, 252)).save(
                root / "preview" / f"{stem}.png"
            )
        (root / "notes" / "slide_01.md").write_text(
            "Explain the decision and establish the cost baseline.", encoding="utf-8"
        )
        (root / "notes" / "slide_02.md").write_text(
            "Call out the measured result and the operational implication.", encoding="utf-8"
        )
        return root

    def test_handout_contains_each_slide_and_matching_notes(self):
        from pypdf import PdfReader

        from tasks.notes_pdf import create_notes_handout_pdf

        root = self._project()
        output = root / "exports" / "presentation-notes.pdf"
        result = create_notes_handout_pdf(root, output)
        self.assertEqual(2, result["slides"])
        self.assertEqual(2, result["pages"])
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)
        self.assertIn("Slide 1: Opening decision", text)
        self.assertIn("establish the cost baseline", text)
        self.assertIn("Slide 2: Measured result", text)
        self.assertIn("operational implication", text)

    def test_previous_release_resolver_uses_hash_not_current_source(self):
        from tasks.release_export import _sha256_file, resolve_previous_released_pptx

        root = self._project()
        release_dir = root / "exports" / "releases" / "old-release"
        release_dir.mkdir(parents=True)
        pptx = release_dir / "presentation.pptx"
        pptx.write_bytes(b"PK\x03\x04immutable-old-release")
        manifest = {
            "status": "released",
            "pptx_path": str(pptx.relative_to(root)),
            "pptx_sha256": _sha256_file(pptx),
            "source_revision_sha256": "an-old-source",
        }
        (root / "validation" / "previous_release_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        resolved, sha, loaded = resolve_previous_released_pptx(root)
        self.assertEqual(pptx.resolve(), Path(resolved).resolve())
        self.assertEqual(manifest["pptx_sha256"], sha)
        self.assertEqual("an-old-source", loaded["source_revision_sha256"])

    def test_release_notes_pdf_writes_source_bound_manifest(self):
        from tasks.release_export import ensure_release_notes_pdf, project_source_revision

        root = self._project()
        release_dir = root / "exports" / "releases" / "current"
        release_dir.mkdir(parents=True)
        pptx = release_dir / "presentation.pptx"
        pptx.write_bytes(b"PK\x03\x04current")
        (root / "validation" / "release_manifest.json").write_text(
            json.dumps({"release_id": "current"}), encoding="utf-8"
        )
        output = Path(ensure_release_notes_pdf(pptx, "pptx-sha", proj_dir=root))
        manifest = json.loads(
            (root / "validation" / "notes_pdf_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(output, root / manifest["notes_pdf_path"])
        self.assertEqual("current", manifest["release_id"])
        self.assertEqual(
            project_source_revision(root)["sha256"],
            manifest["source_revision_sha256"],
        )
        self.assertTrue(manifest["notes_pdf_sha256"])


if __name__ == "__main__":
    unittest.main()
