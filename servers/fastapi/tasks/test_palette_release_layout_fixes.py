"""Palette lock, release manifest, HTML host-lane placement."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tasks.deck_prompt_context import palette_lock_block
from tasks.free_design_pipeline import write_settings_obedience
from tasks.release_export import ReleaseExportError, resolve_released_pptx, write_release_manifest


class PaletteLockBlockTests(unittest.TestCase):
    def test_formats_hex_swatches(self):
        block = palette_lock_block(
            {
                "background": "#FFFFFF",
                "primary": "#1A365D",
                "accent": "#3182CE",
            }
        )
        self.assertIn("background=#FFFFFF", block)
        self.assertIn("Deck palette (locked)", block)


class FinalizeCompileTerminalStatusTests(unittest.TestCase):
    def test_finalize_compile_writes_done_not_completed(self):
        from tasks.generator_agent import finalize_compile

        root = Path(tempfile.mkdtemp())
        (root / "html_output").mkdir()
        written: list[tuple] = []

        def _fake_write(storage_dir, status, progress=0, **kwargs):
            written.append((status, progress, kwargs.get("message_key")))

        generate_task = types.ModuleType("tasks.generate_task")
        generate_task.write_status = _fake_write
        generate_task.send_ws_message = lambda *_args, **_kwargs: None

        with (
            patch.dict(sys.modules, {"tasks.generate_task": generate_task}),
            patch(
                "tasks.html_to_pptx.finalize_compile_html",
                return_value={
                    "ok": True,
                    "release_manifest": {"status": "released"},
                },
            ),
            patch("asyncio.new_event_loop") as loop_factory,
        ):
            loop = loop_factory.return_value
            loop.run_until_complete.return_value = None
            result = finalize_compile(str(root), project_id="p1", run_id="r1")

        self.assertTrue(result.get("ok"))
        terminal = [w for w in written if w[1] == 100]
        self.assertTrue(terminal)
        self.assertEqual(terminal[-1][0], "done")


class ReleaseManifestTests(unittest.TestCase):
    def test_write_and_resolve_released_pptx(self):
        root = Path(tempfile.mkdtemp())
        exports = root / "exports"
        exports.mkdir(parents=True)
        pptx = exports / "presentation.pptx"
        pptx.write_bytes(b"PK\x03\x04fake")
        (root / "validation").mkdir(parents=True)
        (root / "validation" / "run_manifest.json").write_text(
            json.dumps({"run_id": "r1"}), encoding="utf-8"
        )
        write_release_manifest(
            root,
            pptx_path=pptx,
            project_id="p1",
            run_id="r1",
            mode="html_deckhtml",
        )
        path, _sha, _manifest = resolve_released_pptx(str(root))
        self.assertEqual(Path(path).resolve(), pptx.resolve())

    def test_release_becomes_stale_when_html_or_notes_change(self):
        root = Path(tempfile.mkdtemp())
        (root / "exports").mkdir()
        (root / "html_output").mkdir()
        (root / "notes").mkdir()
        pptx = root / "exports" / "presentation.pptx"
        pptx.write_bytes(b"PK\x03\x04fake")
        slide = root / "html_output" / "slide_01.html"
        slide.write_text("<html>one</html>", encoding="utf-8")
        (root / "notes" / "slide_01.md").write_text("Original note", encoding="utf-8")
        write_release_manifest(root, pptx_path=pptx, project_id="p1")
        resolve_released_pptx(root)

        slide.write_text("<html>changed</html>", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseExportError, "stale"):
            resolve_released_pptx(root)


class SettingsObedienceTablePlacementTests(unittest.TestCase):
    def test_placed_tables_clear_missing(self):
        root = Path(tempfile.mkdtemp())
        validation = root / "validation"
        validation.mkdir(parents=True)
        report = write_settings_obedience(
            storage_dir=str(root),
            validation_dir=str(validation),
            result_data={
                "selected_table_ids": ["t1"],
                "grounding_mode": "pdf_strict",
                "proactive_speaker_notes": False,
            },
            placement={"tables": [{"slide": 4, "table_id": "t1"}], "figures": [], "errors": []},
        )
        self.assertEqual(report.get("missing_table_ids"), [])


if __name__ == "__main__":
    unittest.main()
