import json
import tempfile
import unittest
from pathlib import Path

from tasks.scene_candidate_store import record_scene_candidate


class SceneCandidateStoreTests(unittest.TestCase):
    def test_whole_slide_replacement_can_never_be_selected(self):
        from tasks.scene_candidate_store import record_scene_candidate

        root = Path(tempfile.mkdtemp())
        with self.assertRaisesRegex(ValueError, "whole-slide replacement"):
            record_scene_candidate(
                root,
                slide_number=1,
                stage="emergency_slide_fallback",
                html="<html></html>",
                valid=True,
                selected=True,
            )

    def test_preserves_creative_and_marks_later_selection_truthfully(self):
        root = Path(tempfile.mkdtemp())
        first = record_scene_candidate(
            root,
            slide_number=3,
            stage="creative_normalized",
            html="<html>creative</html>",
            valid=False,
            findings=["runtime_text_overflow"],
        )
        second = record_scene_candidate(
            root,
            slide_number=3,
            stage="creative_repaired",
            html="<html>repaired</html>",
            valid=True,
            selected=True,
        )
        folder = root / "validation" / "candidates" / "slide_03"
        self.assertTrue((folder / first["html"]).is_file())
        self.assertTrue((folder / second["html"]).is_file())
        index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
        self.assertFalse(index["candidates"][0]["selected"])
        self.assertTrue(index["candidates"][1]["selected"])
        self.assertEqual(second["sha256"], index["selected_sha256"])


if __name__ == "__main__":
    unittest.main()
