"""Slide transition setup: one named effect for all slides, or random."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class SlideTransitionNormalizeTests(unittest.TestCase):
    def test_off_disables(self):
        from tasks.slide_transitions import normalize_slide_transition

        self.assertIsNone(normalize_slide_transition(False, "fade"))
        self.assertIsNone(normalize_slide_transition(False, "random"))

    def test_on_defaults_to_fade_for_all_slides(self):
        from tasks.slide_transitions import DEFAULT_FIXED_TRANSITION, normalize_slide_transition

        self.assertEqual(normalize_slide_transition(True, None), DEFAULT_FIXED_TRANSITION)
        self.assertEqual(normalize_slide_transition(True, ""), DEFAULT_FIXED_TRANSITION)
        self.assertEqual(normalize_slide_transition(True, "unknown-fx"), DEFAULT_FIXED_TRANSITION)

    def test_named_and_random_pass_through(self):
        from tasks.slide_transitions import normalize_slide_transition

        self.assertEqual(normalize_slide_transition(True, "Wipe"), "wipe")
        self.assertEqual(normalize_slide_transition(True, "random"), "random")
        self.assertEqual(normalize_slide_transition(True, "page-curl-double"), "page-curl-double")


class ResolveSlideTransitionPrefsTests(unittest.TestCase):
    def test_reads_confirm_prefs(self):
        from tasks.speaker_notes import resolve_slide_transition

        root = Path(tempfile.mkdtemp())
        confirm = root / "confirm_ui"
        confirm.mkdir()
        (confirm / "result.json").write_text(
            json.dumps(
                {
                    "proactive_custom_animations": True,
                    "custom_animation_effect": "push",
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(resolve_slide_transition(root), "push")

    def test_off_even_if_effect_set(self):
        from tasks.speaker_notes import resolve_slide_transition

        root = Path(tempfile.mkdtemp())
        confirm = root / "confirm_ui"
        confirm.mkdir()
        (confirm / "result.json").write_text(
            json.dumps(
                {
                    "proactive_custom_animations": False,
                    "custom_animation_effect": "fade",
                }
            ),
            encoding="utf-8",
        )
        self.assertIsNone(resolve_slide_transition(root))


if __name__ == "__main__":
    unittest.main()
