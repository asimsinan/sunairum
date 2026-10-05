"""Blocking validation for PDF-grounded slide plans."""

from __future__ import annotations

import os
import re
from typing import Any


def _slide_markup_blob(storage_dir: str, index: int) -> str | None:
    """Read HTML (preferred) or legacy SVG markup for grounding presence checks."""
    html_path = os.path.join(storage_dir, "html_output", f"slide_{index:02d}.html")
    try:
        with open(html_path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        pass
    svg_path = os.path.join(storage_dir, "svg_output", f"slide_{index:02d}.svg")
    try:
        with open(svg_path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return None


def prune_unplaced_figure_bindings(
    storage_dir: str,
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop figure_bindings whose asset_id is absent from HTML/IR markup.

    Plan–render invariant: Bound ⇒ placed and tagged, or the binding is removed
    from the live plan before ``validate_rendered_grounding``. Returns a list of
    prune records for the run manifest / QA trail.
    """
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    if html_sot_enabled(storage_dir):
        # Prefer html_output; skip prune when no markup yet (resume mid-run).
        pass
    dropped: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else None
        if not grounding:
            continue
        bindings = grounding.get("figure_bindings")
        if not isinstance(bindings, list) or not bindings:
            continue
        markup = _slide_markup_blob(storage_dir, index)
        if markup is None:
            continue
        kept: list[Any] = []
        for binding in bindings:
            asset_id = ""
            if isinstance(binding, dict):
                asset_id = str(binding.get("asset_id") or "")
            else:
                asset_id = str(getattr(binding, "asset_id", "") or "")
            if asset_id and asset_id not in markup:
                dropped.append({
                    "slide": index,
                    "asset_id": asset_id,
                    "reason": "absent-from-markup",
                })
                continue
            kept.append(binding)
        if len(kept) != len(bindings):
            grounding["figure_bindings"] = kept
            if not kept:
                visual = slide.get("visual_plan")
                if isinstance(visual, dict) and visual.get("primary") == "figure":
                    visual["primary"] = "none"
    return dropped


def run_grounding_qa(
    slides: list[dict[str, Any]],
    slide_plans: list[dict[str, Any]],
    evidence_bundle: dict[str, Any],
    grounding_mode: str,
) -> dict[str, Any]:
    """Check source bindings before any SVG is authored."""
    if grounding_mode != "pdf_strict":
        return {"schema_version": "sunairum.grounding-qa/v1", "status": "skipped", "issues": []}
    evidence_ids = {
        str(item.get("evidence_id"))
        for item in evidence_bundle.get("evidence", [])
        if isinstance(item, dict)
    }
    for page in evidence_bundle.get("structure", {}).get("pages", []):
        for block in page.get("blocks", []) if isinstance(page, dict) else []:
            if isinstance(block, dict) and block.get("evidence_id"):
                evidence_ids.add(str(block["evidence_id"]))
    for table in evidence_bundle.get("tables", {}).get("tables", []):
        if isinstance(table, dict) and table.get("evidence_id"):
            evidence_ids.add(str(table["evidence_id"]))
    for formula in evidence_bundle.get("formulas", {}).get("formulas", []):
        if isinstance(formula, dict) and formula.get("evidence_id"):
            evidence_ids.add(str(formula["evidence_id"]))
    for asset in evidence_bundle.get("assets", {}).get("assets", []):
        if isinstance(asset, dict) and asset.get("caption_evidence_id"):
            evidence_ids.add(str(asset["caption_evidence_id"]))
    table_ids = {
        str(item.get("table_id"))
        for item in evidence_bundle.get("tables", {}).get("tables", [])
        if isinstance(item, dict)
    }
    asset_ids = {
        str(item.get("asset_id"))
        for item in evidence_bundle.get("assets", {}).get("assets", [])
        if isinstance(item, dict)
    }
    formula_ids = {
        str(item.get("formula_id"))
        for item in evidence_bundle.get("formulas", {}).get("formulas", [])
        if isinstance(item, dict)
    }
    assets_by_id = {
        str(item.get("asset_id")): item
        for item in evidence_bundle.get("assets", {}).get("assets", [])
        if isinstance(item, dict)
    }
    formulas_by_id = {
        str(item.get("formula_id")): item
        for item in evidence_bundle.get("formulas", {}).get("formulas", [])
        if isinstance(item, dict)
    }
    issues: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        refs = set(str(value) for value in grounding.get("evidence_ids", []))
        for claim in grounding.get("claims", []):
            refs.update(str(value) for value in claim.get("evidence_ids", []))
        for metric in grounding.get("metrics", []):
            refs.update(str(value) for value in metric.get("evidence_ids", []))
        for binding in grounding.get("table_bindings", []) + grounding.get("figure_bindings", []) + grounding.get("formula_bindings", []):
            refs.update(str(value) for value in binding.get("evidence_ids", []))
        if not refs:
            issues.append({"slide": index, "category": "claim-evidence-missing", "severity": "error", "detail": "slide has no evidence references"})
        unknown_refs = sorted(ref for ref in refs if ref not in evidence_ids and ref not in table_ids and ref not in asset_ids and ref not in formula_ids)
        if unknown_refs:
            issues.append({"slide": index, "category": "claim-evidence-not-found", "severity": "error", "detail": ", ".join(unknown_refs)})
        table_bindings = grounding.get("table_bindings", [])
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        if "table" in content and not table_bindings:
            issues.append({"slide": index, "category": "table-source-binding-missing", "severity": "error", "detail": "table content has no source binding"})
        for binding in table_bindings:
            table_id = str(binding.get("table_id"))
            if table_id not in table_ids:
                issues.append({"slide": index, "category": "table-source-binding-missing", "severity": "error", "detail": table_id})
            if content.get("table", {}).get("source_table_id") not in {None, table_id}:
                issues.append({"slide": index, "category": "table-cell-mismatch", "severity": "error", "detail": f"content table is not bound to {table_id}"})
        for binding in grounding.get("figure_bindings", []):
            asset_id = str(binding.get("asset_id"))
            if asset_id not in asset_ids:
                issues.append({"slide": index, "category": "figure-source-binding-missing", "severity": "error", "detail": str(binding.get("asset_id"))})
            asset = assets_by_id.get(asset_id)
            if asset and binding.get("citation_pages") and int(asset.get("page") or 1) not in binding.get("citation_pages", []):
                issues.append({"slide": index, "category": "figure-page-mismatch", "severity": "error", "detail": asset_id})
        for binding in grounding.get("formula_bindings", []):
            formula_id = str(binding.get("formula_id"))
            if formula_id not in formula_ids:
                issues.append({"slide": index, "category": "formula-source-binding-missing", "severity": "error", "detail": str(binding.get("formula_id"))})
            formula = formulas_by_id.get(formula_id)
            if formula and binding.get("render_policy") == "source_latex" and formula.get("rendering_status") == "needs_review":
                issues.append({"slide": index, "category": "formula-source-binding-missing", "severity": "error", "detail": f"{formula_id}: rendering unavailable"})
        plan = slide_plans[index - 1] if index - 1 < len(slide_plans) else {}
        # AI / stock illustrations are allowed under pdf_strict (claim SoT ≠ visual ban).
        if plan.get("primary_visual_source") == "chart" and not grounding.get("metrics"):
            issues.append({"slide": index, "category": "metric-evidence-missing", "severity": "error", "detail": "chart has no grounded metrics"})
    return {
        "schema_version": "sunairum.grounding-qa/v1",
        "status": "failed" if issues else "passed",
        "error_count": len(issues),
        "issues": issues,
    }


def validate_rendered_grounding(
    storage_dir: str,
    slides: list[dict[str, Any]],
    grounding_mode: str,
) -> dict[str, Any]:
    """Verify source bindings survive HTML/IR materialization (legacy: SVG)."""
    if grounding_mode != "pdf_strict":
        return {"schema_version": "sunairum.rendered-grounding-qa/v1", "status": "skipped", "issues": []}
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    issues: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        markup = _slide_markup_blob(storage_dir, index)
        if markup is None:
            # Zero-SVG decks without html yet: skip rather than invent svg_output misses.
            if html_sot_enabled(storage_dir):
                continue
            path = os.path.join(storage_dir, "svg_output", f"slide_{index:02d}.svg")
            issues.append({
                "slide": index,
                "category": "grounding-svg-missing",
                "severity": "error",
                "detail": path,
            })
            continue
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        for binding in grounding.get("figure_bindings", []):
            asset_id = str(binding.get("asset_id", ""))
            if asset_id and asset_id not in markup:
                issues.append({
                    "slide": index,
                    "category": "figure-source-binding-missing",
                    "severity": "error",
                    "detail": asset_id,
                })
        for binding in grounding.get("table_bindings", []):
            table_id = str(binding.get("table_id", ""))
            if not table_id:
                continue
            has_table_carrier = (
                'data-pptx-replace-with="table"' in markup
                or 'data-sunairum-source-type="table"' in markup
                or 'data-pptx="table"' in markup
            )
            if has_table_carrier and table_id not in markup:
                issues.append({
                    "slide": index,
                    "category": "table-source-binding-missing",
                    "severity": "error",
                    "detail": table_id,
                })
    return {
        "schema_version": "sunairum.rendered-grounding-qa/v1",
        "status": "failed" if issues else "passed",
        "error_count": len(issues),
        "issues": issues,
    }
