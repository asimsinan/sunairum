"""Fail-closed Chromium layout gate for Scene v2 slides."""

from __future__ import annotations

from typing import Any


def audit_runtime_html_layout(html: str) -> dict[str, Any]:
    """Audit resolved geometry; unavailable browser measurement is a hard failure."""
    if not html:
        return {"ok": True, "issues": [], "hard": [], "inspection": {}}

    from tasks.html_runtime_layout import inspect_html_layout

    inspection = inspect_html_layout(html)
    issues: list[str] = []
    hard: list[str] = []
    if not inspection.get("available"):
        message = (
            "runtime_layout_unavailable: "
            f"{inspection.get('error') or 'no Chromium report'}"
        )
        return {
            "ok": False,
            "issues": [message],
            "hard": [message],
            "inspection": inspection,
        }

    for element in inspection.get("elements") or []:
        element_id = str(element.get("id") or "element")
        overflow = element.get("overflow") if isinstance(element.get("overflow"), dict) else {}
        # scrollWidth includes pseudo-elements and intentional background
        # decoration. The runtime probe separately measures real, non-decorative
        # authored descendants and text against the component bounds.
        scroll_x = float(overflow.get("contentX", overflow.get("scrollX")) or 0)
        scroll_y = float(overflow.get("contentY", overflow.get("scrollY")) or 0)
        # The page number is pipeline-owned margin chrome, not a content canvas.
        # Older generated footers can report 1–2px of glyph ink beyond their
        # CSS line box while remaining safely inside the reserved footer band.
        # Up to four CSS pixels of ink can extend beyond an abstract Scene box
        # because of font ascenders/descenders without clipping or touching the
        # next region. Real collisions and plate overflow are checked below.
        typography = element.get("typography") if isinstance(element.get("typography"), dict) else {}
        try:
            title_font_size = float(typography.get("fontSize") or 0)
        except (TypeError, ValueError):
            title_font_size = 0.0
        for target in overflow.get("targets") or []:
            if not isinstance(target, dict):
                continue
            try:
                title_font_size = max(title_font_size, float(target.get("fontSize") or 0))
            except (TypeError, ValueError):
                continue
        # Chromium's serif glyph ink can extend roughly 0.14em beyond its line
        # box even when the element and every ancestor remain fully in bounds.
        # A fixed 8px threshold rejected a correct 64px cover title by 1px and
        # triggered a whole-slide fallback.  Scale the allowance with type;
        # clipping, plate escape and collisions remain independently hard.
        title_ink_limit = max(8.0, min(12.0, title_font_size * 0.16))
        title_ink_tolerance = (
            str(element.get("sceneRole") or element.get("role") or "").casefold() == "title"
            and scroll_x <= title_ink_limit
            and scroll_y <= title_ink_limit
        )
        overflow_targets = [
            target for target in (overflow.get("targets") or [])
            if isinstance(target, dict)
            and (float(target.get("overflowX") or 0) > 4.0 or float(target.get("overflowY") or 0) > 4.0)
        ]
        # Labels, badges and annotations may intentionally bleed outside their
        # Scene lane while remaining inside the slide plate. They are safe when
        # absolutely positioned, visible (not clipped), and independently
        # collision-checked. Treating their lane's scroll extent as text
        # overflow erased otherwise valid authored compositions.
        # An element that paints its own surface is a visible container, not an
        # abstract lane: copy escaping a coloured card reads as broken even when
        # it stays inside the slide plate. The bleed exemption only ever meant
        # "an invisible Scene box may be overrun by a badge", so withhold it from
        # anything the audience can actually see the edge of.
        safe_absolute_bleed = (
            bool(overflow_targets)
            and not element.get("painted")
            and all(
                str(target.get("position") or "") in {"absolute", "fixed"}
                and not bool(target.get("outsidePlate"))
                for target in overflow_targets
            )
            and not bool(overflow.get("clippedByAncestor"))
        )
        # Glyph ink legitimately extends past its line box, and by more pixels
        # the larger the type: a 40px numeral routinely reports ~5px without any
        # visible clipping. A flat threshold therefore reads as a defect on every
        # display-size element while still being loose for body copy.
        #
        # The bound is the share of the em a face can place outside its own line
        # box — the same quantity the collision guard measures. It used to be
        # 0.16em under a flat 12px ceiling, and that ceiling is what misfired on
        # display type: a 57px numeral overshooting 15px was called an overflow
        # although 15px is 0.26em, well inside what the face needs. Body copy is
        # unaffected — at 16px the bound is 5.6px, so a 10px region overrun is
        # still far above it.
        overflow_slack = max(4.0, title_font_size * 0.35)
        if (
            (scroll_x > overflow_slack or scroll_y > overflow_slack)
            and not element.get("pageNumber")
            and not title_ink_tolerance
            and not safe_absolute_bleed
        ):
            message = (
                f"runtime_text_overflow: {element_id} scrolls "
                f"({scroll_x:.1f}px x, {scroll_y:.1f}px y)"
            )
            issues.append(message)
            hard.append(message)
        if overflow.get("clippedByAncestor"):
            message = f"runtime_ancestor_clip: {element_id} crosses a clipping ancestor"
            issues.append(message)
            hard.append(message)
        if element.get("outsidePlate"):
            message = f"runtime_canvas_overflow: {element_id} paints outside the slide plate"
            issues.append(message)
            hard.append(message)
        escaped = element.get("escapesOwner")
        if isinstance(escaped, dict):
            message = (
                f"runtime_owner_escape: {element_id} sits {float(escaped.get('worst') or 0):.1f}px "
                f"outside {escaped.get('ownerSelector') or 'its owner'}"
            )
            issues.append(message)
            hard.append(message)

    for item in inspection.get("textContrast") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_text_contrast: "
            f"{item.get('selector')} reads at {float(item.get('ratio') or 0):.2f}:1 "
            f"({item.get('color')} on {item.get('surface')}): "
            f"{str(item.get('text') or '')[:60]}"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("hostShortfall") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_host_shortfall: "
            f"{item.get('selector')} holds {float(item.get('contentHeight') or 0):.0f}px of "
            f"{item.get('kind')} content in a {float(item.get('hostHeight') or 0):.0f}px host"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("hostSlack") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_host_dead_space: "
            f"{item.get('selector')} reserves "
            f"{float(item.get('hostHeight') or 0):.0f}px for "
            f"{float(item.get('contentHeight') or 0):.0f}px of content "
            f"({float(item.get('slack') or 0):.0f}px unused)"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("regionOverruns") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_region_overrun: "
            f"{item.get('deepestSelector') or item.get('selector')} runs "
            f"{float(item.get('overrun') or 0):.1f}px "
            f"past the bottom of scene-{item.get('region')}"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("gridItemOverflow") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_grid_item_overflow: "
            f"{item.get('selector')} has {item.get('items')} grid items for "
            f"{item.get('columns')} columns, wrapping content into a "
            "decoration track"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("gridTrackOverflow") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_grid_track_overflow: "
            f"{item.get('selector')} tracks plus a {float(item.get('gap') or 0):.1f}px gap "
            f"exceed the container by {float(item.get('overflow') or 0):.1f}px"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("freehandCharts") or []:
        if not isinstance(item, dict):
            continue
        # Advisory: the slide is not broken by this, but the figure is drawn
        # rather than plotted, so nothing guarantees it matches its numbers.
        issues.append(
            "runtime_freehand_chart: "
            f"scene-{item.get('sceneOwner')} plots {item.get('lines')} rotated rules "
            f"at {item.get('angles')} with no chart host"
        )

    for item in inspection.get("ambientDecoration") or []:
        if not isinstance(item, dict):
            continue
        # Advisory, not hard: the shape does not break the layout, it makes the
        # deck read as decorated rather than authored. Reporting it keeps the
        # judgement with the author instead of silently repainting the slide.
        issues.append(
            "runtime_ambient_decoration: "
            f"{item.get('selector')} is a {float(item.get('diameter') or 0):.0f}px "
            "round shape with no content and no role"
        )

    for item in inspection.get("roundOverflows") or []:
        if not isinstance(item, dict):
            continue
        message = (
            "runtime_round_container_overflow: "
            f"{item.get('selector')} copy needs "
            f"{max(float(item.get('inkWidth') or 0), float(item.get('inkHeight') or 0)):.1f}px "
            f"inside a {float(item.get('inscribed') or 0):.1f}px circle"
        )
        issues.append(message)
        hard.append(message)

    for fragment in inspection.get("wordFragments") or []:
        word = str(fragment.get("word") or "text")
        element_id = str(fragment.get("element") or "element")
        lines = int(fragment.get("lines") or 0)
        message = (
            f"runtime_word_fragmented: {word!r} splits across {lines} lines in {element_id}"
        )
        issues.append(message)
        hard.append(message)

    for item in inspection.get("narrowText") or []:
        message = (
            "runtime_narrow_text: "
            f"{item.get('element')} lays out {item.get('lines')} lines in "
            f"{float(item.get('width') or 0):.1f}px "
            f"({float(item.get('charsPerLine') or 0):.1f} chars/line): "
            f"{str(item.get('text') or '')[:80]}"
        )
        issues.append(message)
        hard.append(message)

    for collision in inspection.get("collisions") or []:
        message = (
            "runtime_sibling_collision: "
            f"{collision.get('a')} overlaps {collision.get('b')} "
            f"by {float(collision.get('width') or 0):.1f}×"
            f"{float(collision.get('height') or 0):.1f}px"
        )
        issues.append(message)
        hard.append(message)

    for collision in inspection.get("textCollisions") or []:
        width = float(collision.get("width") or 0)
        height = float(collision.get("height") or 0)
        gap = float(collision.get("gap") or 0)
        required = float(collision.get("requiredGap") or 0)
        if width > 0 and height > 0:
            detail = f"overlaps by {width:.1f}×{height:.1f}px"
        else:
            detail = f"has only {gap:.1f}px clearance (minimum {required:.1f}px)"
        message = (
            "runtime_text_collision: "
            f"{collision.get('a')} and {collision.get('b')} {detail}"
        )
        issues.append(message)
        hard.append(message)

    for collision in inspection.get("decorationCollisions") or []:
        if collision.get("gap") is not None:
            message = (
                "runtime_decoration_collision: "
                f"{collision.get('line')} has only {float(collision.get('gap') or 0):.1f}px "
                f"clearance from {collision.get('target')} "
                f"(minimum {float(collision.get('requiredGap') or 0):.1f}px)"
            )
        else:
            message = (
                "runtime_decoration_collision: "
                f"{collision.get('line')} crosses {collision.get('target')} "
                f"by {float(collision.get('width') or 0):.1f}×"
                f"{float(collision.get('height') or 0):.1f}px"
            )
        issues.append(message)
        hard.append(message)

    for pseudo in inspection.get("pseudoIssues") or []:
        selector = f"{pseudo.get('selector') or 'element'}{pseudo.get('pseudo') or ''}"
        if pseudo.get("type") == "connector_mask":
            message = (
                "runtime_connector_mask: "
                f"{selector} paints an opaque box behind connector "
                f"{str(pseudo.get('content') or '')[:24]!r}"
            )
        elif pseudo.get("type") == "text_separation":
            message = (
                "runtime_text_separation: "
                f"{selector} sits {float(pseudo.get('gap') or 0):.1f}px from title text "
                f"(maximum {float(pseudo.get('maxGap') or 0):.1f}px)"
            )
        elif pseudo.get("type") == "marker_gutter_collision":
            overlap = pseudo.get("overlap") if isinstance(pseudo.get("overlap"), dict) else {}
            message = (
                "runtime_marker_gutter_collision: "
                f"{selector} marker overlaps its own copy by "
                f"{float(overlap.get('width') or 0):.1f}px"
            )
        elif pseudo.get("type") == "pseudo_text_collision":
            overlap = pseudo.get("overlap") if isinstance(pseudo.get("overlap"), dict) else {}
            message = (
                "runtime_pseudo_text_collision: "
                f"{selector} overlaps {pseudo.get('against') or 'text'} by "
                f"{float(overlap.get('width') or 0):.1f}×"
                f"{float(overlap.get('height') or 0):.1f}px"
            )
        else:
            message = (
                "runtime_text_proximity: "
                f"{selector} sits {float(pseudo.get('gap') or 0):.1f}px from title text "
                f"(minimum {float(pseudo.get('minGap') or 0):.1f}px)"
            )
        issues.append(message)
        hard.append(message)

    return {
        "ok": not hard,
        "issues": issues,
        "hard": hard,
        "inspection": inspection,
    }
