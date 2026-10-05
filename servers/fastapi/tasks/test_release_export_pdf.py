"""PDF export: preview PNGs when html_output exists; Impress otherwise."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ReleaseExportPdfTests(unittest.TestCase):
    def test_release_status_maps_to_history_terminal_status(self):
        from tasks.release_export import ui_status_for_release

        self.assertEqual("done", ui_status_for_release("released"))
        self.assertEqual(
            "done_with_issues",
            ui_status_for_release("released_with_advisories"),
        )

    def test_unknown_status_publishes_and_records_the_defect(self):
        """An unrecognised status must not strand a finished deck."""
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "exports" / "deck.pptx"
        pptx.parent.mkdir()
        pptx.write_bytes(b"PK")
        manifest = release_export.write_release_manifest(
            root, pptx_path=pptx, status="draft_invalid"
        )
        self.assertEqual("released_with_defects", manifest["status"])
        self.assertIn("unknown_release_status:draft_invalid", manifest["defects"])
        self.assertTrue(release_export.is_published_release(manifest["status"]))

    def test_manifest_publishes_visual_failure_as_a_defect(self):
        """Validation reports quality; it never withholds the artifact."""
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "exports" / "deck.pptx"
        pptx.parent.mkdir()
        pptx.write_bytes(b"PK")
        manifest = release_export.write_release_manifest(
            root,
            pptx_path=pptx,
            status="released_with_advisories",
            advisories=[{"code": "native_fidelity_failed"}],
        )
        self.assertEqual("released_with_defects", manifest["status"])
        self.assertEqual(["native_fidelity_failed"], manifest["defects"])
        self.assertEqual("done_with_issues", release_export.ui_status_for_release(manifest["status"]))
        self.assertTrue((root / "validation" / "release_manifest.json").is_file())

    def test_defective_release_is_still_downloadable(self):
        from tasks import release_export

        for status in ("released", "released_with_advisories", "released_with_defects"):
            self.assertTrue(release_export.is_published_release(status))
        self.assertFalse(release_export.is_published_release("draft_invalid"))

    def test_snapshot_current_release_creates_labelled_fallback(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "exports" / "releases" / "r1" / "presentation.pptx"
        pptx.parent.mkdir(parents=True)
        pptx.write_bytes(b"PK-current")
        release_export.write_release_manifest(root, pptx_path=pptx, status="released")
        self.assertTrue(release_export.snapshot_current_release_as_previous(root))
        previous_path, _sha, manifest = release_export.resolve_previous_released_pptx(root)
        self.assertEqual(pptx.resolve(), Path(previous_path).resolve())
        self.assertEqual("released", manifest["status"])

    def test_cached_release_matches_complete_export_revision(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        (root / "html_output").mkdir()
        (root / "notes").mkdir()
        (root / "images").mkdir()
        (root / "html_output" / "slide_01.html").write_text("<main>one</main>", encoding="utf-8")
        (root / "notes" / "slide_01.md").write_text("note one", encoding="utf-8")
        (root / "images" / "figure.png").write_bytes(b"image-one")
        pptx = root / "exports" / "releases" / "r1" / "presentation.pptx"
        pptx.parent.mkdir(parents=True)
        pptx.write_bytes(b"PK-current")
        release_export.write_release_manifest(root, pptx_path=pptx, status="released")

        cached_path, _sha, manifest = release_export.resolve_cached_released_pptx(root)
        self.assertEqual(pptx.resolve(), Path(cached_path).resolve())
        self.assertEqual(
            release_export.project_export_revision(root)["sha256"],
            manifest["export_revision_sha256"],
        )

        # Assets are outside the legacy source revision, but still affect PPTX.
        (root / "images" / "figure.png").write_bytes(b"image-two")
        with self.assertRaisesRegex(release_export.ReleaseExportError, "export inputs changed"):
            release_export.resolve_cached_released_pptx(root)

    def test_rebuild_uses_cached_release_without_compiling(self):
        from tasks import deck_editor, release_export

        root = Path(tempfile.mkdtemp())
        (root / "html_output").mkdir()
        (root / "html_output" / "slide_01.html").write_text("<main>one</main>", encoding="utf-8")
        pptx = root / "exports" / "releases" / "r1" / "presentation.pptx"
        pptx.parent.mkdir(parents=True)
        pptx.write_bytes(b"PK-current")
        release_export.write_release_manifest(root, pptx_path=pptx, status="released")

        with mock.patch("tasks.html_to_pptx.finalize_compile_html") as compile_mock:
            result = deck_editor.rebuild_pptx(root, "proj-cache")
        compile_mock.assert_not_called()
        self.assertTrue(result["cache_hit"])
        self.assertEqual(str(pptx.resolve()), str(Path(result["pptx"]).resolve()))

    def test_ensure_release_pdf_uses_impress_when_no_html(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "deck.pptx"
        pptx.write_bytes(b"PK")
        calls: list[str] = []

        def fake_pptx(_pptx, pdf_path):
            calls.append("pptx")
            pdf_path.write_bytes(b"%PDF-pptx")

        with mock.patch.object(release_export, "_pdf_from_pptx", side_effect=fake_pptx):
            out = release_export.ensure_release_pdf(pptx, "sha", root)
        self.assertEqual(["pptx"], calls)
        self.assertEqual(b"%PDF-pptx", Path(out).read_bytes())
        stamp = Path(str(out) + ".source_sha256").read_text(encoding="utf-8")
        self.assertIn("html-preview-v10", stamp)
        self.assertIn("pptx", stamp)

    def test_fontconfig_aliases_office_faces(self):
        from tasks.release_export import _write_fontconfig

        root = Path(tempfile.mkdtemp())
        fonts = root / "fonts"
        fonts.mkdir()
        conf = root / "fonts.conf"
        _write_fontconfig(conf, fonts)
        text = conf.read_text(encoding="utf-8")
        self.assertIn("Source Serif 4", text)
        self.assertIn("Source Sans 3", text)
        self.assertIn("<string>Georgia</string>", text)
        self.assertIn("<string>Arial</string>", text)
        self.assertIn("<family>sans-serif</family>", text)
        self.assertNotIn("/usr/local/share/fonts/sunairum", text)

    def test_ensure_release_pdf_falls_back_to_impress_when_html_fails(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "deck.pptx"
        pptx.write_bytes(b"PK")
        html_dir = root / "html_output"
        html_dir.mkdir()
        (html_dir / "slide_01.html").write_text(
            "<section class='slide'></section>", encoding="utf-8"
        )
        calls: list[str] = []

        def fake_pptx(_pptx, pdf_path):
            calls.append("pptx")
            pdf_path.write_bytes(b"%PDF-pptx")

        with mock.patch(
            "tasks.html_pdf.pdf_from_html_dir", side_effect=RuntimeError("no chromium")
        ), mock.patch.object(release_export, "_pdf_from_pptx", side_effect=fake_pptx):
            out = release_export.ensure_release_pdf(pptx, "sha", root)
        self.assertEqual(["pptx"], calls)
        self.assertEqual(b"%PDF-pptx", Path(out).read_bytes())


if __name__ == "__main__":
    unittest.main()
