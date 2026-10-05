#!/usr/bin/env python3
"""
OpenRouter image generation backend.

Configuration keys:
  OPENROUTER_API_KEY   (required)
  OPENROUTER_BASE_URL  (optional)
  OPENROUTER_MODEL     (optional)
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from console_encoding import configure_utf8_stdio  # noqa: E402

configure_utf8_stdio()

if __name__ == "__main__":
    print(__doc__)
    print("Use via: python3 skills/ppt-master/scripts/image_gen.py \"prompt\" --backend openrouter")
    raise SystemExit(0 if any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]) else 1)

import base64
import os
import re
import time
import threading
from typing import Any

import requests

from image_backends.backend_common import (
    MAX_RETRIES,
    is_rate_limit_error,
    normalize_image_size,
    resolve_output_path,
    retry_delay,
    save_image_bytes,
)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Constants                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

VALID_ASPECT_RATIOS = [
    "auto",
    "1:1", "1:2", "1:4", "1:8",
    "2:1", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]

# Qwen Image 3 Image API allow-list (stricter than chat image_config).
QWEN_IMAGES_ASPECT_RATIOS = frozenset({
    "auto",
    "1:1", "1:2", "1:4",
    "2:1", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "9:16", "16:9",
})

VALID_IMAGE_SIZES = ["1K", "2K", "4K", "0.5K"]

DEFAULT_MODEL = "qwen/qwen-image-3"
DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1"

# Image-primary / image-only model ID fragments (OpenRouter: modalities=["image"]).
_IMAGE_PRIMARY_MARKERS = (
    "grok-imagine",
    "flux",
    "sourceful",
    "seedream",
    "gpt-image",
    "imagen",
    "recraft",
    "ideogram",
    "stable-diffusion",
    "sdxl",
)

# Models that must use OpenRouter's dedicated Image API (POST /api/v1/images).
# chat/completions returns HTML 404 for these (e.g. qwen/qwen-image-3).
_IMAGES_API_MARKERS = (
    "qwen-image",
    "qwen/qwen-image",
)

_DATA_URL_RE = re.compile(
    r"^data:(?P<mime>[\w/+.-]+);base64,(?P<data>.+)$",
    flags=re.I | re.S,
)


class OpenRouterImageError(RuntimeError):
    """Provider/client failure. ``retryable`` controls the outer retry loop."""

    def __init__(self, message: str, *, retryable: bool = True, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

def _normalize_api_root(base_url: str | None) -> str:
    """Strip a pasted full endpoint down to the API root.

    Settings often store ``…/api/v1/images`` or ``…/chat/completions``. Always
    append path segments onto the root, never onto an already-suffixed URL.
    """
    root = (base_url or DEFAULT_ENDPOINT).strip().rstrip("/")
    lower = root.lower()
    for suffix in ("/images", "/chat/completions", "/models"):
        if lower.endswith(suffix):
            root = root[: -len(suffix)].rstrip("/")
            break
    return root or DEFAULT_ENDPOINT


def _resolve_url(base_url: str | None) -> str:
    """Resolve the OpenRouter chat/completions image endpoint."""
    return _normalize_api_root(base_url) + "/chat/completions"


def _resolve_images_url(base_url: str | None) -> str:
    """Resolve OpenRouter's dedicated Image API endpoint."""
    return _normalize_api_root(base_url) + "/images"


def base_url_prefers_images_api(base_url: str | None) -> bool:
    """True when Settings base URL already points at the Image API."""
    raw = (base_url or "").strip().rstrip("/").lower()
    return raw.endswith("/images")


def uses_images_api(model: str, base_url: str | None = None) -> bool:
    """True when generation must use POST /api/v1/images.

    See https://openrouter.ai/qwen/qwen-image-3 — Qwen Image models reject
    chat/completions with a bare HTML 404. Also honor a Settings base URL
    that already ends with ``/images``.
    """
    if base_url_prefers_images_api(base_url):
        return True
    slug = (model or "").strip().lower()
    return any(marker in slug for marker in _IMAGES_API_MARKERS)


def modalities_for_model(model: str) -> list[str]:
    """Pick OpenRouter modalities for the model.

    Image-primary IDs (Grok Imagine, Flux, …) must use ``["image"]``.
    Dual-output models (e.g. Gemini flash image) use ``["image", "text"]``.
    """
    slug = (model or "").strip().lower()
    if uses_images_api(slug) or any(marker in slug for marker in _IMAGE_PRIMARY_MARKERS):
        return ["image"]
    return ["image", "text"]


def _images_api_resolution(image_size: str) -> str:
    """Clamp size presets to values the Image API accepts (1K/2K)."""
    size = (image_size or "1K").strip().upper()
    # Qwen Image 3 documents 1K and 2K only; 4K is rejected by some providers.
    if size == "2K":
        return "2K"
    return "1K"


def _images_api_aspect_ratio(
    aspect_ratio: str,
    *,
    model: str,
    reference_image: str | None,
) -> str:
    """Normalize aspect for /images; prefer source match for edits."""
    ratio = (aspect_ratio or "").strip() or "1:1"
    if ratio.casefold() == "auto":
        return "auto"
    if uses_images_api(model) and ratio not in QWEN_IMAGES_ASPECT_RATIOS:
        # Fall back to nearest supported label rather than 400 from the provider.
        try:
            from image_backends.backend_common import nearest_aspect_ratio

            left, right = ratio.split(":", 1)
            ratio = nearest_aspect_ratio(
                float(left),
                float(right),
                candidates=tuple(r for r in QWEN_IMAGES_ASPECT_RATIOS if r != "auto"),
            )
        except Exception:
            ratio = "1:1"
    if reference_image and ratio == "16:9":
        # Callers often default to slide 16:9; for image-to-image prefer the
        # reference geometry so academic figures are not stretched landscape.
        try:
            from image_backends.backend_common import aspect_ratio_for_image_file

            matched = aspect_ratio_for_image_file(reference_image)
            if matched:
                return matched
        except Exception:
            pass
        return "auto"
    return ratio


def _flip_modalities(modalities: list[str]) -> list[str]:
    if modalities == ["image"]:
        return ["image", "text"]
    return ["image"]


def _is_modalities_error(message: str) -> bool:
    lower = (message or "").lower()
    return any(
        token in lower
        for token in (
            "modalit",
            "output modality",
            "does not support",
            "unsupported modality",
        )
    )


def _is_hard_client_error(exc: BaseException) -> bool:
    if isinstance(exc, OpenRouterImageError) and not exc.retryable:
        return True
    status = getattr(exc, "status_code", None)
    if status in {401, 402, 403, 404}:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "invalid api key",
            "unauthorized",
            "forbidden",
            "not found",
            "unknown model",
            "no endpoints found",
            "model not found",
            "insufficient credits",
            "payment required",
            "cannot identify image file",
            "returned svg",
            "cannot rasterize svg",
        )
    )


def _provider_error_message(result: dict[str, Any], *, status_code: int | None = None) -> str | None:
    err = result.get("error")
    if err is None:
        return None
    if isinstance(err, str) and err.strip():
        msg = err.strip()
    elif isinstance(err, dict):
        msg = str(err.get("message") or err.get("msg") or err).strip()
    else:
        msg = str(err).strip()
    if not msg:
        return None
    if status_code:
        return f"OpenRouter HTTP {status_code}: {msg}"
    return f"OpenRouter error: {msg}"


def _decode_data_url(url: str) -> tuple[bytes, str | None]:
    """Decode a ``data:<mime>;base64,...`` URL. Returns (bytes, mime|None)."""
    raw = (url or "").strip()
    if not raw:
        raise OpenRouterImageError("empty image data URL", retryable=False)
    match = _DATA_URL_RE.match(raw)
    mime: str | None = None
    if match:
        mime = (match.group("mime") or "").strip().lower() or None
        payload = match.group("data")
    elif "," in raw and "base64" in raw[:80].lower():
        header, payload = raw.split(",", 1)
        if ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0].strip().lower() or None
    else:
        # Not a data URL — caller should fetch http(s) instead.
        raise OpenRouterImageError(
            "image ref is not a data URL",
            retryable=False,
        )
    payload = "".join(payload.split())
    try:
        data = base64.b64decode(payload, validate=False)
    except Exception:
        data = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return data, mime


def _is_svg_bytes(data: bytes, mime: str | None = None) -> bool:
    if mime and "svg" in mime:
        return True
    head = (data or b"")[:256].lstrip().lower()
    return head.startswith(b"<svg") or (
        head.startswith(b"<?xml") and b"<svg" in (data or b"")[:2048].lower()
    )


def _svg_to_png_bytes(svg_bytes: bytes) -> bytes:
    """Rasterize SVG → PNG when a converter is installed."""
    try:
        import cairosvg  # type: ignore

        return cairosvg.svg2png(bytestring=svg_bytes)
    except Exception:
        pass
    try:
        from io import BytesIO
        from reportlab.graphics import renderPM  # type: ignore
        from svglib.svglib import svg2rlg  # type: ignore

        drawing = svg2rlg(BytesIO(svg_bytes))
        if drawing is None:
            raise RuntimeError("svglib could not parse SVG")
        buf = BytesIO()
        renderPM.drawToFile(drawing, buf, fmt="PNG")
        return buf.getvalue()
    except Exception as error:
        raise OpenRouterImageError(
            "Model returned SVG (vector). This worker cannot rasterize SVG "
            "(install cairosvg), and Pillow cannot open SVG. "
            "Switch Settings → Image engine to a raster model "
            "(e.g. black-forest-labs/flux-1.1-pro or openai/gpt-image) "
            f"for figure AI restyle. Detail: {error}",
            retryable=False,
        ) from error


def _bytes_from_image_ref(url: str) -> bytes:
    """Load image bytes from a data URL or http(s) URL; SVG → PNG when needed."""
    raw = (url or "").strip()
    if not raw:
        raise OpenRouterImageError("empty image URL", retryable=False)

    mime: str | None = None
    if raw.lower().startswith("data:"):
        data, mime = _decode_data_url(raw)
    elif raw.lower().startswith(("http://", "https://")):
        try:
            response = requests.get(raw, timeout=60)
        except requests.RequestException as error:
            raise OpenRouterImageError(
                f"failed to download image URL: {error}",
                retryable=True,
            ) from error
        if response.status_code >= 400:
            raise OpenRouterImageError(
                f"image URL HTTP {response.status_code}",
                retryable=response.status_code >= 500 or response.status_code == 429,
                status_code=response.status_code,
            )
        data = response.content or b""
        mime = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower() or None
    else:
        # Bare base64 blob (some providers omit the data: prefix).
        try:
            data, mime = _decode_data_url(f"data:image/png;base64,{raw}")
        except OpenRouterImageError:
            raise OpenRouterImageError(
                "unsupported image URL scheme (expected data: or https:)",
                retryable=False,
            ) from None

    if not data:
        raise OpenRouterImageError("empty image payload", retryable=False)

    if _is_svg_bytes(data, mime):
        print("  [..] Provider returned SVG; rasterizing to PNG...")
        return _svg_to_png_bytes(data)
    return data


def _image_url_from_message(message: dict[str, Any]) -> str | None:
    images = message.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        return None
    for key in ("image_url", "imageUrl"):
        block = first.get(key)
        if isinstance(block, dict):
            url = block.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        elif isinstance(block, str) and block.strip():
            return block.strip()
    url = first.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _empty_image_detail(message: dict[str, Any], choice: dict[str, Any]) -> str:
    parts: list[str] = ["No image was generated."]
    finish = choice.get("finish_reason") or choice.get("native_finish_reason")
    if finish:
        parts.append(f"finish_reason={finish}")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        parts.append(f"content={content.strip()[:240]}")
    elif isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(str(part.get("text") or "")[:120])
        if texts:
            parts.append("content=" + " ".join(texts)[:240])
    parts.append("The server may have refused the request.")
    return " ".join(parts)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Image Generation                                               ║
# ╚══════════════════════════════════════════════════════════════════╝

def _bytes_from_images_api_result(result: dict[str, Any]) -> bytes:
    """Decode the first image from an OpenRouter /images response."""
    data = result.get("data")
    if not isinstance(data, list) or not data:
        raise OpenRouterImageError(
            "OpenRouter /images returned no data[]. "
            f"keys={list(result.keys())[:12]}",
            retryable=True,
        )
    first = data[0] if isinstance(data[0], dict) else {}
    b64 = first.get("b64_json") or first.get("b64Json")
    if isinstance(b64, str) and b64.strip():
        try:
            raw = base64.b64decode("".join(b64.split()), validate=False)
        except Exception as error:
            raise OpenRouterImageError(
                f"failed to decode b64_json: {error}",
                retryable=False,
            ) from error
        if _is_svg_bytes(raw):
            return _svg_to_png_bytes(raw)
        return raw
    url = None
    for key in ("url", "image_url", "imageUrl"):
        block = first.get(key)
        if isinstance(block, str) and block.strip():
            url = block.strip()
            break
        if isinstance(block, dict):
            nested = block.get("url")
            if isinstance(nested, str) and nested.strip():
                url = nested.strip()
                break
    if url:
        return _bytes_from_image_ref(url)
    raise OpenRouterImageError(
        "OpenRouter /images item missing b64_json/url",
        retryable=True,
    )


def _generate_via_images_api(
    api_key: str,
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "1K",
    output_dir: str = None,
    filename: str = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_ENDPOINT,
    reference_image: str | None = None,
) -> str:
    """Generate via OpenRouter POST /api/v1/images (Qwen Image 3, …)."""
    url = _resolve_images_url(base_url)
    resolution = _images_api_resolution(image_size)
    aspect_ratio = _images_api_aspect_ratio(
        aspect_ratio, model=model, reference_image=reference_image
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "n": 1,
    }
    if reference_image:
        payload["input_references"] = [
            {
                "type": "image_url",
                "image_url": {"url": _reference_data_url(reference_image)},
            }
        ]

    print(f"[OpenRouter /images]")
    print(f"  Model:        {model}")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect Ratio: {aspect_ratio}")
    print(f"  Resolution:   {resolution}")
    if reference_image:
        print(f"  References:   1")
    print()

    start_time = time.time()
    print("  [..] Generating...", end="", flush=True)
    heartbeat_stop = threading.Event()

    def _heartbeat():
        while not heartbeat_stop.is_set():
            heartbeat_stop.wait(5)
            if not heartbeat_stop.is_set():
                elapsed = time.time() - start_time
                print(f" {elapsed:.0f}s...", end="", flush=True)

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        try:
            result = response.json()
        except ValueError:
            body = (response.text or "")[:300]
            raise OpenRouterImageError(
                f"OpenRouter HTTP {response.status_code}: non-JSON response: {body}",
                retryable=response.status_code >= 500 or response.status_code == 429,
                status_code=response.status_code,
            ) from None
    finally:
        heartbeat_stop.set()
        hb_thread.join(timeout=1)

    elapsed = time.time() - start_time
    if not isinstance(result, dict):
        raise OpenRouterImageError(
            f"OpenRouter returned unexpected payload type: {type(result).__name__}",
            retryable=True,
            status_code=getattr(response, "status_code", None),
        )

    provider_err = _provider_error_message(result, status_code=response.status_code)
    if provider_err:
        hard = response.status_code in {401, 402, 403, 404} or _is_hard_client_error(
            OpenRouterImageError(provider_err, status_code=response.status_code)
        )
        print(f"\n  [FAIL] after {elapsed:.1f}s: {provider_err}")
        raise OpenRouterImageError(
            provider_err,
            retryable=not hard and response.status_code not in {400, 401, 402, 403, 404},
            status_code=response.status_code,
        )

    if response.status_code >= 400:
        msg = f"OpenRouter HTTP {response.status_code}: {(response.text or '')[:300]}"
        print(f"\n  [FAIL] after {elapsed:.1f}s: {msg}")
        raise OpenRouterImageError(
            msg,
            retryable=response.status_code >= 500 or response.status_code == 429,
            status_code=response.status_code,
        )

    image_data = _bytes_from_images_api_result(result)
    path = resolve_output_path(prompt, output_dir, filename, ".png")
    saved = save_image_bytes(image_data, path)
    print(f"\n  [DONE] Image generated ({elapsed:.1f}s)")
    return saved


def _reference_data_url(path: str) -> str:
    """Encode a local reference image as a data URL for multimodal edit prompts."""
    raw = Path(path).read_bytes()
    if len(raw) < 32:
        raise OpenRouterImageError("reference image too small", retryable=False)
    suffix = Path(path).suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _user_content(prompt: str, reference_image: str | None) -> Any:
    if not reference_image:
        return prompt
    data_url = _reference_data_url(reference_image)
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]


def _generate_image(
    api_key: str,
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "1K",
    output_dir: str = None,
    filename: str = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_ENDPOINT,
    modalities: list[str] | None = None,
    reference_image: str | None = None,
) -> str:
    """Image generation via OpenRouter's chat/completions API."""
    url = _resolve_url(base_url)
    modalities = list(modalities or modalities_for_model(model))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": _user_content(prompt, reference_image),
            }
        ],
        "modalities": modalities,
        "image_config": {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
    }

    print(f"[OpenRouter]")
    print(f"  Model:        {model}")
    print(f"  Modalities:   {modalities}")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect Ratio: {aspect_ratio}")
    print(f"  Image Size:   {image_size}")
    print()

    start_time = time.time()
    print("  [..] Generating...", end="", flush=True)

    heartbeat_stop = threading.Event()

    def _heartbeat():
        while not heartbeat_stop.is_set():
            heartbeat_stop.wait(5)
            if not heartbeat_stop.is_set():
                elapsed = time.time() - start_time
                print(f" {elapsed:.0f}s...", end="", flush=True)

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        try:
            result = response.json()
        except ValueError:
            body = (response.text or "")[:300]
            raise OpenRouterImageError(
                f"OpenRouter HTTP {response.status_code}: non-JSON response: {body}",
                retryable=response.status_code >= 500 or response.status_code == 429,
                status_code=response.status_code,
            ) from None
    finally:
        heartbeat_stop.set()
        hb_thread.join(timeout=1)

    elapsed = time.time() - start_time
    if not isinstance(result, dict):
        raise OpenRouterImageError(
            f"OpenRouter returned unexpected payload type: {type(result).__name__}",
            retryable=True,
            status_code=getattr(response, "status_code", None),
        )

    provider_err = _provider_error_message(result, status_code=response.status_code)
    if provider_err:
        hard = response.status_code in {401, 402, 403, 404} or _is_hard_client_error(
            OpenRouterImageError(provider_err, status_code=response.status_code)
        )
        print(f"\n  [FAIL] after {elapsed:.1f}s: {provider_err}")
        raise OpenRouterImageError(
            provider_err,
            retryable=not hard and response.status_code not in {400, 401, 402, 403, 404},
            status_code=response.status_code,
        )

    if response.status_code >= 400:
        msg = f"OpenRouter HTTP {response.status_code}: {(response.text or '')[:300]}"
        print(f"\n  [FAIL] after {elapsed:.1f}s: {msg}")
        raise OpenRouterImageError(
            msg,
            retryable=response.status_code >= 500 or response.status_code == 429,
            status_code=response.status_code,
        )

    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict):
            image_url = _image_url_from_message(message)
            if image_url:
                path = resolve_output_path(prompt, output_dir, filename, ".png")
                try:
                    image_data = _bytes_from_image_ref(image_url)
                    saved = save_image_bytes(image_data, path)
                except OpenRouterImageError:
                    raise
                except Exception as error:
                    # Pillow UnidentifiedImageError etc. — format issues do not retry.
                    msg = str(error)
                    retryable = "cannot identify image file" not in msg.casefold()
                    print(f"\n  [FAIL] after {elapsed:.1f}s: {msg}")
                    raise OpenRouterImageError(
                        msg,
                        retryable=retryable,
                        status_code=response.status_code,
                    ) from error
                print(f"\n  [DONE] Image generated ({elapsed:.1f}s)")
                return saved
            detail = _empty_image_detail(message, choice if isinstance(choice, dict) else {})
            print(f"\n  [FAIL] after {elapsed:.1f}s: {detail}")
            raise OpenRouterImageError(detail, retryable=True, status_code=response.status_code)

    print(f"\n  [FAIL] after {elapsed:.1f}s: no choices/images in response")
    raise OpenRouterImageError(
        "No image was generated. The server may have refused the request.",
        retryable=True,
        status_code=response.status_code,
    )


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Public Entry Point                                             ║
# ╚══════════════════════════════════════════════════════════════════╝

def generate(
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "1K",
    output_dir: str = None,
    filename: str = None,
    model: str = None,
    max_retries: int = MAX_RETRIES,
    reference_image: str = None,
) -> str:
    """
    OpenRouter image generation with automatic retry.

    When ``reference_image`` is set, the prompt is sent as a multimodal edit
    (text + attached image). Credentials from env / `.env`:
      OPENROUTER_API_KEY
      OPENROUTER_BASE_URL
      OPENROUTER_MODEL (optional override)
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    base_url = os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_ENDPOINT

    if not api_key:
        raise ValueError(
            "No API key found. Set OPENROUTER_API_KEY in the current environment or a .env file."
        )

    if model is None:
        model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL

    if reference_image and not Path(reference_image).is_file():
        raise ValueError(f"reference_image not found: {reference_image}")

    image_size = normalize_image_size(image_size)

    if aspect_ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(f"Invalid aspect ratio '{aspect_ratio}'. Valid: {VALID_ASPECT_RATIOS}")

    if image_size not in VALID_IMAGE_SIZES:
        raise ValueError(f"Invalid image size '{image_size}'. Valid: {VALID_IMAGE_SIZES}")

    # Qwen Image 3+ / Settings base URL ending in /images → dedicated Image API.
    if uses_images_api(model, base_url):
        last_error: BaseException | None = None
        for attempt in range(max_retries + 1):
            try:
                return _generate_via_images_api(
                    api_key,
                    prompt,
                    aspect_ratio,
                    image_size,
                    output_dir,
                    filename,
                    model,
                    base_url,
                    reference_image=reference_image,
                )
            except Exception as e:
                last_error = e
                if _is_hard_client_error(e):
                    break
                if attempt < max_retries and is_rate_limit_error(e):
                    delay = retry_delay(attempt, rate_limited=True)
                    print(
                        f"\n  [WARN] Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Waiting {delay}s before retry..."
                    )
                    time.sleep(delay)
                elif attempt < max_retries and (
                    not isinstance(e, OpenRouterImageError) or e.retryable
                ):
                    delay = retry_delay(attempt, rate_limited=False)
                    print(
                        f"\n  [WARN] Error (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    break
        raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")

    modalities = modalities_for_model(model)
    modalities_flipped = False
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return _generate_image(
                api_key,
                prompt,
                aspect_ratio,
                image_size,
                output_dir,
                filename,
                model,
                base_url,
                modalities=modalities,
                reference_image=reference_image,
            )
        except Exception as e:
            last_error = e
            # Modalities mismatch often returns HTTP 404 — flip before hard-fail.
            if (
                not modalities_flipped
                and _is_modalities_error(str(e))
            ):
                modalities = _flip_modalities(modalities)
                modalities_flipped = True
                print(
                    f"\n  [WARN] Modalities rejected; retrying once with {modalities}"
                )
                continue
            # chat/completions HTML 404 → model may need the dedicated Image API.
            status = getattr(e, "status_code", None)
            if status == 404 and "non-json" in str(e).lower():
                print(
                    "\n  [WARN] chat/completions 404; retrying once via /api/v1/images"
                )
                try:
                    return _generate_via_images_api(
                        api_key,
                        prompt,
                        aspect_ratio,
                        image_size,
                        output_dir,
                        filename,
                        model,
                        base_url,
                        reference_image=reference_image,
                    )
                except Exception as images_error:
                    last_error = images_error
                    break
            if _is_hard_client_error(e):
                break
            if attempt < max_retries and is_rate_limit_error(e):
                delay = retry_delay(attempt, rate_limited=True)
                print(
                    f"\n  [WARN] Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). "
                    f"Waiting {delay}s before retry..."
                )
                time.sleep(delay)
            elif attempt < max_retries and (
                not isinstance(e, OpenRouterImageError) or e.retryable
            ):
                delay = retry_delay(attempt, rate_limited=False)
                print(
                    f"\n  [WARN] Error (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                break

    raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")
