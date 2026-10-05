"""Regenerate selected slide with human feedback."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


_MINI_SPEC = """<!-- sunairum-schema: design-spec/v1 -->
# Demo - Design Spec

## IX. Content Outline

### P01: Title
- **Title**: Paper Title
- **Role**: title
- **Content**: Cover

### P05: Loop
- **Title**: Destroy-and-repair loop
- **Role**: content
- **Content**:
  - Represent the instance
  - Retrieve candidates
  - Score repairs
- **Layout**: Process on left; figure on right
- **Figure:** `pdf-page-3-picture-1`

### P10: Scale
- **Title**: Scale effects
- **Role**: content
- **Content**: Homberger cost rises with fleet size.
- **Layout**: Chart with sidebar cards
"""


class ApplyFeedbackIrTests(unittest.TestCase):
    def test_feedback_attached_and_tighten_shortens_bodies(self):
        from tasks.free_design_pipeline import apply_human_feedback_to_slide

        slide = {
            "slide": 10,
            "title": "Scale",
            "cards": [
                {
                    "title": "Scale",
                    "body": "A" * 200,
                }
            ],
            "content": {"BODY": "B" * 300},
        }
        out = apply_human_feedback_to_slide(slide, "Tighten copy on the sidebar cards")
        self.assertEqual("Tighten copy on the sidebar cards", out["human_feedback"])
        self.assertLessEqual(len(out["cards"][0]["body"]), 121)
        self.assertLessEqual(len(out["content"]["BODY"]), 221)

    def test_prompt_includes_human_feedback_block(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        slide = {
            "slide": 5,
            "role": "content",
            "title": "Loop",
            "content": {"BODY": "Steps"},
            "figure_id": "pdf-page-3-picture-1",
            "human_feedback": "Keep steps on the left only; do not cover the figure.",
        }
        prompt = build_executor_slide_prompt(
            slide=slide,
            spec_lock_md="lock",
            design_spec_md=_MINI_SPEC,
        )
        self.assertIn("## Human feedback (HARD", prompt)
        self.assertIn("Keep steps on the left only", prompt)


class RematerializeFeedbackTests(unittest.TestCase):
    def test_rematerialize_passes_feedback_only_for_target(self):
        from tasks import free_design_pipeline as fdp

        root = Path(tempfile.mkdtemp())
        (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
        (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        # Pre-existing other slide must stay untouched.
        other = svg_dir / "slide_10.svg"
        other.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            "<text>keep-me</text></svg>\n",
            encoding="utf-8",
        )
        other_mtime = other.stat().st_mtime_ns
        seen: dict = {}

        def _fake_materialize(**kwargs):
            seen["slide_feedback"] = kwargs.get("slide_feedback")
            seen["slide_filter"] = kwargs.get("slide_filter")
            seen["slides"] = [int(s["slide"]) for s in kwargs.get("slides") or []]
            for slide in kwargs.get("slides") or []:
                n = int(slide["slide"])
                path = svg_dir / f"slide_{n:02d}.svg"
                fb = str(slide.get("human_feedback") or "")
                path.write_text(
                    f'<svg xmlns="http://www.w3.org/2000/svg"><text>{fb or "painted"}</text></svg>\n',
                    encoding="utf-8",
                )
            return {
                "authored": [{"slide": 5, "source": "model"}],
                "budget_spent": 0,
            }

        with mock.patch.object(fdp, "materialize_free_design_slides", side_effect=_fake_materialize):
            out = fdp.rematerialize_free_design_slides(
                str(root),
                [5],
                slide_feedback={5: "Cards covering figure — keep left only"},
                call_text=None,
                gt=mock.Mock(),
            )
        self.assertEqual([5], out.get("rebuilt"))
        self.assertEqual({5}, seen.get("slide_filter"))
        self.assertEqual(
            {5: "Cards covering figure — keep left only"},
            seen.get("slide_feedback"),
        )
        self.assertEqual([5], seen.get("slides"))
        self.assertEqual(other_mtime, other.stat().st_mtime_ns)
        painted = (svg_dir / "slide_05.svg").read_text(encoding="utf-8")
        self.assertIn("keep left only", painted)


class RegenerateApiTests(unittest.TestCase):
    def test_empty_feedback_rejected(self):
        from tasks.regenerate_slide import validate_regenerate_slide_request

        root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError) as ctx:
            validate_regenerate_slide_request(
                str(root), slide=5, feedback="   ", generation_active=False
            )
        self.assertTrue(str(ctx.exception).startswith("bad_request:"))

    def test_persists_request_artifact(self):
        from tasks.regenerate_slide import validate_regenerate_slide_request

        root = Path(tempfile.mkdtemp())
        (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
        (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
        payload = validate_regenerate_slide_request(
            str(root),
            slide=5,
            feedback="Keep steps on the left only.",
            generation_active=False,
        )
        self.assertEqual(5, payload["slide"])
        self.assertIn("Keep steps", payload["feedback"])
        req_path = root / "validation" / "regenerate_slide_request.json"
        self.assertTrue(req_path.is_file())
        disk = json.loads(req_path.read_text(encoding="utf-8"))
        self.assertEqual(5, disk["slide"])

    def test_unknown_slide_rejected(self):
        from tasks.regenerate_slide import validate_regenerate_slide_request

        root = Path(tempfile.mkdtemp())
        (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
        (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            validate_regenerate_slide_request(
                str(root), slide=99, feedback="Fix overlaps", generation_active=False
            )
        self.assertTrue(str(ctx.exception).startswith("bad_request:"))

    def test_active_generation_blocked(self):
        from tasks.regenerate_slide import validate_regenerate_slide_request

        root = Path(tempfile.mkdtemp())
        (root / "design_spec.md").write_text(_MINI_SPEC, encoding="utf-8")
        (root / "spec_lock.md").write_text("# lock\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            validate_regenerate_slide_request(
                str(root), slide=5, feedback="Fix overlaps", generation_active=True
            )
        self.assertTrue(str(ctx.exception).startswith("conflict:"))


if __name__ == "__main__":
    unittest.main()
