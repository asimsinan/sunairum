"""LLM visual authorship inside immutable Scene Layout v2 geometry.

The scene solver owns top-level placement.  The LLM owns art direction and the
HTML/CSS composition inside those boxes.  This prevents the two failure modes
from being conflated: browser-safe placement does not require template-like
slides, and creative styling does not require freehand slide geometry.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from collections.abc import Iterable
from typing import Any, Callable

from tasks.html_constitution import extract_html_document, validate_slide_html
from tasks.slide_scene import format_scene_layout_block


SCENE_AUTHOR_SYSTEM = """You are Sunairum's senior presentation art director and HTML designer.

Author ONE polished 1280x720 HTML presentation slide. Return only a complete
HTML document. Use the supplied Scene Layout v2 boxes as immutable top-level
geometry, while exercising strong visual judgment inside them.

VISUAL QUALITY IS A HARD REQUIREMENT
- Turn the design brief into a distinctive visual system, not a generic card UI.
- Establish a clear focal point, strong scale contrast, intentional whitespace,
  meaningful color masses, and content-specific visual metaphors.
- Vary slide silhouettes across the deck. Avoid repeating the same pale panels.
- Prefer one governed composition over a dashboard of interchangeable cards.
- Use CSS backgrounds, borders, rules, pseudo-elements, typography, numerals,
  and simple HTML shapes to make the slide feel authored and editorial.
- Mark every purely decorative glyph, watermark, ornament, or oversized
  background character with aria-hidden="true" and data-pptx-kind="decoration".
  Accessibility-hidden artwork is still visible ink and MUST be exported.
  Use data-pptx-kind="ignore" only for genuinely preview-only/runtime UI that
  has a separate native export owner (for example an injected chart preview).
  Decorative ink must never be treated as audience copy or layout overflow.
- Decoration must mean something on THIS slide. A rule may separate, a bar may
  index, a numeral may count, a connector may show a direction that the copy
  actually describes. What is forbidden is generic ambient geometry: circles,
  orbits, rings, arcs, blobs and gradient orbs floating behind content because
  the slide looked empty. A reader asks what a large circle behind a paragraph
  denotes, gets no answer, and reads the deck as decorated rather than authored.
  If you cannot say in one clause what a shape tells the audience, leave it out
  and let the space stay empty — empty space is a legitimate composition.
- Text must remain readable at presentation distance: title >=36px, body >=16px.

GEOMETRY CONTRACT
- The direct children of .slide that represent content regions MUST use the
  exact data-layout-id, data-layout-role, left, top, width, and height supplied.
- All region roots are position:absolute. Do not move, resize, overlap, clip, or
  add another top-level content region. Internal children may use grid/flex.
- The footer region is reserved; do not author it or any page number.
- Do not use CSS transforms to move content across region boundaries.
- Use overflow:visible on text regions. Make copy fit by editing hierarchy and
  internal composition, never by hiding or clipping text.
- Keep 32–64px of visible clearance between main title ink and following
  subtitle furniture; target 40px. Text in ::before/::after counts toward this
  cross-render Chromium/PowerPoint font-metric budget.
- When an internal callout or note is position:absolute, reserve its full height
  in the normal-flow content above it. Never let bullets continue behind it.
- Connector lines/arrows belong behind nodes and labels. Their pseudo-elements
  must use transparent backgrounds; never place an opaque white box around an
  arrow to mask a line.
- Keep display phrases intended as one line inside their painted panel. Shorten
  the phrase or reduce decorative padding before allowing a highlighted suffix
  to wrap below the panel.
- Every absolutely positioned overlay (ordinal numeral, badge, corner label,
  annotation) must sit inside the box it belongs to: give that box
  position:relative, and keep the overlay's offsets positive so it cannot land
  on a neighbouring card. A card's own number printed over the card above it
  reads as mislabelled content.
- A box with its own background or border must fit its copy. Shorten the copy or
  grow the box rather than letting a line spill past a painted edge.
- Any internal grid/flex lane containing prose must resolve to at least 180px.
  Never reserve an icon/number column unless that child is actually emitted;
  otherwise make the copy span the full row. For 4+ process steps in a narrow
  region, use full-width stacked rows or a horizontal sequence with readable
  labels—never auto-place all copy into the marker column.

CONTENT AND EXPORT CONTRACT
- Preserve the supplied title, lede, claims, labels, and byline faithfully.
- TITLE composition is a true cover. Show only title, optional eyebrow,
  authors/byline, affiliation, and essential metadata provided for those
  fields. Never show lede, core_message, summary, abstract, claims, bullets,
  or explanatory prose on a TITLE composition—even if present in slide data.
- Never display evidence IDs, planner codes, or production instructions.
- Never invent table values, chart values, formulas, people, or institutions.
- For bound figure/table/chart/formula regions, emit one EMPTY semantic host
  using the supplied data-pptx and ID attributes. The pipeline fills it.
- The host is the ONLY renderer of its bound content. Never also draw that
  formula, table, chart or figure yourself next to it, and never hide the host
  (no opacity below 1, visibility:hidden, display:none, clip, or zero size) to
  make room for your own copy of it. A hidden host still paints faintly in the
  browser while being dropped from the export, so the slide ends up showing a
  ghost of the content twice and the deck exports without it.
- Place each semantic host *inside its matching region root only*: a figure or
  image host belongs in scene-figure, a table host in scene-table, a chart host
  in scene-chart, and a formula host in scene-formula. Never nest a host in a
  title, lede, primary, secondary, or another semantic region.
- Never draw a quantitative figure by hand. Rotated rules, tilted bars, hand-set
  axes and stacked divs standing in for a plot answer to no data: the slope is
  whatever the angle happened to be, and the lines run outside their own axes.
  A trend, a comparison or a distribution goes in a chart host, which is exported
  as a real, editable chart. If no chart region was bound to this slide, state
  the numbers as text instead of drawing them.
- Never print TeX delimiters or commands as visible text. Outside the formula
  host, write symbols as readable Unicode/plain labels (C(R), C₀, β, γ).
- No SVG, canvas, script, iframe, external CSS, event handlers, or page numbers.
- Use a single <style> element. The .slide root must be exactly 1280x720.
"""


class SceneAuthorContractError(ValueError):
    """An authored candidate exists but still violates the Scene contract.

    Keeping the candidate on the exception is important: callers can repair the
    failing regions without throwing away the visual composition that the LLM
    successfully authored.
    """

    def __init__(self, issues: list[str], html: str = "") -> None:
        self.issues = [str(item) for item in issues]
        self.html = str(html or "")
        super().__init__("Scene author contract failed: " + "; ".join(self.issues[:20]))


def _content_payload(slide: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "slide", "total_slides", "role", "page_role", "title", "lede",
        "subtitle", "core_message", "eyebrow", "section", "authors",
        "affiliations", "bullets", "cards", "steps", "content",
        "content_blocks", "formula_terms", "formula_gloss", "visualization",
        "visual_job", "layout_intent", "page_rhythm", "structure_atom",
        "audience_move", "figure_id", "table_id", "formula", "formula_tex",
    )
    payload = {key: slide[key] for key in keep if key in slide and slide[key] not in (None, "", [], {})}
    # Defense in depth: the visual author and deterministic fallback must see
    # the same audience-safe copy even when a resumed/legacy plan predates the
    # grounded-planner scrub pass.
    try:
        from tasks.grounded_planner import scrub_content_provenance
    except ImportError:  # pragma: no cover
        from grounded_planner import scrub_content_provenance  # type: ignore
    payload = scrub_content_provenance(payload)
    role = str(slide.get("role") or slide.get("page_role") or "").strip().casefold()
    composition = str(slide.get("scene_composition") or "").strip().casefold()
    if role in {"title", "hero"} or composition == "title":
        # Do not tempt the visual author with outline prose that is forbidden on
        # a cover. Keep only cover furniture and visual-direction metadata.
        allowed = {
            "slide", "total_slides", "role", "page_role", "title", "eyebrow",
            "section", "authors", "affiliations", "visualization", "visual_job",
            "layout_intent", "page_rhythm", "structure_atom", "audience_move",
        }
        payload = {key: value for key, value in payload.items() if key in allowed}
    return payload


#: BCP 47 code → the endonym to name in the contract, so the instruction reads
#: in the language it is asking for.
_LANGUAGE_NAMES = {
    "tr": "Türkçe (Turkish)",
    "en": "English",
    "de": "Deutsch (German)",
    "fr": "français (French)",
    "es": "español (Spanish)",
    "it": "italiano (Italian)",
    "pt": "português (Portuguese)",
    "nl": "Nederlands (Dutch)",
    "pl": "polski (Polish)",
    "ru": "русский (Russian)",
    "ar": "العربية (Arabic)",
    "zh": "中文 (Chinese)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
}


def language_contract_block(primary_language: str) -> str:
    """The deck language, stated for the copy this author writes itself.

    The slide payload carries translated titles and body copy, but an eyebrow,
    a section kicker, a figure caption or an axis label is invented here — and
    with no language named, they came out English over Turkish body copy
    ("ACADEMIC BLUEPRINT · VEHICLE ROUTING"). A deck in two languages reads as
    broken however good each half is.
    """
    code = str(primary_language or "").strip()
    if not code:
        return (
            "## Language\n"
            "- Write every string you author yourself in the same language as the "
            "slide content above. Never mix two languages in one deck."
        )
    name = _LANGUAGE_NAMES.get(code.split("-")[0].casefold(), code)
    return (
        "## Language (HARD)\n"
        f"- The deck language is {name} (`{code}`). Every viewer-visible string "
        "you author yourself — eyebrows, kickers, section labels, captions, axis "
        f"and legend labels, table headers, units, connective words — MUST be in {name}.\n"
        "- Reproduce the slide content above exactly as given. Do not translate "
        "it, and do not translate it back: a cover may quote the source's own "
        "title, authors and affiliation in the language they were published in, "
        "which is deliberate — a translated title cites nothing.\n"
        "- Established technical symbols, product and algorithm names, citation "
        "identifiers and code stay as written.\n"
        f"- Never emit English filler such as \"OVERVIEW\", \"KEY POINTS\" or "
        f"\"FIG 01\" when the deck language is not English; write them in {name}."
    )


def build_scene_author_prompt(
    *,
    slide: dict[str, Any],
    scene: dict[str, Any],
    design_spec_md: str,
    design_reference_brief: str,
    palette: dict[str, Any] | None,
    prior_diary: str = "",
    feedback: str = "",
    previous_html: str = "",
    primary_language: str = "",
) -> str:
    regions = [r for r in scene.get("regions") or [] if r.get("role") != "footer"]
    hosts: list[str] = []
    for region in regions:
        rid = str(region.get("id") or "")
        role = str(region.get("role") or "")
        if role in {"figure", "table", "chart", "formula"}:
            host_id = (
                str(slide.get("figure_id") or "f1") if role == "figure"
                else str(slide.get("table_id") or "t1") if role == "table"
                else "c" + (rid.split("_")[-1] if rid.startswith("chart_") else "1") if role == "chart"
                else "f1"
            )
            hosts.append(f"- {rid}: data-pptx=\"{role}\" data-{role}-id=\"{host_id}\"")
    compact_spec = design_spec_md[:14000]
    parts = [
        "## Slide content (authoritative)\n" + json.dumps(_content_payload(slide), ensure_ascii=False, indent=2),
        language_contract_block(primary_language),
        "## Immutable layout\n" + format_scene_layout_block({**scene, "regions": regions}),
        "## Required semantic hosts\n" + ("\n".join(hosts) if hosts else "- none"),
        "## Deck design specification\n" + compact_spec,
        "## Palette tokens\n" + json.dumps(palette or {}, ensure_ascii=False, indent=2),
    ]
    if design_reference_brief.strip():
        parts.append("## Design reference brief\n" + design_reference_brief[:5000])
    if prior_diary.strip():
        parts.append("## Prior slide silhouettes to avoid repeating\n" + prior_diary[-2400:])
    if feedback.strip():
        parts.append("## Required revision feedback\n" + feedback[:4000])
    if previous_html.strip():
        parts.append(
            "## Previous HTML to revise\nPreserve its successful art direction, but correct every issue above.\n"
            + previous_html[:30000]
        )
    parts.append("Return the finished HTML document only.")
    return "\n\n".join(parts)


class _SceneDomInspector(HTMLParser):
    """Small, dependency-free structural inspector for authored slide DOM."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.region_nodes: list[dict[str, Any]] = []
        self.host_nodes: list[dict[str, Any]] = []

    @staticmethod
    def _attrs(raw: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).lower(): str(value or "") for key, value in raw}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag.lower(), "attrs": self._attrs(attrs), "parent": self.stack[-1] if self.stack else None}
        self.stack.append(node)
        if node["attrs"].get("data-layout-id", "").startswith("scene-"):
            self.region_nodes.append(node)
        if node["attrs"].get("data-pptx"):
            self.host_nodes.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == wanted:
                del self.stack[index:]
                return


def _class_tokens(node: dict[str, Any] | None) -> set[str]:
    if not node:
        return set()
    return set(str(node.get("attrs", {}).get("class") or "").split())


def _nearest_scene_role(node: dict[str, Any]) -> str:
    current: dict[str, Any] | None = node
    while current:
        role = str(current.get("attrs", {}).get("data-layout-role") or "").strip().casefold()
        if role:
            return role
        current = current.get("parent")
    return ""


_VISIBLE_TEX_RE = re.compile(r"\\(?:\(|\[|beta\b|gamma\b|frac\b|mathrm\b|text\b)", re.I)


def _plain_visible_math(value: str) -> str:
    """Turn accidental visible TeX prose into presentation-safe Unicode."""
    text = str(value or "").replace("`", "")
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1⁄\2", text)
    text = re.sub(r"\\(?:mathrm|text)\{([^{}]*)\}", r"\1", text)
    text = text.replace(r"\beta", "β").replace(r"\gamma", "γ")
    return text.replace(r"\(", "").replace(r"\)", "").replace(r"\[", "").replace(r"\]", "")


def normalize_scene_authored_html(html: str, scene: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Enforce solver-owned roots and sanitize accidental visible TeX.

    This never redesigns the authored composition. It only restores immutable
    Scene geometry and converts prose that would otherwise display raw TeX.
    """
    if not html or not isinstance(scene, dict):
        return html, {"changed": False}
    try:
        from lxml import html as lxml_html

        document = lxml_html.document_fromstring(html)
    except (ImportError, TypeError, ValueError):
        return html, {"changed": False, "error": "html_unreadable"}
    changed = False
    roots_fixed = 0
    decorations_marked = 0
    for region in scene.get("regions") or []:
        if region.get("role") == "footer":
            continue
        identifier = f"scene-{str(region.get('id') or '')}"
        nodes = document.xpath('//*[@data-layout-id=$identifier]', identifier=identifier)
        if not nodes:
            continue
        node = nodes[0]
        style = str(node.attrib.get("style") or "")
        for prop in ("position", "left", "top", "width", "height"):
            style = re.sub(rf"(?:^|;)\s*{prop}\s*:[^;]*", "", style, flags=re.I)
        owned = (
            f"position:absolute;left:{float(region['x']):g}px;top:{float(region['y']):g}px;"
            f"width:{float(region['w']):g}px;height:{float(region['h']):g}px;"
        )
        normalized = owned + style.strip(" ;")
        if normalized != str(node.attrib.get("style") or ""):
            node.attrib["style"] = normalized
            changed = True
            roots_fixed += 1
    tex_nodes = 0
    exportable_decorations_restored = 0
    for node in document.iter():
        if str(getattr(node, "tag", "")).casefold() in {"style", "script"}:
            continue
        for field in ("text", "tail"):
            value = getattr(node, field, None)
            if value and (_VISIBLE_TEX_RE.search(value) or "`" in value):
                plain = _plain_visible_math(value)
                if plain != value:
                    setattr(node, field, plain)
                    changed = True
                    tex_nodes += 1
        if "data-formula-symbol" in node.attrib:
            plain = _plain_visible_math(node.attrib["data-formula-symbol"])
            if plain != node.attrib["data-formula-symbol"]:
                node.attrib["data-formula-symbol"] = plain
                changed = True
        class_tokens = set(str(node.attrib.get("class") or "").casefold().split())
        # aria-hidden is an accessibility semantic, not an export semantic.
        # Older authoring prompts told the model to mark visible artwork as
        # data-pptx-kind="ignore", which made the browser and PPTX diverge by
        # deleting rules, arrows, nodes, grids, watermarks, and background
        # furniture during compilation.  Only pipeline-owned preview/runtime
        # duplicates may remain ignored.  This migration deliberately runs
        # again immediately before every compile, so already-authored projects
        # are repaired as well as newly generated slides.
        if (
            node.attrib.get("data-pptx-kind") == "ignore"
            and node.attrib.get("aria-hidden") == "true"
            and node.attrib.get("data-sunairum-preview-only") != "1"
            and node.attrib.get("data-sunairum-chart-preview") != "1"
            and node.attrib.get("data-sunairum-runtime-ui") != "1"
        ):
            node.attrib["data-pptx-kind"] = "decoration"
            changed = True
            exportable_decorations_restored += 1
        if class_tokens & {
            "decorative", "decoration", "ornament", "watermark",
            "question-mark", "background-mark", "background-glyph",
        }:
            if node.attrib.get("aria-hidden") != "true":
                node.attrib["aria-hidden"] = "true"
                changed = True
            if node.attrib.get("data-pptx-kind") != "decoration":
                node.attrib["data-pptx-kind"] = "decoration"
                changed = True
            decorations_marked += 1
    if not changed:
        return html, {"changed": False, "roots_fixed": 0, "tex_nodes": 0, "decorations_marked": 0, "exportable_decorations_restored": 0}
    rendered = lxml_html.tostring(document, encoding="unicode", method="html", doctype="<!doctype html>")
    return rendered, {
        "changed": True,
        "roots_fixed": roots_fixed,
        "tex_nodes": tex_nodes,
        "decorations_marked": decorations_marked,
        "exportable_decorations_restored": exportable_decorations_restored,
    }


def _validate_scene_dom_structure(html: str, scene: dict[str, Any]) -> list[str]:
    """Validate tree ownership, not merely regex-visible attributes.

    Asset injectors select ``data-pptx`` hosts after authoring.  A host nested
    in a title/lede region can otherwise be filled with a large absolute figure
    and silently cover the slide.  Geometry validation cannot see that error.
    """
    inspector = _SceneDomInspector()
    try:
        inspector.feed(html)
        inspector.close()
    except Exception as exc:  # pragma: no cover - HTMLParser is forgiving
        return [f"scene_dom_unreadable:{exc}"]

    expected_regions = {
        f"scene-{str(region.get('id') or '')}": str(region.get("role") or "").casefold()
        for region in scene.get("regions") or []
        if region.get("role") != "footer"
    }
    expected_host_counts: dict[str, int] = {}
    for role in expected_regions.values():
        if role in {"figure", "table", "chart", "formula"}:
            expected_host_counts[role] = expected_host_counts.get(role, 0) + 1
    issues: list[str] = []
    seen_regions: set[str] = set()
    for node in inspector.region_nodes:
        attrs = node["attrs"]
        identifier = str(attrs.get("data-layout-id") or "")
        role = str(attrs.get("data-layout-role") or "").casefold()
        if identifier not in expected_regions:
            issues.append(f"unexpected_region:{identifier}")
            continue
        if identifier in seen_regions:
            issues.append(f"duplicate_region:{identifier}")
        seen_regions.add(identifier)
        parent = node.get("parent")
        if "slide" not in _class_tokens(parent):
            issues.append(f"region_not_direct_slide_child:{identifier}")
        if role != expected_regions[identifier]:
            issues.append(f"wrong_region_owner:{identifier}:{role or 'none'}")

    host_role_map = {"image": "figure", "figure": "figure", "table": "table", "chart": "chart", "formula": "formula"}
    allowed_host_roles = set(expected_host_counts)
    host_counts: dict[str, int] = {}
    for node in inspector.host_nodes:
        attrs = node["attrs"]
        host_kind = str(attrs.get("data-pptx") or "").casefold()
        expected_owner = host_role_map.get(host_kind, host_kind)
        owner = _nearest_scene_role(node)
        if expected_owner not in allowed_host_roles:
            issues.append(f"unexpected_host:{host_kind}")
        if owner != expected_owner:
            issues.append(f"host_wrong_region:{host_kind}:{owner or 'none'}")
        host_counts[expected_owner] = host_counts.get(expected_owner, 0) + 1
    # Host cardinality follows Scene cardinality. Multi-chart compositions own
    # several independent chart regions, so treating chart:3 as a duplicate
    # blocks payload injection and produces three polished-but-empty panels.
    for role, expected_count in expected_host_counts.items():
        actual_count = host_counts.get(role, 0)
        if actual_count < expected_count:
            issues.append(f"missing_host:{role}:{actual_count}/{expected_count}")
        elif actual_count > expected_count:
            issues.append(f"duplicate_host:{role}:{actual_count}/{expected_count}")
    return issues


def validate_scene_authored_html(html: str, scene: dict[str, Any]) -> list[str]:
    """Check that creative HTML respects the immutable top-level scene boxes."""
    issues = [f"constitution:{item.code}" for item in validate_slide_html(html).errors()]
    visible_source = re.sub(r"<(?:style|script)\b[^>]*>.*?</(?:style|script)>", "", html, flags=re.I | re.S)
    visible_source = re.sub(r"<[^>]+>", "", visible_source)
    if _VISIBLE_TEX_RE.search(visible_source):
        issues.append("visible_tex_syntax")
    issues.extend(_validate_scene_dom_structure(html, scene))
    for region in scene.get("regions") or []:
        if region.get("role") == "footer":
            continue
        rid = str(region.get("id") or "")
        expected_id = f"scene-{rid}"
        match = re.search(
            rf'<(?P<tag>div|section|article|header|aside)\b(?P<attrs>[^>]*\bdata-layout-id=["\']{re.escape(expected_id)}["\'][^>]*)>',
            html,
            flags=re.I,
        )
        if not match:
            issues.append(f"missing_region:{expected_id}")
            continue
        attrs = match.group("attrs")
        role = str(region.get("role") or "")
        if not re.search(rf'\bdata-layout-role=["\']{re.escape(role)}["\']', attrs, flags=re.I):
            issues.append(f"wrong_role:{expected_id}")
        style_m = re.search(r'\bstyle=["\']([^"\']*)["\']', attrs, flags=re.I)
        style = style_m.group(1) if style_m else ""
        for prop, key in (("left", "x"), ("top", "y"), ("width", "w"), ("height", "h")):
            value = float(region[key])
            prop_m = re.search(rf'(?:^|;)\s*{prop}\s*:\s*(-?\d+(?:\.\d+)?)px\s*(?:;|$)', style, flags=re.I)
            if not prop_m or abs(float(prop_m.group(1)) - value) > 0.1:
                issues.append(f"geometry:{expected_id}:{prop}={value:g}px")
        if not re.search(r'(?:^|;)\s*position\s*:\s*absolute\s*(?:;|$)', style, flags=re.I):
            issues.append(f"position:{expected_id}")
    return issues


def off_language_authored_copy(
    html: str,
    primary_language: str,
    quoted: Iterable[str] = (),
) -> list[str]:
    """Author-written copy that is not in the deck language.

    The language contract in the prompt is an instruction; this is the check
    that makes it hold. Without it a Turkish deck shipped a cover reading
    "ACADEMIC BLUEPRINT · VEHICLE ROUTING" over Turkish body copy — detected
    afterwards by the settings-obedience report, long past the point where
    anything could be done about it. Returned as a contract issue, it becomes
    retry feedback naming the offending string while the author is still up.

    Quoted identity is exempt: the paper's own title, its authors and their
    affiliation are cited, not written, so they carry the source's language.
    """
    from tasks.settings_obedience_artifacts import off_language_fragments

    return [
        "off_language_copy: write this in {expected!r}, not {detected!r} — {sample!r}".format(
            expected=item["expected"],
            detected=item["detected"],
            sample=str(item["sample"])[:80],
        )
        for item in off_language_fragments(html, primary_language, quoted=quoted)
    ]


def author_scene_html(
    *,
    slide: dict[str, Any],
    scene: dict[str, Any],
    design_spec_md: str,
    design_reference_brief: str,
    palette: dict[str, Any] | None,
    call_text: Callable[[str, str], str],
    prior_diary: str = "",
    feedback: str = "",
    previous_html: str = "",
    scaffold_html: str = "",
    max_attempts: int = 2,
    on_attempt: Callable[[], None] | None = None,
    primary_language: str = "",
) -> str:
    attempts = max(1, int(max_attempts or 1))
    candidate = str(previous_html or "")
    last_issues: list[str] = []
    for attempt in range(attempts):
        repair_feedback = feedback
        if attempt and last_issues:
            repair_feedback = (
                (feedback.strip() + "\n\n" if feedback.strip() else "")
                + "CONTRACT-ONLY REVISION: preserve the successful art direction and "
                "composition. Correct only these measured/structural issues: "
                + "; ".join(last_issues[:20])
            )
        prompt = build_scene_author_prompt(
            slide=slide,
            scene=scene,
            primary_language=primary_language,
            design_spec_md=design_spec_md,
            design_reference_brief=design_reference_brief,
            palette=palette,
            prior_diary=prior_diary,
            feedback=repair_feedback,
            previous_html=candidate or (scaffold_html if attempt else ""),
        )
        try:
            if on_attempt is not None:
                on_attempt()
            raw = call_text(SCENE_AUTHOR_SYSTEM, prompt)
            doc = extract_html_document(raw)
        except Exception as exc:  # noqa: BLE001
            last_issues = [f"author_call_failed:{str(exc).strip() or type(exc).__name__}"]
            # A measured scaffold is prompt context for the retry, never the
            # final replacement for a successfully authored slide.
            candidate = candidate or str(scaffold_html or "")
            continue
        if doc:
            candidate = doc
        if not candidate:
            last_issues = ["empty_html_document"]
            continue
        # Scene owns root geometry. Canonicalize solver-owned properties before
        # validation while leaving the authored internal composition untouched.
        candidate, _normalization = normalize_scene_authored_html(candidate, scene)
        last_issues = validate_scene_authored_html(candidate, scene)
        if not last_issues:
            # The deck language is a contract like the geometry, so a violation
            # is caught here — while a retry can still fix it — rather than in
            # a report the reader sees after the deck ships.
            last_issues = off_language_authored_copy(
                candidate,
                primary_language,
                quoted=[
                    str(slide.get(key) or "")
                    for key in ("title", "subtitle", "authors", "affiliations")
                ],
            )
        if not last_issues:
            return candidate
    raise SceneAuthorContractError(last_issues or ["authoring_failed"], candidate)
