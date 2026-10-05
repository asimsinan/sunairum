"""Constrained Slide HTML allow/deny validator (zero-SVG generation)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

CANVAS_W = 1280
CANVAS_H = 720
# Print raster for preview/slide_*.png and download PDF (CSS canvas stays 1280×720).
PREVIEW_DPI = 300
PREVIEW_DEVICE_SCALE = PREVIEW_DPI / 96.0  # 3.125 → 4000×2250

FORBIDDEN_TAGS = frozenset(
    {
        "svg",
        "foreignobject",
        "script",
        "iframe",
        "object",
        "embed",
        "canvas",
        "video",
        "audio",
        # MathML is the inert, editable formula representation emitted by the
        # trusted formula materializer and consumed by DeckHTML as OMML.
    }
)

FORBIDDEN_ATTR_PREFIXES = ("on",)  # onclick, etc.
FORBIDDEN_STYLE_TOKENS = (
    "filter:",
    "mask",
    "clip-path",
    "background-clip",
    "-webkit-background-clip",
    "backdrop-filter",
    "mix-blend-mode",
    "conic-gradient",
)

REQUIRED_HOST_ATTRS = {
    "table": ("data-pptx", "data-table-id"),
    "chart": ("data-pptx", "data-chart-id"),
    "formula": ("data-pptx",),
}


@dataclass
class ConstitutionIssue:
    level: str  # error | warning
    code: str
    message: str


@dataclass
class ConstitutionReport:
    ok: bool
    issues: list[ConstitutionIssue] = field(default_factory=list)

    def errors(self) -> list[ConstitutionIssue]:
        return [i for i in self.issues if i.level == "error"]


class _ScanParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, dict[str, str]]] = []
        self.has_root_section = False
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.casefold()
        self.tags.append(t)
        ad = {k.casefold(): (v or "") for k, v in attrs}
        self.attrs.append((t, ad))
        if t == "section" and "slide" in (ad.get("class") or "").casefold():
            self.has_root_section = True
        if t == "div" and ad.get("data-pptx"):
            self.has_root_section = self.has_root_section or True

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self.texts.append(data.strip())


def extract_html_document(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:html|HTML)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
    match = re.search(r"(<!DOCTYPE html>[\s\S]*</html>|<html\b[\s\S]*</html>)", raw, re.I)
    if match:
        return match.group(1).strip()
    # Accept a single .slide section
    sec = re.search(r"(<section\b[^>]*class=[\"'][^\"']*slide[^\"']*[\"'][^>]*>[\s\S]*?</section>)", raw, re.I)
    if sec:
        return (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>"
            f"<style>{_BASE_CSS}</style></head><body>{sec.group(1)}</body></html>"
        )
    return raw


_BASE_CSS = f"""
html,body{{margin:0;padding:0;background:#111;}}
.slide{{width:{CANVAS_W}px;height:{CANVAS_H}px;position:relative;overflow:hidden;
  box-sizing:border-box;font-family:Georgia,serif;}}
.slide *{{box-sizing:border-box;}}
[data-pptx]:empty{{outline:1px dashed rgba(0,0,0,.15);}}
"""


def wrap_slide_fragment(body_inner: str, *, background: str = "#FFFFFF") -> str:
    inner = (body_inner or "").strip()
    if not re.search(r'class=["\'][^"\']*\bslide\b', inner, re.I):
        inner = (
            f'<section class="slide" style="background:{background};'
            f'width:{CANVAS_W}px;height:{CANVAS_H}px;">{inner}</section>'
        )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>"
        f"<style>{_BASE_CSS}</style></head><body>{inner}</body></html>"
    )


def _has_slide_class(markup: str) -> bool:
    return bool(re.search(r'class=["\'][^"\']*\bslide\b', markup or "", re.I))


def sanitize_html_control_chars(html: str) -> str:
    """Map C0 controls (esp. vertical tab) to spaces so words are not glued.

    LLMs emit ``\\x0b`` as a soft break; browsers treat it as whitespace (awkward
    wraps) while PPT XML sanitizers that *delete* it produce ``Inserthere``.
    """
    if not html:
        return html
    # Keep \t \n \r; replace other C0 + DEL with space.
    out = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", html)
    # Collapse runs of spaces/nbsp inside text (not across tags).
    def _collapse(match: re.Match[str]) -> str:
        return re.sub(r"[ \t\u00a0]{2,}", " ", match.group(0))

    return re.sub(r">[^<]+<", _collapse, out)


def ensure_slide_root(html: str, *, background: str = "#FFFFFF") -> str:
    """Guarantee a ``.slide`` root so Playwright measure/preview can locate the plate.

    Executors often emit a full ``<html>`` with a bare ``<section style=…>`` and no
    ``class="slide"``. ``wrap_slide_fragment`` is skipped for full documents, which
    previously left preview waiting on ``.slide`` until timeout.
    """
    doc = sanitize_html_control_chars(extract_html_document(html))
    if "<html" not in doc.casefold():
        return wrap_slide_fragment(doc, background=background)
    if _has_slide_class(doc):
        return doc

    def _inject_section_class(match: re.Match[str]) -> str:
        open_tag = match.group(0)
        if re.search(r"\bclass=", open_tag, re.I):
            def _add(m: re.Match[str]) -> str:
                quote, existing = m.group(1), m.group(2)
                if re.search(r"(?i)\bslide\b", existing):
                    return m.group(0)
                merged = f"slide {existing}".strip()
                return f"class={quote}{merged}{quote}"

            return re.sub(
                r'\bclass=(["\'])([^"\']*)\1',
                _add,
                open_tag,
                count=1,
                flags=re.I,
            )
        return re.sub(r"^<section\b", '<section class="slide"', open_tag, count=1, flags=re.I)

    if re.search(r"<section\b", doc, re.I):
        return re.sub(r"<section\b[^>]*>", _inject_section_class, doc, count=1, flags=re.I)

    body = re.search(r"(<body\b[^>]*>)([\s\S]*?)(</body\s*>)", doc, re.I)
    if body:
        inner = body.group(2).strip()
        wrapped = (
            f'<section class="slide" style="background:{background};'
            f'width:{CANVAS_W}px;height:{CANVAS_H}px;">{inner}</section>'
        )
        return doc[: body.start(2)] + wrapped + doc[body.end(2) :]
    return wrap_slide_fragment(doc, background=background)


def validate_slide_html(html: str) -> ConstitutionReport:
    issues: list[ConstitutionIssue] = []
    doc = extract_html_document(html)
    if not doc or "<" not in doc:
        return ConstitutionReport(
            ok=False,
            issues=[ConstitutionIssue("error", "empty", "No HTML document found")],
        )
    if re.search(r"<\s*svg\b", doc, re.I):
        issues.append(ConstitutionIssue("error", "svg_forbidden", "SVG elements are forbidden"))
    if re.search(r"foreignObject", doc, re.I):
        issues.append(
            ConstitutionIssue("error", "foreignObject", "foreignObject is forbidden")
        )
    parser = _ScanParser()
    try:
        parser.feed(doc)
    except Exception as exc:  # noqa: BLE001
        issues.append(ConstitutionIssue("error", "parse", f"HTML parse failed: {exc}"))
        return ConstitutionReport(ok=False, issues=issues)

    # <style> allowed only for the pipeline base canvas CSS in <head>.
    style_count = sum(1 for t in parser.tags if t == "style")
    if style_count > 1:
        issues.append(
            ConstitutionIssue(
                "error", "forbidden_tag", "Extra <style> tags forbidden (one base CSS only)"
            )
        )
    for tag in parser.tags:
        if tag in FORBIDDEN_TAGS:
            issues.append(
                ConstitutionIssue("error", "forbidden_tag", f"Forbidden tag <{tag}>")
            )

    for tag, ad in parser.attrs:
        for key, val in ad.items():
            if key.startswith(FORBIDDEN_ATTR_PREFIXES):
                issues.append(
                    ConstitutionIssue(
                        "error", "event_handler", f"Event handler attribute {key} forbidden"
                    )
                )
            if key == "style":
                low = val.casefold()
                for token in FORBIDDEN_STYLE_TOKENS:
                    if token in low:
                        issues.append(
                            ConstitutionIssue(
                                "error",
                                "forbidden_css",
                                f"Forbidden CSS token {token!r} on <{tag}>",
                            )
                        )
            if key == "src" and val and not (
                val.startswith("data:") or val.startswith("/") or val.startswith("./")
            ):
                if val.startswith("http://") or val.startswith("https://"):
                    issues.append(
                        ConstitutionIssue(
                            "warning",
                            "external_image",
                            "External image URLs should be inlined as data: URIs",
                        )
                    )
        pptx = (ad.get("data-pptx") or "").casefold()
        if pptx == "table" and not ad.get("data-table-id"):
            issues.append(
                ConstitutionIssue(
                    "error", "table_host", "data-pptx=table requires data-table-id"
                )
            )
        if pptx == "chart" and not (ad.get("data-chart-id") or ad.get("data-series")):
            issues.append(
                ConstitutionIssue(
                    "warning",
                    "chart_host",
                    "data-pptx=chart should set data-chart-id or data-series",
                )
            )
        # CSS-only bar charts disguised as nested height:% divs inside non-host
        if tag == "div" and "bar" in (ad.get("class") or "").casefold() and not pptx:
            issues.append(
                ConstitutionIssue(
                    "warning",
                    "css_chart_suspect",
                    "Possible CSS chart — use data-pptx=chart semantic host instead",
                )
            )
        style = ad.get("style") or ""
        if "data-sunairum-claim" in ad or tag in {"p", "h1", "h2"}:
            hm = re.search(r"(?:^|;)\s*height\s*:\s*([\d.]+)px", style, flags=re.I)
            fsm = re.search(r"font-size\s*:\s*([\d.]+)px", style, flags=re.I)
            lhm = re.search(r"line-height\s*:\s*([\d.]+)px", style, flags=re.I)
            if hm and fsm:
                h = float(hm.group(1))
                fs = float(fsm.group(1))
                lh = float(lhm.group(1)) if lhm else fs * 1.3
                if h + 0.5 < lh * 2 and "data-sunairum-claim" in ad:
                    issues.append(
                        ConstitutionIssue(
                            "error",
                            "tight_claim_box",
                            "Claim box fixed height cannot fit ≥2 text lines — "
                            "use min-height + padding, not a clipping height",
                        )
                    )
        # Tiny fixed-width chips (SCORE etc.)
        wm = re.search(r"(?:^|;)\s*width\s*:\s*([\d.]+)px", style, flags=re.I)
        fsm = re.search(r"font-size\s*:\s*([\d.]+)px", style, flags=re.I)
        if wm and fsm and float(wm.group(1)) <= 48 and float(fsm.group(1)) <= 12:
            if "letter-spacing" in style.casefold() or "SCORE" in (ad.get("data-sunairum-claim") or ""):
                issues.append(
                    ConstitutionIssue(
                        "warning",
                        "tight_chip",
                        "Narrow fixed-width chip — prefer min-width + horizontal padding",
                    )
                )

    if not re.search(r"\bslide\b", doc, re.I):
        issues.append(
            ConstitutionIssue(
                "warning", "missing_slide_class", "Expected a .slide root section"
            )
        )

    ok = not any(i.level == "error" for i in issues)
    return ConstitutionReport(ok=ok, issues=issues)


def relax_clipping_styles(html: str) -> str:
    """Rewrite fixed heights/widths that commonly clip text (product safety net).

    - Claim boxes: height:NNpx (≤140) → min-height + height:auto
    - Tiny ALLCAPS chips: narrow width + small font → min-width + horizontal padding
    """
    if not html:
        return html

    def _fix_claim_open(match: re.Match[str]) -> str:
        tag = match.group(0)

        def _height(hm: re.Match[str]) -> str:
            h = float(hm.group(1))
            if h <= 140:
                return f"min-height:{int(round(h))}px;height:auto"
            return hm.group(0)

        if re.search(r"height\s*:\s*[\d.]+px", tag, flags=re.I) and not re.search(
            r"min-height\s*:", tag, flags=re.I
        ):
            tag = re.sub(
                r"height\s*:\s*([\d.]+)px", _height, tag, count=1, flags=re.I
            )
        if "padding" not in tag.casefold():
            if 'style="' in tag:
                tag = re.sub(
                    r'style="',
                    'style="padding:4px 2px 0;',
                    tag,
                    count=1,
                    flags=re.I,
                )
        return tag

    out = re.sub(
        r"<div\b[^>]*\bdata-sunairum-claim\b[^>]*>",
        _fix_claim_open,
        html,
        flags=re.I,
    )

    def _fix_chip(match: re.Match[str]) -> str:
        tag, body, close = match.group(1), match.group(2), match.group(3)
        label = re.sub(r"\s+", "", body or "")
        if not (3 <= len(label) <= 12 and label.isupper()):
            return match.group(0)
        wm = re.search(r"width\s*:\s*([\d.]+)px", tag, flags=re.I)
        fsm = re.search(r"font-size\s*:\s*([\d.]+)px", tag, flags=re.I)
        if not wm or not fsm:
            return match.group(0)
        w, fs = float(wm.group(1)), float(fsm.group(1))
        if w > 56 or fs > 13:
            return match.group(0)
        need = int(max(56, math.ceil(fs * len(label) * 0.62 + 24)))
        tag = re.sub(
            r"width\s*:\s*[\d.]+px",
            f"min-width:{need}px;width:auto;padding:0 12px;box-sizing:border-box",
            tag,
            count=1,
            flags=re.I,
        )
        return f"{tag}{body}{close}"

    out = re.sub(
        r"(<div\b[^>]*style=\"[^\"]*\"[^>]*>)(\s*[A-Za-z0-9][A-Za-z0-9 _+-]{1,14}\s*)(</div>)",
        _fix_chip,
        out,
        flags=re.I,
    )
    return out


def constitution_prompt_block() -> str:
    """Inject into Executor / Strategist prompts under zero-SVG."""
    return f"""## Constrained Slide HTML (HARD)
- Return ONE complete HTML document (or a single <section class="slide">…).
- Canvas exactly {CANVAS_W}×{CANVAS_H}px. Use flex/grid + gap for layout.
- SAFE INSET (HARD): all text, cards, diagrams, tables, footers stay ≥60px from
  every canvas edge (top/right/bottom/left). Never place content at top:0 / left:0
  / flush to the 720 bottom cut. Full-bleed background plates may fill 0,0→1280×720;
  everything else must breathe inside the 60px safe rect. Pipeline will scale-fit
  violations, but authors must target the inset so type stays readable.
- FORBIDDEN: <svg>, <foreignObject>, <script>, <style> tags, class-based frameworks that need external CSS files, filters/masks/clip-path/background-clip, CSS-only charts.
- Allowed: inline style=, solid/linear-gradient fills, border-radius, text, images as data: URIs, flex/grid.
- Tables/charts/formulas/figures: EMPTY semantic hosts only (pipeline fills media):
  <div data-pptx="table" data-table-id="t1" style="…"></div>
  <div data-pptx="chart" data-chart-id="c1" style="…"></div>
  Chart hosts: reserve a bottom band inside the card; body copy must end ≥12px
  above the chart top (never absolute-overlap text + chart in the same AABB).
  Do not plot Cost (~1e5) and CV (~1) as one shared-axis series — use separate
  series / dual-axis-friendly payload categories so both metrics stay visible.
  <div data-pptx="formula" data-formula-id="f1" style="…;height:96px;"></div>
  (formula hosts stay compact ~72–120px tall — never half-slide empty bands)
  <div data-pptx="figure" data-figure-id="pdf-page-…" style="…;border-radius:16px;"></div>
  (pipeline wraps filled figures in a white rounded panel with soft border/shadow)
- Do not invent table cells, chart bars, or redraw PDF figures — hosts stay empty.
- Claims: use data-sunairum-claim containers; no overlapping absolute content stacks.
- Text breathing room: claim/body boxes need ≥16px padding from card edges; avoid
  fixed height that clips wrapped lines — prefer min-height + height:auto. Never
  absolute-position body lines inside a short fixed card. Badges/pills need ≥8px
  horizontal padding (never squeeze labels like SCORE into a too-narrow chip).
- Diagram node labels (e.g. "Insert here", "Stop"): white-space:nowrap is OK only
  for short chips (≤18 chars / ≤2 words). Never put white-space:nowrap on labels
  inside a multi-stage horizontal process strip in a narrow card (<520px) — stack
  the stages vertically (flex-direction:column) or allow wrap. Claim columns with
  an explicit width must use min-width:0 so flex min-content cannot blow the lane.
  Never emit vertical-tab/control characters between words — use a normal space.
- Split-table / table+claims pages: LEFT lane claims only (left≈60, width≤500,
  content ends ≤560). Table host RIGHT lane only (left≥640, width≤580, gap≥28).
  NEVER place a table host over claim cards.
- Split-figure / figure+claims pages: same dual-lane law — LEFT claims end ≤560;
  figure/image host RIGHT only (left≥640, width≤560, gap≥28 + shadow clearance).
  Left panel must fit the remaining lane (margin → figure_left−gap). NEVER place
  a figure host over claim cards or leave claims wider than the open left lane.
  Title/lede on these pages must also end ≤560 (never full-bleed under the figure).
  Stack left cards so the last one clears the bottom inset.
- Formula-hero pages: compact formula host band (~72–120px; up to ~148px when the
  MathML has ∑ limits / fractions) full width under title;
  title header uses min-height / auto height (never fixed ~132px that clips a subtitle
  behind the formula plate or a gloss/callout card); fill remaining canvas with per-symbol term cards
  (symbol + short explanation from FORMULA_TERMS/GLOSS). Empty right half when terms
  are available is a constitution violation — prefer right column or 2×N grid under
  the band. FORMULA_TERMS dialect: ``R=set of routes; c(R_j)=distance of route j``
  — never ``\\(R=\\) set of routes`` (breaks symbol/explanation split).
- Title/lede vs callouts: never let wrapped subtitle/lede paint under an opaque
  left-accent callout (ENCODE/gloss). Keep ≥14px gap or grow the title stack.
- Lede/subtitle copy: one flowing paragraph — never manual <br> that orphans the
  last words (…in<br>total<br>cost.). On single-column pages use width ≥900px
  (left≈60 → right≤1220); on split-figure pages fill the left lane only.
"""


def report_to_dict(report: ConstitutionReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "issues": [
            {"level": i.level, "code": i.code, "message": i.message} for i in report.issues
        ],
    }
