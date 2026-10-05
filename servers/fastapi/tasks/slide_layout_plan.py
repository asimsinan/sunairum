"""Two-call LayoutCoT: JSON region plan (Call 1) before SVG paint (Call 2).

Plan boxes may be nudged during validation — authored Constrained HTML is never restacked here.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

CANVAS_W = 1280.0
CANVAS_H = 720.0
_SAFE = (40.0, 40.0, 1200.0, 640.0)

_VALID_ROLES = frozenset(
    {
        "title",
        "subtitle",
        "card",
        "motif",
        "icon",
        "body",
        "claim",
        "takeaway",
        "host_void",
        "footer",
        "aside",
        "chip",
        "label",
        "callout",
    }
)
# Roles that must stay free of body/claim copy (short labels only for label/callout).
_NO_BODY_ROLES = frozenset({"host_void", "motif", "icon", "label", "callout"})

LAYOUT_PLANNER_SYSTEM = """You are Sunairum's Layout Planner.
Return ONLY a JSON object matching SlideLayoutPlan — no markdown fences, no SVG.
Canvas is 1280×720. Author 3–8 regions the Executor will paint into.
Creativity: you choose composition and metaphors; host_void regions from the user
prompt are locked — copy them unchanged and never place freehand there.
"""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def locked_host_voids(slide: dict[str, Any]) -> list[dict[str, Any]]:
    """Pipeline-owned host voids the planner must preserve."""
    voids: list[dict[str, Any]] = []
    try:
        from tasks.intent_hosts import FIGURE_HOST, FORMULA_HOST, TABLE_HOST
    except ImportError:  # pragma: no cover
        from intent_hosts import FIGURE_HOST, FORMULA_HOST, TABLE_HOST  # type: ignore

    tid = str(slide.get("table_id") or "").strip()
    if tid and tid.casefold() not in {"none", "null", "n/a", "-"}:
        band = slide.get("_table_band") if isinstance(slide.get("_table_band"), dict) else None
        if band and all(k in band for k in ("x", "y", "w", "h")):
            x, y, w, h = _f(band["x"]), _f(band["y"]), _f(band["w"]), _f(band["h"])
        else:
            x, y, w, h = TABLE_HOST
        voids.append(
            {
                "id": "table_host",
                "role": "host_void",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "metaphor": "pipeline table/findings inject",
            }
        )

    fid = str(slide.get("figure_id") or "").strip()
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        x, y, w, h = FIGURE_HOST
        voids.append(
            {
                "id": "figure_host",
                "role": "host_void",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "metaphor": "pipeline figure inject",
            }
        )

    formula = str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    band = slide.get("_formula_band") if isinstance(slide.get("_formula_band"), dict) else None
    if formula or band:
        if band and all(k in band for k in ("x", "y", "w", "h")):
            x, y, w, h = _f(band["x"]), _f(band["y"]), _f(band["w"]), _f(band["h"])
        else:
            x, y, w, h = FORMULA_HOST
        voids.append(
            {
                "id": "formula_host",
                "role": "host_void",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "metaphor": "pipeline formula PNG+legend inject",
            }
        )
    return voids


def _normalize_region(raw: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    role = str(raw.get("role") or "body").strip().casefold()
    if role not in _VALID_ROLES:
        role = "body"
    rid = str(raw.get("id") or f"r{index}").strip() or f"r{index}"
    x = max(0.0, min(CANVAS_W - 8.0, _f(raw.get("x"), _SAFE[0])))
    y = max(0.0, min(CANVAS_H - 8.0, _f(raw.get("y"), _SAFE[1])))
    w = max(24.0, min(CANVAS_W - x, _f(raw.get("w"), 200.0)))
    h = max(20.0, min(CANVAS_H - y, _f(raw.get("h"), 80.0)))
    out: dict[str, Any] = {
        "id": rid,
        "role": role,
        "x": round(x, 1),
        "y": round(y, 1),
        "w": round(w, 1),
        "h": round(h, 1),
    }
    if raw.get("title_y") is not None:
        out["title_y"] = round(max(y + 8.0, min(y + h - 8.0, _f(raw.get("title_y")))), 1)
    if raw.get("pair_id"):
        out["pair_id"] = str(raw.get("pair_id")).strip()
    if raw.get("metaphor"):
        out["metaphor"] = str(raw.get("metaphor")).strip()[:120]
    if raw.get("claim"):
        out["claim"] = str(raw.get("claim")).strip()[:200]
    return out


def _aabb_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def _nudge_non_host_overlaps(regions: list[dict[str, Any]]) -> None:
    """Nudge plan boxes only (not painted SVG) when non-nested peers overlap."""
    hosts = [r for r in regions if r.get("role") == "host_void"]
    others = [r for r in regions if r.get("role") != "host_void"]
    for i, a in enumerate(others):
        abox = (a["x"], a["y"], a["w"], a["h"])
        for host in hosts:
            hbox = (host["x"], host["y"], host["w"], host["h"])
            if not _aabb_overlap(abox, hbox):
                continue
            # Prefer shifting left of host when possible.
            new_w = max(24.0, host["x"] - a["x"] - 12.0)
            if new_w >= 80.0 and a["x"] < host["x"]:
                a["w"] = round(new_w, 1)
            else:
                a["y"] = round(min(CANVAS_H - a["h"] - 8.0, host["y"] + host["h"] + 12.0), 1)
            abox = (a["x"], a["y"], a["w"], a["h"])
        for b in others[i + 1 :]:
            bbox = (b["x"], b["y"], b["w"], b["h"])
            if not _aabb_overlap(abox, bbox):
                continue
            # Nested (card contains body/motif) — keep.
            if (
                a["x"] <= b["x"]
                and a["y"] <= b["y"]
                and a["x"] + a["w"] >= b["x"] + b["w"]
                and a["y"] + a["h"] >= b["y"] + b["h"]
            ) or (
                b["x"] <= a["x"]
                and b["y"] <= a["y"]
                and b["x"] + b["w"] >= a["x"] + a["w"]
                and b["y"] + b["h"] >= a["y"] + a["h"]
            ):
                continue
            b["y"] = round(min(CANVAS_H - b["h"] - 8.0, a["y"] + a["h"] + 10.0), 1)


def validate_layout_plan(
    raw: Any,
    *,
    slide: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize/clamp a SlideLayoutPlan; reinject locked host voids."""
    slide = slide or {}
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    regions_in = raw.get("regions") if isinstance(raw.get("regions"), list) else []
    regions: list[dict[str, Any]] = []
    for i, item in enumerate(regions_in[:12]):
        norm = _normalize_region(item, index=i)
        if norm:
            regions.append(norm)

    # Drop model-authored host_voids; reinject pipeline locks.
    regions = [r for r in regions if r.get("role") != "host_void"]
    voids = locked_host_voids(slide)
    # Keep non-host regions that don't duplicate void ids.
    void_ids = {v["id"] for v in voids}
    regions = [r for r in regions if r.get("id") not in void_ids]
    regions.extend(voids)

    if not regions:
        regions = list(voids) or [
            {
                "id": "body",
                "role": "body",
                "x": 80.0,
                "y": 160.0,
                "w": 1120.0,
                "h": 420.0,
            }
        ]

    _nudge_non_host_overlaps(regions)

    # Peer card title_y consensus.
    cards = [r for r in regions if r.get("role") == "card" and r.get("title_y") is not None]
    if len(cards) >= 2:
        median = sorted(float(c["title_y"]) for c in cards)[len(cards) // 2]
        for c in cards:
            c["title_y"] = round(median, 1)

    job = str(raw.get("job") or slide.get("visual_job") or slide.get("core_message") or "").strip()
    composition = str(raw.get("composition") or slide.get("visualization") or "free_composition").strip()
    rules = raw.get("rules") if isinstance(raw.get("rules"), list) else []
    rules_out = [str(r).strip() for r in rules if str(r).strip()][:8]
    if "no freehand in host_void" not in " ".join(rules_out).casefold():
        rules_out.append("no freehand in host_void")

    return {
        "job": job[:240],
        "composition": composition[:80],
        "regions": regions,
        "rules": rules_out,
    }


def fallback_layout_plan(slide: dict[str, Any]) -> dict[str, Any]:
    """Host voids + a single body band when the planner fails."""
    voids = locked_host_voids(slide)
    body = {
        "id": "body",
        "role": "body",
        "x": 80.0,
        "y": 160.0,
        "w": 500.0 if voids else 1120.0,
        "h": 420.0,
        "metaphor": "primary claims",
    }
    if voids:
        hx = min(v["x"] for v in voids)
        if hx > 200:
            body["w"] = max(200.0, hx - 100.0)
    return validate_layout_plan(
        {
            "job": str(slide.get("visual_job") or slide.get("core_message") or "one visual job"),
            "composition": str(slide.get("visualization") or "free_composition"),
            "regions": [body],
            "rules": ["no freehand in host_void", "motif paired to claim"],
        },
        slide=slide,
    )


def format_layout_plan_block(plan: dict[str, Any]) -> str:
    """Markdown block injected into the Executor paint prompt."""
    if not plan or not isinstance(plan.get("regions"), list):
        return ""
    lines = [
        "## Locked layout plan (honor exactly)",
        f"- JOB: {plan.get('job') or '(one visual job)'}",
        f"- COMPOSITION: {plan.get('composition') or 'free_composition'}",
        "Paint shapes/text ONLY inside their regions. host_void regions stay EMPTY groups.",
        "NO-TEXT ZONES: host_void / motif / figure / table voids — no body copy inside.",
        "label/callout regions: short labels only (≤6 words); never paragraph body.",
        "Meaning alignment: each motif/icon must encode its paired claim (pair_id / metaphor); "
        "no orphan decorative shapes.",
    ]
    for region in plan["regions"]:
        if not isinstance(region, dict):
            continue
        role = str(region.get("role") or "")
        bit = (
            f"- region id={region.get('id')} role={role} "
            f"x={region.get('x')} y={region.get('y')} "
            f"w={region.get('w')} h={region.get('h')}"
        )
        if role in _NO_BODY_ROLES:
            bit += " [no-body]"
        if region.get("title_y") is not None:
            bit += f" title_y={region.get('title_y')}"
        if region.get("pair_id"):
            bit += f" pair_id={region.get('pair_id')}"
        if region.get("metaphor"):
            bit += f" metaphor={region.get('metaphor')!r}"
        if region.get("claim"):
            bit += f" claim={region.get('claim')!r}"
        lines.append(bit)
    rules = plan.get("rules") if isinstance(plan.get("rules"), list) else []
    if rules:
        lines.append("Rules: " + "; ".join(str(r) for r in rules))
    lines.append("")
    return "\n".join(lines)


def build_layout_planner_prompt(
    *,
    slide: dict[str, Any],
    design_pack: str = "",
    prior_diary: str = "",
) -> str:
    """User prompt for Call 1 (JSON only)."""
    voids = locked_host_voids(slide)
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    body = str(content.get("BODY") or slide.get("content_blocks") or "").strip()
    core = str(slide.get("core_message") or "").strip()
    title = str(slide.get("title") or "").strip()
    page_role = str(slide.get("page_role") or slide.get("role") or "content")
    viz = str(slide.get("visualization") or "free_composition")

    has_table = bool(str(slide.get("table_id") or "").strip()) and str(
        slide.get("table_id")
    ).casefold() not in {"none", "null", "n/a", "-"}
    has_formula = bool(str(slide.get("formula") or slide.get("formula_tex") or "").strip())
    has_figure = bool(str(slide.get("figure_id") or "").strip()) and str(
        slide.get("figure_id")
    ).casefold() not in {"none", "null", "n/a", "-"}

    job_hints: list[str] = []
    if has_table:
        job_hints.append(
            "JOB: make the table finding readable in a LEFT takeaway column "
            "(icons/chips that explain the finding). Host void = Intent findings "
            "visual (ranked_bars / top_k / small grid) — not an LLM-drawn fake grid."
        )
    if has_formula:
        job_hints.append(
            "JOB: explain what the equation does with meaning chrome OUTSIDE the host "
            "(trade-off, weights, dual chips). Host void = PNG+legend only — never paint TeX."
        )
    if has_figure:
        job_hints.append(
            "JOB: explain the figure. COMPOSITION: left claims + empty figure host_void; "
            "motif mid-band; caption ≥12–16px below motif; takeaway x+w ≤ figure_x − gutter "
            "(never underlap the figure column)."
        )
    if not job_hints:
        job_hints.append(
            "JOB: one clear visual job; peer cards share title_y; motif mid / body bottom."
        )

    void_json = json.dumps(voids, ensure_ascii=False)
    pack_snip = (design_pack or "").strip()[:3500]
    diary = (prior_diary or "").strip()[:800] or "(none)"

    return (
        "## SlideLayoutPlan schema\n"
        "{\n"
        '  "job": "one sentence",\n'
        '  "composition": "peer_cards_row|formula_hero_aside|table_left_takeaway|…",\n'
        '  "regions": [{"id","role","x","y","w","h","title_y?","pair_id?","metaphor?","claim?"}],\n'
        '  "rules": ["…"]\n'
        "}\n"
        f"Canvas {CANVAS_W:g}×{CANVAS_H:g}. Roles: "
        + ", ".join(sorted(_VALID_ROLES))
        + ".\n\n"
        "## Locked host_void regions (copy unchanged into regions[])\n"
        f"{void_json}\n\n"
        "## JOB / COMPOSITION / GUARDRAILS\n"
        + "\n".join(f"- {h}" for h in job_hints)
        + "\n"
        "- COMPOSITION: choose freely; vary vs prior diary.\n"
        "- GUARDRAILS: empty host_void; no freehand in voids; no orphan décor; "
        "every motif/icon has pair_id to a body/claim and a one-phrase metaphor.\n"
        "- Use role=label / role=callout for short motif/chart annotations "
        "(never put body paragraphs in those boxes).\n"
        "- Motif/figure/table host_void = no-text zones for body/claim copy.\n"
        "- Peer step cards: shared title_y; title top → motif mid → body bottom.\n"
        "- Multi-line claims: each claim owns a body region; next block below prior.\n\n"
        f"## Page\n- title: {title or '(untitled)'}\n"
        f"- page_role: {page_role}\n- visualization: {viz}\n"
        f"- core: {core or '(none)'}\n- content: {body[:1200] or '(none)'}\n\n"
        f"## Prior diary\n{diary}\n\n"
        f"## Content pack (snippet)\n{pack_snip or '(none)'}\n\n"
        "Return JSON only.\n"
    )


def plan_slide_layout(
    *,
    slide: dict[str, Any],
    call_text: Callable[[str, str], str] | None,
    design_pack: str = "",
    prior_diary: str = "",
) -> dict[str, Any]:
    """Call 1: ask the LLM for JSON regions; validate; store on slide['_layout_plan']."""
    if call_text is None:
        plan = fallback_layout_plan(slide)
        slide["_layout_plan"] = plan
        return plan

    prompt = build_layout_planner_prompt(
        slide=slide, design_pack=design_pack, prior_diary=prior_diary
    )
    raw_text = ""
    try:
        raw_text = call_text(LAYOUT_PLANNER_SYSTEM, prompt)
    except Exception as exc:
        print(f"[layout_plan] planner LLM failed: {exc}")
        plan = fallback_layout_plan(slide)
        slide["_layout_plan"] = plan
        return plan

    plan = validate_layout_plan(raw_text, slide=slide)
    # If planner ignored voids, reinject via validate already handled; ensure ≥1 void when expected.
    expected = locked_host_voids(slide)
    if expected:
        have = {
            r["id"]
            for r in plan.get("regions", [])
            if isinstance(r, dict) and r.get("role") == "host_void"
        }
        if any(v["id"] not in have for v in expected):
            plan = validate_layout_plan(plan, slide=slide)
    if len(plan.get("regions") or []) < 1:
        plan = fallback_layout_plan(slide)
    slide["_layout_plan"] = plan
    return plan


def spatial_issues_suggest_replan(issues: list[str]) -> bool:
    """True only for region/host failures that mechanical normalize cannot fix.

    Overlaps, peer drift, font drift, and table residual are mechanical — replan
    would burn an extra Plan+Paint for no quality gain.
    """
    blob = " ".join(issues).casefold()
    keys = (
        "missing_svg",
        "missing_figure_slot",
        "missing_table_slot",
        "missing_formula",
        "host_void_empty_content",
        "export_gate",
    )
    return any(k in blob for k in keys)
