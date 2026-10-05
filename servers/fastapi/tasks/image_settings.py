"""User-configurable image generation engine (separate from text LLM settings)."""

from __future__ import annotations

import importlib
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tasks.settings_validation import SettingsValidationError, assert_not_google_model

DEFAULT_IMAGE_PROVIDER = "openrouter"
DEFAULT_IMAGE_MODEL = "qwen/qwen-image-3"
DEFAULT_IMAGE_BASE_URL = "https://openrouter.ai/api/v1"

IMAGE_PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {
        "label": "OpenRouter",
        "module": "image_backends.backend_openrouter",
        "default_model": DEFAULT_IMAGE_MODEL,
        "default_base_url": DEFAULT_IMAGE_BASE_URL,
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url_env": "OPENROUTER_BASE_URL",
        "model_env": "OPENROUTER_MODEL",
    },
    "openai": {
        "label": "OpenAI / compatible",
        "module": "image_backends.backend_openai",
        "default_model": "gpt-image-2",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "model_env": "OPENAI_MODEL",
    },
}


def normalize_image_provider(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    aliases = {
        "openai_compatible": "openai",
        "openai-compatible": "openai",
    }
    value = aliases.get(value, value)
    if value in {"gemini", "google"}:
        raise SettingsValidationError(
            "Google Gemini image generation is no longer supported. "
            "Choose OpenRouter or OpenAI in Settings → Image engine."
        )
    if value in IMAGE_PROVIDERS:
        return value
    if not value:
        return DEFAULT_IMAGE_PROVIDER
    raise SettingsValidationError(
        f"Unsupported image provider {raw!r}. Allowed: openrouter, openai."
    )


def image_defaults(provider: str | None = None) -> dict[str, Any]:
    """Placeholders for empty Settings fields (not live env secrets)."""
    try:
        prov = normalize_image_provider(provider)
    except SettingsValidationError:
        prov = DEFAULT_IMAGE_PROVIDER
    meta = IMAGE_PROVIDERS[prov]
    return {
        "provider": prov,
        "model_name": meta["default_model"],
        "base_url": meta["default_base_url"],
        "api_key_from_env": False,
        "providers": [
            {"id": key, "label": cfg["label"], "default_model": cfg["default_model"]}
            for key, cfg in IMAGE_PROVIDERS.items()
        ],
    }


def resolve_image_config(user_id: str | None = None) -> dict[str, str]:
    """Return provider/model/base_url/api_key from Settings UI only."""
    from llm_client import get_active_settings

    settings = get_active_settings(user_id)
    try:
        provider = normalize_image_provider(getattr(settings, "image_provider", None))
    except SettingsValidationError:
        provider = DEFAULT_IMAGE_PROVIDER
    model = (getattr(settings, "image_model_name", None) or "").strip()
    base_url = (getattr(settings, "image_base_url", None) or "").strip()
    api_key = (getattr(settings, "image_api_key", None) or "").strip()
    meta = IMAGE_PROVIDERS[provider]
    if not model:
        raise RuntimeError(
            "an image model name is required: set it in Settings → Image engine"
        )
    assert_not_google_model("Image model", model)
    assert_not_google_model("Image base URL", base_url)
    if not api_key:
        raise RuntimeError(
            "an image API key is required: set it in Settings → Image engine"
        )
    if not base_url:
        base_url = meta["default_base_url"]
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "api_key_env": meta["api_key_env"],
        "base_url_env": meta["base_url_env"],
        "model_env": meta["model_env"],
        "module": meta["module"],
    }


def _ensure_image_backends_path() -> Path:
    """Put ``sunairum_scripts`` on sys.path so ``image_backends.*`` imports resolve."""
    import sys

    scripts = Path(__file__).resolve().parents[1] / "sunairum_scripts"
    scripts_str = str(scripts)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    return scripts


@contextmanager
def _apply_image_env(cfg: dict[str, str]) -> Iterator[None]:
    """Temporarily publish credentials so backend modules can read os.environ."""
    keys = (cfg["api_key_env"], cfg["base_url_env"], cfg["model_env"], "IMAGE_BACKEND")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ[cfg["api_key_env"]] = cfg["api_key"]
        if cfg["base_url"]:
            os.environ[cfg["base_url_env"]] = cfg["base_url"]
        os.environ[cfg["model_env"]] = cfg["model"]
        os.environ["IMAGE_BACKEND"] = cfg["provider"]
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def aspect_ratio_for_reference(path: str | None) -> str | None:
    """Nearest OpenRouter/Qwen aspect label for a local reference image."""
    if not path:
        return None
    _ensure_image_backends_path()
    from image_backends.backend_common import aspect_ratio_for_image_file  # type: ignore

    return aspect_ratio_for_image_file(path)


def aspect_ratio_for_box(width: float, height: float) -> str:
    """Nearest supported aspect label for a figure slot / box size."""
    _ensure_image_backends_path()
    from image_backends.backend_common import nearest_aspect_ratio  # type: ignore

    try:
        w = float(width)
        h = float(height)
    except (TypeError, ValueError):
        return "4:3"
    if w <= 0 or h <= 0:
        return "4:3"
    return nearest_aspect_ratio(w, h)


def generate_presentation_image(
    *,
    prompt: str,
    output_path: str,
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    reference_image: str | None = None,
    user_id: str | None = None,
) -> str:
    """Generate one figure using the user's image-engine settings."""
    cfg = resolve_image_config(user_id)
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ensure_image_backends_path()
    module = importlib.import_module(cfg["module"])
    generate = getattr(module, "generate", None)
    if not callable(generate):
        raise RuntimeError(f"image backend {cfg['provider']} has no generate()")

    # Image-to-image: match the source figure, never force slide 16:9.
    resolved_aspect = aspect_ratio
    if reference_image:
        matched = aspect_ratio_for_reference(reference_image)
        if matched:
            resolved_aspect = matched
        elif (aspect_ratio or "").strip() in {"", "16:9"}:
            resolved_aspect = "auto"

    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": resolved_aspect,
        "image_size": image_size,
        "output_dir": str(dest.parent),
        "filename": dest.stem,
        "model": cfg["model"] or None,
    }
    if reference_image:
        import inspect

        params = inspect.signature(generate).parameters
        if "reference_image" in params:
            kwargs["reference_image"] = reference_image

    with _apply_image_env(cfg):
        saved = generate(**kwargs)
    saved_path = Path(saved)
    if saved_path.resolve() != dest.resolve():
        saved_path.replace(dest)
    return str(dest)


def probe_image_connection(
    *,
    provider: str = "",
    model_name: str = "",
    base_url: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    """Cheap auth check for the image engine (no paid image generation)."""
    try:
        prov = normalize_image_provider(provider)
    except SettingsValidationError as error:
        return {
            "ok": False,
            "skipped": False,
            "model": (model_name or "").strip(),
            "latency_ms": 0,
            "detail": str(error),
        }
    defaults = image_defaults(prov)
    model = (model_name or "").strip() or defaults["model_name"]
    endpoint = (base_url or "").strip() or defaults["base_url"]
    meta = IMAGE_PROVIDERS[prov]
    key = (api_key or "").strip()
    if not key:
        return {
            "ok": False,
            "skipped": True,
            "model": model,
            "latency_ms": 0,
            "detail": "No image API key configured in Settings → Image engine",
        }

    timeout = 12.0
    started = time.perf_counter()
    try:
        import requests

        root = (endpoint or meta["default_base_url"]).strip().rstrip("/")
        lower = root.lower()
        for suffix in ("/images", "/chat/completions", "/models"):
            if lower.endswith(suffix):
                root = root[: -len(suffix)].rstrip("/")
                break
        url = (root or meta["default_base_url"]).rstrip("/") + "/models"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": f"Authenticated in {latency_ms} ms",
        }
    except Exception as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = str(error)
        if len(detail) > 220:
            detail = detail[:217] + "..."
        return {
            "ok": False,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": detail,
        }
