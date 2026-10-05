"""Deck editor helpers: rebuild PPTX, reorder/duplicate/delete slides, image upload."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

SLIDE_RE = re.compile(r"^slide_(\d+)\.(json|html|png)$")
PPTX_COMPILE_TIMEOUT_SECONDS = 600

_ARTIFACT_DIRS = (
    ("html_output", ".html"),
    ("preview", ".png"),
    ("scene", ".json"),
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_slide_files(proj_dir: str | Path) -> list[Path]:
    """Return the authoritative Scene-v2 HTML slide files."""
    return sorted((Path(proj_dir) / "html_output").glob("slide_*.html"))


def _slide_index(name: str) -> int | None:
    match = SLIDE_RE.match(name)
    return int(match.group(1)) if match else None


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def rebuild_pptx(proj_dir: str | Path, project_id: str) -> dict:
    """Compile html_output/ into a new PPTX release via deckhtml."""
    root = Path(proj_dir)
    from tasks.release_export import ReleaseExportError, resolve_cached_released_pptx

    try:
        cached_path, _cached_sha, cached_manifest = resolve_cached_released_pptx(root)
        return {
            "status": cached_manifest.get("status") or "released",
            "pptx": cached_path,
            "cache_hit": True,
            **cached_manifest,
        }
    except ReleaseExportError:
        pass

    from tasks.html_to_pptx import finalize_compile_html

    html_dir = root / "html_output"
    if not any(html_dir.glob("slide_*.html")):
        raise FileNotFoundError("No HTML slides to rebuild")
    from tasks.release_export import snapshot_current_release_as_previous

    snapshot_current_release_as_previous(root)
    result = finalize_compile_html(str(root), project_id=project_id)
    pptx_path = Path(result["pptx_path"])
    from tasks.release_export import write_release_manifest

    manifest = result.get("release_manifest") or write_release_manifest(
        root,
        pptx_path=pptx_path,
        project_id=project_id,
        mode="html_deckhtml",
    )
    return {
        "status": manifest.get("status") or "released",
        "pptx": str(pptx_path),
        "cache_hit": False,
        **manifest,
    }


def _stem(name: str) -> str:
    return Path(name).stem


def reorder_slides(proj_dir: str | Path, filenames: list[str]) -> list[str]:
    """Transactionally reorder HTML, Scene, preview, and note artifacts."""
    root = Path(proj_dir)
    current = {p.name: p for p in list_slide_files(root)}
    requested_stems = [_stem(n) for n in filenames]
    current_stems = [_stem(n) for n in current]
    if set(requested_stems) != set(current_stems):
        raise ValueError("Reorder list must include every existing slide exactly once")
    for name in filenames:
        if not SLIDE_RE.match(name) and not re.match(r"^slide_\d+$", _stem(name)):
            raise ValueError(f"Invalid slide filename: {name}")

    staging = root / f".reorder_{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        staged_names: list[str] = []
        for index, old_name in enumerate(filenames, start=1):
            old_stem = _stem(old_name)
            new_stem = f"slide_{index:02d}"
            for dirname, ext in _ARTIFACT_DIRS:
                src = root / dirname / f"{old_stem}{ext}"
                if src.is_file():
                    dest_dir = staging / dirname
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest_dir / f"{new_stem}{ext}")
            notes_src = root / "notes" / f"{old_stem}.md"
            if notes_src.is_file():
                (staging / "notes").mkdir(parents=True, exist_ok=True)
                shutil.copy2(notes_src, staging / "notes" / f"{new_stem}.md")
            staged_names.append(f"{new_stem}.html")

        for dirname, ext in _ARTIFACT_DIRS:
            d = root / dirname
            if d.is_dir():
                for path in d.glob(f"slide_*{ext}"):
                    path.unlink()
        for dirname, ext in _ARTIFACT_DIRS:
            staged = staging / dirname
            if not staged.is_dir():
                continue
            (root / dirname).mkdir(parents=True, exist_ok=True)
            for path in staged.glob(f"slide_*{ext}"):
                os.replace(path, root / dirname / path.name)
        notes_dir = root / "notes"
        if notes_dir.is_dir():
            for stale in notes_dir.glob("slide_*.md"):
                stale.unlink()
        staged_notes = staging / "notes"
        if staged_notes.is_dir():
            notes_dir.mkdir(parents=True, exist_ok=True)
            for notes_file in staged_notes.glob("slide_*.md"):
                os.replace(notes_file, notes_dir / notes_file.name)

        from tasks.html_pipeline import (
            _render_preview_png,
            sanitize_html_presentation_chrome,
        )

        total = len(staged_names)
        for index, staged_name in enumerate(staged_names, start=1):
            html_path = root / "html_output" / staged_name
            authored = html_path.read_text(encoding="utf-8")
            authored = sanitize_html_presentation_chrome(
                authored,
                slide_number=index,
                total_slides=total,
            )
            html_path.write_text(
                authored if authored.endswith("\n") else authored + "\n",
                encoding="utf-8",
            )
            preview_path = root / "preview" / f"slide_{index:02d}.png"
            try:
                preview_ok = _render_preview_png(authored, str(preview_path))
            except Exception:  # noqa: BLE001
                preview_ok = False
            if not preview_ok:
                preview_path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _invalidate_release(root)
    return staged_names


def duplicate_slide(proj_dir: str | Path, filename: str) -> list[str]:
    root = Path(proj_dir)
    stem = _stem(filename)
    if _slide_index(f"{stem}.json") is None and _slide_index(f"{stem}.html") is None:
        raise ValueError("Invalid slide filename")
    slides = list_slide_files(root)
    order = [p.name for p in slides]
    if stem not in {_stem(n) for n in order}:
        raise FileNotFoundError(filename)
    insert_at = next(i for i, n in enumerate(order) if _stem(n) == stem) + 1
    new_stem = f"slide_{len(slides) + 1:02d}"
    for dirname, ext in _ARTIFACT_DIRS:
        src = root / dirname / f"{stem}{ext}"
        if src.is_file():
            (root / dirname).mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / dirname / f"{new_stem}{ext}")
    order.insert(insert_at, f"{new_stem}.html")
    return reorder_slides(root, order)


def delete_slide(proj_dir: str | Path, filename: str) -> list[str]:
    root = Path(proj_dir)
    slides = list_slide_files(root)
    if len(slides) <= 1:
        raise ValueError("Cannot delete the last slide")
    stem = _stem(filename)
    if stem not in {_stem(p.name) for p in slides}:
        raise FileNotFoundError(filename)
    order = [p.name for p in slides if _stem(p.name) != stem]
    for dirname, ext in _ARTIFACT_DIRS:
        (root / dirname / f"{stem}{ext}").unlink(missing_ok=True)
    notes = root / "notes" / f"{stem}.md"
    notes.unlink(missing_ok=True)
    return reorder_slides(root, order)


def save_uploaded_image(proj_dir: str | Path, filename: str, data: bytes) -> dict:
    root = Path(proj_dir)
    images = root / "images"
    images.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    if not safe or ".." in safe:
        raise ValueError("Invalid image filename")
    ext = Path(safe).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        raise ValueError("Unsupported image type")
    stored = f"edit_{uuid.uuid4().hex[:10]}{ext}"
    path = images / stored
    path.write_bytes(data)
    return {
        "filename": stored,
        "relative_path": f"../images/{stored}",
        "abs_path": str(path),
    }


def generate_ai_image_for_editor(
    proj_dir: str | Path,
    *,
    prompt: str,
    aspect_ratio: str = "16:9",
    user_id: str | None = None,
    slide: int | None = None,
) -> dict:
    """Generate a PNG via Settings → Image engine for the slide editor."""
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("Prompt is required")
    if len(text) > 4000:
        raise ValueError("Prompt is too long (max 4000 characters)")
    ratio = str(aspect_ratio or "16:9").strip() or "16:9"
    if ratio not in {"16:9", "4:3", "1:1", "3:4", "9:16", "auto"}:
        raise ValueError("Unsupported aspect_ratio")

    from tasks.image_settings import generate_presentation_image, resolve_image_config

    resolve_image_config(user_id)
    root = Path(proj_dir)
    images = root / "images"
    images.mkdir(parents=True, exist_ok=True)
    slide_bit = f"_s{int(slide):02d}" if slide and int(slide) > 0 else ""
    stored = f"ai_editor{slide_bit}_{uuid.uuid4().hex[:10]}.png"
    path = images / stored
    generate_presentation_image(
        prompt=text,
        output_path=str(path),
        aspect_ratio=ratio,
        image_size="1K",
        user_id=user_id,
    )
    if not path.is_file():
        raise RuntimeError("Image engine did not write an output file")
    return {
        "filename": stored,
        "relative_path": f"../images/{stored}",
        "abs_path": str(path),
        "prompt": text,
        "aspect_ratio": ratio,
    }


def _invalidate_release(root: Path) -> None:
    validation = root / "validation"
    release = validation / "release_manifest.json"
    if release.is_file():
        previous = validation / "previous_release_manifest.json"
        temporary = previous.with_suffix(".json.tmp")
        shutil.copy2(release, temporary)
        os.replace(temporary, previous)
        release.unlink(missing_ok=True)
    (validation / "quality_review.json").unlink(missing_ok=True)


def _plain_slide_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def save_slide_html(
    proj_dir: str | Path,
    filename: str,
    html_content: str,
    *,
    refresh_preview: bool = True,
) -> dict[str, Any]:
    """Persist free-form HTML editor writes to ONE html_output file (+ its preview PNG).

    Does **not** reorder, rename, duplicate, or delete any slide. Other
    ``slide_*.html`` / preview / notes files are left untouched.
    """
    root = Path(proj_dir)
    stem = _stem(filename)
    if _slide_index(f"{stem}.html") is None:
        raise ValueError("Invalid slide filename")
    html = str(html_content or "").strip()
    if not html:
        raise ValueError("HTML content is empty")
    if len(html) > 2_500_000:
        raise ValueError("HTML content is too large")
    # Basic sanity — reject non-document payloads.
    lowered = html[:500].casefold()
    if "<html" not in lowered and "<!doctype" not in lowered and "<section" not in lowered:
        raise ValueError("Expected a full HTML slide document")

    html_dir = root / "html_output"
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"{stem}.html"
    # Edits must target an existing stem — never create a new ordered slot.
    if not html_path.is_file():
        raise FileNotFoundError(filename)

    from tasks.html_constitution import ensure_slide_root

    doc = ensure_slide_root(html)
    # Strip ephemeral editor chrome if the client forgot.
    doc = re.sub(
        r"<style[^>]*id=[\"']__sun-editor-style[\"'][^>]*>[\s\S]*?</style>",
        "",
        doc,
        flags=re.I,
    )
    doc = re.sub(r"\sclass=([\"'])(?:[^\"']*\s)?__sun-(?:sel|edit)(?:\s[^\"']*)?\1", "", doc)
    doc = re.sub(r"\scontenteditable=([\"'])[^\"']*\1", "", doc, flags=re.I)

    temporary = html_path.with_suffix(".html.tmp")
    temporary.write_text(doc, encoding="utf-8")
    os.replace(temporary, html_path)

    preview_ok = False
    if refresh_preview:
        try:
            from tasks.html_pipeline import _render_preview_png

            preview_dir = root / "preview"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview_ok = bool(_render_preview_png(doc, str(preview_dir / f"{stem}.png")))
        except Exception as error:
            print(f"[deck_editor] preview refresh failed for {stem}: {error}")

    from tasks.html_layout_qa import audit_runtime_html_layout

    layout_qa = audit_runtime_html_layout(doc)
    report_path = root / "validation" / "editor_layout_qa" / f"{stem}.json"
    _write_json_atomic(report_path, layout_qa)

    _invalidate_release(root)
    previous_release_available = (
        root / "validation" / "previous_release_manifest.json"
    ).is_file()
    return {
        # Free-form editing is intentionally permissive. Runtime layout QA is
        # recorded for the export transaction, but it must never turn a
        # successful save into an editor failure.
        "status": "ok",
        "filename": f"{stem}.html",
        "stem": stem,
        "preview_refreshed": preview_ok,
        "sha256": _sha256_file(html_path),
        "layout_valid": bool(layout_qa.get("ok")),
        "layout_qa": layout_qa,
        "layout_advisory": not bool(layout_qa.get("ok")),
        "previous_release_available": previous_release_available,
    }


def edit_element_text(
    *,
    text: str,
    instruction: str,
    grounding_mode: str = "scratch",
) -> dict[str, Any]:
    """Selection-scoped AI rewrite for one text element.

    Returns ``{"text": "..."}``. Falls back to a deterministic trim when the
    model is unavailable so the editor never hard-fails on AI outages.
    """
    source = str(text or "").strip()
    request = str(instruction or "").strip()
    if not source:
        raise ValueError("No text to edit")
    if not request:
        raise ValueError("Instruction is required")

    system = (
        "You are Sunairum's selection editor. Rewrite ONLY the supplied text "
        "according to the instruction. Return plain text only — no JSON, no "
        "markdown fences, no commentary. Preserve factual numbers and proper "
        "nouns unless the instruction explicitly asks to change them."
    )
    if grounding_mode == "pdf_strict":
        system += (
            " This deck is PDF-grounded: do not invent numbers or claims that "
            "are not already present in the supplied text."
        )
    user = f"Instruction: {request}\n\nText:\n{source}"
    try:
        from llm_client import call_llm_text

        rewritten = str(call_llm_text(system, user) or "").strip()
        if rewritten.startswith("```"):
            rewritten = re.sub(r"^```(?:\w+)?\s*", "", rewritten)
            rewritten = re.sub(r"\s*```$", "", rewritten).strip()
        if rewritten:
            return {"text": rewritten, "source": "model"}
    except Exception as error:
        print(f"[deck_editor] edit_element LLM failed: {error}")

    lowered = request.casefold()
    if "shorten" in lowered or "concise" in lowered or "brief" in lowered:
        sentences = re.split(r"(?<=[.!?])\s+", source)
        trimmed = " ".join(sentences[: max(1, min(2, len(sentences)))]).strip()
        return {"text": trimmed or source, "source": "fallback"}
    return {"text": source, "source": "fallback"}
