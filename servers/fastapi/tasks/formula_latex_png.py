"""Block formulas → PNG only (Codecogs or MathJax SVG → rsvg/cairosvg).

TeX remains the IR. Flat MathJax path groups are never paint-ready output.
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def _ascii_to_tex_fallback(formula: str) -> str:
    text = " ".join(str(formula or "").replace("`", "").split())
    if not text:
        return ""
    if "\\" in text or "{" in text:
        return text
    try:
        from tasks.math_ast import ascii_to_ast, ast_to_tex

        ast = ascii_to_ast(text)
        if ast is not None:
            tex = ast_to_tex(ast)
            if tex:
                return tex
    except Exception:
        pass
    # Prefer real subscripts (C_0 → C_{0}) over literal underscores.
    text = re.sub(r"\b([A-Za-z]+)_([A-Za-z0-9]+)\b", r"\1_{\2}", text)
    text = text.replace("*", "\\cdot ")
    text = re.sub(r"\bbeta\b", r"\\beta", text, flags=re.I)
    text = re.sub(r"\bgamma\b", r"\\gamma", text, flags=re.I)
    text = re.sub(r"\bDelta\b", r"\\Delta", text)
    return text


def resolve_formula_tex(formula: str = "", formula_tex: str = "") -> str:
    tex = str(formula_tex or "").strip()
    if tex:
        return tex
    return _ascii_to_tex_fallback(formula)


def _expand_math_svg(svg: str) -> ET.Element | None:
    text = str(svg or "").strip()
    if "<svg" not in text.casefold():
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    return root


def _local(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in str(tag):
        return str(tag).rsplit("}", 1)[-1].casefold()
    return str(tag).casefold()


def flatten_math_svg_to_group(
    svg: str,
    *,
    width: float,
    height: float,
    fill: str = "#1A365D",
) -> str:
    """Legacy helper retained for tests; not used as paint-ready formula output."""
    root = _expand_math_svg(svg)
    if root is None:
        return ""
    vb = (root.get("viewBox") or "").strip().split()
    try:
        vx, vy, vw, vh = (
            (float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3]))
            if len(vb) == 4
            else (0.0, 0.0, width, height)
        )
    except (TypeError, ValueError):
        vx, vy, vw, vh = 0.0, 0.0, width, height
    scale = min(width / max(vw, 1.0), height / max(vh, 1.0))
    parts: list[str] = [
        f'<g data-sunairum-formula-math="1" fill="{fill}" stroke="none" '
        f'stroke-width="0" '
        f'transform="translate({-vx * scale:.3f},{-vy * scale:.3f}) '
        f'scale({scale:.6f})">'
    ]

    def walk(elem: ET.Element) -> None:
        tag = _local(elem.tag)
        if tag in {"defs", "style", "title", "desc", "metadata"}:
            return
        if tag == "use":
            return
        if tag in {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}:
            if tag == "path" and not str(elem.get("d") or "").strip():
                return
            if tag in {"polygon", "polyline"} and not str(elem.get("points") or "").strip():
                return
            attrs = " ".join(
                f'{k}="{v}"'
                for k, v in elem.attrib.items()
                if not str(k).startswith("{") and k not in {"id", "class", "style"}
            )
            parts.append(f"<{tag} {attrs}/>" if attrs else f"<{tag}/>")
        for child in list(elem):
            walk(child)

    walk(root)
    parts.append("</g>")
    return "".join(parts)


def _try_rasterize_svg(
    svg: str,
    out_png: Path,
    *,
    width_px: float | None = None,
    height_px: float | None = None,
) -> bool:
    """SVG→PNG via rsvg-convert / cairosvg / inkscape / convert.

    Pass only one of width/height so the rasterizer preserves aspect ratio
    (passing both stretches glyphs — the red ``\\`` / ``[`` failure mode).
    """
    w_flag = int(max(64, width_px or 0)) if width_px else 0
    h_flag = int(max(32, height_px or 0)) if height_px else 0
    # Prefer width-driven scale; ignore height when both are set.
    if w_flag and h_flag:
        h_flag = 0
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = Path(tmp) / "formula.svg"
        svg_path.write_text(svg, encoding="utf-8")
        attempts: list[list[str]] = []
        if shutil.which("rsvg-convert"):
            cmd = ["rsvg-convert", "-f", "png"]
            if w_flag:
                cmd.extend(["-w", str(w_flag)])
            elif h_flag:
                cmd.extend(["-h", str(h_flag)])
            cmd.extend(["-o", str(out_png), str(svg_path)])
            attempts.append(cmd)
        if shutil.which("convert"):
            attempts.append(["convert", "-background", "none", str(svg_path), str(out_png)])
        if shutil.which("inkscape"):
            ink = ["inkscape", str(svg_path), f"--export-filename={out_png}"]
            if w_flag:
                ink.append(f"--export-width={w_flag}")
            elif h_flag:
                ink.append(f"--export-height={h_flag}")
            attempts.append(ink)
        for cmd in attempts:
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=20, check=False
                )
                if proc.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 32:
                    return True
            except (subprocess.SubprocessError, OSError):
                continue
    try:
        import cairosvg  # type: ignore

        kwargs: dict[str, Any] = {"bytestring": svg.encode("utf-8"), "write_to": str(out_png)}
        if w_flag:
            kwargs["output_width"] = w_flag
        elif h_flag:
            kwargs["output_height"] = h_flag
        cairosvg.svg2png(**kwargs)
        if out_png.is_file() and out_png.stat().st_size > 32:
            return True
    except Exception:
        pass
    return False


def formula_png_is_usable(
    png_path: str | Path,
    *,
    ink: str = "#1A365D",
) -> bool:
    """Reject Codecogs/MathJax error rasters (pure-red scribble, empty ink)."""
    path = Path(png_path)
    if not path.is_file() or path.stat().st_size < 64:
        return False
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return path.stat().st_size > 200

    try:
        with Image.open(path) as im:
            rgba = im.convert("RGBA")
            arr = np.asarray(rgba)
    except Exception:
        return False
    if arr.ndim != 3 or arr.shape[0] < 8 or arr.shape[1] < 16:
        return False
    alpha = arr[:, :, 3]
    opaque = alpha >= 128
    opaque_n = int(opaque.sum())
    if opaque_n < 80:
        return False
    r = arr[:, :, 0][opaque].astype("int16")
    g = arr[:, :, 1][opaque].astype("int16")
    b = arr[:, :, 2][opaque].astype("int16")
    # Codecogs TeX errors paint pure red glyphs on transparent canvas.
    ink_hex = (ink or "").lstrip("#")
    ink_is_red = False
    if len(ink_hex) == 6:
        try:
            ir, ig, ib = int(ink_hex[0:2], 16), int(ink_hex[2:4], 16), int(ink_hex[4:6], 16)
            ink_is_red = ir > 180 and ig < 90 and ib < 90
        except ValueError:
            ink_is_red = False
    pure_red = (r > 200) & (g < 80) & (b < 80)
    if not ink_is_red and float(pure_red.sum()) / float(opaque_n) > 0.55:
        return False
    # Reject absurdly wide hairline rasters (failed layout → stretched strip).
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if h > 0 and w / h > 40.0:
        return False
    return True


def _trim_formula_png(png_path: Path, *, pad: int = 6) -> None:
    """Crop transparent padding so placement uses tight ink bounds."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return
    try:
        with Image.open(png_path) as im:
            rgba = im.convert("RGBA")
            arr = np.asarray(rgba)
            alpha = arr[:, :, 3]
            ys, xs = (alpha >= 16).nonzero()
            if len(xs) == 0 or len(ys) == 0:
                return
            x0 = max(0, int(xs.min()) - pad)
            y0 = max(0, int(ys.min()) - pad)
            x1 = min(arr.shape[1], int(xs.max()) + 1 + pad)
            y1 = min(arr.shape[0], int(ys.max()) + 1 + pad)
            cropped = rgba.crop((x0, y0, x1, y1))
            cropped.save(png_path)
    except Exception:
        return


def _try_codecogs_png(tex: str, out_png: Path, *, color: str = "1A365D") -> bool:
    """Optional online render. Fail soft offline; reject red error rasters."""
    import urllib.parse
    import urllib.request

    hex_color = color.lstrip("#")
    payload = urllib.parse.quote(f"\\dpi{{300}} \\color{{{hex_color}}} {tex}")
    url = f"https://latex.codecogs.com/png.image?{payload}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
            data = resp.read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        out_png.write_bytes(data)
        if not formula_png_is_usable(out_png, ink=f"#{hex_color}"):
            try:
                out_png.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        _trim_formula_png(out_png)
        return out_png.is_file()
    except Exception:
        return False


def _attach_png(out: dict[str, Any], png_path: Path, *, ink: str = "#1A365D") -> dict[str, Any]:
    if not formula_png_is_usable(png_path, ink=ink):
        return out
    _trim_formula_png(png_path)
    out["png_path"] = str(png_path)
    out["png_href"] = f"../images/{png_path.name}"
    out["flat_group"] = ""
    try:
        out["data_uri"] = (
            "data:image/png;base64,"
            + base64.b64encode(png_path.read_bytes()).decode("ascii")
        )
    except OSError:
        pass
    try:
        from PIL import Image

        with Image.open(png_path) as im:
            out["width"] = float(im.width)
            out["height"] = float(im.height)
    except Exception:
        pass
    return out


def render_formula_asset(
    tex: str,
    *,
    images_dir: str | Path,
    formula_id: str = "formula_001",
    color: str = "#1A365D",
    prefer_network: bool = False,
) -> dict[str, Any]:
    """PNG-only formula asset. Local MathJax first; network only as validated fallback."""
    clean = str(tex or "").strip()
    out: dict[str, Any] = {
        "tex": clean,
        "png_path": "",
        "png_href": "",
        "data_uri": "",
        "flat_group": "",
        "width": 640.0,
        "height": 90.0,
    }
    if not clean:
        return out
    images = Path(images_dir)
    images.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{clean}|{color}".encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", formula_id) or "formula"
    png_path = images / f"{stem}_{digest}.png"

    # Reuse a previously validated local PNG.
    if png_path.is_file() and formula_png_is_usable(png_path, ink=color):
        return _attach_png(out, png_path, ink=color)

    from tasks.formula_katex import render_tex_svg

    def _local_mathjax() -> dict[str, Any]:
        svg = render_tex_svg(clean, display=True, color=color) or ""
        if not svg:
            return out
        wm = re.search(r'\bdata-sunairum-math-w="([-\d.]+)"', svg)
        hm = re.search(r'\bdata-sunairum-math-h="([-\d.]+)"', svg)
        try:
            layout_w = float(wm.group(1)) if wm else 320.0
            layout_h = float(hm.group(1)) if hm else 40.0
        except (TypeError, ValueError, AttributeError):
            layout_w, layout_h = 320.0, 40.0
        # Width-only raster (~3× CSS layout) — never force height.
        target_w = max(640.0, min(1800.0, layout_w * 3.5))
        out["math_svg"] = svg
        if _try_rasterize_svg(svg, png_path, width_px=target_w):
            attached = _attach_png(out, png_path, ink=color)
            if attached.get("data_uri") or attached.get("png_href"):
                return attached
            try:
                png_path.unlink(missing_ok=True)
            except OSError:
                pass
        return out

    # Local-first (reliable ink color). Network only if requested or local fails.
    if not prefer_network:
        local = _local_mathjax()
        if local.get("data_uri") or local.get("png_href"):
            return local
        if _try_codecogs_png(clean, png_path, color=color.lstrip("#")):
            return _attach_png(out, png_path, ink=color)
        return out

    if _try_codecogs_png(clean, png_path, color=color.lstrip("#")):
        return _attach_png(out, png_path, ink=color)
    local = _local_mathjax()
    if local.get("data_uri") or local.get("png_href"):
        return local
    out["flat_group"] = ""
    return out
