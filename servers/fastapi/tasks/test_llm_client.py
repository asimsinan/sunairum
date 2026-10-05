import unittest
from unittest.mock import MagicMock, patch

from llm_client import (
    JsonParseError,
    _completion_text,
    _parse_json_output,
    call_llm_text,
    get_active_settings,
)


class CompletionTextTests(unittest.TestCase):
    def test_null_choices_raises_clear_error(self):
        response = MagicMock()
        response.choices = None
        with self.assertRaisesRegex(RuntimeError, "null choices"):
            _completion_text(response)

    def test_reads_message_content(self):
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="  hello  "))]
        self.assertEqual("hello", _completion_text(response))

    def test_call_llm_text_retries_null_choices_once(self):
        settings = MagicMock(
            provider="openai_compatible",
            model_name="test-model",
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test",
        )
        bad = MagicMock(choices=None, id="gen-bad", model="test-model")
        good = MagicMock()
        good.choices = [MagicMock(message=MagicMock(content="ok slide"))]
        client = MagicMock()
        client.chat.completions.create.side_effect = [bad, good]

        with patch("llm_client.get_active_settings", return_value=settings), patch(
            "llm_client._openai_client", return_value=client
        ), patch("llm_client._prompt_cache_enabled", return_value=True), patch(
            "llm_client._prompt_cache_disabled", False
        ), patch("llm_client.time.sleep"), patch(
            "llm_client._llm_session_id"
        ) as session_var:
            session_var.get.return_value = "sess-1"
            text = call_llm_text("sys", "user")

        self.assertEqual("ok slide", text)
        self.assertEqual(2, client.chat.completions.create.call_count)
        # Second attempt must not keep the cache extra_body that caused null choices.
        second_kwargs = client.chat.completions.create.call_args_list[1].kwargs
        self.assertNotIn("extra_body", second_kwargs)


class LlmClientJsonTests(unittest.TestCase):
    def test_model_json_with_literal_control_character_is_decoded(self):
        payload = _parse_json_output('{"body":"line one\nline two"}')

        self.assertEqual("line one\nline two", payload["body"])

    def test_missing_comma_is_repaired_once_before_schema_validation(self):
        payload = _parse_json_output(
            '{"slides":[{"title":"HERO" "description":"Grounded"}]}'
        )

        self.assertEqual("HERO", payload["slides"][0]["title"])
        self.assertEqual("Grounded", payload["slides"][0]["description"])

    def test_json_shape_is_checked_after_parsing(self):
        with self.assertRaises(JsonParseError):
            _parse_json_output("[1, 2, 3]")

        self.assertEqual([1, 2, 3], _parse_json_output("[1, 2, 3]", list))


class GetActiveSettingsTests(unittest.TestCase):
    def test_returns_usable_snapshot_when_reencrypt_is_noop(self):
        """Plaintext keys + no Fernet must not DetachedInstanceError after commit."""
        row = MagicMock()
        row.id = 1
        row.user_id = "user-1"
        row.provider = "openai_compatible"
        row.base_url = "https://example.test/v1"
        row.api_key = "sk-test-plain"
        row.model_name = "test-model"
        row.vision_model_name = ""
        row.vision_base_url = ""
        row.vision_api_key = ""
        row.image_provider = "openrouter"
        row.image_model_name = ""
        row.image_base_url = ""
        row.image_api_key = ""
        row.connection_test_json = ""

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        with patch("llm_client.SessionLocal", return_value=db), patch(
            "llm_client.ensure_encrypted", side_effect=lambda v: v or ""
        ), patch("llm_client.decrypt_secret", side_effect=lambda v: v or ""):
            settings = get_active_settings("user-1")

        self.assertEqual("openai_compatible", settings.provider)
        self.assertEqual("test-model", settings.model_name)
        self.assertEqual("sk-test-plain", settings.api_key)
        self.assertEqual("https://example.test/v1", settings.base_url)
        db.commit.assert_not_called()

    def test_scrubs_legacy_gemini_provider_and_google_models(self):
        row = MagicMock()
        row.id = 2
        row.user_id = "user-2"
        row.provider = "gemini"
        row.base_url = "https://openrouter.ai/api/v1"
        row.api_key = "sk-test"
        row.model_name = "google/gemini-2.5-flash"
        row.vision_model_name = "google/gemini-3.6-flash"
        row.vision_base_url = ""
        row.vision_api_key = ""
        row.image_provider = "gemini"
        row.image_model_name = "gemini-3.1-flash-image-preview"
        row.image_base_url = ""
        row.image_api_key = ""
        row.connection_test_json = ""

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        with patch("llm_client.SessionLocal", return_value=db), patch(
            "llm_client.ensure_encrypted", side_effect=lambda v: v or ""
        ), patch("llm_client.decrypt_secret", side_effect=lambda v: v or ""):
            settings = get_active_settings("user-2")

        self.assertEqual("openai_compatible", settings.provider)
        self.assertEqual("", settings.model_name)
        self.assertEqual("", settings.vision_model_name)
        self.assertEqual("openrouter", settings.image_provider)
        self.assertEqual("", settings.image_model_name)
        db.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
