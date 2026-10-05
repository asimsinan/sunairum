"""Python bridge to the formula worker (TeX → MathML via MathJax; SVG legacy)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

_WORKER_DIR = Path(__file__).resolve().parent / "formula_worker"
_RENDER_JS = _WORKER_DIR / "render_math.mjs"
_RENDER_MATHML_JS = _WORKER_DIR / "render_mathml.mjs"
_MATHJAX_DIR = _WORKER_DIR / "node_modules" / "mathjax-full"
_LOCK = threading.Lock()
_NPM_READY = False


def _node_bin() -> str | None:
    return shutil.which("node")


def ensure_formula_worker_deps(*, timeout: float = 180.0) -> bool:
    """Install mathjax-full once if node_modules missing. Returns True when ready."""
    global _NPM_READY
    if _NPM_READY and _MATHJAX_DIR.is_dir():
        return True
    if not _node_bin():
        return False
    if not _RENDER_MATHML_JS.is_file() and not _RENDER_JS.is_file():
        return False
    with _LOCK:
        if _MATHJAX_DIR.is_dir():
            _NPM_READY = True
            return True
        npm = shutil.which("npm")
        if not npm:
            return False
        try:
            subprocess.run(
                [npm, "install", "--omit=dev", "--no-fund", "--no-audit"],
                cwd=str(_WORKER_DIR),
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "npm_config_update_notifier": "false"},
            )
        except (subprocess.SubprocessError, OSError):
            return False
        _NPM_READY = _MATHJAX_DIR.is_dir()
        return _NPM_READY


def _run_worker(script: Path, tex: str, *, display: bool, color: str) -> str:
    node = _node_bin()
    if not node or not script.is_file() or not ensure_formula_worker_deps():
        return ""
    payload = json.dumps(
        {"tex": tex, "display": display, "color": color},
        ensure_ascii=False,
    )
    try:
        proc = subprocess.run(
            [node, str(script)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=12.0,
            cwd=str(_WORKER_DIR),
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


@lru_cache(maxsize=256)
def _cached_render_mathml(tex: str, display: bool, color: str) -> str:
    out = _run_worker(_RENDER_MATHML_JS, tex, display=display, color=color)
    if "<math" not in out.casefold():
        return ""
    if "<svg" in out.casefold() or "foreignObject" in out:
        return ""
    return out


@lru_cache(maxsize=256)
def _cached_render_svg(tex: str, display: bool, color: str) -> str:
    out = _run_worker(_RENDER_JS, tex, display=display, color=color)
    if "<svg" not in out.casefold():
        return ""
    if "foreignObject" in out or "<style" in out.casefold():
        return ""
    return out


def render_tex_mathml(
    tex: str,
    *,
    display: bool = True,
    color: str = "#0F172A",
) -> str:
    """Render TeX to a MathML ``<math>`` fragment. Empty string on failure."""
    clean = str(tex or "").strip()
    if not clean:
        return ""
    _ = hashlib.sha1(clean.encode("utf-8")).hexdigest()
    try:
        return _cached_render_mathml(clean, bool(display), str(color or "#0F172A"))
    except Exception:
        return ""


def render_tex_svg(
    tex: str,
    *,
    display: bool = True,
    color: str = "#0F172A",
) -> str:
    """Legacy TeX → SVG (degraded path only). Prefer ``render_tex_mathml``."""
    clean = str(tex or "").strip()
    if not clean:
        return ""
    _ = hashlib.sha1(clean.encode("utf-8")).hexdigest()
    try:
        return _cached_render_svg(clean, bool(display), str(color or "#0F172A"))
    except Exception:
        return ""


def katex_available() -> bool:
    """True when the Node MathJax worker can render TeX."""
    return bool(_node_bin()) and ensure_formula_worker_deps()
