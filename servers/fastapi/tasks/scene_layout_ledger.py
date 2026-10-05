"""Attribute Chromium layout findings to immutable Scene Layout v2 regions.

The browser reports rendered DOM rectangles.  A useful repair system needs a
stable answer to *whose* budget was exceeded before it changes CSS.  This
module turns that raw report into a compact, serializable ownership ledger and
never mutates HTML.
"""

from __future__ import annotations

import re
from typing import Any


_SCENE_ID_RE = re.compile(r"scene-([a-z0-9_-]+)", re.I)


def _rect(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
    box = item.get("box") if isinstance(item.get("box"), dict) else item
    try:
        x = float(box.get("left"))
        y = float(box.get("top"))
        w = float(box.get("width"))
        h = float(box.get("height"))
    except (AttributeError, TypeError, ValueError):
        return None
    return x, y, w, h


def _intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0.0, min(ay + ah, by + bh) - max(ay, by))


def _scene_regions(scene: dict[str, Any]) -> dict[str, dict[str, Any]]:
    regions: dict[str, dict[str, Any]] = {}
    for raw in scene.get("regions") or []:
        if not isinstance(raw, dict) or raw.get("role") == "footer":
            continue
        rid = str(raw.get("id") or "").strip()
        rect = _rect({"left": raw.get("x"), "top": raw.get("y"), "width": raw.get("w"), "height": raw.get("h")})
        if rid and rect:
            regions[rid] = {"role": str(raw.get("role") or ""), "rect": rect}
    return regions


def _owner_for_element(element: dict[str, Any], regions: dict[str, dict[str, Any]]) -> str | None:
    identifier = str(element.get("id") or "")
    match = _SCENE_ID_RE.search(identifier)
    if match and match.group(1) in regions:
        return match.group(1)
    rect = _rect(element)
    if not rect:
        return None
    ranked = sorted(
        ((rid, _intersection_area(rect, info["rect"])) for rid, info in regions.items()),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[0][0] if ranked and ranked[0][1] > 0 else None


def build_scene_layout_ledger(scene: dict[str, Any], runtime_qa: dict[str, Any]) -> dict[str, Any]:
    """Return a repair-oriented ledger for a single measured slide.

    ``regions`` carries independent failure counts and exact component samples;
    ``collisions`` names both scene owners.  Consumers can therefore repair an
    internal element only when it remains wholly inside its assigned root.
    """
    regions = _scene_regions(scene)
    inspection = runtime_qa.get("inspection") if isinstance(runtime_qa.get("inspection"), dict) else {}
    elements = [item for item in inspection.get("elements") or [] if isinstance(item, dict)]
    by_id = {str(item.get("id") or ""): item for item in elements}
    ledger_regions: dict[str, dict[str, Any]] = {
        rid: {"role": info["role"], "issues": [], "components": []}
        for rid, info in regions.items()
    }
    unowned: list[str] = []

    for issue in runtime_qa.get("hard") or []:
        text = str(issue)
        owners: set[str] = set()
        for element in elements:
            identifier = str(element.get("id") or "")
            if identifier and identifier in text:
                owner = _owner_for_element(element, regions)
                if owner:
                    owners.add(owner)
                    entry = {
                        "id": identifier,
                        "selector": element.get("repairSelector"),
                        "box": element.get("box"),
                        "overflow": element.get("overflow"),
                        "typography": element.get("typography"),
                        "position": element.get("position"),
                        "scene_role": element.get("sceneRole"),
                        "textual": element.get("textual"),
                        "layout_candidates": element.get("layoutCandidates") or [],
                    }
                    if entry not in ledger_regions[owner]["components"]:
                        ledger_regions[owner]["components"].append(entry)
        if not owners:
            # Runtime messages use ``section[scene-lede]`` or similar IDs in
            # normal operation; preserve nonstandard diagnostics explicitly.
            for match in _SCENE_ID_RE.finditer(text):
                if match.group(1) in regions:
                    owners.add(match.group(1))
        if owners:
            for owner in sorted(owners):
                ledger_regions[owner]["issues"].append(text)
        else:
            unowned.append(text)

    # An element positioned outside the card it belongs to is repaired through
    # the same absolute-top channel as a collision, so it inherits the clamp that
    # keeps a suggestion inside the owner.
    for element in elements:
        escape = element.get("escapesOwner")
        if not isinstance(escape, dict) or escape.get("strategy") != "set_absolute_top":
            continue
        owner = str(escape.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("collision_repairs", [])
        if escape.get("suggestedTop") is not None:
            repair = {
                "targetSelector": escape.get("targetSelector"),
                "strategy": "set_absolute_top",
                "suggestedTop": escape.get("suggestedTop"),
            }
            if repair not in repairs:
                repairs.append(repair)
        if escape.get("suggestedLeft") is not None:
            text_repairs = ledger_regions[owner].setdefault("text_collision_repairs", [])
            repair = {
                "targetSelector": escape.get("targetSelector"),
                "strategy": "set_absolute_left",
                "suggestedLeft": escape.get("suggestedLeft"),
            }
            if repair not in text_repairs:
                text_repairs.append(repair)

    collisions: list[dict[str, Any]] = []
    for raw in inspection.get("collisions") or []:
        if not isinstance(raw, dict):
            continue
        left = _owner_for_element(by_id.get(str(raw.get("a") or ""), {}), regions)
        right = _owner_for_element(by_id.get(str(raw.get("b") or ""), {}), regions)
        collisions.append({
            "a": raw.get("a"), "b": raw.get("b"), "owners": [left, right],
            "width": raw.get("width"), "height": raw.get("height"),
        })
        repair = raw.get("repair") if isinstance(raw.get("repair"), dict) else None
        owner = str((repair or {}).get("sceneOwner") or "")
        if repair and owner in ledger_regions:
            repairs = ledger_regions[owner].setdefault("collision_repairs", [])
            if repair not in repairs:
                repairs.append(repair)
    for item in inspection.get("narrowText") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        grid_repair = item.get("gridRepair") if isinstance(item.get("gridRepair"), dict) else None
        if grid_repair:
            repairs = ledger_regions[owner].setdefault("grid_repairs", [])
            if grid_repair not in repairs:
                repairs.append(grid_repair)
        # Attribute the finding itself, not only its repair. The repair pass
        # visits a region that owns at least one issue, and this finding names a
        # synthesized element id ("span.mini:-1") that matches no measured
        # component — so it stayed in `unowned_issues`, no region was ever
        # visited for it, and a column laying out four lines in 91px could never
        # be repaired at all. An unowned finding is a finding nothing can fix.
        needle = str(item.get("element") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)
    for item in inspection.get("hostSlack") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("host_repairs", [])
        repair = {key: item.get(key) for key in ("selector", "strategy", "suggestedHeight")}
        if repair not in repairs:
            repairs.append(repair)
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("gridItemOverflow") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("grid_repairs", [])
        repair = {
            key: item.get(key)
            for key in ("selector", "spareSelector", "strategy", "columns", "items")
        }
        if repair not in repairs:
            repairs.append(repair)
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("gridTrackOverflow") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("grid_repairs", [])
        repair = {
            key: item.get(key)
            for key in ("selector", "strategy", "suggestedColumns", "overflow", "gap")
        }
        if repair not in repairs:
            repairs.append(repair)
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("textContrast") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("contrast_repairs", [])
        repair = {
            key: item.get(key)
            for key in (
                "selector", "strategy", "ratio", "trespass",
                "surfaceSelector", "surfaceLeft", "boxLeft",
                "color", "surface",
            )
        }
        if repair not in repairs:
            repairs.append(repair)
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("hostShortfall") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("host_shortfall_repairs", [])
        repair = {
            key: item.get(key)
            for key in ("selector", "strategy", "suggestedHeight", "above", "below")
        }
        if repair not in repairs:
            repairs.append(repair)
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("regionOverruns") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("region_overrun_repairs", [])
        repair = {
            key: item.get(key)
            for key in (
                "selector", "deepestSelector", "strategy",
                "overrun", "paddingTop", "paddingBottom", "suggestedTop",
                "regionHeight",
            )
        }
        if repair not in repairs:
            repairs.append(repair)
        # The finding names a selector, not a measured element id, so it has to
        # be attributed here or the repair pass never visits the region.
        needle = str(item.get("deepestSelector") or item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("roundOverflows") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("round_repairs", [])
        repair = {
            key: item.get(key)
            for key in ("selector", "strategy", "suggestedFontSize", "inscribed")
        }
        if repair not in repairs:
            repairs.append(repair)
        # The repair pass only visits a region that owns at least one issue, and
        # this finding names a selector rather than a measured element id, so it
        # has to be attributed here or the region is skipped entirely.
        needle = str(item.get("selector") or "")
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)

    for item in inspection.get("pseudoIssues") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("pseudo_repairs", [])
        repair = {
            key: item.get(key)
            for key in (
                "type", "selector", "pseudo", "strategy", "suggestedTop",
                "suggestedPaddingLeft",
                "gap", "minGap", "maxGap", "content", "against", "overlap",
            )
        }
        if repair not in repairs:
            repairs.append(repair)
        needle = f"{item.get('selector') or ''}{item.get('pseudo') or ''}"
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if needle and needle in text and text not in ledger_regions[owner]["issues"]:
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)
    for item in inspection.get("decorationCollisions") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        if owner not in ledger_regions:
            continue
        repairs = ledger_regions[owner].setdefault("decoration_repairs", [])
        repair = {
            key: item.get(key)
            for key in (
                "line", "target", "targetSelector", "strategy", "shiftY",
                "currentMarginTop", "suggestedMarginTop", "suggestedTop", "pseudo",
                # Moving the rule is preferred over moving the copy: it carries
                # no content, so it can be relocated or dropped without loss.
                "ruleSelector", "ruleStrategy",
                "suggestedRuleBottom", "suggestedRuleTop",
                # A vertical bar is cleared sideways.
                "suggestedPaddingLeft", "currentPaddingLeft",
            )
        }
        if repair not in repairs:
            repairs.append(repair)
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if (
                str(item.get("line") or "") in text
                and str(item.get("target") or "") in text
                and text not in ledger_regions[owner]["issues"]
            ):
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)
    for item in inspection.get("textCollisions") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("sceneOwner") or "")
        repair = item.get("repair") if isinstance(item.get("repair"), dict) else None
        if owner not in ledger_regions or not repair:
            continue
        repairs = ledger_regions[owner].setdefault("text_collision_repairs", [])
        if repair not in repairs:
            repairs.append(repair)
        for issue in runtime_qa.get("hard") or []:
            text = str(issue)
            if (
                str(item.get("a") or "") in text
                and str(item.get("b") or "") in text
                and text not in ledger_regions[owner]["issues"]
            ):
                ledger_regions[owner]["issues"].append(text)
                if text in unowned:
                    unowned.remove(text)
    from tasks.layout_findings import classify_runtime_findings

    return {
        "version": "scene_layout_ledger_v1",
        "ok": not bool(runtime_qa.get("hard")),
        "findings": classify_runtime_findings(runtime_qa.get("hard") or []),
        "regions": ledger_regions,
        "collisions": collisions,
        "unowned_issues": unowned,
    }
