"""Selected figures get an injected slot when Executor omitted one."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class FigureSlotInjectTests(unittest.TestCase):
    def test_injects_slot_when_missing(self):
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        images = root / "images"
        sources = root / "sources" / "pdf_images"
        svg_dir.mkdir(parents=True)
        images.mkdir()
        sources.mkdir(parents=True)
        # Minimal PNG
        png = sources / "fig.png"
        png.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
        )
        (sources / "index.json").write_text(
            '{"figures":[{"id":"pdf-page-4-picture-2","file":"fig.png"}]}',
            encoding="utf-8",
        )
        (svg_dir / "slide_03.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#FFFFFF"/>'
            '<text x="64" y="80">No slot here</text></svg>',
            encoding="utf-8",
        )
        # Also copy via resolve path used by pipeline
        shutil.copy2(png, images / "keep.png")

        placed = place_selected_assets(
            slides=[
                {
                    "slide": 3,
                    "role": "content",
                    "figure_id": "pdf-page-4-picture-2",
                }
            ],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=None,
            figure_render_mode="exact",
            table_render_mode="exact",
            color_palette={},
        )
        svg = (svg_dir / "slide_03.svg").read_text(encoding="utf-8")
        self.assertTrue(placed["figures"] or "injected" in str(placed.get("warnings")))
        if placed["figures"]:
            self.assertIn("pdf-page-4-picture-2", svg)
            self.assertIn("<image", svg)

    def test_ai_replica_figure_mode_uses_exact_copy(self):
        """ai_replica is ignored — always copy the PDF crop."""
        from tasks.free_design_pipeline import place_selected_assets

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        images = root / "images"
        sources = root / "sources" / "pdf_images"
        svg_dir.mkdir(parents=True)
        images.mkdir()
        sources.mkdir(parents=True)
        png = sources / "fig.png"
        png.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
        )
        (sources / "index.json").write_text(
            '{"figures":[{"id":"pdf-page-3-picture-1","file":"fig.png"}]}',
            encoding="utf-8",
        )
        (svg_dir / "slide_05.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-sunairum-figure-slot="1" data-sunairum-figure-id="pdf-page-3-picture-1" '
            'transform="translate(700,150)">'
            '<rect width="520" height="400" fill="none"/></g></svg>',
            encoding="utf-8",
        )

        placed = place_selected_assets(
            slides=[
                {
                    "slide": 5,
                    "role": "content",
                    "figure_id": "pdf-page-3-picture-1",
                }
            ],
            storage_dir=str(root),
            svg_dir=str(svg_dir),
            evidence_bundle=None,
            figure_render_mode="ai_replica",
            table_render_mode="exact",
            color_palette={"primary": "#0B3B6F", "accent": "#E07A2F"},
        )
        self.assertEqual(1, len(placed["figures"]))
        self.assertEqual("exact", placed["figures"][0]["mode"])
        dest = images / "pdf_pdf-page-3-picture-1.png"
        self.assertTrue(dest.exists())
        self.assertEqual(png.read_bytes(), dest.read_bytes())
        svg = (svg_dir / "slide_05.svg").read_text(encoding="utf-8")
        self.assertIn("<image", svg)
        self.assertIn("pdf-page-3-picture-1", svg)


if __name__ == "__main__":
    unittest.main()
