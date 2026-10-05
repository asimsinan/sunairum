"""Image source policy: PDF coerce, scratch enrich budget, prompt blocks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ImageSourcePolicyTests(unittest.TestCase):
    def test_pdf_strict_coerces_ai_to_both(self):
        from tasks.image_source_policy import coerce_image_source_for_grounding

        self.assertEqual(
            "both",
            coerce_image_source_for_grounding("ai", "pdf_strict"),
        )
        self.assertEqual(
            "both",
            coerce_image_source_for_grounding("both", "pdf_strict"),
        )

    def test_scratch_keeps_ai(self):
        from tasks.image_source_policy import coerce_image_source_for_grounding

        self.assertEqual("ai", coerce_image_source_for_grounding("ai", "scratch"))
        self.assertEqual("both", coerce_image_source_for_grounding("both", "scratch"))

    def test_enrich_budget_pdf_always_zero(self):
        from tasks.image_source_policy import normalize_ai_enrich_max_new

        self.assertEqual(
            0,
            normalize_ai_enrich_max_new(
                5, grounding_mode="pdf_strict", image_source="ai"
            ),
        )

    def test_enrich_budget_scratch_ai(self):
        from tasks.image_source_policy import normalize_ai_enrich_max_new

        self.assertEqual(
            3,
            normalize_ai_enrich_max_new(
                None, grounding_mode="scratch", image_source="ai"
            ),
        )
        self.assertEqual(
            0,
            normalize_ai_enrich_max_new(
                0, grounding_mode="scratch", image_source="ai"
            ),
        )
        self.assertEqual(
            6,
            normalize_ai_enrich_max_new(
                99, grounding_mode="scratch", image_source="ai"
            ),
        )
        self.assertEqual(
            0,
            normalize_ai_enrich_max_new(
                3, grounding_mode="scratch", image_source="both"
            ),
        )

    def test_visual_policy_scratch_asks_for_slots(self):
        from tasks.image_source_policy import visual_policy_prompt_block

        block = visual_policy_prompt_block("ai", grounding_mode="scratch")
        self.assertIn("figure-slot", block)
        self.assertIn("Image engine", block)

    def test_visual_policy_pdf_no_ai_enrich_pitch(self):
        from tasks.image_source_policy import visual_policy_prompt_block

        block = visual_policy_prompt_block("ai", grounding_mode="pdf_strict")
        self.assertIn("PDF assets", block)
        self.assertNotIn("Image engine", block)


class GenerateEditorImageTests(unittest.TestCase):
    def test_generate_ai_image_for_editor_writes_png(self):
        from tasks import deck_editor as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_generate(**kwargs):
                path = Path(kwargs["output_path"])
                path.write_bytes(b"\x89PNG\r\n\x1a\n")
                return str(path)

            with mock.patch.object(mod, "generate_ai_image_for_editor", wraps=mod.generate_ai_image_for_editor):
                with mock.patch(
                    "tasks.image_settings.resolve_image_config",
                    return_value={
                        "provider": "openai",
                        "model": "gpt-image-2",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-test",
                        "module": "image_backends.backend_openai",
                        "api_key_env": "OPENAI_API_KEY",
                        "base_url_env": "OPENAI_BASE_URL",
                        "model_env": "OPENAI_MODEL",
                    },
                ), mock.patch(
                    "tasks.image_settings.generate_presentation_image",
                    side_effect=fake_generate,
                ):
                    saved = mod.generate_ai_image_for_editor(
                        root,
                        prompt="soft abstract navy illustration",
                        aspect_ratio="4:3",
                        slide=2,
                    )
            path = Path(saved["abs_path"])
            self.assertTrue(path.is_file())
            self.assertTrue(saved["filename"].startswith("ai_editor_s02_"))
            self.assertEqual(saved["relative_path"], f"../images/{saved['filename']}")

    def test_generate_requires_prompt(self):
        from tasks.deck_editor import generate_ai_image_for_editor

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_ai_image_for_editor(tmp, prompt="  ")

    def test_generate_requires_image_engine(self):
        from tasks.deck_editor import generate_ai_image_for_editor

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "tasks.image_settings.resolve_image_config",
                side_effect=RuntimeError(
                    "an image API key is required: set it in Settings → Image engine"
                ),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    generate_ai_image_for_editor(tmp, prompt="hello")
            self.assertIn("Image engine", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
