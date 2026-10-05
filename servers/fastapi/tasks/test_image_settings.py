"""Image engine settings: provider normalize + resolve (UI-only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tasks.settings_validation import SettingsValidationError


class ImageSettingsTests(unittest.TestCase):
    def test_normalize_image_provider(self):
        from tasks.image_settings import normalize_image_provider

        self.assertEqual("openrouter", normalize_image_provider(""))
        self.assertEqual("openai", normalize_image_provider("openai_compatible"))
        with self.assertRaises(SettingsValidationError):
            normalize_image_provider("google")
        with self.assertRaises(SettingsValidationError):
            normalize_image_provider("gemini")

    def test_resolve_uses_saved_settings_only(self):
        from tasks import image_settings as mod

        fake = mock.Mock(
            image_provider="openai",
            image_model_name="gpt-image-2",
            image_base_url="https://api.openai.com/v1",
            image_api_key="sk-test",
        )
        with mock.patch("llm_client.get_active_settings", return_value=fake):
            cfg = mod.resolve_image_config()
        self.assertEqual("openai", cfg["provider"])
        self.assertEqual("gpt-image-2", cfg["model"])
        self.assertEqual("sk-test", cfg["api_key"])

    def test_resolve_fails_without_ui_key(self):
        from tasks import image_settings as mod

        fake = mock.Mock(
            image_provider="openrouter",
            image_model_name="black-forest-labs/flux-1.1-pro",
            image_base_url="https://openrouter.ai/api/v1",
            image_api_key="",
        )
        with mock.patch("llm_client.get_active_settings", return_value=fake):
            with self.assertRaises(RuntimeError):
                mod.resolve_image_config()

    def test_generate_presentation_image_writes_dest(self):
        from tasks import image_settings as mod

        root = Path(tempfile.mkdtemp())
        dest = root / "out.png"
        dest.write_bytes(b"placeholder")

        def fake_generate(**kwargs):
            path = Path(kwargs["output_dir"]) / f"{kwargs['filename']}.png"
            path.write_bytes(b"png-bytes")
            return str(path)

        fake_mod = mock.Mock(generate=fake_generate)
        with mock.patch.object(
            mod,
            "resolve_image_config",
            return_value={
                "provider": "openrouter",
                "model": "black-forest-labs/flux-1.1-pro",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test",
                "api_key_env": "OPENROUTER_API_KEY",
                "base_url_env": "OPENROUTER_BASE_URL",
                "model_env": "OPENROUTER_MODEL",
                "module": "image_backends.backend_openrouter",
            },
        ), mock.patch.object(mod.importlib, "import_module", return_value=fake_mod):
            out = mod.generate_presentation_image(
                prompt="a chart",
                output_path=str(dest),
            )
        self.assertEqual(str(dest), out)
        self.assertEqual(b"png-bytes", dest.read_bytes())

    def test_probe_skips_without_key(self):
        from tasks.image_settings import probe_image_connection

        result = probe_image_connection(provider="openrouter", api_key="")
        self.assertTrue(result["skipped"])
        self.assertFalse(result["ok"])

    def test_aspect_ratio_for_box_matches_slot(self):
        from tasks.image_settings import aspect_ratio_for_box

        # Default enrich slot 520×400 is closer to 4:3 than 16:9.
        self.assertEqual("4:3", aspect_ratio_for_box(520, 400))
        self.assertEqual("16:9", aspect_ratio_for_box(1600, 900))
        self.assertEqual("1:1", aspect_ratio_for_box(400, 400))

    def test_ensure_path_makes_image_backends_importable(self):
        import importlib
        import sys

        from tasks.image_settings import _ensure_image_backends_path

        # Drop a stale failed import if present so this test is meaningful.
        sys.modules.pop("image_backends", None)
        sys.modules.pop("image_backends.backend_openrouter", None)
        scripts = _ensure_image_backends_path()
        self.assertTrue(scripts.is_dir())
        self.assertIn(str(scripts), sys.path)
        mod = importlib.import_module("image_backends.backend_openrouter")
        self.assertTrue(callable(getattr(mod, "generate", None)))


class SettingsValidationTests(unittest.TestCase):
    def test_rejects_google_model_ids(self):
        from tasks.settings_validation import SettingsValidationError, validate_settings_payload

        with self.assertRaises(SettingsValidationError):
            validate_settings_payload(
                provider="openai_compatible",
                model_name="google/gemini-2.5-flash",
            )
        with self.assertRaises(SettingsValidationError):
            validate_settings_payload(provider="gemini", model_name="openai/gpt-4o")
        self.assertEqual(
            "openai_compatible",
            validate_settings_payload(
                provider="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                model_name="openai/gpt-4o",
                image_provider="openrouter",
                image_model_name="black-forest-labs/flux-1.1-pro",
            ),
        )


if __name__ == "__main__":
    unittest.main()
