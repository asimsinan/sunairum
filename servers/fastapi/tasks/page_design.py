"""Merged Art + Layout Plan authoring (single LLM call, single-thread)."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable


PAGE_DESIGN_SYSTEM = """You are Sunairum's Page Designer (text only).
Emit ONE JSON object with keys "art" and "plan". No SVG. No markdown fences.

art keys (Art Director brief):
- job, energy (vivid|balanced|sparse), hierarchy, host, copy_zones, type, craft, forbid
Content pages: energy=vivid (never sparse). Title/hero/closing: sparse.

plan keys (SlideLayoutPlan):
- job, composition, regions[{id,role,x,y,w,h,title_y?,pair_id?,metaphor?,claim?}], rules
Canvas 1280×720. Copy locked host_void regions unchanged into plan.regions.
Never invent table cell or equation text.
"""


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw or "").strip(), flags=re.I).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _overwrite_art_title(art: dict[str, Any], slide: dict[str, Any]) -> dict[str, Any]:
    """Keep art brief aligned with IR title (never invent a competing headline)."""
    out = dict(art or {})
    title = str(slide.get("title") or "").strip()
    if not title:
        return out
    job = str(out.get("job") or "").strip()
    if not job or job in {"one visual job", "sparse title plate", "sparse cover plate"}:
        role = str(slide.get("role") or "content").casefold()
        out["job"] = f"{role} — {title[:80]}" if role in {"title", "hero", "closing"} else job or title[:80]
    zones = out.get("copy_zones") if isinstance(out.get("copy_zones"), dict) else {}
    zones = dict(zones)
    zones.setdefault("lede", title[:120])
    out["copy_zones"] = zones
    return out


def build_page_design_prompt(
    *,
    slide: dict[str, Any],
    design_sot_brief: str = "",
    craft_lines: list[str] | None = None,
    design_pack: str = "",
    prior_diary: str = "",
    reuse_art: dict[str, Any] | None = None,
) -> str:
    try:
        from tasks.slide_layout_plan import build_layout_planner_prompt, locked_host_voids
    except ImportError:  # pragma: no cover
        from slide_layout_plan import build_layout_planner_prompt, locked_host_voids  # type: ignore
    plan_prompt = build_layout_planner_prompt(
        slide=slide, design_pack=design_pack, prior_diary=prior_diary
    )
    voids = locked_host_voids(slide)
    craft = list(craft_lines or [])
    reuse_block = ""
    if isinstance(reuse_art, dict) and reuse_art:
        reuse_block = (
            "## Reuse art (keep these values; only refresh plan)\n"
            f"{json.dumps(reuse_art, ensure_ascii=False)[:2500]}\n\n"
        )
    return (
        "## Output schema\n"
        '{"art":{...},"plan":{...}}\n\n'
        f"{reuse_block}"
        "## Art brief context\n"
        f"- design_sot: {(design_sot_brief or '')[:2000]}\n"
        f"- craft_defaults: {craft[:12]}\n"
        f"- prior_diary: {(prior_diary or '')[:600]}\n"
        f"- slide: {json.dumps({k: slide.get(k) for k in ('slide','role','title','core_message','table_id','figure_id','visualization','page_rhythm')}, ensure_ascii=False)}\n"
        f"- formula: {bool(slide.get('formula') or slide.get('formula_tex'))}\n"
        f"- locked_voids: {json.dumps(voids, ensure_ascii=False)}\n\n"
        "## Plan brief (same constraints as Layout Planner)\n"
        f"{plan_prompt}\n"
    )


def author_page_design(
    slide: dict[str, Any],
    *,
    design_sot_brief: str = "",
    craft_lines: list[str] | None = None,
    design_pack: str = "",
    prior_diary: str = "",
    call_text: Callable[[str, str], str] | None = None,
    reuse_art: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Single-thread Art+Plan. Returns (art_brief, layout_plan, design_ms)."""
    try:
        from tasks.art_director import author_art_direction, format_art_direction_block
    except ImportError:  # pragma: no cover
        from art_director import author_art_direction, format_art_direction_block  # type: ignore
    try:
        from tasks.slide_layout_plan import fallback_layout_plan, validate_layout_plan
    except ImportError:  # pragma: no cover
        from slide_layout_plan import fallback_layout_plan, validate_layout_plan  # type: ignore

    t0 = time.perf_counter()
    # Skip LLM when plan already present and not forcing redesign.
    if (
        isinstance(slide.get("_layout_plan"), dict)
        and slide.get("_layout_plan")
        and not slide.get("_force_layout_replan")
        and isinstance(slide.get("_art_brief"), dict)
        and not reuse_art
    ):
        art = _overwrite_art_title(dict(slide["_art_brief"]), slide)
        plan = slide["_layout_plan"]
        slide["_art_direction_block"] = format_art_direction_block(art)
        return art, plan, int((time.perf_counter() - t0) * 1000)

    kept_art = reuse_art if isinstance(reuse_art, dict) and reuse_art else None
    if kept_art is None and slide.get("_force_layout_replan"):
        prior = slide.get("_art_brief")
        if isinstance(prior, dict) and prior:
            kept_art = prior

    if call_text is None:
        art = kept_art or author_art_direction(
            slide, design_sot_brief=design_sot_brief, craft_lines=craft_lines, call_text=None
        )
        art = _overwrite_art_title(art, slide)
        plan = fallback_layout_plan(slide)
        slide["_art_brief"] = art
        slide["_art_direction_block"] = format_art_direction_block(art)
        slide["_layout_plan"] = plan
        slide.pop("_force_layout_replan", None)
        return art, plan, int((time.perf_counter() - t0) * 1000)

    prompt = build_page_design_prompt(
        slide=slide,
        design_sot_brief=design_sot_brief,
        craft_lines=craft_lines,
        design_pack=design_pack,
        prior_diary=prior_diary,
        reuse_art=kept_art,
    )
    raw = ""
    try:
        raw = str(call_text(PAGE_DESIGN_SYSTEM, prompt) or "").strip()
    except Exception as exc:
        print(f"[page_design] LLM failed: {exc}")
        raw = ""

    parsed = _parse_json_object(raw) or {}
    art_raw = parsed.get("art") if isinstance(parsed.get("art"), dict) else None
    plan_raw = parsed.get("plan") if isinstance(parsed.get("plan"), dict) else None
    # Tolerate top-level plan-shaped payloads.
    if plan_raw is None and isinstance(parsed.get("regions"), list):
        plan_raw = parsed

    if kept_art is not None:
        art = kept_art
    elif art_raw is None:
        art = author_art_direction(
            slide,
            design_sot_brief=design_sot_brief,
            craft_lines=craft_lines,
            call_text=None,
        )
    else:
        # Validate via art_director fallback merge path.
        art = author_art_direction(
            slide,
            design_sot_brief=design_sot_brief,
            craft_lines=craft_lines,
            call_text=lambda _s, _p: json.dumps(art_raw, ensure_ascii=False),
        )
    art = _overwrite_art_title(art, slide)

    if plan_raw is None:
        plan = fallback_layout_plan(slide)
    else:
        plan = validate_layout_plan(plan_raw, slide=slide)
        if len(plan.get("regions") or []) < 1:
            plan = fallback_layout_plan(slide)

    slide["_art_brief"] = art
    slide["_art_direction_block"] = format_art_direction_block(art)
    slide["_layout_plan"] = plan
    slide.pop("_force_layout_replan", None)
    design_ms = int((time.perf_counter() - t0) * 1000)
    return art, plan, design_ms
