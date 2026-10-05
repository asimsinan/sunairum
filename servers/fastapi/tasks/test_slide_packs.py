"""Per-slide design pack persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    from tasks.free_design_pipeline import (
        extract_executor_design_pack,
        materialize_free_design_slides,
        persist_slide_design_packs,
    )
    from tasks.authoring_budget import AuthoringBudget
except ModuleNotFoundError:  # pragma: no cover
    from free_design_pipeline import (  # type: ignore
        extract_executor_design_pack,
        materialize_free_design_slides,
        persist_slide_design_packs,
    )
    from authoring_budget import AuthoringBudget  # type: ignore


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


class SlidePackPersistTests(unittest.TestCase):
    def test_persist_writes_scoped_pack(self):
        root = Path(tempfile.mkdtemp())
        slides = [{"slide": 2, "body_md": ""}]
        paths = persist_slide_design_packs(str(root), _MINI_SPEC, slides)
        self.assertEqual(1, len(paths))
        pack_path = root / "slide_packs" / "P02.md"
        self.assertTrue(pack_path.is_file())
        text = pack_path.read_text(encoding="utf-8")
        self.assertIn("### P02: Why Vehicle Routing", text)
        self.assertNotIn("### P03:", text)
        self.assertIn("Speak about routing", text)

    def test_materialize_writes_packs(self):
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        gt = MagicMock()
        gt.sanitize_flat_structure_metadata.side_effect = lambda s: s
        gt.sanitize_presentation_chrome.side_effect = lambda s, **_kw: s
        gt.sanitize_project_geometry_lengths.side_effect = lambda s: s
        gt.finalize_svg_document.side_effect = lambda s: s
        gt.minimal_slide_svg.return_value = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>\n'
        )
        slides = [
            {
                "slide": 2,
                "total_slides": 3,
                "role": "content",
                "title": "Why Vehicle Routing",
                "body_md": "",
                "content": {},
            }
        ]
        materialize_free_design_slides(
            slides=slides,
            design_spec_md=_MINI_SPEC,
            spec_lock_md="# lock",
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            color_palette={"background": "#fff", "primary": "#000", "accent": "#f00", "body_text": "#111"},
            budget=AuthoringBudget(limit=4),
            call_text=None,
            gt=gt,
        )
        pack = (root / "slide_packs" / "P02.md").read_text(encoding="utf-8")
        self.assertIn("### P02:", pack)
        self.assertNotIn("### P01:", pack)
        # Direct extract must match persisted body shape for the same slide.
        expected = extract_executor_design_pack(_MINI_SPEC, 2)
        self.assertEqual(expected.strip(), pack.strip())


if __name__ == "__main__":
    unittest.main()
