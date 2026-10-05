"""Build a small, frontend-safe summary of PDF grounding artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _storage_url(path: Path, storage_root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(storage_root.resolve())
    except ValueError:
        return None
    return "/storage/" + relative.as_posix()


def _run_bound(path: Path, run_id: str | None) -> tuple[dict[str, Any], bool]:
    payload = _read_json(path, {})
    if not isinstance(payload, dict):
        return {}, False
    if run_id and payload.get("run_id") != run_id:
        return {}, path.is_file()
    return payload, False


def _page_ranges(pages: list[int]) -> list[dict[str, int]]:
    values = sorted(set(page for page in pages if page > 0))
    ranges: list[dict[str, int]] = []
    for page in values:
        if ranges and page == ranges[-1]["page_end"] + 1:
            ranges[-1]["page_end"] = page
        else:
            ranges.append({"page_start": page, "page_end": page})
    return ranges


def _slide_number(value: Any) -> int | None:
    match = re.search(r"(\d+)$", str(value or ""))
    return int(match.group(1)) if match else None


def _reference_pages(
    grounding: dict[str, Any],
    pages_by_reference: dict[str, list[int]],
) -> tuple[list[str], list[int]]:
    references: set[str] = set()
    for value in grounding.get("evidence_ids", []):
        references.add(str(value))
    for key in ("claims", "metrics", "table_bindings", "figure_bindings", "formula_bindings"):
        for item in grounding.get(key, []):
            if not isinstance(item, dict):
                continue
            for value in item.get("evidence_ids", []):
                references.add(str(value))
            for identifier_key in ("table_id", "asset_id", "formula_id"):
                if item.get(identifier_key):
                    references.add(str(item[identifier_key]))
    pages = sorted({page for reference in references for page in pages_by_reference.get(reference, [])})
    return sorted(references), pages


def _artifact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    return {
        "status": str(payload.get("status") or "not-run"),
        "error_count": int(payload.get("error_count") or sum(
            1 for issue in issues
            if isinstance(issue, dict) and issue.get("severity") == "error"
        )),
        "issues": [issue for issue in issues[:40] if isinstance(issue, dict)],
    }


def build_grounding_status(project_dir: str | Path, storage_root: str | Path) -> dict[str, Any]:
    """Return grounding metadata without exposing source file contents."""
    project = Path(project_dir)
    storage = Path(storage_root)
    validation = project / "validation"
    sources = project / "sources"

    policy = _read_json(validation / "source_policy.json", {})
    run_manifest = _read_json(validation / "run_manifest.json", {})
    release_manifest = _read_json(validation / "release_manifest.json", {})
    parser_manifest = _read_json(sources / "parser_manifest.json", {})
    evidence_manifest = _read_json(sources / "evidence_manifest.json", {})
    structure = _read_json(sources / "source_structure.json", {})
    sections_payload = _read_json(sources / "source_sections.json", {})
    tables_payload = _read_json(sources / "source_tables.json", {})
    formulas_payload = _read_json(sources / "source_formulas.json", {})
    assets_payload = _read_json(sources / "source_assets.json", {})
    from tasks.settings_obedience_artifacts import reconcile_settings_obedience

    # The confirmed language is a Production Setting like any other: check that
    # the delivered slides are in it, because no geometry gate can see a
    # beautifully laid out slide in the wrong language.
    confirmed_language = str(
        _read_json(project / "confirm_ui" / "result.json", {}).get("primary_language")
        or policy.get("primary_language")
        or ""
    )
    settings_obedience = reconcile_settings_obedience(
        _read_json(validation / "settings_obedience.json", {}),
        project,
        primary_language=confirmed_language,
    )

    grounding_mode = (
        policy.get("grounding_mode")
        or release_manifest.get("grounding_mode")
        or run_manifest.get("grounding_mode")
    )
    if grounding_mode not in {"pdf_strict", "source_grounded", "scratch"}:
        grounding_mode = "pdf_strict" if (project / "source.pdf").is_file() and evidence_manifest else "scratch"

    run_id = str(run_manifest.get("run_id") or "") or None
    grounded_plan, plan_stale = _run_bound(validation / "grounded_plan.json", run_id)
    grounding_qa, grounding_qa_stale = _run_bound(validation / "grounding_qa.json", run_id)
    rendered_qa, rendered_qa_stale = _run_bound(validation / "rendered_grounding_qa.json", run_id)
    if release_manifest and run_id and release_manifest.get("run_id") != run_id:
        release_manifest = {}

    sections = [
        section for section in sections_payload.get("sections", [])
        if isinstance(section, dict)
    ]
    section_titles = {
        str(section.get("section_id")): str(section.get("title") or section.get("section_id"))
        for section in sections
    }
    tables = [table for table in tables_payload.get("tables", []) if isinstance(table, dict)]
    formulas = [formula for formula in formulas_payload.get("formulas", []) if isinstance(formula, dict)]
    assets = [asset for asset in assets_payload.get("assets", []) if isinstance(asset, dict)]

    pages_by_reference: dict[str, list[int]] = {}
    for page in structure.get("pages", []) if isinstance(structure, dict) else []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 1)
        for block in page.get("blocks", []) if isinstance(page.get("blocks"), list) else []:
            if isinstance(block, dict) and block.get("evidence_id"):
                pages_by_reference[str(block["evidence_id"])] = [page_number]
    for table in tables:
        page_start = int(table.get("page_start") or table.get("page") or 1)
        page_end = int(table.get("page_end") or page_start)
        pages_by_reference[str(table.get("table_id"))] = list(range(page_start, page_end + 1))
        if table.get("evidence_id"):
            pages_by_reference[str(table["evidence_id"])] = list(range(page_start, page_end + 1))
    for formula in formulas:
        page = int(formula.get("page") or 1)
        pages_by_reference[str(formula.get("formula_id"))] = [page]
        if formula.get("evidence_id"):
            pages_by_reference[str(formula["evidence_id"])] = [page]
    for asset in assets:
        page = int(asset.get("page") or 1)
        pages_by_reference[str(asset.get("asset_id"))] = [page]
        if asset.get("caption_evidence_id"):
            pages_by_reference[str(asset["caption_evidence_id"])] = [page]

    # Section coverage is the one part of this panel that exists before the
    # outline does: the parser produces the sections, and the plan only adds the
    # slide assignments. Collecting the assignments separately lets the UI show
    # the real section list from the moment parsing ends, then fill it in.
    assigned_slides: dict[str, set[int]] = {}
    assigned_modes: dict[str, str] = {}

    plan_payload: dict[str, Any] | None = None
    if grounded_plan:
        coverage = []
        raw_coverage = grounded_plan.get("coverage_plan") or grounded_plan.get("section_coverage") or []
        for item in raw_coverage if isinstance(raw_coverage, list) else []:
            if not isinstance(item, dict):
                continue
            section_ids = [str(value) for value in item.get("section_ids", [])]
            if item.get("section_id") and not section_ids:
                section_ids = [str(item["section_id"])]
            slide_ids = [str(value) for value in item.get("slide_ids", [])]
            if item.get("slide_id") and not slide_ids:
                slide_ids = [str(item["slide_id"])]
            slide_numbers = [number for number in (_slide_number(value) for value in slide_ids) if number]
            coverage_mode = str(item.get("coverage_mode") or "full")
            for section_id in section_ids:
                assigned_slides.setdefault(section_id, set()).update(slide_numbers)
                assigned_modes.setdefault(section_id, coverage_mode)
            coverage.append({
                "slide_ids": slide_ids,
                "slide_numbers": slide_numbers,
                "section_ids": section_ids,
                "section_titles": [section_titles.get(value, value) for value in section_ids],
                "coverage_mode": coverage_mode,
                "required_evidence_count": len(item.get("required_evidence_ids", [])),
            })

        slides = []
        for index, slide in enumerate(grounded_plan.get("slides", []), start=1):
            if not isinstance(slide, dict):
                continue
            grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
            evidence_ids, citation_pages = _reference_pages(grounding, pages_by_reference)
            section_ids = [str(value) for value in grounding.get("section_ids", slide.get("section_ids", []))]
            slide_coverage_mode = str(slide.get("coverage_mode") or "full")
            # A plan may assign sections per slide instead of through a coverage
            # group, so both paths have to feed the section list.
            for section_id in section_ids:
                assigned_slides.setdefault(section_id, set()).add(index)
                assigned_modes.setdefault(section_id, slide_coverage_mode)
            slides.append({
                "slide_number": index,
                "slide_id": str(slide.get("slide_id") or f"slide-{index}"),
                "title": str(slide.get("title") or slide.get("content", {}).get("TITLE") or f"Slide {index}"),
                "section_titles": [section_titles.get(value, value) for value in section_ids],
                "coverage_mode": slide_coverage_mode,
                "citation_pages": citation_pages,
                "citation_ranges": _page_ranges(citation_pages),
                "evidence_count": len(evidence_ids),
                "table_count": len(grounding.get("table_bindings", [])),
                "figure_count": len(grounding.get("figure_bindings", [])),
                "formula_count": len(grounding.get("formula_bindings", [])),
            })
        plan_payload = {
            "requested_slide_count": int(grounded_plan.get("requested_slide_count") or 0),
            "actual_slide_count": int(grounded_plan.get("actual_slide_count") or len(slides)),
            "coverage_compressed": bool(
                grounded_plan.get("coverage_compressed")
                or release_manifest.get("coverage_compressed")
            ),
            "coverage": coverage,
            "slides": slides,
        }

    try:
        from tasks.grounded_planner import content_sections, is_backmatter_section
    except ImportError:  # pragma: no cover
        from grounded_planner import content_sections, is_backmatter_section

    section_payload: list[dict[str, Any]] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        page_start = int(section.get("page_start") or 0)
        level = int(section.get("level") or 1)
        backmatter = is_backmatter_section(section)
        section_payload.append({
            "section_id": section_id,
            "title": str(section.get("title") or section_id),
            "level": level,
            "page_start": page_start,
            "page_end": int(section.get("page_end") or page_start),
            "evidence_count": len(section.get("evidence_ids") or []),
            # Empty until the plan lands, which is what the UI renders as pending.
            "slide_numbers": sorted(assigned_slides.get(section_id, ())),
            "coverage_mode": assigned_modes.get(section_id),
            "is_backmatter": backmatter,
            "counts_toward_coverage": (not backmatter) and level == 1,
        })
    # Coverage fraction follows major L1 content sections (same contract as
    # validate_section_coverage), not every nested/back-matter heading.
    content = content_sections(sections)
    required_sections = [
        item for item in content
        if int(item.get("level") or 1) == 1 and not is_backmatter_section(item)
    ]
    if not required_sections:
        required_sections = [item for item in content if not is_backmatter_section(item)]
    required_ids = {
        str(item.get("section_id") or "")
        for item in required_sections
        if item.get("section_id")
    }
    covered_section_count = sum(
        1
        for entry in section_payload
        if entry["section_id"] in required_ids and entry["slide_numbers"]
    )
    required_section_count = len(required_ids)

    stale_artifacts = [
        name for name, stale in (
            ("grounded_plan.json", plan_stale),
            ("grounding_qa.json", grounding_qa_stale),
            ("rendered_grounding_qa.json", rendered_qa_stale),
        ) if stale
    ]
    return {
        "available": grounding_mode == "pdf_strict" and (
            (project / "source.pdf").is_file() or bool(evidence_manifest)
        ),
        "grounding_mode": grounding_mode,
        "run_id": run_id,
        "source": {
            "parser_requested": parser_manifest.get("parser_requested") or policy.get("parser_requested") or "unknown",
            "parser_selected": parser_manifest.get("parser_selected") or "unknown",
            "parser_version": parser_manifest.get("parser_version") or "unknown",
            "fallback_used": bool(parser_manifest.get("fallback_used")),
            "fallback_reason": parser_manifest.get("fallback_reason"),
            "page_count": int(parser_manifest.get("page_count") or 0),
            "tables_detected": int(parser_manifest.get("tables", {}).get("detected") or len(tables)),
            "structured_tables": int(parser_manifest.get("tables", {}).get("structured") or len(tables)),
            "figures_detected": int(parser_manifest.get("figures", {}).get("detected") or len(assets)),
            "figures_verified": int(parser_manifest.get("figures", {}).get("provenance_verified") or 0),
            "source_pdf_sha256": parser_manifest.get("source_pdf_sha256") or evidence_manifest.get("source_pdf_sha256"),
        },
        "evidence": {
            "manifest_sha256": _sha256(sources / "evidence_manifest.json"),
            "evidence_count": int(evidence_manifest.get("evidence_count") or 0),
            "section_count": len(sections),
            "required_section_count": required_section_count,
            "covered_section_count": covered_section_count,
            "table_count": int(evidence_manifest.get("table_count") or len(tables)),
            "formula_count": int(evidence_manifest.get("formula_count") or len(formulas)),
            "asset_count": int(evidence_manifest.get("asset_count") or len(assets)),
            "manifest_url": _storage_url(sources / "evidence_manifest.json", storage),
        },
        "sections": section_payload,
        "plan": plan_payload,
        "grounding_qa": _artifact_summary(grounding_qa),
        "rendered_grounding_qa": _artifact_summary(rendered_qa),
        "release": {
            "status": release_manifest.get("status") or "not-released",
            "coverage_compressed": bool(release_manifest.get("coverage_compressed")),
        },
        "settings_obedience": settings_obedience,
        "artifacts": {
            "parser_manifest_url": _storage_url(sources / "parser_manifest.json", storage),
            "source_policy_url": _storage_url(validation / "source_policy.json", storage),
            "settings_obedience_url": _storage_url(validation / "settings_obedience.json", storage),
        },
        "stale_artifacts": stale_artifacts,
    }
