"""Typed repair scope for browser-layout and native-PPTX fidelity findings.

Validation reports remain evidence.  This module adds the decision layer that
the old boolean gate lacked: what failed, who owns it, and the smallest safe
scope at which the pipeline may repair or fall back.
"""

from __future__ import annotations

import re
from typing import Any


_ELEMENT_RE = re.compile(r":\s*([^:]+?)(?:\s+(?:scrolls|crosses|paints|lays|overlaps)|$)")


def classify_runtime_finding(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    code = text.split(":", 1)[0].strip() or "runtime_unknown"
    element_match = _ELEMENT_RE.search(text)
    owner = element_match.group(1).strip() if element_match else ""
    severity = "repairable"
    scope = "object"
    if code in {"runtime_layout_unavailable", "scene_manifest_missing_or_invalid"}:
        severity, scope = "slide_blocking", "slide"
    elif code in {"runtime_canvas_overflow", "runtime_ancestor_clip"}:
        severity, scope = "region_blocking", "region"
    elif code in {"runtime_sibling_collision", "runtime_decoration_collision"}:
        # Ownership metadata may subsequently downgrade this to intentional.
        severity, scope = "repairable", "object_pair"
    elif code.startswith("scene_contract"):
        severity, scope = "region_blocking", "region"
    return {
        "code": code,
        "severity": severity,
        "repair_scope": scope,
        "owner": owner or None,
        "raw": text,
    }


def classify_runtime_findings(items: list[Any] | tuple[Any, ...]) -> list[dict[str, Any]]:
    return [classify_runtime_finding(str(item)) for item in items]


def _native_item(
    stem: str,
    category: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    code = str(item.get("type") or category or "native_fidelity_unknown")
    semantic_component_codes = {
        "table_cell_content_drift",
        "table_row_height_drift",
        "table_column_width_drift",
        "semantic_owner_conflict",
        "duplicate_semantic_owner",
    }
    region_codes = {
        "missing_scene_drawable",
        "scene_manifest_missing_or_invalid",
    }
    if code in semantic_component_codes:
        scope, severity = "component", "region_blocking"
    elif code in region_codes:
        scope, severity = "region", "region_blocking"
    else:
        # Geometry, line-count, font-scale, identity and clipping failures all
        # name an exported drawable and are repaired at that object first.
        scope, severity = "object", "repairable"
    return {
        "stem": stem,
        "code": code,
        "category": category,
        "severity": severity,
        "repair_scope": scope,
        "element_id": item.get("elementId"),
        "detail": item,
    }


def native_fidelity_remediation_plan(report: dict[str, Any]) -> dict[str, Any]:
    """Translate a verifier report into a stable object-first repair backlog."""
    findings: list[dict[str, Any]] = []
    for failure in report.get("failures") or []:
        if not isinstance(failure, dict):
            continue
        stem = str(failure.get("stem") or "")
        semantic = failure.get("semantic") if isinstance(failure.get("semantic"), dict) else {}
        for category in ("geometry_failures", "typography_failures", "ownership_failures"):
            for item in semantic.get(category) or []:
                if isinstance(item, dict):
                    findings.append(_native_item(stem, category, item))
        for missing in semantic.get("missing_element_ids") or []:
            findings.append(
                {
                    "stem": stem,
                    "code": "missing_scene_drawable",
                    "category": "missing_element_ids",
                    "severity": "region_blocking",
                    "repair_scope": "region",
                    "element_id": str(missing),
                    "detail": {"missing": str(missing)},
                }
            )
        # Raster drift without a semantic attribution is evidence of gross
        # corruption, but it is still sent through regional attribution before
        # any slide-wide fallback is considered.
        if not semantic or semantic.get("ok") is True:
            for region in failure.get("top_regions") or []:
                if not isinstance(region, dict):
                    continue
                findings.append(
                    {
                        "stem": stem,
                        "code": "raster_region_drift",
                        "category": "raster",
                        "severity": "region_blocking",
                        "repair_scope": "region",
                        "element_id": region.get("elementId"),
                        "detail": region,
                    }
                )
    by_slide: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        by_slide.setdefault(str(finding.get("stem") or "unknown"), []).append(finding)
    return {
        "version": "sunairum.native-fidelity-remediation/v1",
        "ok": not findings,
        "whole_slide_fallback_allowed": False,
        "repair_order": ["object", "component", "region", "slide"],
        "findings": findings,
        "slides": [
            {"stem": stem, "findings": entries}
            for stem, entries in sorted(by_slide.items())
        ],
    }
