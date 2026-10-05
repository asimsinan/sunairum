"""Validate Settings payloads: OpenAI-compatible only; ban Google/Gemini IDs."""

from __future__ import annotations

import re

_GOOGLE_MODEL_RE = re.compile(
    r"(?i)(?:^|/)(google|gemini)\b|generativelanguage\.googleapis\.com"
)


class SettingsValidationError(ValueError):
    """Raised when Settings contain a forbidden provider or model ID."""


def is_banned_google_string(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    return bool(_GOOGLE_MODEL_RE.search(text))


def normalize_text_provider(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"", "openai_compatible", "openai", "openai-compatible", "openrouter"}:
        return "openai_compatible"
    if value in {"gemini", "google"}:
        raise SettingsValidationError(
            "Google Gemini is no longer supported. Use an OpenAI-compatible "
            "provider (e.g. OpenRouter) in Settings → Text engine."
        )
    raise SettingsValidationError(
        f"Unsupported text provider {raw!r}. Only openai_compatible is allowed."
    )


def assert_not_google_model(label: str, value: str | None) -> None:
    if is_banned_google_string(value):
        raise SettingsValidationError(
            f"{label} must not use Google/Gemini model IDs or Google endpoints. "
            f"Got {value!r}."
        )


def validate_settings_payload(
    *,
    provider: str | None,
    base_url: str | None = None,
    model_name: str | None = None,
    image_provider: str | None = None,
    image_model_name: str | None = None,
    image_base_url: str | None = None,
) -> str:
    """Return normalized text provider or raise SettingsValidationError."""
    text_provider = normalize_text_provider(provider)
    assert_not_google_model("Text model", model_name)
    assert_not_google_model("Text base URL", base_url)
    assert_not_google_model("Image model", image_model_name)
    assert_not_google_model("Image base URL", image_base_url)
    if image_provider is not None:
        from tasks.image_settings import normalize_image_provider

        normalize_image_provider(image_provider)
    return text_provider


def coerce_stored_provider(raw: str | None) -> str:
    """Migrate legacy gemini rows to openai_compatible without raising."""
    value = (raw or "").strip().lower()
    if value in {"gemini", "google"}:
        return "openai_compatible"
    if value in {"", "openai", "openai-compatible", "openrouter"}:
        return "openai_compatible"
    if value == "openai_compatible":
        return value
    return "openai_compatible"


def scrub_banned_model(value: str | None) -> str:
    """Clear banned google/gemini model strings so the user must re-enter."""
    text = (value or "").strip()
    if not text or is_banned_google_string(text):
        return ""
    return text
