"""Asynchronous PDF source parsing and evidence-bundle creation."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from celery import shared_task

try:
    from .evidence_bundle import build_evidence_bundle
    from .pdf_provenance import extract_pdf_figures
    from .source_import import write_source_status
    from .source_parser import parse_project_pdf, update_parser_manifest
except ImportError:  # pragma: no cover - supports direct task imports
    from evidence_bundle import build_evidence_bundle
    from pdf_provenance import extract_pdf_figures
    from source_import import write_source_status
    from source_parser import parse_project_pdf, update_parser_manifest


def _sha256_file(path: Path) -> str | None:
    import hashlib

    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_notes_from_sources(project_dir: Path) -> None:
    """Cache PDF markdown chunks under sources/note_chunks — not notes/.

    Job A owns ``notes/slide_*.md`` (spoken speaker notes). Source dumps here
    are retrieval aids only and must not trigger regenerate-as-notes.
    """
    sources_dir = project_dir / "sources"
    chunks_dir = sources_dir / "note_chunks"
    markdown_files = sorted(
        path for path in sources_dir.glob("*.md") if path.parent == sources_dir
    )
    if not markdown_files:
        return
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    slide_index = 0
    for markdown_path in markdown_files:
        content = markdown_path.read_text(encoding="utf-8")
        chunks: list[list[str]] = []
        current: list[str] = []
        for line in content.splitlines():
            if heading_re.match(line):
                if current:
                    chunks.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            chunks.append(current)
        for chunk in chunks:
            slide_index += 1
            note_path = chunks_dir / f"chunk_{slide_index:02d}.md"
            note_path.write_text("\n".join(chunk).strip() + "\n", encoding="utf-8")


@shared_task(bind=True, name="tasks.source_import_task.parse_uploaded_source")
def parse_uploaded_source(self, project_id: str, topic: str, user_id: str = ""):
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context

    storage_root = Path(os.environ.get("STORAGE_ROOT", "/app/storage"))
    project = storage_root / user_id / project_id
    with llm_user_context(user_id):
        return _parse_uploaded_source_body(self, project_id, topic, user_id, storage_root, project)


def _parse_uploaded_source_body(self, project_id, topic, user_id, storage_root, project):
    source_pdf = project / "source.pdf"
    task_id = getattr(self.request, "id", None)
    try:
        # Stale redelivery after delete/restart: PDF gone → terminal status, ack
        # (do not raise — raises leave noisy "unexpected" failures and can recreate
        # empty project dirs via the failure signal).
        if not source_pdf.is_file() or source_pdf.stat().st_size <= 0:
            detail = (
                "uploaded source.pdf is missing"
                if not source_pdf.is_file()
                else "uploaded source.pdf is empty"
            )
            print(
                f"[source_import] {detail} for {user_id}/{project_id} "
                f"(task={task_id}); treating as terminal orphan"
            )
            # Only persist status when the project tree still exists — avoid
            # recreating deleted project dirs from stale Celery redeliveries.
            if project.is_dir():
                write_source_status(
                    project,
                    "source_error",
                    0,
                    "PDF source parsing failed",
                    message_key="source_status_error",
                    task_id=task_id,
                    error=detail,
                )
            return {
                "status": "source_error",
                "project_id": project_id,
                "error": detail,
                "orphan": True,
            }
        write_source_status(project, "source_parsing", 10, "Parsing the uploaded PDF",
                            message_key="source_status_parsing", task_id=task_id)
        import_summary = parse_project_pdf(project, source_pdf)
        _build_notes_from_sources(project)
        write_source_status(project, "source_parsing", 55, "Extracting figures and tables",
                            message_key="source_status_extracting", task_id=task_id)
        figures = extract_pdf_figures(project)
        update_parser_manifest(project, figures=figures)
        write_source_status(project, "source_grounding", 75, "Building the grounded evidence bundle",
                            message_key="source_status_grounding", task_id=task_id)
        evidence_bundle = build_evidence_bundle(project)
        policy_dir = project / "validation"
        policy_dir.mkdir(parents=True, exist_ok=True)
        (policy_dir / "source_policy.json").write_text(
            json.dumps({
                "schema_version": "sunairum.source-policy/v1",
                "grounding_mode": "pdf_strict",
                "source_pdf_sha256": _sha256_file(source_pdf),
                "parser_manifest": str(project / "sources" / "parser_manifest.json"),
                "evidence_manifest": str(project / "sources" / "evidence_manifest.json"),
                "evidence_bundle_sha256": evidence_bundle["manifest"].get("bundle_sha256"),
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        chunks_dir = project / "sources" / "note_chunks"
        has_source_text = chunks_dir.is_dir() and any(
            path.suffix == ".md" for path in chunks_dir.iterdir()
        )
        sources_md = any((project / "sources").glob("*.md")) if (project / "sources").is_dir() else False
        if not has_source_text and not sources_md and not figures:
            raise ValueError("No usable source text or figures were extracted from the upload")
        ready = write_source_status(project, "source_ready", 100, "PDF source is ready for the Communication Contract",
                                  message_key="source_status_ready", task_id=task_id)
        return {
            "status": "source_ready",
            "project_id": project_id,
            "parser_selected": import_summary["parser_selected"],
            "fallback_used": import_summary["fallback_used"],
            "pages": import_summary["pages"],
            "tables": evidence_bundle["manifest"].get("table_count", 0),
            "figures": len(figures),
            "status_payload": ready,
        }
    except Exception as exc:
        write_source_status(project, "source_error", 0, "PDF source parsing failed",
                            message_key="source_status_error", task_id=task_id, error=str(exc))
        raise
