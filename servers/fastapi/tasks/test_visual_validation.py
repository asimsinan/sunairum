import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from visual_validation import _image_tags, validate_provenance


class VisualValidationTests(unittest.TestCase):
    def _storage(self, image_tag: str, *, manifest_ratio: float = 2.4048) -> Path:
        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        image_dir = root / "images"
        pdf_dir = root / "sources" / "pdf_images"
        svg_dir.mkdir()
        image_dir.mkdir()
        pdf_dir.mkdir(parents=True)

        image = image_dir / "figure.png"
        image.write_bytes(b"deterministic-test-image")
        manifest = {
            "figures": [{
                "file": "figure.png",
                "page": 1,
                "width": 2400,
                "height": 998,
                "ratio": manifest_ratio,
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }],
        }
        (pdf_dir / "figure_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (svg_dir / "slide_01.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">{image_tag}</svg>',
            encoding="utf-8",
        )
        return root

    def _plan(self) -> list[dict]:
        return [{
            "title": "PDF visual",
            "primary_visual_source": "pdf",
            "visual_plan": {"allow_figure": True},
            "visual_slots": [{"x": 100, "y": 100, "width": 400, "height": 200}],
            "rules": {"max_non_background_images": 1},
        }]

    def _pdf_tag(self, **attributes: str) -> str:
        values = {
            "href": "../images/figure.png",
            "x": "100",
            "y": "100",
            "width": "400",
            "height": "200",
            "data-sunairum-visual-id": "primary_visual",
            "data-sunairum-source-type": "pdf",
            "data-sunairum-source-file": "figure.png",
            "preserveAspectRatio": "xMidYMid meet",
        }
        values.update(attributes)
        return "<image " + " ".join(f'{key}="{value}"' for key, value in values.items()) + " />"

    def test_ancestor_transform_is_included_in_effective_geometry(self):
        tags = _image_tags(
            '<svg xmlns="http://www.w3.org/2000/svg"><g transform="translate(20 30)">'
            '<image x="10" y="15" width="100" height="50" /></g></svg>'
        )
        self.assertEqual({"x": 30.0, "y": 45.0, "width": 100.0, "height": 50.0}, tags[0]["effective_geometry"])

    def test_pdf_nonuniform_effective_scale_is_blocked(self):
        issues = validate_provenance(
            str(self._storage(self._pdf_tag(transform="scale(1 3.7594)"))),
            self._plan(),
            "pdf",
        )
        self.assertIn("image-nonuniform-transform", {issue["category"] for issue in issues})

    def test_pdf_shear_is_blocked(self):
        issues = validate_provenance(
            str(self._storage(self._pdf_tag(transform="matrix(1 0.2 0 1 0 0)"))),
            self._plan(),
            "pdf",
        )
        self.assertIn("image-nonuniform-transform", {issue["category"] for issue in issues})

    def test_pdf_none_and_ratio_mismatch_are_blocked(self):
        issues = validate_provenance(
            str(self._storage(self._pdf_tag(width="300", height="300", preserveAspectRatio="none"))),
            self._plan(),
            "pdf",
        )
        categories = {issue["category"] for issue in issues}
        self.assertIn("image-invalid-fit-policy", categories)
        self.assertIn("image-aspect-ratio-mismatch", categories)

    def test_pdf_meet_allows_different_slot_ratio_without_distortion_error(self):
        issues = validate_provenance(
            str(self._storage(self._pdf_tag(width="300", height="300"))),
            self._plan(),
            "pdf",
        )
        categories = {issue["category"] for issue in issues}
        self.assertNotIn("image-aspect-ratio-mismatch", categories)
        self.assertNotIn("image-invalid-fit-policy", categories)

    def test_pdf_only_flags_primary_ai_fallback_even_when_large(self):
        tag = self._pdf_tag(
            href="../images/figure.png",
            width="1280",
            height="720",
            **{
                "data-sunairum-source-type": "ai",
                "data-sunairum-source-file": "ai.png",
            },
        )
        issues = validate_provenance(str(self._storage(tag)), self._plan(), "pdf")
        self.assertIn("pdf-fallback-forbidden", {issue["category"] for issue in issues})


if __name__ == "__main__":
    unittest.main()
