"""OpenRouter image backend: modalities, errors, data-URL decode."""

from __future__ import annotations

import base64
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_backend():
    scripts = Path(__file__).resolve().parents[1] / "sunairum_scripts"
    scripts_s = str(scripts)
    if scripts_s not in sys.path:
        sys.path.insert(0, scripts_s)
    if "image_backends.backend_openrouter" in sys.modules:
        return importlib.reload(sys.modules["image_backends.backend_openrouter"])
    return importlib.import_module("image_backends.backend_openrouter")


class OpenRouterImageBackendTests(unittest.TestCase):
    def test_grok_uses_image_only_modalities(self):
        mod = _load_backend()
        self.assertEqual(
            ["image"],
            mod.modalities_for_model("x-ai/grok-imagine-image-quality"),
        )
        self.assertEqual(
            ["image"],
            mod.modalities_for_model("black-forest-labs/flux-1.1-pro"),
        )
        self.assertEqual(
            ["image"],
            mod.modalities_for_model("recraft/recraft-v4.1-vector"),
        )
        self.assertEqual(
            ["image", "text"],
            mod.modalities_for_model("some-org/gemini-flash-image"),
        )
        self.assertTrue(mod.uses_images_api("qwen/qwen-image-3"))
        self.assertFalse(mod.uses_images_api("black-forest-labs/flux-1.1-pro"))
        self.assertTrue(
            mod.uses_images_api(
                "black-forest-labs/flux-1.1-pro",
                "https://openrouter.ai/api/v1/images",
            )
        )
        self.assertEqual(
            "https://openrouter.ai/api/v1",
            mod._normalize_api_root("https://openrouter.ai/api/v1/images"),
        )
        self.assertEqual(
            "https://openrouter.ai/api/v1/images",
            mod._resolve_images_url("https://openrouter.ai/api/v1/images"),
        )

    def test_settings_images_base_url_is_honored(self):
        """User pasted …/api/v1/images in Settings — do not append /chat/completions."""
        mod = _load_backend()
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        out_png = png + b"\xff"
        root = Path(tempfile.mkdtemp())

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {"data": [{"b64_json": base64.b64encode(out_png).decode("ascii")}]}

        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            return FakeResp()

        with mock.patch.object(mod.requests, "post", side_effect=fake_post), mock.patch.dict(
            mod.os.environ,
            {
                "OPENROUTER_API_KEY": "sk-test",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1/images",
            },
            clear=False,
        ):
            path = mod.generate(
                prompt="a chart",
                aspect_ratio="16:9",
                output_dir=str(root),
                filename="settings_images",
                model="black-forest-labs/flux-1.1-pro",
                max_retries=0,
            )
        self.assertEqual("https://openrouter.ai/api/v1/images", captured["url"])
        self.assertTrue(Path(path).is_file())

    def test_qwen_image_uses_dedicated_images_endpoint(self):
        mod = _load_backend()
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        out_png = png + b"\x00\x01\x02\x03"
        root = Path(tempfile.mkdtemp())
        ref = root / "src.png"
        ref.write_bytes(png)

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "data": [
                        {"b64_json": base64.b64encode(out_png).decode("ascii")},
                    ]
                }

        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

        with mock.patch.object(mod.requests, "post", side_effect=fake_post), mock.patch.dict(
            mod.os.environ,
            {
                "OPENROUTER_API_KEY": "sk-test",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            },
            clear=False,
        ):
            path = mod.generate(
                prompt="Edit the attached academic figure",
                aspect_ratio="16:9",
                image_size="1K",
                output_dir=str(root),
                filename="qwen_edit",
                model="qwen/qwen-image-3",
                max_retries=0,
                reference_image=str(ref),
            )
        self.assertEqual("https://openrouter.ai/api/v1/images", captured["url"])
        self.assertEqual("qwen/qwen-image-3", captured["json"]["model"])
        # 1×1 reference + default 16:9 must rematch to source geometry (1:1), not slide AR.
        self.assertEqual("1:1", captured["json"]["aspect_ratio"])
        self.assertEqual("1K", captured["json"]["resolution"])
        self.assertNotIn("modalities", captured["json"])
        self.assertNotIn("messages", captured["json"])
        refs = captured["json"]["input_references"]
        self.assertEqual(1, len(refs))
        self.assertEqual("image_url", refs[0]["type"])
        self.assertIn("base64,", refs[0]["image_url"]["url"])
        self.assertTrue(Path(path).is_file())
        self.assertEqual(out_png, Path(path).read_bytes())

    def test_generate_attaches_reference_image(self):
        mod = _load_backend()
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        # Output must differ from reference for callers that hash-check.
        out_png = png + b"\x00\x01\x02\x03"
        data_url = "data:image/png;base64," + base64.b64encode(out_png).decode("ascii")
        root = Path(tempfile.mkdtemp())
        ref = root / "src.png"
        ref.write_bytes(png)

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "images": [{"image_url": {"url": data_url}}],
                            }
                        }
                    ]
                }

        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["json"] = json
            return FakeResp()

        with mock.patch.object(mod.requests, "post", side_effect=fake_post), mock.patch.dict(
            mod.os.environ,
            {"OPENROUTER_API_KEY": "sk-test"},
            clear=False,
        ):
            path = mod.generate(
                prompt="Edit the attached figure",
                aspect_ratio="16:9",
                output_dir=str(root),
                filename="edited",
                model="black-forest-labs/flux-1.1-pro",
                max_retries=0,
                reference_image=str(ref),
            )
        content = captured["json"]["messages"][0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual("text", content[0]["type"])
        self.assertEqual("image_url", content[1]["type"])
        self.assertIn("base64,", content[1]["image_url"]["url"])
        self.assertTrue(Path(path).is_file())

    def test_generate_sends_image_modalities_for_grok(self):
        mod = _load_backend()
        tiny = base64.b64encode(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        ).decode("ascii")
        data_url = f"data:image/png;base64,{tiny}"

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "images": [{"image_url": {"url": data_url}}],
                            }
                        }
                    ]
                }

        captured: dict = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

        root = Path(tempfile.mkdtemp())
        with mock.patch.object(mod.requests, "post", side_effect=fake_post), mock.patch.dict(
            mod.os.environ,
            {
                "OPENROUTER_API_KEY": "sk-test",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            },
            clear=False,
        ):
            path = mod.generate(
                prompt="a chart",
                aspect_ratio="16:9",
                output_dir=str(root),
                filename="fig",
                model="x-ai/grok-imagine-image-quality",
                max_retries=0,
            )
        self.assertEqual(["image"], captured["json"]["modalities"])
        self.assertEqual("x-ai/grok-imagine-image-quality", captured["json"]["model"])
        self.assertTrue(Path(path).is_file())

    def test_api_error_message_is_surfaced(self):
        mod = _load_backend()

        class FakeResp:
            status_code = 400
            text = '{"error":{"message":"Provider returned error"}}'

            def json(self):
                return {"error": {"message": "No endpoints found for this model"}}

        with mock.patch.object(mod.requests, "post", return_value=FakeResp()), mock.patch.dict(
            mod.os.environ,
            {"OPENROUTER_API_KEY": "sk-test"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                mod.generate(
                    prompt="x",
                    model="x-ai/grok-imagine-image-quality",
                    max_retries=0,
                )
        self.assertIn("No endpoints found", str(ctx.exception))
        self.assertNotIn("may have refused", str(ctx.exception).lower())

    def test_jpeg_data_url_decodes(self):
        mod = _load_backend()
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 32
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        decoded, mime = mod._decode_data_url(data_url)
        self.assertEqual(jpeg, decoded)
        self.assertEqual("image/jpeg", mime)

    def test_svg_payload_rasterizes_or_fails_closed(self):
        mod = _load_backend()
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            b'<rect width="10" height="10" fill="#0B3B6F"/></svg>'
        )
        data_url = "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
        try:
            out = mod._bytes_from_image_ref(data_url)
        except mod.OpenRouterImageError as error:
            self.assertFalse(error.retryable)
            self.assertIn("SVG", str(error))
            return
        self.assertTrue(out.startswith(b"\x89PNG"), msg="SVG should become PNG bytes")

        # CamelCase imageUrl + non-png mime still extracts and saves via generate.
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

        class FakeResp:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "images": [{"imageUrl": {"url": png_url}}],
                            }
                        }
                    ]
                }

        root = Path(tempfile.mkdtemp())
        with mock.patch.object(mod.requests, "post", return_value=FakeResp()), mock.patch.dict(
            mod.os.environ,
            {"OPENROUTER_API_KEY": "sk-test"},
            clear=False,
        ):
            path = mod.generate(
                prompt="photo",
                output_dir=str(root),
                filename="jpg_out",
                model="black-forest-labs/flux-1.1-pro",
                max_retries=0,
            )
        self.assertTrue(Path(path).is_file())
        self.assertGreater(Path(path).stat().st_size, 0)

    def test_hard_client_error_does_not_retry(self):
        mod = _load_backend()
        calls = {"n": 0}

        class FakeResp:
            status_code = 401
            text = "unauthorized"

            def json(self):
                calls["n"] += 1
                return {"error": {"message": "Invalid API key"}}

        with mock.patch.object(mod.requests, "post", return_value=FakeResp()), mock.patch.dict(
            mod.os.environ,
            {"OPENROUTER_API_KEY": "sk-bad"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                mod.generate(
                    prompt="x",
                    model="x-ai/grok-imagine-image-quality",
                    max_retries=3,
                )
        self.assertEqual(1, calls["n"])


if __name__ == "__main__":
    unittest.main()
