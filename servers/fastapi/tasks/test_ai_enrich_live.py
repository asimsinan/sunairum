"""Live AI enrich during materialize (per-slide, shared budget)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestAiEnrichLive(unittest.TestCase):
    def test_enrich_one_skips_when_image_present(self):
        from tasks import free_design_pipeline as fdp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            (svg_dir / "slide_02.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<image href="../images/x.png" width="10" height="10"/>'
                "</svg>\n",
                encoding="utf-8",
            )
            out = fdp._enrich_one_slide_ai_figure(
                slide={"slide": 2, "role": "content", "title": "T"},
                storage_dir=str(root),
                svg_dir=str(svg_dir),
                color_palette={"primary": "#000", "accent": "#f00"},
            )
            self.assertEqual(out.get("status"), "skipped")
            self.assertEqual(out.get("reason"), "already_has_image")

    def test_enrich_one_skips_without_reserved_figure_slot(self):
        from tasks import free_design_pipeline as fdp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            (svg_dir / "slide_03.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
                '<text x="40" y="80">Dense card layout</text>'
                "</svg>\n",
                encoding="utf-8",
            )
            out = fdp._enrich_one_slide_ai_figure(
                slide={"slide": 3, "role": "content", "title": "HERO Changes"},
                storage_dir=str(root),
                svg_dir=str(svg_dir),
                color_palette={"primary": "#000", "accent": "#f00"},
            )
            self.assertEqual(out.get("status"), "skipped")
            self.assertEqual(out.get("reason"), "no_figure_slot")
            self.assertNotIn("<image", (svg_dir / "slide_03.svg").read_text(encoding="utf-8"))

    def test_count_existing_ai_enrich_pngs(self):
        from tasks import free_design_pipeline as fdp

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            images = root / "images"
            svg_dir.mkdir()
            images.mkdir()
            (images / "ai_enrich_slide_03.png").write_bytes(b"x")
            (images / "ai_enrich_slide_05.png").write_bytes(b"y")
            (images / "other.png").write_bytes(b"z")
            self.assertEqual(
                fdp._count_existing_ai_enrich_images(str(svg_dir), str(root)),
                2,
            )

    def test_enrich_requires_slot_and_respects_max_new(self):
        from tasks import free_design_pipeline as fdp

        with_slot = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
            '<text data-role="title">Hi</text>'
            '<g data-sunairum-figure-slot="1" data-x="700" data-y="150" '
            'transform="translate(700, 150)">'
            '<rect x="0" y="0" width="520" height="400" fill="none"/></g>'
            "</svg>\n"
        )

        def fake_generate(*, prompt, output_path, aspect_ratio="16:9", **_kwargs):
            Path(output_path).write_bytes(b"png")
            return output_path

        slides = [
            {"slide": 2, "role": "content", "title": "A"},
            {"slide": 3, "role": "content", "title": "B"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg_output"
            svg_dir.mkdir()
            for n in (2, 3):
                (svg_dir / f"slide_{n:02d}.svg").write_text(with_slot, encoding="utf-8")
            with mock.patch(
                "tasks.image_settings.generate_presentation_image",
                side_effect=fake_generate,
            ):
                first = fdp._enrich_one_slide_ai_figure(
                    slide=slides[0],
                    storage_dir=str(root),
                    svg_dir=str(svg_dir),
                    color_palette={"primary": "#000", "accent": "#f00"},
                )
                # Remaining budget 0 → gap-fill places nothing more.
                second = fdp.enrich_ai_figures(
                    slides=slides,
                    storage_dir=str(root),
                    svg_dir=str(svg_dir),
                    image_source="ai",
                    color_palette={"primary": "#000", "accent": "#f00"},
                    max_new=0,
                    skip_slides={2} if first.get("status") == "placed" else set(),
                )
            self.assertEqual(first.get("status"), "placed", first)
            self.assertEqual(second.get("placed"), [])
            self.assertIn('data-sunairum-image-source="ai"', (svg_dir / "slide_02.svg").read_text())
            self.assertNotIn("<image", (svg_dir / "slide_03.svg").read_text())


if __name__ == "__main__":
    unittest.main()
