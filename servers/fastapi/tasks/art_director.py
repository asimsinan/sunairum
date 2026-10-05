"""Text-only Art Director: structured brief for Executor (no SVG, no vision)."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

ART_DIRECTOR_SYSTEM = """You are Sunairum's Art Director (text only).
Emit ONE JSON object for this page. No markdown fences.
Keys:
- job: short string (one visual job)
- energy: vivid|balanced|sparse
- hierarchy: array of 2–4 roles in paint order (e.g. title, table, callout)
- host: {kind: none|table|figure|formula, placement: short, band: optional hint}
- copy_zones: {lede?, aside?, callout?} short rules
- type: {title, body, caption} integer px when known
- craft: array of 3–6 concrete rules (margins, gaps, motif avoid)
- forbid: array of things not to paint
Keep it short. Obey Design SoT density/type. Never invent table cell or equation text.
Never emit energy=sparse for content pages. Content pages default to energy=vivid
(Fill Contract). Title/hero/closing stay sparse.
"""


def _fallback_brief(slide: dict[str, Any], craft_lines: list[str]) -> dict[str, Any]:
    tid = str(slide.get("table_id") or "").strip()
    fid = str(slide.get("figure_id") or "").strip()
    formula = str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    kind = "none"
    placement = "content free"
    band = ""
    if tid and tid.casefold() not in {"none", "null", "n/a", "-"}:
        kind = "table"
        band_d = slide.get("_table_band") if isinstance(slide.get("_table_band"), dict) else {}
        if band_d:
            placement = "reserved table band"
            band = (
                f"x≈{band_d.get('x')}, y≈{band_d.get('y')}, "
                f"w≈{band_d.get('w')}, h≈{band_d.get('h')}"
            )
        else:
            placement = "center-right table"
    elif formula:
        kind = "formula"
        placement = "formula-band mid page"
        band = "x≈60, y≈160, w≈1160, h≈160"
    elif fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        kind = "figure"
        placement = "right figure slot"
    role = str(slide.get("role") or "content").casefold()
    hierarchy = ["title"]
    if kind != "none":
        hierarchy.append(kind)
    hierarchy.append("callout" if role == "content" else "chrome")
    energy = "sparse" if role in {"title", "hero", "closing"} else "vivid"
    if kind != "none" and role == "content":
        energy = "vivid"
    aside = "outside host AABB only"
    if kind in {"table", "figure"}:
        aside = "2–4 IR insights/claims in complementary column (required)"
    craft = list(craft_lines[:6] or ["≥24px gaps", "narrative outside hosts"])
    if role == "content":
        craft = craft + [
            "solid primary/accent mass + accent_tint panel",
            "callout outside host",
        ]
    return {
        "job": "one visual job" if role == "content" else f"{role} plate",
        "energy": energy,
        "hierarchy": hierarchy,
        "host": {"kind": kind, "placement": placement, "band": band},
        "copy_zones": {
            "lede": "one line under title when needed",
            "aside": aside,
            "callout": "one fact max",
        },
        "type": {},
        "craft": craft[:8],
        "forbid": [
            "fake table chrome",
            "raw TeX",
            "eyebrow codes",
            "KPI strip on title",
            "title+footer-only content page",
        ],
    }


def format_art_direction_block(brief: dict[str, Any] | None) -> str:
    if not isinstance(brief, dict) or not brief:
        return ""
    lines = ["## Art direction (this page — follow)"]
    if brief.get("job"):
        lines.append(f"- Job: {brief['job']}")
    if brief.get("energy"):
        lines.append(f"- Energy: {brief['energy']}")
    hier = brief.get("hierarchy")
    if isinstance(hier, list) and hier:
        lines.append(f"- Hierarchy: {' → '.join(str(x) for x in hier)}")
    host = brief.get("host") if isinstance(brief.get("host"), dict) else {}
    if host.get("kind") and str(host.get("kind")) != "none":
        lines.append(
            f"- Host: {host.get('kind')} — {host.get('placement') or ''}"
            + (f" ({host.get('band')})" if host.get("band") else "")
        )
    zones = brief.get("copy_zones") if isinstance(brief.get("copy_zones"), dict) else {}
    for key in ("lede", "aside", "callout"):
        if zones.get(key):
            lines.append(f"- Copy/{key}: {zones[key]}")
    typ = brief.get("type") if isinstance(brief.get("type"), dict) else {}
    if typ:
        bits = [f"{k}={v}" for k, v in typ.items() if v]
        if bits:
            lines.append(f"- Type: {', '.join(bits)}")
    for rule in brief.get("craft") or []:
        lines.append(f"- Craft: {rule}")
    forbid = brief.get("forbid") or []
    if forbid:
        lines.append(f"- Forbid: {', '.join(str(x) for x in forbid)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def author_art_direction(
    slide: dict[str, Any],
    *,
    design_sot_brief: str = "",
    craft_lines: list[str] | None = None,
    prior_diary: str = "",
    call_text: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    craft = list(craft_lines or [])
    role = str(slide.get("role") or "content").casefold()
    if role in {"title", "hero", "closing"}:
        brief = _fallback_brief(slide, craft)
        brief["job"] = f"sparse {role} plate"
        brief["energy"] = "sparse"
        brief["craft"] = (craft[:4] or []) + ["one job + generous air"]
        return brief
    fallback = _fallback_brief(slide, craft)
    if call_text is None:
        return fallback
    payload = {
        "design_sot": (design_sot_brief or "")[:2500],
        "craft_defaults": craft[:12],
        "prior_diary": (prior_diary or "")[:800],
        "slide": {
            "slide": slide.get("slide"),
            "role": slide.get("role"),
            "title": slide.get("title"),
            "core_message": slide.get("core_message"),
            "table_id": slide.get("table_id"),
            "figure_id": slide.get("figure_id"),
            "formula": bool(slide.get("formula") or slide.get("formula_tex")),
            "visualization": slide.get("visualization"),
            "page_rhythm": slide.get("page_rhythm"),
            "_table_band": slide.get("_table_band"),
            "_formula_band": slide.get("_formula_band"),
        },
    }
    try:
        raw = str(
            call_text(ART_DIRECTOR_SYSTEM, json.dumps(payload, ensure_ascii=False)[:6000])
            or ""
        ).strip()
    except Exception:
        return fallback
    if not raw:
        return fallback
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return fallback
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return fallback
    if not isinstance(parsed, dict):
        return fallback
    out = dict(fallback)
    for key in ("job", "energy", "hierarchy", "host", "copy_zones", "type", "craft", "forbid"):
        if key in parsed and parsed[key]:
            out[key] = parsed[key]
    host = out.get("host") if isinstance(out.get("host"), dict) else {}
    host_kind = str(host.get("kind") or "").casefold()
    energy = str(out.get("energy") or "").casefold()
    if role == "content":
        if energy in {"sparse", "balanced", ""}:
            out["energy"] = "vivid"
    if host_kind in {"table", "figure", "formula"} and energy == "sparse":
        out["energy"] = "vivid"
    return out
