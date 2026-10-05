#!/usr/bin/env python3
"""Translate Chinese text in servers/fastapi/examples to English.

Modes:
  extract   — build/update .translation_cache.json keys (values empty)
  translate — fill missing cache values via app LLM
  apply     — rewrite .svg/.md/.json using the cache + SVG reflow
  verify    — write .translation_leftovers.md
  all       — extract → translate → apply → verify
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = APP_ROOT / "examples"
CACHE_PATH = EXAMPLES / ".translation_cache.json"
LEFTOVERS_PATH = EXAMPLES / ".translation_leftovers.md"
TEXT_EXTS = {".svg", ".md", ".json"}
HAN_RE = re.compile(r"[\u3400-\u9fff]")
CJK_FONT_RE = re.compile(
    r"(KaiTi|STKaiti|SimSun|SimHei|Microsoft YaHei|PingFang|Noto Sans CJK|"
    r"Source Han|WenQuanYi|FangSong|STSong|STHeiti)",
    re.I,
)
BATCH_SIZE = 28
MAX_UNIT_CHARS = 1200

sys.path.insert(0, str(APP_ROOT))


def has_han(text: str) -> bool:
    return bool(HAN_RE.search(text or ""))


def load_cache() -> dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) if v is not None else "" for k, v in data.items()}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def iter_text_files():
    for path in sorted(EXAMPLES.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        yield path


def extract_svg_units(text: str) -> list[str]:
    units: list[str] = []
    for match in re.finditer(r">([^<]*[\u3400-\u9fff][^<]*)<", text):
        unit = match.group(1).strip()
        if unit:
            units.append(unit)
    return units


def extract_md_units(text: str) -> list[str]:
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para or not has_han(para):
            continue
        if len(para) <= MAX_UNIT_CHARS:
            units.append(para)
            continue
        buf: list[str] = []
        size = 0
        for line in para.splitlines():
            line = line.rstrip()
            if not line:
                continue
            if size + len(line) + 1 > MAX_UNIT_CHARS and buf:
                chunk = "\n".join(buf).strip()
                if has_han(chunk):
                    units.append(chunk)
                buf, size = [], 0
            buf.append(line)
            size += len(line) + 1
        if buf:
            chunk = "\n".join(buf).strip()
            if has_han(chunk):
                units.append(chunk)
    return units


def extract_json_units(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return extract_md_units(text)
    units: list[str] = []

    def walk(node):
        if isinstance(node, str):
            if has_han(node):
                units.append(node.strip())
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(data)
    return units


def extract_units_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not has_han(text):
        return []
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return extract_svg_units(text)
    if suffix == ".json":
        return extract_json_units(text)
    return extract_md_units(text)


def cmd_extract(cache: dict[str, str]) -> dict[str, str]:
    added = 0
    for path in iter_text_files():
        for unit in extract_units_from_file(path):
            if unit not in cache:
                cache[unit] = ""
                added += 1
    save_cache(cache)
    pending = sum(1 for v in cache.values() if not str(v).strip())
    print(f"extract: keys={len(cache)} added={added} pending={pending}")
    return cache


def _configure_stdio() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass


def translate_batch(items: list[str]) -> dict[str, str]:
    from llm_client import call_llm_json

    numbered = {str(i + 1): text for i, text in enumerate(items)}
    system = (
        "You translate presentation and documentation text from Chinese to English. "
        "Return a JSON object mapping the same numeric string keys to English strings. "
        "Preserve numbers, Latin brands, punctuation intent, and markdown structure. "
        "Keep translations concise for slide labels. Do not add explanations."
    )
    prompt = (
        "Translate each value to natural English.\n\n"
        + json.dumps(numbered, ensure_ascii=False, indent=2)
    )
    result = call_llm_json(system, prompt)
    out: dict[str, str] = {}
    if not isinstance(result, dict):
        return out
    for key, source in numbered.items():
        value = result.get(key)
        if value is None:
            # Some models echo the source as key.
            value = result.get(source)
        if isinstance(value, str) and value.strip():
            out[source] = value.strip()
    return out


def cmd_translate(cache: dict[str, str]) -> dict[str, str]:
    pending = [k for k, v in cache.items() if has_han(k) and not str(v).strip()]
    print(f"translate: pending={len(pending)}")
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        attempt = 0
        while attempt < 3:
            attempt += 1
            try:
                mapped = translate_batch(batch)
                if not mapped:
                    raise RuntimeError("empty translation batch")
                for src, dst in mapped.items():
                    cache[src] = dst
                save_cache(cache)
                done = start + len(batch)
                print(f"  translated {done}/{len(pending)} (+{len(mapped)})")
                break
            except Exception as error:
                print(f"  batch failed (attempt {attempt}): {error}")
                time.sleep(min(8, 2 * attempt))
        else:
            print(f"  giving up on batch starting at {start}")
        time.sleep(0.35)
    pending_left = sum(1 for k, v in cache.items() if has_han(k) and not str(v).strip())
    print(f"translate: pending_left={pending_left}")
    return cache


def estimate_width(text: str) -> float:
    width = 0.0
    for ch in text:
        if HAN_RE.match(ch):
            width += 1.0
        elif ch == " ":
            width += 0.33
        else:
            width += 0.55
    return width


def latin_font_stack(original: str) -> str:
    lower = original.lower()
    if any(token in lower for token in ("kai", "song", "serif", "georgia", "times")):
        return 'Georgia, "Times New Roman", serif'
    return 'Arial, Helvetica, sans-serif'


def reflow_text_element(elem: ET.Element, old_text: str, new_text: str) -> None:
    old_w = max(estimate_width(old_text), 0.01)
    new_w = estimate_width(new_text)
    font_size = None
    for attr in ("font-size", "fontSize"):
        raw = elem.attrib.get(attr) or elem.attrib.get(attr.lower())
        if raw:
            match = re.search(r"([\d.]+)", raw)
            if match:
                font_size = float(match.group(1))
                size_attr = attr if attr in elem.attrib else "font-size"
                break
    else:
        size_attr = "font-size"
        style = elem.attrib.get("style", "")
        match = re.search(r"font-size\s*:\s*([\d.]+)", style)
        if match:
            font_size = float(match.group(1))

    if font_size and new_w > old_w * 1.15:
        scale = min(1.0, (old_w * 1.05) / new_w)
        scaled = max(font_size * 0.70, font_size * scale)
        if size_attr in elem.attrib or "font-size" in elem.attrib:
            key = "font-size" if "font-size" in elem.attrib else size_attr
            raw = elem.attrib.get(key, str(font_size))
            unit = re.sub(r"[\d.]+", "", raw) or ""
            elem.set(key if key in elem.attrib else "font-size", f"{scaled:.2f}{unit}")
        elif "style" in elem.attrib:
            elem.set(
                "style",
                re.sub(
                    r"font-size\s*:\s*[\d.]+[a-z%]*",
                    f"font-size:{scaled:.2f}",
                    elem.attrib["style"],
                    count=1,
                ),
            )
        if new_w * (scaled / font_size) > old_w * 1.2 and len(new_text) < 48:
            elem.set("textLength", f"{old_w * font_size:.1f}")
            elem.set("lengthAdjust", "spacingAndGlyphs")

    for attr in ("font-family", "fontFamily"):
        if attr in elem.attrib and CJK_FONT_RE.search(elem.attrib[attr]):
            elem.set(attr, latin_font_stack(elem.attrib[attr]))
    if "style" in elem.attrib and CJK_FONT_RE.search(elem.attrib["style"]):
        elem.set(
            "style",
            CJK_FONT_RE.sub("Georgia", elem.attrib["style"]),
        )


def _entity_variants(src: str, dst: str) -> list[tuple[str, str]]:
    pairs = [(src, dst)]
    u_src, u_dst = html.unescape(src), html.unescape(dst)
    pairs.append((u_src, u_dst))
    e_src = u_src.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    e_dst = u_dst.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pairs.append((e_src, e_dst))
    return pairs


def apply_text_replacements(text: str, cache: dict[str, str]) -> str:
    # Longest first avoids partial overlaps. Include HTML-entity variants so
    # SVG text like `P95 &lt; 5s · 单次成本` still matches cache keys.
    pairs: list[tuple[str, str]] = []
    for src, dst in cache.items():
        if not src or not dst or not has_han(src):
            continue
        pairs.extend(_entity_variants(src, dst))
    pairs = list(dict.fromkeys(pairs))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    for src, dst in pairs:
        if src in text:
            text = text.replace(src, dst)
    return text


def apply_svg(path: Path, cache: dict[str, str]) -> bool:
    original = path.read_text(encoding="utf-8", errors="ignore")
    if not has_han(original):
        return False

    # Prefer structural edit when XML parses; fall back to string replace.
    try:
        # Preserve default namespace by keeping xmlns on root via register.
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        root = ET.fromstring(original)
        changed = False
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag not in {"text", "tspan", "title", "desc"}:
                continue
            if elem.text and has_han(elem.text):
                key = elem.text.strip()
                # Exact and in-string cache hits.
                new = cache.get(key) or cache.get(elem.text)
                if not new:
                    replaced = apply_text_replacements(elem.text, cache)
                    if replaced != elem.text:
                        old = elem.text
                        elem.text = replaced
                        reflow_text_element(elem, old, replaced)
                        changed = True
                    continue
                old = elem.text
                # Keep surrounding whitespace style from original when key was stripped.
                prefix = elem.text[: len(elem.text) - len(elem.text.lstrip())]
                suffix = elem.text[len(elem.text.rstrip()) :]
                elem.text = f"{prefix}{new}{suffix}"
                reflow_text_element(elem, old, elem.text)
                changed = True
            if elem.tail and has_han(elem.tail):
                new_tail = apply_text_replacements(elem.tail, cache)
                if new_tail != elem.tail:
                    elem.tail = new_tail
                    changed = True
        if changed:
            # ElementTree may alter header; keep XML declaration if present.
            body = ET.tostring(root, encoding="unicode")
            if original.lstrip().startswith("<?xml"):
                decl = original.split("?>", 1)[0] + "?>\n"
                path.write_text(decl + body + "\n", encoding="utf-8")
            else:
                path.write_text(body + "\n", encoding="utf-8")
            # Font families in attributes outside text nodes.
            rewritten = path.read_text(encoding="utf-8")
            if CJK_FONT_RE.search(rewritten):
                path.write_text(CJK_FONT_RE.sub("Georgia", rewritten), encoding="utf-8")
            return True
    except ET.ParseError:
        pass

    updated = apply_text_replacements(original, cache)
    if CJK_FONT_RE.search(updated):
        updated = CJK_FONT_RE.sub("Georgia", updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def apply_plain(path: Path, cache: dict[str, str]) -> bool:
    original = path.read_text(encoding="utf-8", errors="ignore")
    if not has_han(original):
        return False
    updated = apply_text_replacements(original, cache)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def cmd_apply(cache: dict[str, str]) -> None:
    usable = {k: v for k, v in cache.items() if k and str(v).strip()}
    changed_files = 0
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not has_han(text):
            continue
        if path.suffix.lower() == ".svg":
            ok = apply_svg(path, usable)
        else:
            ok = apply_plain(path, usable)
        if ok:
            changed_files += 1
            print(f"  applied {path.relative_to(EXAMPLES)}")
    print(f"apply: changed_files={changed_files}")


def cmd_verify() -> None:
    text_leftovers: list[str] = []
    binary_hits: list[str] = []
    for path in sorted(EXAMPLES.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = str(path.relative_to(EXAMPLES))
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTS:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if has_han(text):
                count = len(HAN_RE.findall(text))
                text_leftovers.append(f"- `{rel}` ({count} Han chars)")
        elif suffix in {".png", ".jpg", ".jpeg", ".pptx", ".gif", ".webp"}:
            # Do not byte-scan large binaries (slow / noisy). List packs that
            # still have Chinese in their path or that are export containers.
            if has_han(rel) or suffix == ".pptx":
                binary_hits.append(f"- `{rel}`")

    lines = [
        "# Translation leftovers",
        "",
        f"Generated by `scripts/translate_examples_to_english.py verify`.",
        "",
        f"## Editable text still containing Chinese ({len(text_leftovers)})",
        "",
    ]
    lines.extend(text_leftovers or ["- none"])
    lines.extend(["", f"## Binary assets that may contain Chinese ({len(binary_hits)})", ""])
    lines.extend(binary_hits or ["- none"])
    lines.append("")
    LEFTOVERS_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"verify: text_leftovers={len(text_leftovers)} binary_hits={len(binary_hits)}")
    print(f"verify: wrote {LEFTOVERS_PATH}")


def main():
    _configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=["extract", "translate", "apply", "verify", "all"],
    )
    args = parser.parse_args()
    os.chdir(APP_ROOT)
    cache = load_cache()
    if args.mode in {"extract", "all"}:
        cache = cmd_extract(cache)
    if args.mode in {"translate", "all"}:
        cache = cmd_translate(cache)
    if args.mode in {"apply", "all"}:
        cmd_apply(cache)
    if args.mode in {"verify", "all"}:
        cmd_verify()


if __name__ == "__main__":
    main()
