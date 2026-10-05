"""Measured Scene copy-recovery contracts."""

from __future__ import annotations

import json
import unittest

from tasks.scene_copy_recovery import recover_scene_copy
from tasks.slide_scene import resolve_slide_scene


class SceneCopyRecoveryTests(unittest.TestCase):
    def test_accepts_bounded_shortening_and_preserves_card_order(self):
        slide = {
            "title": "A deliberately long title about retrieval and exact filtering",
            "core_message": "A long lede that can be expressed more directly without changing its claim.",
            "cards": [
                {"title": "Feature encoding", "body": "Each candidate carries spatial and workload context."},
                {"title": "Exact filtering", "body": "Capacity and time-window checks remain exact."},
            ],
        }

        def call(_system: str, _prompt: str) -> str:
            return json.dumps(
                {
                    "title": "Retrieval narrows exact evaluation",
                    "lede": "Approximate search reduces work without relaxing feasibility.",
                    "cards": [
                        {"title": "Feature encoding", "body": "Candidates retain spatial and workload context."},
                        {"title": "Exact filtering", "body": "Capacity and time windows remain exact."},
                    ],
                }
            )

        recovered = recover_scene_copy(
            slide=slide,
            scene=resolve_slide_scene(slide),
            diagnostics=["runtime_text_overflow: primary"],
            call_text=call,
        )
        self.assertIsNotNone(recovered)
        self.assertEqual("Feature encoding", recovered["cards"][0]["title"])
        self.assertEqual(2, len(recovered["cards"]))

    def test_rejects_over_budget_or_changed_card_count(self):
        slide = {"title": "Title", "cards": [{"title": "A", "body": "B"}]}
        recovered = recover_scene_copy(
            slide=slide,
            scene=resolve_slide_scene(slide),
            diagnostics=[],
            call_text=lambda _s, _p: json.dumps(
                {"title": "x" * 91, "lede": "", "cards": []}
            ),
        )
        self.assertIsNone(recovered)


if __name__ == "__main__":
    unittest.main()
