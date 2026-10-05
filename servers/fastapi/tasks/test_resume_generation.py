"""Resume after stop: gap detection + cancelled→active status transition."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tasks import free_design_pipeline as fdp
from tasks.generate_task import write_status


_MINI_SPEC = """\
# Demo - Design Spec

## I. Project Information

- **Core message:** Demo

## IX. Content Outline

### P01: Title

- **Title:** Title
- **Content:**
  - Cover

### P02: Why Vehicle Routing

- **Title:** Why Vehicle Routing
- **Content:**
  - Only P02 body

### P03: Closing

- **Title:** Closing
- **Content:**
  - End

## X. Speaker Notes

- **P02:** Speak about routing.
"""


class ResumeHelpersTest(unittest.TestCase):
    def test_missing_slide_numbers_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp) / "svg_output"
            svg_dir.mkdir()
            (svg_dir / "slide_01.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>\n',
                encoding="utf-8",
            )
            (svg_dir / "slide_02.svg").write_text("tiny", encoding="utf-8")  # too small
            slides = [{"slide": 1}, {"slide": 2}, {"slide": 3}]
            missing = fdp.missing_slide_numbers(slides, str(svg_dir))
            self.assertEqual(missing, [2, 3])

    def test_can_resume_requires_cancelled_and_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "status.json").write_text(
                json.dumps({"status": "cancelled", "progress": 54}),
                encoding="utf-8",
            )
            self.assertFalse(fdp.can_resume_free_design(str(root))["ok"])

            (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
            (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            (svg_dir / "slide_01.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>\n',
                encoding="utf-8",
            )
            info = fdp.can_resume_free_design(str(root))
            self.assertTrue(info["ok"])
            self.assertEqual(info["existing_slides"], [1])
            self.assertEqual(info["missing_slides"], [2, 3])
            self.assertEqual(info["missing_notes"], [1])
            self.assertFalse(info["notes_complete"])

    def test_missing_note_numbers_and_keep_existing(self) -> None:
        from tasks import speaker_notes as sn

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            notes_dir = root / "notes"
            svg_dir.mkdir()
            notes_dir.mkdir()
            for n in (1, 2):
                (svg_dir / f"slide_{n:02d}.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"></svg>\n',
                    encoding="utf-8",
                )
            (notes_dir / "slide_01.md").write_text(
                "Welcome everyone to this short talk about routing.\n",
                encoding="utf-8",
            )
            self.assertEqual(sn.missing_note_numbers(root), [2])
            self.assertFalse(sn.notes_complete_for_svgs(root))
            (notes_dir / "slide_02.md").write_text(
                "Next we cover why workload equity matters in repair.\n",
                encoding="utf-8",
            )
            self.assertEqual(sn.missing_note_numbers(root), [])
            self.assertTrue(sn.notes_complete_for_svgs(root))

            with mock.patch.object(sn, "notes_enabled", return_value=True):
                kept = sn.maybe_generate_speaker_notes_for_project(
                    root, call_text=None, keep_existing=True
                )
            self.assertEqual(kept.get("status"), "kept")
            self.assertTrue(kept.get("kept_existing"))

    def test_worker_accepts_queued_handoff_after_api_flip(self) -> None:
        """API writes status=queued before Celery runs; worker must not reject that."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
            (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
            (root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "queued",
                        "progress": 54,
                        "message_key": "status_resuming",
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(fdp.can_resume_free_design(str(root))["ok"])
            self.assertTrue(fdp.can_resume_free_design(str(root), worker=True)["ok"])

    def test_write_status_can_leave_cancelled_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_status(tmp, "cancelled", 54, message="stopped", message_key="status_cancelled")
            write_status(tmp, "queued", 54, message="Resume queued", message_key="status_resuming")
            payload = json.loads(Path(tmp, "status.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "queued")
            self.assertEqual(payload["message_key"], "status_resuming")

    def test_materialize_keep_existing_skips_authored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            kept = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                '<text>kept</text></svg>\n'
            )
            (svg_dir / "slide_01.svg").write_text(kept, encoding="utf-8")
            gt = mock.Mock()
            gt.sanitize_flat_structure_metadata.side_effect = lambda s: s
            gt.sanitize_presentation_chrome.side_effect = lambda s, **_kw: s
            gt.sanitize_project_geometry_lengths.side_effect = lambda s: s
            gt.finalize_svg_document.side_effect = lambda s: s
            gt.minimal_slide_svg.return_value = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                "<text>new</text></svg>\n"
            )
            slides = [
                {
                    "slide": 1,
                    "total_slides": 2,
                    "role": "title",
                    "title": "One",
                    "body_md": "",
                    "content": {},
                },
                {
                    "slide": 2,
                    "total_slides": 2,
                    "role": "content",
                    "title": "Two",
                    "body_md": "",
                    "content": {},
                },
            ]
            from tasks.authoring_budget import AuthoringBudget

            out = fdp.materialize_free_design_slides(
                slides=slides,
                design_spec_md=_MINI_SPEC,
                spec_lock_md="# lock",
                storage_dir=str(root),
                svg_dir=str(svg_dir),
                color_palette={
                    "background": "#fff",
                    "primary": "#000",
                    "accent": "#f00",
                    "body_text": "#111",
                },
                budget=AuthoringBudget(limit=4),
                call_text=None,
                gt=gt,
                keep_existing=True,
            )
            self.assertFalse(out.get("cancelled"))
            self.assertEqual((svg_dir / "slide_01.svg").read_text(encoding="utf-8"), kept)
            self.assertTrue((svg_dir / "slide_02.svg").is_file())
            authored_nums = {int(item["slide"]) for item in out.get("authored") or []}
            self.assertNotIn(1, authored_nums)
            self.assertIn(2, authored_nums)

    def test_materialize_continues_with_scene_fallback_on_llm_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
            (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
            kept = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
                '<text>kept</text></svg>\n'
            )
            (svg_dir / "slide_01.svg").write_text(kept, encoding="utf-8")

            def _boom(_system: str, _user: str) -> str:
                raise RuntimeError("connection refused")

            from tasks.authoring_budget import AuthoringBudget

            out = fdp.materialize_free_design_slides(
                slides=[
                    {
                        "slide": 1,
                        "total_slides": 3,
                        "role": "title",
                        "title": "One",
                        "content": {},
                    },
                    {
                        "slide": 2,
                        "total_slides": 3,
                        "role": "content",
                        "title": "Two",
                        "content": {"BODY": "claim"},
                    },
                    {
                        "slide": 3,
                        "total_slides": 3,
                        "role": "closing",
                        "title": "Three",
                        "content": {},
                    },
                ],
                design_spec_md=_MINI_SPEC,
                spec_lock_md="# lock",
                storage_dir=str(root),
                svg_dir=str(svg_dir),
                color_palette={"primary": "#0B3B6F", "body_text": "#111"},
                budget=AuthoringBudget(limit=8),
                call_text=_boom,
                gt=None,
                keep_existing=True,
            )
            self.assertFalse(out.get("cancelled", False))
            self.assertFalse(out.get("llm_failed", False))
            self.assertEqual(3, len(out.get("authored") or []))
            self.assertTrue(all(
                (item.get("author_fallback") or {}).get("used")
                for item in out.get("authored") or []
            ))
            self.assertTrue(all(
                item.get("llm_calls") == 1
                for item in out.get("authored") or []
            ))
            self.assertTrue((root / "html_output" / "slide_02.html").is_file())
            self.assertTrue((root / "html_output" / "slide_03.html").is_file())
            self.assertFalse((svg_dir / "slide_02.svg").exists())
            self.assertFalse((svg_dir / "slide_03.svg").exists())
            self.assertEqual((svg_dir / "slide_01.svg").read_text(encoding="utf-8"), kept)
            (root / "status.json").write_text(
                json.dumps({"status": "error", "progress": 42, "message_key": "status_llm_unavailable"}),
                encoding="utf-8",
            )
            info = fdp.can_resume_free_design(str(root))
            self.assertTrue(info["ok"])
            self.assertEqual(info["missing_slides"], [])


if __name__ == "__main__":
    unittest.main()
