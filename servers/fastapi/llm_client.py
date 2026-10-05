import os
import json
import base64
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from openai import OpenAI
from database import SessionLocal
from models import UserSettings
from auth.secrets_crypto import decrypt_secret, ensure_encrypted
from tasks.settings_validation import (
    coerce_stored_provider,
    scrub_banned_model,
)

_llm_user_id: ContextVar[str | None] = ContextVar("llm_user_id", default=None)
_llm_session_id: ContextVar[str | None] = ContextVar("llm_session_id", default=None)
# Process-wide fail-open after a bad cache_control request.
_prompt_cache_disabled = False
_last_cache_hit: ContextVar[bool] = ContextVar("llm_cache_hit", default=False)


@contextmanager
def llm_user_context(user_id: str | None) -> Iterator[None]:
    token = _llm_user_id.set(user_id)
    try:
        yield
    finally:
        _llm_user_id.reset(token)


@contextmanager
def llm_session_context(session_id: str | None) -> Iterator[None]:
    """Sticky OpenRouter session for prompt-cache routing across Art/Plan/Executor."""
    token = _llm_session_id.set(session_id)
    try:
        yield
    finally:
        _llm_session_id.reset(token)


def last_prompt_cache_hit() -> bool:
    return bool(_last_cache_hit.get())

DEFAULT_LLM_TIMEOUT_SECONDS = 180
MAX_JSON_RESPONSE_CHARS = 2_000_000

# UI placeholders only — never used as live env credential fallbacks.
DEFAULT_TEXT_MODEL = "openai/gpt-4o"
DEFAULT_VISION_MODEL = "openai/gpt-4o"
DEFAULT_VISION_BASE_URL = "https://openrouter.ai/api/v1"
# The chat endpoint. `.../v1/images` is where pictures are generated, and pointing
# review at it makes every call 404 with nothing in the message to say why.
_GENERATION_PATH_SUFFIXES = ("/images", "/images/generations", "/generations")


class JsonParseError(ValueError):
    """Raised when a model response cannot be safely decoded as JSON."""

    def __init__(self, message: str, *, position: int | None = None):
        super().__init__(message)
        self.position = position

def _request_timeout_seconds() -> float:
    try:
        return max(10.0, float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return float(DEFAULT_LLM_TIMEOUT_SECONDS)


def _openai_client(settings):
    base_url = (settings.base_url or "").strip() or None
    headers = {}
    if base_url and "openrouter.ai" in base_url:
        headers = {
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost:3000"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "Sunairum"),
        }
    api_key = (settings.api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "a text API key is required: set it in Settings → Text engine"
        )
    model = (settings.model_name or "").strip()
    if not model:
        raise RuntimeError(
            "a text model name is required: set it in Settings → Text engine"
        )
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=_request_timeout_seconds(),
        # Transient DNS/TLS blips to OpenRouter show up as APIConnectionError;
        # a couple of SDK retries is cheaper than failing Stage 1 cold.
        max_retries=2,
        default_headers=headers or None,
    )


def format_llm_connection_error(error: Exception, *, provider: str, base_url: str) -> str:
    """Short operator-facing reason when the text engine cannot be reached."""
    endpoint = (base_url or "").strip() or "OpenAI-compatible endpoint"
    return (
        f"Could not reach the text model at {endpoint}. "
        f"Check Settings → Text engine (base URL, API key, model), then retry. "
        f"Detail: {error}"
    )

def get_active_settings(user_id: str | None = None):
    """Load LLM settings for the active user.

    Returns a *detached* ``UserSettings`` snapshot with plaintext secrets so
    callers can read attributes after the DB session closes. Never returns a
    live/expunged ORM row (commit+expunge used to raise DetachedInstanceError
    when Fernet was unavailable and lazy re-encrypt kept marking the row dirty).
    """
    uid = user_id or _llm_user_id.get() or os.environ.get("SUNAIRUM_TASK_USER_ID") or ""
    db = SessionLocal()
    try:
        settings = None
        if uid:
            settings = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
        if not settings:
            return UserSettings(
                user_id=uid or "unset",
                provider="openai_compatible",
                base_url="",
                api_key="",
                model_name="",
                vision_model_name="",
                vision_base_url="",
                vision_api_key="",
                image_provider="openrouter",
                image_model_name="",
                image_base_url="",
                image_api_key="",
            )
        plain_key = decrypt_secret(settings.api_key)
        plain_vision = decrypt_secret(settings.vision_api_key)
        plain_image = decrypt_secret(getattr(settings, "image_api_key", None))

        # Only persist when encryption actually changes the stored value.
        # Without SETTINGS_SECRET_KEY, ensure_encrypted is a no-op and the old
        # dirty=True path committed + expunged every call → DetachedInstanceError.
        dirty = False
        if settings.api_key and not str(settings.api_key).startswith("enc:v1:"):
            encrypted = ensure_encrypted(plain_key)
            if encrypted != settings.api_key:
                settings.api_key = encrypted
                dirty = True
        if settings.vision_api_key and not str(settings.vision_api_key).startswith("enc:v1:"):
            encrypted_vision = ensure_encrypted(plain_vision)
            if encrypted_vision != settings.vision_api_key:
                settings.vision_api_key = encrypted_vision
                dirty = True
        if getattr(settings, "image_api_key", None) and not str(
            settings.image_api_key
        ).startswith("enc:v1:"):
            encrypted_image = ensure_encrypted(plain_image)
            if encrypted_image != settings.image_api_key:
                settings.image_api_key = encrypted_image
                dirty = True

        provider = coerce_stored_provider(settings.provider)
        if settings.provider != provider:
            settings.provider = provider
            dirty = True
        model_name = scrub_banned_model(settings.model_name)
        vision_model = scrub_banned_model(getattr(settings, "vision_model_name", None))
        image_model = scrub_banned_model(getattr(settings, "image_model_name", None))
        if model_name != (settings.model_name or ""):
            settings.model_name = model_name
            dirty = True
        if vision_model != (getattr(settings, "vision_model_name", None) or ""):
            settings.vision_model_name = vision_model
            dirty = True
        if image_model != (getattr(settings, "image_model_name", None) or ""):
            settings.image_model_name = image_model
            dirty = True
        image_provider = getattr(settings, "image_provider", None) or "openrouter"
        if str(image_provider).strip().lower() in {"gemini", "google"}:
            settings.image_provider = "openrouter"
            image_provider = "openrouter"
            dirty = True

        # Snapshot fields while the session is still open. UI values only.
        snapshot = UserSettings(
            id=settings.id,
            user_id=settings.user_id,
            provider=provider,
            base_url=settings.base_url or "",
            api_key=plain_key or "",
            model_name=model_name,
            vision_model_name=vision_model,
            vision_base_url=getattr(settings, "vision_base_url", None) or "",
            vision_api_key=plain_vision or "",
            image_provider=image_provider,
            image_model_name=image_model,
            image_base_url=getattr(settings, "image_base_url", None) or "",
            image_api_key=plain_image or "",
            connection_test_json=getattr(settings, "connection_test_json", None) or "",
        )
        if dirty:
            db.commit()
        return snapshot
    finally:
        db.close()

def _clean_json_output(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
    elif content.startswith("```"):
        content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
    # Some OpenAI-compatible models emit literal control characters inside
    # JSON strings. Replace only invalid controls; preserve JSON whitespace.
    content = "".join(
        character if ord(character) >= 0x20 or character in "\t\n\r" else " "
        for character in content
    )
    return content.strip()


def _message_text(content: Any) -> str:
    """Normalize OpenAI string/content-part responses into one JSON string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return str(content)


def _completion_text(response: Any) -> str:
    """Extract chat completion text; raise clearly when the provider returns null choices."""
    if response is None:
        raise RuntimeError("provider returned null response")
    choices = getattr(response, "choices", None)
    if choices is None:
        # OpenRouter occasionally returns HTTP 200 with choices:null (often with
        # prompt-cache extra_body). Include id/model for operator logs.
        rid = getattr(response, "id", None) or "?"
        model = getattr(response, "model", None) or "?"
        raise RuntimeError(f"provider returned null choices id={rid} model={model}")
    if not choices:
        raise RuntimeError("provider returned no choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    text = _message_text(content).strip() if content is not None else ""
    if not text:
        raise RuntimeError("provider returned an empty response")
    return text


def _is_retryable_empty_completion(error: BaseException) -> bool:
    detail = str(error).casefold()
    return any(
        token in detail
        for token in (
            "null choices",
            "no choices",
            "empty response",
            "null response",
        )
    )


def _parse_json_output(content: str, expected_type: type = dict):
    """Parse model JSON, repairing grammar once before failing closed."""
    cleaned = _clean_json_output(_message_text(content))
    if len(cleaned) > MAX_JSON_RESPONSE_CHARS:
        raise JsonParseError(
            f"model JSON response exceeds {MAX_JSON_RESPONSE_CHARS} characters"
        )
    try:
        parsed = json.loads(cleaned, strict=False)
    except json.JSONDecodeError as original_error:
        try:
            from json_repair import repair_json

            parsed = repair_json(cleaned, return_objects=True)
            print(
                "Model JSON grammar repair applied "
                f"at position {original_error.pos}"
            )
        except Exception as repair_error:
            raise JsonParseError(
                f"malformed model JSON: {original_error.msg} at position {original_error.pos}; "
                f"repair failed: {repair_error}",
                position=original_error.pos,
            ) from original_error
    if not isinstance(parsed, expected_type):
        expected_name = getattr(expected_type, "__name__", str(expected_type))
        raise JsonParseError(
            f"model JSON must be a {expected_name}, got {type(parsed).__name__}"
        )
    return parsed

def call_llm_json(system_instruction: str, prompt: str) -> dict:
    settings = get_active_settings()
    if coerce_stored_provider(settings.provider) != "openai_compatible":
        raise RuntimeError(
            "text engine must be OpenAI-compatible: update Settings → Text engine"
        )
    client = _openai_client(settings)
    try:
        sys_inst = system_instruction + "\n\nYou MUST return your answer as a valid JSON object. Do not include any markdown formatting or explanatory text."
        last_error: BaseException | None = None
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=(settings.model_name or "").strip(),
                    messages=[
                        {"role": "system", "content": sys_inst},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
                return _parse_json_output(_completion_text(response), dict)
            except RuntimeError as error:
                last_error = error
                if attempt == 0 and _is_retryable_empty_completion(error):
                    print(f"[llm_client] retrying JSON completion ({error})")
                    time.sleep(0.4)
                    continue
                raise
        raise RuntimeError(f"provider JSON completion failed: {last_error}")
    except JsonParseError as e:
        print(f"OpenAI Compatible JSON parse error: {e}")
        raise
    except Exception as e:
        print(f"OpenAI Compatible API error: {e}")
        name = type(e).__name__
        if "APIConnectionError" in name or "ConnectError" in name:
            raise RuntimeError(
                format_llm_connection_error(
                    e,
                    provider=settings.provider or "",
                    base_url=settings.base_url or "",
                )
            ) from e
        raise e

def vision_defaults() -> dict:
    """Placeholders for empty Settings fields (not live env secrets)."""
    return {
        "model_name": DEFAULT_VISION_MODEL,
        "base_url": DEFAULT_VISION_BASE_URL,
        "api_key_from_env": False,
    }


def resolve_vision_config() -> tuple[str, str, str]:
    """Return (model, base_url, api_key) for rendered QA from Settings only."""
    settings = get_active_settings()
    model = (settings.vision_model_name or "").strip()
    base_url = (settings.vision_base_url or "").strip()
    api_key = (settings.vision_api_key or "").strip()
    if not model:
        raise RuntimeError(
            "a vision model name is required: set it in Settings → Vision QA"
        )
    if not api_key:
        raise RuntimeError(
            "a vision API key is required: set it in Settings → Vision QA"
        )
    if not base_url:
        base_url = DEFAULT_VISION_BASE_URL
    return model, vision_chat_endpoint(base_url), api_key


def vision_chat_endpoint(base_url: str) -> str:
    """Keep review pointed at the chat endpoint rather than image generation.

    A base URL ending in `/images` is where a provider generates pictures. Review
    posts to `<base>/chat/completions`, so that setting produced
    `/v1/images/chat/completions` and a bare `404 Not Found` on every rendered
    slide -- for long enough that the vision pass looked implemented and was in
    fact never once executed.
    """
    trimmed = (base_url or "").rstrip("/")
    for suffix in _GENERATION_PATH_SUFFIXES:
        if trimmed.endswith(suffix):
            corrected = trimmed[: -len(suffix)] or DEFAULT_VISION_BASE_URL
            print(
                f"[vision] {base_url!r} is an image-generation endpoint; "
                f"reviewing through {corrected!r} instead"
            )
            return corrected
    return trimmed or DEFAULT_VISION_BASE_URL


def call_llm_vision(prompt: str, images: list[tuple[str, str]]) -> list:
    """Run multimodal review through an OpenAI-compatible vision endpoint."""
    model, base_url, api_key = resolve_vision_config()
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=_request_timeout_seconds(),
        max_retries=0,
        default_headers={
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost:3000"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "Sunairum"),
        },
    )
    content = [{"type": "text", "text": prompt}]
    for path, mime in images:
        with open(path, "rb") as stream:
            encoded = base64.b64encode(stream.read()).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        })
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=0.2,
            )
            choices = getattr(response, "choices", None) or []
            message = getattr(choices[0], "message", None) if choices else None
            output = getattr(message, "content", None)
            if not isinstance(output, str) or not output.strip():
                raise RuntimeError("vision endpoint returned no textual review")
            return _parse_json_output(output, list)
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f"vision review failed after 3 attempts: {last_error}") from last_error


def _prompt_cache_enabled(base_url: str) -> bool:
    global _prompt_cache_disabled
    if _prompt_cache_disabled:
        return False
    flag = os.environ.get("SUNAIRUM_PROMPT_CACHE", "1").strip().casefold()
    if flag in {"0", "false", "off", "no"}:
        return False
    return "openrouter.ai" in (base_url or "").casefold()


def _extract_cache_hit(response: Any) -> bool:
    usage = getattr(response, "usage", None)
    if usage is None:
        return False
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
        if cached is None and isinstance(details, dict):
            cached = details.get("cached_tokens")
        try:
            return int(cached or 0) > 0
        except (TypeError, ValueError):
            return False
    # Some providers expose cache fields flat on usage.
    for key in ("cached_tokens", "cache_read_input_tokens"):
        try:
            if int(getattr(usage, key, 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def call_llm_text(system_instruction: str, prompt: str) -> str:
    global _prompt_cache_disabled
    settings = get_active_settings()
    if coerce_stored_provider(settings.provider) != "openai_compatible":
        raise RuntimeError(
            "text engine must be OpenAI-compatible: update Settings → Text engine"
        )
    client = _openai_client(settings)
    base_url = (settings.base_url or "").strip()
    kwargs: dict[str, Any] = {
        "model": (settings.model_name or "").strip(),
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    extra_body: dict[str, Any] = {}
    if _prompt_cache_enabled(base_url):
        extra_body["cache_control"] = {"type": "ephemeral"}
        session = (_llm_session_id.get() or "").strip()
        if session:
            extra_body["session_id"] = session
    if extra_body:
        kwargs["extra_body"] = extra_body
    try:
        last_error: BaseException | None = None
        for attempt in range(2):
            try:
                try:
                    response = client.chat.completions.create(**kwargs)
                except Exception as cache_err:
                    # Fail-open: drop cache knobs and retry once (non-OR proxies / 400).
                    if extra_body and not _prompt_cache_disabled:
                        err_s = str(cache_err).casefold()
                        if (
                            "400" in err_s
                            or "cache_control" in err_s
                            or "session_id" in err_s
                        ):
                            _prompt_cache_disabled = True
                            print(
                                "[llm_client] prompt cache disabled for process "
                                f"({cache_err})"
                            )
                            kwargs.pop("extra_body", None)
                            response = client.chat.completions.create(**kwargs)
                        else:
                            raise
                    else:
                        raise
                _last_cache_hit.set(_extract_cache_hit(response))
                return _completion_text(response)
            except RuntimeError as error:
                last_error = error
                if attempt == 0 and _is_retryable_empty_completion(error):
                    # Same kwargs often keep returning null choices when
                    # cache_control/session_id is attached — strip and retry.
                    if "extra_body" in kwargs:
                        _prompt_cache_disabled = True
                        kwargs.pop("extra_body", None)
                        print(
                            "[llm_client] retrying text completion without prompt "
                            f"cache ({error})"
                        )
                    else:
                        print(f"[llm_client] retrying text completion ({error})")
                    time.sleep(0.4)
                    continue
                raise
        raise RuntimeError(f"provider text completion failed: {last_error}")
    except Exception as e:
        print(f"OpenAI Compatible API error: {e}")
        raise e


def _connection_test_timeout_seconds() -> float:
    try:
        return max(5.0, min(45.0, float(os.environ.get("LLM_CONNECTION_TEST_TIMEOUT_SECONDS", "20"))))
    except (TypeError, ValueError):
        return 20.0


def _short_error(error: BaseException, *, limit: int = 220) -> str:
    text = str(error).strip() or error.__class__.__name__
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def probe_text_connection(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model_name: str,
) -> dict[str, Any]:
    """Cheap live check that the text provider accepts credentials + model."""
    from tasks.settings_validation import SettingsValidationError, normalize_text_provider

    try:
        provider_norm = normalize_text_provider(provider)
    except SettingsValidationError as error:
        return {
            "ok": False,
            "skipped": False,
            "model": (model_name or "").strip(),
            "latency_ms": 0,
            "detail": str(error),
        }
    model = (model_name or "").strip()
    if not model:
        return {
            "ok": False,
            "skipped": False,
            "model": "",
            "latency_ms": 0,
            "detail": "Text model name is required in Settings",
        }
    timeout = _connection_test_timeout_seconds()
    started = time.perf_counter()
    try:
        if not (api_key or "").strip():
            raise RuntimeError("API key is required in Settings → Text engine")
        if not (base_url or "").strip():
            raise RuntimeError("Base URL is required in Settings → Text engine")
        client = OpenAI(
            base_url=base_url.strip(),
            api_key=api_key.strip(),
            timeout=timeout,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Reply with exactly: ok"},
                {"role": "user", "content": "ping"},
            ],
            temperature=0,
            max_tokens=8,
        )
        content = _completion_text(response)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": f"Responded in {latency_ms} ms",
        }
    except Exception as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": _short_error(error),
        }


def probe_vision_connection(
    *,
    model_name: str = "",
    base_url: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    """Live check for the multimodal review endpoint (text-only chat call)."""
    defaults = vision_defaults()
    model = (model_name or "").strip() or defaults["model_name"]
    endpoint = vision_chat_endpoint((base_url or "").strip() or defaults["base_url"])
    key = (api_key or "").strip()
    if not key:
        return {
            "ok": False,
            "skipped": True,
            "model": model,
            "latency_ms": 0,
            "detail": "No vision API key configured in Settings → Vision QA",
        }

    timeout = _connection_test_timeout_seconds()
    started = time.perf_counter()
    try:
        client = OpenAI(
            base_url=endpoint,
            api_key=key,
            timeout=timeout,
            max_retries=0,
            default_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost:3000"),
                "X-Title": os.environ.get("OPENROUTER_APP_NAME", "Sunairum"),
            },
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            temperature=0,
            max_tokens=8,
        )
        choices = getattr(response, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("vision endpoint returned an empty response")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": f"Responded in {latency_ms} ms",
        }
    except Exception as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "skipped": False,
            "model": model,
            "latency_ms": latency_ms,
            "detail": _short_error(error),
        }
