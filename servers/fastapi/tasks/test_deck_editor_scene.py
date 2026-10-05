"""Scene-v2 editor artifact operations stay aligned across a reorder."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tasks.deck_editor import reorder_slides
from tasks.html_constitution import wrap_slide_fragment


class DeckEditorSceneTests(unittest.TestCase):
    def test_reorder_moves_scene_notes_and_rewrites_page_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for dirname in ("html_output", "preview", "scene", "notes", "validation"):
                (root / dirname).mkdir()
            for number, marker in ((1, "alpha"), (2, "beta")):
                stem = f"slide_{number:02d}"
                html = wrap_slide_fragment(
                    f'<div data-marker="{marker}">{marker}</div>'
                    f'<span data-sunairum-page-number="1">{number}/2</span>'
                )
                (root / "html_output" / f"{stem}.html").write_text(html, encoding="utf-8")
                (root / "preview" / f"{stem}.png").write_bytes(b"old")
                (root / "scene" / f"{stem}.json").write_text(
                    json.dumps({"version": "scene_layout_v2", "marker": marker}),
                    encoding="utf-8",
                )
                (root / "notes" / f"{stem}.md").write_text(f"note-{marker}", encoding="utf-8")

            def fake_preview(_html: str, path: str) -> bool:
                Path(path).write_bytes(b"new-preview")
                return True

            with patch("tasks.html_pipeline._render_preview_png", side_effect=fake_preview):
                names = reorder_slides(root, ["slide_02.html", "slide_01.html"])

            self.assertEqual(["slide_01.html", "slide_02.html"], names)
            first = (root / "html_output" / "slide_01.html").read_text(encoding="utf-8")
            second = (root / "html_output" / "slide_02.html").read_text(encoding="utf-8")
            self.assertIn('data-marker="beta"', first)
            self.assertIn(">1/2<", first)
            self.assertIn('data-marker="alpha"', second)
            self.assertIn(">2/2<", second)
            self.assertEqual("beta", json.loads((root / "scene" / "slide_01.json").read_text())["marker"])
            self.assertEqual("note-beta", (root / "notes" / "slide_01.md").read_text())
            self.assertEqual(b"new-preview", (root / "preview" / "slide_01.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
