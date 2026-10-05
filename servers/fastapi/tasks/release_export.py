"""Resolve a released PPTX and derive a downloadable PDF beside it.

Default PDF stitches editor preview/slide_*.png (WYSIWYG). Missing slides are
hi-DPI HTML screenshots. LibreOffice Impress from the released PPTX remains
the fallback when HTML PDF fails or PDF_ENGINE=impress.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Bump when the export pipeline changes so stale caches are rebuilt.
# v10: preview/PDF at 300 dpi (DPR 3.125 → 4000×2250); skip sub-300 thumbs.
PDF_CACHE_VERSION = "html-preview-v10"
PPTX_EXPORT_CACHE_VERSION = "pptx-export-input-v1"


class ReleaseExportError(LookupError):
    """Raised when a project has no downloadable released PPTX."""


# Terminal states of an immutable release. ``released_with_defects`` publishes a
# deck whose visual/grounding QA found problems: the artifact is still delivered
# and downloadable, and the offending codes are listed in ``manifest["defects"]``.
RELEASE_STATUSES = frozenset({"released", "released_with_advisories", "released_with_defects"})

# Advisory codes that describe a visually or semantically degraded deck. They
# downgrade the release status and are reported to the user; they never block.
DEFECT_ADVISORY_CODES = frozenset(
    {
        "runtime_layout_failed",
        "runtime_layout_unavailable",
        "native_fidelity_failed",
        "fidelity_verifier_failed",
        "missing_previews",
        "whole_slide_raster_fallback",
    }
)


def is_published_release(status: str) -> bool:
    """True when a manifest status denotes a real, downloadable release.

    Every terminal release state is downloadable — including one carrying
    defects. Quality is reported alongside the artifact, never used to withhold
    it.
    """
    return str(status or "").strip() in RELEASE_STATUSES


def ui_status_for_release(status: str) -> str:
    """Map immutable-release lifecycle states onto UI/history states."""
    value = str(status or "").strip()
    if value in {"released_with_advisories", "released_with_defects"}:
        return "done_with_issues"
    if value == "released":
        return "done"
    return value


def _sha256_file(path: str | Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_source_revision(proj_dir: str | Path) -> dict:
    """Hash the immutable source set represented by a released presentation."""
    root = Path(proj_dir)
    members: list[tuple[str, str]] = []
    for dirname, pattern in (
        ("html_output", "slide_*.html"),
        ("scene", "slide_*.json"),
        ("notes", "slide_*.md"),
    ):
        directory = root / dirname
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                members.append((str(path.relative_to(root)).replace("\\", "/"), _sha256_file(path)))
    digest = hashlib.sha256()
    for relative, sha in members:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha.encode("ascii"))
        digest.update(b"\n")
    return {
        "sha256": digest.hexdigest(),
        "file_count": len(members),
        "files": [relative for relative, _sha in members],
    }


def project_export_revision(proj_dir: str | Path) -> dict:
    """Hash every input capable of changing the native PPTX artifact.

    This is deliberately broader than ``project_source_revision``: HTML,
    scenes and notes define the authored deck, while local assets, project
    settings and converter code can also change the binary export.
    """
    root = Path(proj_dir)
    members: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(path: Path, label: str | None = None) -> None:
        if not path.is_file():
            return
        relative = label or str(path.relative_to(root)).replace("\\", "/")
        if relative in seen:
            return
        seen.add(relative)
        members.append((relative, _sha256_file(path)))

    for dirname, pattern in (
        ("html_output", "slide_*.html"),
        ("scene", "slide_*.json"),
        ("notes", "slide_*.md"),
        ("images", "**/*"),
        ("figures", "**/*"),
        ("assets", "**/*"),
        ("tables", "**/*"),
    ):
        directory = root / dirname
        if directory.is_dir():
            for path in sorted(directory.glob(pattern)):
                add(path)

    for filename in ("result.json", "generation_preferences.json", "settings.json"):
        add(root / filename)

    # A deployment of new conversion logic must invalidate old native output
    # even when the project files themselves are unchanged.
    task_dir = Path(__file__).resolve().parent
    add(task_dir / "html_to_pptx.py", "@engine/html_to_pptx.py")
    vendor = task_dir.parent / "vendor" / "deckhtml"
    add(vendor / "package.json", "@engine/deckhtml/package.json")
    add(vendor / "dist" / "api.js", "@engine/deckhtml/api.js")
    add(vendor / "dist" / "generator.js", "@engine/deckhtml/generator.js")

    digest = hashlib.sha256()
    digest.update(PPTX_EXPORT_CACHE_VERSION.encode("ascii"))
    digest.update(b"\n")
    for relative, sha in sorted(members):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha.encode("ascii"))
        digest.update(b"\n")
    return {
        "sha256": digest.hexdigest(),
        "file_count": len(members),
        "version": PPTX_EXPORT_CACHE_VERSION,
        "files": [relative for relative, _sha in sorted(members)],
    }


def write_release_manifest(
    proj_dir: str | Path,
    *,
    pptx_path: str | Path,
    project_id: str = "",
    run_id: str = "",
    status: str = "released",
    mode: str = "html_deckhtml",
    source_revision: dict | None = None,
    release_id: str = "",
    advisories: list[dict] | None = None,
    compile_meta: dict | None = None,
) -> dict:
    """Write canonical validation/release_manifest.json for download/has_pptx."""
    root = Path(proj_dir)
    pptx = Path(pptx_path)
    if not pptx.is_file():
        raise FileNotFoundError(f"PPTX not found: {pptx}")
    try:
        rel = str(pptx.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = f"exports/{pptx.name}"
    validation = root / "validation"
    validation.mkdir(parents=True, exist_ok=True)

    run_manifest: dict = {}
    run_path = validation / "run_manifest.json"
    if run_path.is_file():
        try:
            run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            run_manifest = {}

    grounding_mode = str(run_manifest.get("grounding_mode") or "")
    # Publishing is never a refusal. A deck the user waited for is always
    # delivered; quality problems are reported *on* the release so the UI can
    # show them, offer a targeted re-generation, and still hand over a file.
    # Withholding the artifact used to strand the project in an active status
    # until the stale-status watchdog turned it into a generic error.
    defects: list[str] = []
    release_status = status
    if release_status not in RELEASE_STATUSES:
        defects.append(f"unknown_release_status:{release_status}")
        release_status = "released_with_advisories"
    gqa_path = validation / "grounding_qa.json"
    gqa_status = ""
    if gqa_path.is_file():
        try:
            gqa_status = str(
                json.loads(gqa_path.read_text(encoding="utf-8")).get("status") or ""
            )
        except (OSError, json.JSONDecodeError):
            gqa_status = ""
    if grounding_mode == "pdf_strict" and gqa_status and gqa_status != "passed":
        defects.append(f"grounding_qa_{gqa_status or 'unknown'}")

    advisory_codes = {
        str(item.get("code") or "") for item in (advisories or []) if isinstance(item, dict)
    }
    defects.extend(sorted(advisory_codes & DEFECT_ADVISORY_CODES))
    if defects:
        release_status = "released_with_defects"

    resolved_run = str(run_id or run_manifest.get("run_id") or "").strip()
    pptx_sha = _sha256_file(pptx)
    resolved_source_revision = source_revision or project_source_revision(root)
    manifest: dict = {
        "schema_version": "sunairum.release-manifest/v2",
        "project_id": project_id or str(run_manifest.get("project_id") or ""),
        "run_id": resolved_run,
        "status": release_status,
        "pptx_path": rel.replace("\\", "/"),
        "pptx_sha256": pptx_sha,
        "mode": mode,
        "grounding_mode": grounding_mode or None,
        "source_revision_sha256": resolved_source_revision.get("sha256"),
        "source_file_count": resolved_source_revision.get("file_count", 0),
        "release_id": release_id or str(resolved_source_revision.get("sha256") or "")[:16],
        "export_revision_sha256": project_export_revision(root).get("sha256"),
        "export_cache_version": PPTX_EXPORT_CACHE_VERSION,
    }
    if advisories:
        manifest["advisories"] = advisories
    if defects:
        manifest["defects"] = sorted(dict.fromkeys(defects))
    if compile_meta:
        manifest["compile"] = compile_meta
    # Identity fields required for pdf_strict download checks.
    for key in (
        "source_pdf_sha256",
        "evidence_manifest_sha256",
        "grounded_plan_sha256",
        "grounding_qa_sha256",
        "coverage_compressed",
    ):
        if key in run_manifest:
            manifest[key] = run_manifest[key]
    # Hash grounding_qa when missing from run manifest.
    if grounding_mode == "pdf_strict" and not manifest.get("grounding_qa_sha256"):
        if gqa_path.is_file():
            manifest["grounding_qa_sha256"] = _sha256_file(gqa_path)
    for plan_name, field in (
        ("grounded_plan.json", "grounded_plan_sha256"),
    ):
        if not manifest.get(field):
            plan_path = validation / plan_name
            if plan_path.is_file():
                manifest[field] = _sha256_file(plan_path)

    out = validation / "release_manifest.json"
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, out)

    # Keep run_manifest in sync for UI/history.
    if run_path.is_file():
        try:
            run_manifest["status"] = release_status
            run_manifest["pptx_path"] = manifest["pptx_path"]
            run_manifest["pptx_sha256"] = pptx_sha
            run_path.write_text(
                json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    return manifest


def resolve_released_pptx(proj_dir: str | Path) -> tuple[str, str, dict]:
    """Return ``(pptx_path, pptx_sha256, manifest)`` for the active release."""
    root = Path(proj_dir)
    exports_dir = root / "exports"
    manifest_path = root / "validation" / "release_manifest.json"
    if not manifest_path.is_file():
        raise ReleaseExportError("No released PPTX is available")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseExportError("No released PPTX is available") from exc

    pptx_path = Path(os.path.realpath(root / manifest.get("pptx_path", "")))
    exports_root = os.path.realpath(exports_dir) + os.sep
    pptx_sha = manifest.get("pptx_sha256") or ""
    live_sha = _sha256_file(pptx_path) if pptx_path.is_file() else ""
    source_revision_sha = str(manifest.get("source_revision_sha256") or "")
    if source_revision_sha:
        live_source_revision = project_source_revision(root)
        if live_source_revision.get("sha256") != source_revision_sha:
            raise ReleaseExportError("Released PPTX is stale; source slides or speaker notes changed")

    if manifest.get("grounding_mode") == "pdf_strict":
        required = (
            "source_pdf_sha256",
            "evidence_manifest_sha256",
            "grounded_plan_sha256",
            "grounding_qa_sha256",
        )
        if any(not manifest.get(field) for field in required):
            raise ReleaseExportError("strict PDF release is missing grounding identity")
        grounding_qa_path = root / "validation" / "grounding_qa.json"
        try:
            grounding_qa = json.loads(grounding_qa_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            grounding_qa = {}
        if grounding_qa.get("status") != "passed":
            raise ReleaseExportError("strict PDF release has failed grounding QA")

    if (
        not is_published_release(manifest.get("status"))
        or not str(pptx_path).startswith(exports_root)
        or not pptx_path.is_file()
        or not pptx_sha
        or pptx_sha != live_sha
    ):
        raise ReleaseExportError("No released PPTX is available")

    return str(pptx_path), pptx_sha, manifest


def resolve_cached_released_pptx(proj_dir: str | Path) -> tuple[str, str, dict]:
    """Resolve the current release only when every export input still matches."""
    path, sha, manifest = resolve_released_pptx(proj_dir)
    expected = str(manifest.get("export_revision_sha256") or "")
    if not expected or manifest.get("export_cache_version") != PPTX_EXPORT_CACHE_VERSION:
        raise ReleaseExportError("Released PPTX predates the export cache contract")
    live = project_export_revision(proj_dir).get("sha256")
    if live != expected:
        raise ReleaseExportError("Released PPTX is stale; export inputs changed")
    return path, sha, manifest


def resolve_previous_released_pptx(proj_dir: str | Path) -> tuple[str, str, dict]:
    """Return the last immutable release after edits invalidate the active one.

    Unlike the active resolver, this intentionally does not compare the old
    release with the current source revision.  The artifact is labelled as the
    previous release and is still protected by its recorded SHA-256 and the
    exports-directory boundary.
    """
    root = Path(proj_dir)
    manifest_path = root / "validation" / "previous_release_manifest.json"
    if not manifest_path.is_file():
        raise ReleaseExportError("No previous released PPTX is available")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseExportError("No previous released PPTX is available") from exc

    pptx_path = Path(os.path.realpath(root / str(manifest.get("pptx_path") or "")))
    exports_root = os.path.realpath(root / "exports") + os.sep
    expected_sha = str(manifest.get("pptx_sha256") or "")
    live_sha = _sha256_file(pptx_path) if pptx_path.is_file() else ""
    if (
        not is_published_release(manifest.get("status"))
        or not str(pptx_path).startswith(exports_root)
        or not pptx_path.is_file()
        or not expected_sha
        or live_sha != expected_sha
    ):
        raise ReleaseExportError("No previous released PPTX is available")
    return str(pptx_path), expected_sha, manifest


def snapshot_current_release_as_previous(proj_dir: str | Path) -> bool:
    """Atomically preserve the current valid release before a rebuild transaction."""
    root = Path(proj_dir)
    try:
        _path, _sha, manifest = resolve_released_pptx(root)
    except ReleaseExportError:
        return False
    validation = root / "validation"
    destination = validation / "previous_release_manifest.json"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    return True


def ensure_release_notes_pdf(
    pptx_path: str | Path,
    pptx_sha: str,
    *,
    proj_dir: str | Path,
) -> str:
    """Return a source-bound slide-plus-speaker-notes handout PDF."""
    root = Path(proj_dir)
    pptx = Path(pptx_path)
    output = pptx.with_name("presentation-notes.pdf")
    stamp_path = output.with_suffix(".pdf.source_sha256")
    source_sha = project_source_revision(root).get("sha256") or ""
    stamp = f"notes-handout-v1:{pptx_sha}:{source_sha}"
    cached = False
    try:
        if output.is_file() and stamp_path.read_text(encoding="utf-8").strip() == stamp:
            cached = True
    except OSError:
        pass
    if not cached:
        from tasks.notes_pdf import create_notes_handout_pdf

        create_notes_handout_pdf(root, output)
        stamp_path.write_text(stamp + "\n", encoding="utf-8")

    active_manifest: dict = {}
    try:
        active_manifest = json.loads(
            (root / "validation" / "release_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        pass
    notes_manifest = {
        "schema_version": "sunairum.notes-pdf-manifest/v1",
        "release_id": active_manifest.get("release_id"),
        "pptx_sha256": pptx_sha,
        "source_revision_sha256": source_sha,
        "notes_pdf_path": str(output.relative_to(root)).replace("\\", "/"),
        "notes_pdf_sha256": _sha256_file(output),
    }
    manifest_path = root / "validation" / "notes_pdf_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(notes_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)
    return str(output)


def _soffice_bin() -> str | None:
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _cache_stamp(pptx_sha256: str, *, source: str = "pptx") -> str:
    return "\n".join([PDF_CACHE_VERSION, source, pptx_sha256])


def _read_stamp(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _assets_font_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _write_fontconfig(conf_path: Path, *font_dirs: Path) -> None:
    """Point LibreOffice at shipped faces and alias Office names onto them.

    ``FONTCONFIG_FILE`` replaces the system config entirely. Do not add the
    template pack dir (Montserrat etc.): generics would resolve there and PDF
    would embed a different face than the remapped/embedded PPTX fonts.
    Staged ``ppt/fonts`` + ``assets/fonts`` cover Source* and any intentional
    embeds; ``/usr/share/fonts`` covers CJK/system fallbacks.
    """
    dirs_xml = "\n".join(
        f"  <dir>{path.resolve()}</dir>"
        for path in font_dirs
        if path.is_dir()
    )
    aliases = (
        ("Georgia", "Source Serif 4"),
        ("Cambria", "Source Serif 4"),
        ("Times New Roman", "Source Serif 4"),
        ("Times", "Source Serif 4"),
        ("Arial", "Source Sans 3"),
        ("Helvetica", "Source Sans 3"),
        ("Helvetica Neue", "Source Sans 3"),
        ("Calibri", "Source Sans 3"),
        ("Segoe UI", "Source Sans 3"),
        ("Verdana", "Source Sans 3"),
        ("Liberation Sans", "Source Sans 3"),
        ("Liberation Serif", "Source Serif 4"),
    )
    alias_xml = "\n".join(
        (
            "  <match target=\"pattern\">\n"
            f"    <test name=\"family\"><string>{src}</string></test>\n"
            "    <edit name=\"family\" mode=\"assign\" binding=\"strong\">"
            f"<string>{dst}</string></edit>\n"
            "  </match>"
        )
        for src, dst in aliases
    )
    prefer_xml = (
        "  <alias>\n"
        "    <family>sans-serif</family>\n"
        "    <prefer><family>Source Sans 3</family></prefer>\n"
        "  </alias>\n"
        "  <alias>\n"
        "    <family>serif</family>\n"
        "    <prefer><family>Source Serif 4</family></prefer>\n"
        "  </alias>\n"
        "  <alias>\n"
        "    <family>monospace</family>\n"
        "    <prefer><family>Source Sans 3</family></prefer>\n"
        "  </alias>"
    )
    conf_path.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        f"{dirs_xml}\n"
        "  <dir>/usr/share/fonts</dir>\n"
        f"{prefer_xml}\n"
        f"{alias_xml}\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )


def _stage_pptx_embedded_fonts(pptx: Path, dest_dir: Path) -> None:
    """Extract ``ppt/fonts/*.fntdata`` as ``.ttf`` so fontconfig can load them."""
    import zipfile

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(pptx) as archive:
            for name in archive.namelist():
                if not name.startswith("ppt/fonts/") or not name.endswith(".fntdata"):
                    continue
                raw = archive.read(name)
                if not raw:
                    continue
                (dest_dir / f"{Path(name).stem}.ttf").write_bytes(raw)
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"[pdf] could not stage pptx fonts: {exc}")


def _run_soffice(
    args: list[str],
    timeout: int = 300,
    *,
    pptx_for_fonts: Path | None = None,
) -> None:
    soffice = _soffice_bin()
    if not soffice:
        raise RuntimeError("LibreOffice (soffice) is not installed; cannot export PDF")
    with tempfile.TemporaryDirectory(prefix="sunairum-lo-profile-") as profile:
        profile_path = Path(profile)
        font_stage = profile_path / "fonts"
        if pptx_for_fonts is not None:
            _stage_pptx_embedded_fonts(pptx_for_fonts, font_stage)
        conf = profile_path / "fonts.conf"
        _write_fontconfig(conf, _assets_font_dir(), font_stage)
        env = os.environ.copy()
        env["FONTCONFIG_FILE"] = str(conf)
        # Fresh cache so the staged/alias config is picked up for this run.
        env["XDG_CACHE_HOME"] = str(profile_path / "cache")
        cmd = [
            soffice,
            "--headless",
            f"-env:UserInstallation=file://{profile_path}",
            *args,
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=timeout, env=env)


def _impress_pdf_filter() -> str:
    """High-fidelity Impress PDF export — preserve images and embed fonts."""
    options = (
        '{"Quality":{"type":"long","value":"100"},'
        '"ReduceImageResolution":{"type":"boolean","value":"false"},'
        '"MaxImageResolution":{"type":"long","value":"600"},'
        '"UseLosslessCompression":{"type":"boolean","value":"true"},'
        '"ExportNotesPages":{"type":"boolean","value":"false"},'
        '"IsExportHiddenSlides":{"type":"boolean","value":"false"},'
        '"IsAddStream":{"type":"boolean","value":"false"},'
        '"ExportFormFields":{"type":"boolean","value":"false"},'
        '"FormsType":{"type":"long","value":"0"},'
        '"EmbedStandardFonts":{"type":"boolean","value":"true"},'
        '"SelectPdfVersion":{"type":"long","value":"0"}}'
    )
    return f"pdf:impress_pdf_Export:{options}"


def _pdf_from_pptx(pptx: Path, pdf_path: Path) -> None:
    """Impress export of the released PPTX (visual parity with download)."""
    with tempfile.TemporaryDirectory(prefix="sunairum-lo-out-") as tmp:
        outdir = Path(tmp)
        _run_soffice(
            ["--convert-to", _impress_pdf_filter(), "--outdir", str(outdir), str(pptx)],
            timeout=300,
            pptx_for_fonts=pptx,
        )
        produced = outdir / f"{pptx.stem}.pdf"
        if not produced.is_file():
            candidates = list(outdir.glob("*.pdf"))
            if not candidates:
                raise RuntimeError("PDF export did not produce an output file")
            produced = candidates[0]
        shutil.copy2(produced, pdf_path)


def _pdf_engine() -> str:
    return (os.environ.get("PDF_ENGINE") or "html_hidpi").strip().casefold()


def _stamp_file(digest, path: Path) -> None:
    digest.update(path.name.encode("utf-8"))
    digest.update(b"\0")
    try:
        digest.update(str(path.stat().st_mtime_ns).encode("ascii"))
        digest.update(str(path.stat().st_size).encode("ascii"))
    except OSError:
        digest.update(b"missing")
    digest.update(b"\0")


def _html_dir_stamp(html_dir: Path, preview_dir: Path | None = None) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(html_dir.glob("slide_*.html")):
        _stamp_file(digest, path)
        if preview_dir is not None:
            _stamp_file(digest, preview_dir / f"{path.stem}.png")
    return digest.hexdigest()


def _prefer_preview_pngs(engine: str) -> bool:
    return engine not in {"html_screenshot", "html_hidpi_force"}


def ensure_release_pdf(
    pptx_path: str | Path,
    pptx_sha256: str,
    proj_dir: str | Path | None = None,
) -> str:
    """Build a downloadable PDF (editor preview PNGs preferred; Impress fallback)."""
    pptx = Path(pptx_path)
    pdf_path = pptx.with_suffix(".pdf")
    stamp_path = Path(str(pdf_path) + ".source_sha256")
    root = Path(proj_dir) if proj_dir else pptx.parent.parent
    html_dir = root / "html_output"
    preview_dir = root / "preview"
    engine = _pdf_engine()
    prefer_preview = _prefer_preview_pngs(engine)

    with tempfile.NamedTemporaryFile(
        prefix=f".{pdf_path.stem}.",
        suffix=".pdf",
        dir=str(pdf_path.parent),
        delete=False,
    ) as handle:
        temp_pdf = Path(handle.name)

    try:
        if engine != "impress" and html_dir.is_dir() and any(html_dir.glob("slide_*.html")):
            html_sha = _html_dir_stamp(html_dir, preview_dir if prefer_preview else None)
            source = "html_preview" if prefer_preview else "html_screenshot"
            expected_stamp = _cache_stamp(html_sha, source=source)
            if pdf_path.is_file() and _read_stamp(stamp_path) == expected_stamp:
                return str(pdf_path)
            try:
                from tasks.html_pdf import (
                    _list_html_slides,
                    _preview_png_usable,
                    pdf_from_html_dir,
                )

                pdf_from_html_dir(
                    html_dir,
                    temp_pdf,
                    preview_dir=preview_dir,
                    prefer_preview=prefer_preview,
                )
                print("[pdf] exported from html_output / preview PNGs")
                if not temp_pdf.is_file() or temp_pdf.stat().st_size == 0:
                    raise RuntimeError("PDF export did not produce an output file")
                os.replace(temp_pdf, pdf_path)
                stamp_path.write_text(expected_stamp + "\n", encoding="utf-8")
                return str(pdf_path)
            except Exception as exc:  # noqa: BLE001
                from tasks.html_pdf import _list_html_slides, _preview_png_usable

                slides = _list_html_slides(html_dir)
                complete = bool(slides) and all(
                    _preview_png_usable(preview_dir / f"{p.stem}.png") for p in slides
                )
                if complete and prefer_preview:
                    raise
                print(f"[pdf] html_preview failed ({exc}); falling back to Impress")

        expected_stamp = _cache_stamp(pptx_sha256, source="pptx")
        if pdf_path.is_file() and _read_stamp(stamp_path) == expected_stamp:
            return str(pdf_path)
        _pdf_from_pptx(pptx, temp_pdf)
        print("[pdf] exported from released PPTX via Impress")
        if not temp_pdf.is_file() or temp_pdf.stat().st_size == 0:
            raise RuntimeError("PDF export did not produce an output file")
        os.replace(temp_pdf, pdf_path)
        stamp_path.write_text(expected_stamp + "\n", encoding="utf-8")
    except Exception:
        try:
            temp_pdf.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return str(pdf_path)
