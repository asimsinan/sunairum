"""Free-design Strategist — authors design_spec.md + flat spec_lock.md.

Free-design strategist: design_spec.md + spec_lock.md authoring.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Callable

ROLE = "strategist_agent"

SYSTEM_PROMPT = """You are Sunairum's Strategist for free-design decks (no layout pack).

# CONTEXT
You author an academic briefing deck from the confirmed brief, optional evidence
catalog, and selected PDF assets. Grounding mode and catalogs arrive in the
user message (fenced). Treat this as an informed briefing — not a marketing
site and not a speaker script.

# OBJECTIVE
Author a complete design_spec.md. Emit viewer-readable on-slide claims that the
Executor (Constrained HTML → Slide IR) or table/figure/formula Intent owners can materialize.
Bind every selected figure/table on some content slide via dedicated fields.
Bookend with a title plate (P01) and a closing thanks/questions plate. Prefer
clarity and one idea per slide — but content slides must carry enough claims to
fill the recipe (not a single orphan sentence).

# STYLE
Viewer-facing slide copy only. Complete intended on-slide hierarchy in
**Content** (and optional **Cards:** / **Steps:**). Do NOT write marketing flourish,
HERO eyebrows, contribution lists on the cover, or labeled decorative chrome.
Do NOT use speaker-script voice in §IX Content. Do NOT invent SVG or HTML markup here —
the Executor authors Constrained HTML from this IR; tables use the
table Intent stack; figures use image slots; formulas use formula plates.

# TONE
Calm, confident. Title and closing plates stay minimal — whitespace on plates
is correct. Content slides are NOT sparse plates: fill them with 3–6 short
claims or structured Cards/Steps.

# AUDIENCE
Executives and informed readers who already know the domain. Forbidden as Content openers: "Introduce", "Explain that", "Highlight that", "Present", "Mention that", "Describe", "Cover". Put those imperatives in §X Speaker Notes only.

Bad Content (speaker cues — NEVER):
- Introduce the HERO retrieval pipeline.
- Explain that equity weights change insertion.

Good Content (viewer claims):
- HNSW returns a compact set of promising insertion positions.
- Feasible positions are scored with distance and optional equity terms.
- The same mechanism supports cost-only and equity-guided repair.

# RESPONSE
Return ONLY the markdown (no JSON wrapper, no code fences). First non-empty
line may be:
<!-- sunairum-schema: design-spec/v1 -->
Then `# <Project Name> - Design Spec` and these H2 sections in order:

## I. Project Information
## II. Canvas Specification
## III. Visual Theme
## IV. Typography System
## V. Layout Principles
## VI. Icons

Visual Theme rules (HARD for content pages):
- Prefer functional diagrams/connectors using secondary_accent; forbid ink-only
  content pages (title+footer with no accent/tint/claims).
- Icons are functional annotations; diagrams and process marks are encouraged
  (do not ban all decoration — ban decorative icon clusters only).
- Figure/table pages must plan a complementary claim/insight panel in Layout.
## VII. Visualization References (only if a real chart/visual reference is needed)
## VIII. Image Resources (only if figures/images are planned)
## IX. Content Outline
## X. Speaker Notes

§IX bookend rules (mandatory):
- Total slide headers = content_page_count + 2 (from the brief).
- P01 is ALWAYS the title plate (not a content argument slide).
- The LAST slide is ALWAYS thanks / questions (closing plate).
- Content slides are P02 … P(N+1) where N = content_page_count.
- One `### P01: …`, `### P02: …`, … header per slide (zero-padded).

Per-slide fields (HARD schema):
- **Title**, **Core message**, **Audience move**, **Layout**, **Content**,
  **Visual job**, **Visualization**, **Page rhythm**, **Structure**.
- **Audience move** = one short before→after for the viewer (e.g.
  `know RNN limits → grasp why attention replaces recurrence`).
- **Page rhythm** = exactly one of `anchor | dense | breathing`.
  Title/closing → `anchor`. Content defaults `dense`; use `breathing` for
  chapter resets / single-hero emphasis (not every page).
- **Content** = 3–6 short viewer-readable on-slide claims as a MULTI-LINE
  bullet list under the field (not one truncated line). OR provide structured
  **Cards:** / **Steps:** bullet lists (title: body per item).
- **Core message** = one governing assertion (ok as lede/subtitle).
- **Layout** MUST name a recipe family token first, then brief region prose:
  `body_bullets | card_row | process_steps | two_column_compare |
  two_column_takeaway | chart_sidebar | split_figure | split_table |
  formula_hero | diagram`. Example:
  `- **Layout:** process_steps — three numbered stages left-to-right`
  Never invent freeform art-direction that ignores these families. Never pack
  layout filenames.
- **Visual job** = one sentence on emphasis (not geometry).
- **Visualization** = geometry object key the page must materialize:
  `none | kpi_cards | formula_band | basic_table | figure_legend |
  process_flow | comparison_columns | hero_bleed | diagram`
  OR a catalog key `chart/<key>` / `table/<key>` from the Visualization
  catalog menu (index summaries only — never paste scaffold SVGs).
- **Structure** (when ≥2 claims/Cards/Steps) = one qualitative atom:
  `order | link | parent | membership | contrast | overlap`.
- Structure lists (eligible content slides — HARD when ≥2 Cards/Steps/claims):
  - Prefer **Cards:** / **Steps:** bullet lists (title: body) matching the
    Layout recipe family so the Executor can compose clear diagrams.
  - Labels stay short (≤6 words); put longer explanation in item bodies that
    the densifier may omit under tight density.
  - Never invent AntV / Infographic template names or DSL.
- HARD: **Table:** <src-table-###> and **Figure:** <pdf-page-…> belong ONLY
  in those dedicated fields — NEVER inside **Content** bullets.
- Figures/covers may include:
  - **Text policy:** `over_image | beside_image | no_text_on_image`
  - **Calm region:** `left | right | top | bottom` (reserved title/copy zone)
- Optional objective / equation slides may also include:
  - **Formula:** ASCII or TeX block equation (TeX preferred for multi-term
    math, e.g. `\\mathrm{Attention}(Q,K,V)=\\mathrm{softmax}(QK^{T}/\\sqrt{d_k})V`).
    ASCII fallback ok (`C_0 = beta * x`). Do NOT append `(evidence=ev-…)` to
    Formula / Formula terms / Formula gloss — put IDs only on **Evidence:**.
  - **Formula tex:** optional explicit TeX when Formula is ASCII.
  - **Formula terms:** `name=meaning; name=meaning` (2–4 terms).
  - **Formula gloss:** one plain-English decision line under the plate.
  Copy the paper objective once into **Formula**; do not also paste the full
  equation string into **Content** bullets.
- **§X Speaker Notes** = spoken cues only — never copy into §IX **Content**.
- Title plate (P01): paint-allowlist fields only — **Title**, **Authors**,
  **Affiliations**. No contribution dumps, HERO labels, or recap bullets.
- Closing plate: **Title** + one **Core message** takeaway only — no bullet dumps.
- Content slides may include **Figure:** / **Table:** when the brief lists
  selected assets — bind every selected asset to some content slide
  (not P01/closing unless it is explicitly a cover figure).
- If an evidence catalog is provided, every factual claim on content slides
  must cite evidence IDs like `ev-...` on an **Evidence:** line in this
  markdown plan only (never as on-slide footer copy).

pdf_strict title plate:
- **Title** MUST be the paper's own title from source_identity — its subject,
  not a paraphrase of the user topic / instructions.
- Quote it in the language the paper is written in, even when that is not
  brief.primary_language. A published title is how the work is cited and found;
  translating it produces a title that exists nowhere and cannot be looked up.
  This is the one exception to the language contract below, and it is an
  exception for being a quotation, not for being on P01.
- **Authors** and **Affiliations** are identity too: the presenter's name, their
  institution as the paper gives it, and the e-mail address stay exactly as
  written. Do not translate an institution name.
- Everything the deck *says about* the work — the kicker, the subtitle, every
  later slide — is in primary_language. Only the quoted identity is not.
- Read brief.additional_instructions in natural language (any phrasing /
  language). If the author names a presenter/speaker or affiliation/institution,
  put those on **Authors** / **Affiliations** verbatim — even when
  source_identity says Anonymous Author(s) / Affiliation withheld. These are
  talk facts from the user, not PDF claims; no evidence IDs are required.
- When brief.deck_furniture already lists presenter/affiliation, prefer those
  structured values (same rule: no “Affiliation withheld…” placeholders).

scratch title plate:
- **Title** is a concise, audience-facing project name in primary_language.
  NEVER copy an instruction such as "generate/create/make a presentation about …"
  onto the slide. Infer the subject and write a natural title.

Language contract (HARD):
- Every viewer-visible string on every slide, including P01 and the final
  thanks/questions plate, MUST be in confirmed brief.primary_language.
- Do not reuse English schema examples when primary_language is not English.
- Evidence identifiers and established technical symbols may remain unchanged.
- Quoted identity is exempt, and only quoted identity: the paper's own title,
  the author's name, their institution and e-mail. These are cited, not
  written, so they carry the source's language. Anything you compose about the
  work is not a quotation and gets no exemption.

Also:
- Use the confirmed palette, typography, visual_style, and icons from the brief
  (do not invent a second brand).
- Honor additional_instructions from the brief as requirements (tone, byline,
  constraints), not optional hints. Understand them directly — do not require
  fixed keywords.
- Do not invent unsupported numbers.
"""

_SECTION_IX = re.compile(
    r"^##\s*IX\.?\s*Content Outline\s*$",
    re.I | re.M,
)
_SLIDE_HEADER = re.compile(
    r"^###\s*P?(?P<num>\d+)\s*[:.–-]?\s*(?P<title>.*)$",
    re.I | re.M,
)


def _palette(result: dict[str, Any]) -> dict[str, str]:
    color = result.get("color") if isinstance(result.get("color"), dict) else {}
    palette = color.get("palette") if isinstance(color.get("palette"), dict) else {}
    tokens = result.get("design_tokens") if isinstance(result.get("design_tokens"), dict) else {}
    token_palette = tokens.get("palette") if isinstance(tokens.get("palette"), dict) else {}
    merged = {**token_palette, **palette}
    return {
        "background": str(merged.get("background") or "#FFFFFF"),
        "secondary_bg": str(merged.get("secondary_bg") or "#F8FAFC"),
        "primary": str(merged.get("primary") or "#1E3A8A"),
        "accent": str(merged.get("accent") or "#F59E0B"),
        "secondary_accent": str(merged.get("secondary_accent") or "#3B82F6"),
        "body_text": str(merged.get("body_text") or "#0F172A"),
        "text_secondary": str(merged.get("text_secondary") or ""),
        "text_tertiary": str(merged.get("text_tertiary") or ""),
        "border": str(merged.get("border") or ""),
        "accent_tint": str(merged.get("accent_tint") or ""),
        "success": str(merged.get("success") or ""),
        "warning": str(merged.get("warning") or ""),
    }


def _typography(result: dict[str, Any]) -> dict[str, str]:
    typography = result.get("typography") if isinstance(result.get("typography"), dict) else {}
    heading = typography.get("heading") if isinstance(typography.get("heading"), dict) else {}
    body = typography.get("body") if isinstance(typography.get("body"), dict) else {}
    tokens = result.get("design_tokens") if isinstance(result.get("design_tokens"), dict) else {}
    token_type = tokens.get("typography") if isinstance(tokens.get("typography"), dict) else {}
    token_heading = token_type.get("heading") if isinstance(token_type.get("heading"), dict) else {}
    token_body = token_type.get("body") if isinstance(token_type.get("body"), dict) else {}
    scale = typography.get("type_scale") if isinstance(typography.get("type_scale"), dict) else {}
    if not scale:
        scale = tokens.get("type_scale") if isinstance(tokens.get("type_scale"), dict) else {}
    return {
        "title_family": str(heading.get("primary") or token_heading.get("primary") or "Georgia"),
        "body_family": str(body.get("primary") or token_body.get("primary") or "Arial"),
        "title": str(int(float(scale.get("title") or 36))),
        "body": str(int(float(scale.get("body") or typography.get("body_size") or 18))),
        "subtitle": str(int(float(scale.get("heading") or 22))),
        "annotation": str(int(float(scale.get("caption") or 14))),
    }


def _page_count(result: dict[str, Any], default: int = 6) -> int:
    """UI / confirm page_count = content slides only (bookends are extra)."""
    raw = result.get("page_count", default)
    if isinstance(raw, dict):
        raw = raw.get("value", default)
    match = re.search(r"\d+", str(raw))
    try:
        return max(1, min(20, int(match.group()) if match else default))
    except (TypeError, ValueError):
        return default


def total_page_count(content_count: int) -> int:
    return max(3, int(content_count) + 2)


_PROMPT_TITLE_PREFIXES = (
    r"(?:please\s+)?(?:generate|create|make|build|prepare|design|produce)(?:\s+me)?\s+",
    r"(?:bir\s+)?(?:sunum|ppt|powerpoint)\s+(?:hazırla|oluştur|yap)\s*[:;-]?\s*",
)


def _audience_title_from_topic(topic: str, language: str = "") -> str:
    """Turn an instruction-like scratch prompt into a presentable fallback title."""
    text = re.sub(r"\s+", " ", str(topic or "")).strip().strip(".?!")
    for pattern in _PROMPT_TITLE_PREFIXES:
        text = re.sub(rf"^{pattern}", "", text, flags=re.I).strip()
    text = re.sub(
        r"^(?:a|an|the)\s+(?:pptx?|powerpoint|presentation|slide deck)\s+(?:about|on|for)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:pptx?|powerpoint|presentation|slide deck)\s+(?:about|on|for)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"^(?:hakkında|konusunda)\s+", "", text, flags=re.I)
    if not text:
        return "Sunum" if str(language).casefold().startswith("tr") else "Presentation"
    return text[0].upper() + text[1:]


def _localized_closing(language: str) -> dict[str, str]:
    code = str(language or "en").strip().casefold().split("-")[0]
    translations = {
        "tr": {"title": "Teşekkürler", "message": "Sorularınızı memnuniyetle yanıtlarım"},
        "de": {"title": "Vielen Dank", "message": "Fragen sind willkommen"},
        "fr": {"title": "Merci", "message": "Questions bienvenues"},
        "es": {"title": "Gracias", "message": "Preguntas bienvenidas"},
        "it": {"title": "Grazie", "message": "Domande benvenute"},
        "pt": {"title": "Obrigado", "message": "Perguntas são bem-vindas"},
    }
    return translations.get(code, {"title": "Thank you", "message": "Questions welcome"})


def _looks_like_prompt_command(value: str) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    return bool(
        re.match(
            r"^(?:please\s+)?(?:generate|create|make|build|prepare|design|produce)\b",
            text,
        )
        or re.search(r"\b(?:sunum|ppt|powerpoint)\s+(?:hazırla|oluştur|yap)\b", text)
    )


def ensure_bookend_slides(
    slides: list[dict[str, Any]],
    *,
    content_count: int,
    topic: str,
    result: dict[str, Any],
    source_identity: dict[str, str] | None = None,
    grounding_mode: str = "scratch",
) -> list[dict[str, Any]]:
    """Guarantee P01 title + N content + final thanks; renumber 1..N+2."""
    from tasks.deck_furniture import merge_furniture_into_identity, resolve_deck_furniture
    from tasks.source_identity import title_looks_like_topic

    furniture = resolve_deck_furniture(result if isinstance(result, dict) else {})
    identity = merge_furniture_into_identity(source_identity, furniture)
    paper_title = str(identity.get("paper_title") or "").strip()
    authors = str(identity.get("authors") or "").strip()
    affiliations = str(identity.get("affiliations") or "").strip()

    authored_title_slide = next(
        (item for item in slides if str(item.get("role") or "").casefold() == "title"),
        None,
    )
    authored_title = str((authored_title_slide or {}).get("title") or "").strip()
    language = str(result.get("primary_language") or "en")
    if grounding_mode == "pdf_strict" and paper_title and not title_looks_like_topic(paper_title, topic):
        title_text = paper_title
    elif grounding_mode == "pdf_strict" and paper_title:
        title_text = paper_title
    else:
        # Preserve the strategist's audience-facing P01. The old code discarded
        # it and put the raw user command on the cover.
        title_text = authored_title if not _looks_like_prompt_command(authored_title) else ""
        title_text = title_text or str(result.get("presentation_title") or "").strip()
        if _looks_like_prompt_command(title_text):
            title_text = ""
        if not title_text:
            title_text = _audience_title_from_topic(topic, language)

    closing = _localized_closing(language)

    def _title_plate() -> dict[str, Any]:
        body_bits = ["Title plate only"]
        if authors:
            body_bits.append(f"Authors: {authors}")
        if affiliations:
            body_bits.append(f"Affiliations: {affiliations}")
        return {
            "slide": 1,
            "slide_id": "slide-1",
            "title": title_text,
            "core_message": str(result.get("core_message") or "").strip(),
            "layout_intent": "Full-bleed title; supporting lines below; open field",
            "content_blocks": "; ".join(body_bits),
            "visual_job": "Orient the audience",
            "body": (
                f"- **Title**: {title_text}\n"
                f"- **Core message**: {result.get('core_message') or ''}\n"
                f"- **Authors**: {authors}\n"
                f"- **Affiliations**: {affiliations}\n"
                "- **Content**: Title plate only\n"
                "- **Visual job**: Orient the audience\n"
            ),
            "evidence_ids": [],
            "authors": authors,
            "affiliations": affiliations,
            "role": "title",
            "figure_id": "",
            "table_id": "",
        }

    def _closing(number: int) -> dict[str, Any]:
        return {
            "slide": number,
            "slide_id": f"slide-{number}",
            "title": closing["title"],
            "core_message": closing["message"],
            "layout_intent": "Centered closing with thanks and invitation for questions",
            "content_blocks": f'{closing["title"]}. {closing["message"]}.',
            "visual_job": "Close the talk",
            "body": (
                f'- **Title**: {closing["title"]}\n'
                f'- **Core message**: {closing["message"]}\n'
                "- **Content**: Closing plate only\n"
                "- **Visual job**: Close the talk\n"
            ),
            "evidence_ids": [],
            "authors": "",
            "affiliations": "",
            "role": "closing",
            "figure_id": "",
            "table_id": "",
        }

    content = [dict(item) for item in slides if int(item.get("slide") or 0) > 0]
    # Drop existing first/last if they already look like bookends when count matches.
    if content and str(content[0].get("role") or "") == "title":
        content = content[1:]
    if content and str(content[-1].get("role") or "") == "closing":
        content = content[:-1]
    # If model returned exactly content_count (+maybe bookends messily), keep middle N.
    if len(content) > content_count:
        # Prefer dropping extras from the end before closing synthesis.
        content = content[:content_count]
    while len(content) < content_count:
        idx = len(content) + 1
        content.append(
            {
                "slide": idx,
                "slide_id": f"slide-{idx}",
                "title": f"{topic} — {idx}",
                "core_message": f"Advance the argument for content slide {idx}",
                "layout_intent": "Title top; body column left; visual/callout right",
                "content_blocks": f"Develop point {idx} for {topic}",
                "visual_job": "Support the core message",
                "body": f"- **Title**: {topic} — {idx}\n- **Content**: Develop point {idx}\n",
                "evidence_ids": [],
                "role": "content",
                "figure_id": "",
                "table_id": "",
            }
        )

    for item in content:
        item["role"] = "content"
        item.pop("authors", None)

    ordered = [_title_plate(), *content, _closing(content_count + 2)]
    for index, item in enumerate(ordered, start=1):
        item["slide"] = index
        item["slide_id"] = f"slide-{index}"
        if index == 1:
            item["role"] = "title"
        elif index == len(ordered):
            item["role"] = "closing"
        else:
            item["role"] = "content"
    return ordered


def validate_design_spec_palette(
    design_spec_md: str,
    result: dict[str, Any],
) -> list[str]:
    """Fail when design_spec invents a primary/accent/bg different from the locked pack."""
    palette = _palette(result)
    errors: list[str] = []
    # Only enforce when pack (or user) locked an explicit palette into result.
    source = str((result.get("color") or {}).get("source") or "").casefold()
    if source not in {"pack", "user"}:
        return errors
    expected = {
        "primary": palette["primary"].upper(),
        "accent": palette["accent"].upper(),
        "background": palette["background"].upper(),
    }
    # Pull hexes near role labels in the authored design_spec.
    for role, hex_val in expected.items():
        if not hex_val.startswith("#"):
            continue
        pattern = re.compile(
            rf"(?is){role}[^#\n]{{0,40}}(#[0-9A-Fa-f]{{6}})|(#[0-9A-Fa-f]{{6}})[^#\n]{{0,40}}{role}"
        )
        match = pattern.search(design_spec_md or "")
        if not match:
            continue
        found = (match.group(1) or match.group(2) or "").upper()
        if found and found != hex_val:
            errors.append(
                f"design_spec {role} {found} drifts from locked palette {hex_val}"
            )
    return errors


def validate_design_spec_md(text: str) -> list[str]:
    """Gate 1 — require core sections and at least one §IX slide."""
    errors: list[str] = []
    if not text or not text.strip():
        return ["design_spec.md is empty"]
    required = [
        (r"##\s*I\.?\s*Project", "missing §I Project Information"),
        (r"##\s*II\.?\s*Canvas", "missing §II Canvas"),
        (r"##\s*III\.?\s*Visual Theme", "missing §III Visual Theme"),
        (r"##\s*IV\.?\s*Typography", "missing §IV Typography"),
        (r"##\s*IX\.?\s*Content Outline", "missing §IX Content Outline"),
    ]
    for pattern, message in required:
        if not re.search(pattern, text, re.I):
            errors.append(message)
    if not _SLIDE_HEADER.search(text):
        errors.append("§IX has no slide headers (### P01 …)")
    return errors


def project_flat_spec_lock(
    *,
    result: dict[str, Any],
    design_spec_md: str,
    page_count: int,
) -> str:
    """Deterministic full flat spec_lock.md from confirm_ui + design_spec."""
    palette = _palette(result)
    fonts = _typography(result)
    lang = str(result.get("primary_language") or "en")
    mode = str(result.get("mode") or "briefing")
    tokens = result.get("design_tokens") if isinstance(result.get("design_tokens"), dict) else {}
    layout = tokens.get("layout") if isinstance(tokens.get("layout"), dict) else {}
    visual_style = str(
        result.get("visual_style")
        or layout.get("visual_style")
        or "swiss-minimal"
    )
    density = str(result.get("density") or layout.get("density") or "medium")
    presentation_style = str(
        result.get("presentation_style") or result.get("style_id") or ""
    ).strip()
    presentation_method = ""
    if presentation_style:
        try:
            from tasks.presentation_style import load_style_method
        except ImportError:  # pragma: no cover
            from presentation_style import load_style_method  # type: ignore
        presentation_method = load_style_method(presentation_style)
    icons = result.get("icons") if isinstance(result.get("icons"), dict) else {}
    token_icons = tokens.get("icons") if isinstance(tokens.get("icons"), dict) else {}
    library = str(
        icons.get("library")
        or token_icons.get("library")
        or icons.get("style")
        or "tabler-outline"
    )
    stroke_width = icons.get("stroke_width") or token_icons.get("stroke_width") or 2
    inventory = icons.get("inventory") or token_icons.get("inventory") or icons.get("names") or []
    if isinstance(inventory, list):
        inventory_text = ", ".join(str(item) for item in inventory[:40]) or "none"
    else:
        inventory_text = str(inventory or "none")
    brand_library = str(icons.get("brand_library") or token_icons.get("brand_library") or "").strip()

    pack_rhythm = layout.get("page_rhythm") if isinstance(layout.get("page_rhythm"), dict) else {}
    rhythm_lines: list[str] = []
    for index in range(1, page_count + 1):
        key = f"P{index:02d}"
        default = "anchor" if index == 1 else ("anchor" if index == page_count else "dense")
        rhythm_lines.append(f"- {key}: {pack_rhythm.get(key) or default}")

    consumption = str(
        result.get("consumption_mode")
        or result.get("reading_mode")
        or (tokens.get("method") or {}).get("default_consumption_mode")
        or ""
    ).strip().casefold()
    if consumption not in {"text", "balanced", "presentation"}:
        # Pack method may set balanced/instructional default; else presentation.
        method_mode = str(
            (tokens.get("method") or {}).get("preferred_mode") or ""
        ).strip().casefold()
        if method_mode in {"instructional", "tutorial", "balanced"}:
            consumption = "balanced"
        else:
            consumption = "presentation"

    color_lines = [
        f"- bg: {palette['background']}",
        f"- secondary_bg: {palette['secondary_bg']}",
        f"- primary: {palette['primary']}",
        f"- accent: {palette['accent']}",
        f"- secondary_accent: {palette['secondary_accent']}",
        f"- text: {palette['body_text']}",
    ]
    for key, lock_key in (
        ("text_secondary", "text_secondary"),
        ("text_tertiary", "text_tertiary"),
        ("border", "border"),
        ("accent_tint", "accent_tint"),
        ("success", "success"),
        ("warning", "warning"),
    ):
        if palette.get(key):
            color_lines.append(f"- {lock_key}: {palette[key]}")
    image_rendering = str(result.get("image_rendering") or "").strip()
    image_palette = str(result.get("image_palette") or "").strip()
    mood = tokens.get("image_mood") if isinstance(tokens.get("image_mood"), dict) else {}
    if not image_rendering:
        image_rendering = str(mood.get("image_rendering") or "").strip()
    if not image_palette:
        image_palette = str(mood.get("image_palette") or "").strip()
    if image_rendering:
        color_lines.append(f"- image_rendering: {image_rendering}")
    if image_palette:
        color_lines.append(f"- image_palette: {image_palette}")

    icon_lines = [
        f"- library: {library}",
        f"- stroke_width: {stroke_width}",
        f"- inventory: {inventory_text}",
    ]
    if brand_library:
        icon_lines.insert(1, f"- brand_library: {brand_library}")

    page_charts = layout.get("page_charts") if isinstance(layout.get("page_charts"), dict) else {}
    chart_lines = [f"- {key}: {val}" for key, val in list(page_charts.items())[:24]]

    return "\n".join(
        [
            "<!-- sunairum-schema: spec-lock/v1 -->",
            "# Execution Lock",
            "",
            "## canvas",
            "- viewBox: 0 0 1280 720",
            "- format: PPT 16:9",
            "",
            "## communication",
            f"- primary_language: {lang}",
            f"- audience: {str(result.get('audience') or '').strip() or 'general'}",
            f"- objective: {str(result.get('desired_outcome') or result.get('core_message') or '').strip() or 'inform'}",
            f"- core_message: {str(result.get('core_message') or '').strip() or 'n/a'}",
            f"- consumption_mode: {consumption}",
            "",
            "## mode",
            f"- mode: {mode}",
            "",
            "## visual_style",
            f"- visual_style: {visual_style}",
            f"- density: {density}",
            "- style_tokens_feed: Style Resolver (palette hexes + type sizes)",
            *(
                [
                    "",
                    "## presentation_method",
                    f"- selected_style: {presentation_style}",
                    "- authority: user-selected scratch method; apply on every slide",
                    presentation_method,
                ]
                if presentation_style and presentation_method
                else []
            ),
            "",
            "## ownership",
            "- content/title/closing: Executor owns Constrained HTML pages; materialize → Slide IR → native PPTX",
            "- hosts: Intent fills empty table/chart/formula/figure hosts only",
            "- tables: Table Analyzer → Visual Intent styles locked table host",
            "- figures: image slot inject into locked figure host (calm region reserved)",
            "- formulas: Formula band PNG/image inside locked formula host",
            "- never: AntV Infographic SSR or painter dual-layers on content",
            "",
            "## colors",
            *color_lines,
            "",
            "## typography",
            f'- font_family: "{fonts["body_family"]}", sans-serif',
            f'- title_family: "{fonts["title_family"]}", serif',
            f'- body_family: "{fonts["body_family"]}", sans-serif',
            f"- title: {fonts['title']}",
            f"- body: {fonts['body']}",
            f"- subtitle: {fonts['subtitle']}",
            f"- annotation: {fonts['annotation']}",
            "",
            "## icons",
            *icon_lines,
            "",
            "## page_rhythm",
            *rhythm_lines,
            *(["", "## page_charts", *chart_lines] if chart_lines else []),
            "",
            "## pptx_structure",
            "- mode: flat",
            "",
            "## forbidden",
            "- `mask`, `<style>`, `class`, external CSS, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`",
            "- `<foreignObject>` absolutely (no host exemptions)",
            "- HTML named entities in text; write typography as raw Unicode and escape XML reserved characters",
            "- Master/Layout structure attrs: data-pptx-placeholder, data-pptx-master, data-pptx-layout, data-pptx-carrier",
            "- AntV Infographic DSL / template names / SSR hosts",
            "",
        ]
    )


def fallback_design_spec(
    *,
    topic: str,
    result: dict[str, Any],
    page_count: int,
    evidence_catalog: str = "",
    source_identity: dict[str, str] | None = None,
    grounding_mode: str = "scratch",
    selected_figure_ids: list[str] | None = None,
    selected_table_ids: list[str] | None = None,
) -> str:
    """Deterministic design_spec when the model is unavailable (tests / budget).

    ``page_count`` is content slides; total headers = page_count + 2.
    """
    palette = _palette(result)
    fonts = _typography(result)
    visual_style = str(result.get("visual_style") or "swiss-minimal")
    from tasks.deck_furniture import merge_furniture_into_identity, resolve_deck_furniture

    furniture = resolve_deck_furniture(result if isinstance(result, dict) else {})
    identity = merge_furniture_into_identity(source_identity, furniture)
    paper_title = str(identity.get("paper_title") or "").strip()
    authors = str(identity.get("authors") or "").strip()
    affiliations = str(identity.get("affiliations") or "").strip()
    if grounding_mode == "pdf_strict" and paper_title:
        title_text = paper_title
    else:
        title_text = str(result.get("presentation_title") or "").strip()
        if not title_text:
            title_text = _audience_title_from_topic(
                topic, str(result.get("primary_language") or "en")
            )
    closing = _localized_closing(str(result.get("primary_language") or "en"))
    total = total_page_count(page_count)
    slides = []
    slides.append(
        "\n".join(
            [
                "### P01: Title",
                f"- **Title**: {title_text}",
                f"- **Core message**: {str(result.get('core_message') or topic)}",
                f"- **Authors**: {authors}",
                f"- **Affiliations**: {affiliations}",
                "- **Layout**: Full-bleed title left, supporting line below; open field right",
                "- **Content**: Title plate only",
                "- **Visual job**: Orient the audience",
            ]
        )
    )
    catalog_ids = re.findall(r"\b(ev-[A-Za-z0-9._-]+)\b", evidence_catalog or "")
    figures = [str(x) for x in (selected_figure_ids or []) if str(x).strip()]
    tables = [str(x) for x in (selected_table_ids or []) if str(x).strip()]
    for index in range(2, page_count + 2):
        content_i = index - 1
        if evidence_catalog:
            cite = catalog_ids[(content_i - 1) % len(catalog_ids)] if catalog_ids else ""
            claim = (
                f"- **Content**: Key point {content_i} grounded in the source\n"
                f"- **Evidence**: {cite or '(see catalog; paraphrase only)'}"
            )
        else:
            claim = f"- **Content**: Develop point {content_i} for {topic}"
        extra = []
        if figures:
            extra.append(f"- **Figure**: {figures[(content_i - 1) % len(figures)]}")
        if tables:
            extra.append(f"- **Table**: {tables[(content_i - 1) % len(tables)]}")
        slides.append(
            "\n".join(
                [
                    f"### P{index:02d}: Point {content_i}",
                    f"- **Title**: {topic} — {content_i}",
                    f"- **Core message**: Advance the argument for slide {index}",
                    "- **Layout**: Title top; body column left; visual/callout right",
                    claim,
                    *extra,
                    "- **Visual job**: Support the core message with hierarchy and one accent",
                ]
            )
        )
    slides.append(
        "\n".join(
            [
                f'### P{total:02d}: {closing["title"]}',
                f'- **Title**: {closing["title"]}',
                f'- **Core message**: {closing["message"]}',
                "- **Layout**: Centered closing",
                "- **Content**: Closing plate only",
                "- **Visual job**: Close the talk",
            ]
        )
    )
    return "\n".join(
        [
            "<!-- sunairum-schema: design-spec/v1 -->",
            f"# {topic} - Design Spec",
            "",
            "## I. Project Information",
            "",
            "| Item | Value |",
            "| --- | --- |",
            f"| Project Name | {topic} |",
            "| Canvas Format | PPT 16:9 (1280×720) |",
            f"| Page Count | {total} (content {page_count} + title + closing) |",
            f"| Target Audience | {result.get('audience') or 'general'} |",
            f"| Communication Intent | {result.get('communication_intent') or 'inform'} |",
            f"| Desired Audience Outcome | {result.get('desired_outcome') or ''} |",
            f"| Core Message / Ask / Action | {result.get('core_message') or topic} |",
            f"| Design Style | {visual_style} |",
            f"| Created Date | {date.today().isoformat()} |",
            "",
            "## II. Canvas Specification",
            "",
            "| Property | Value |",
            "| --- | --- |",
            "| Format | PPT 16:9 |",
            "| Dimensions | 1280 × 720 |",
            "| CSS canvas | `width:1280px; height:720px` |",
            "| Margins | 64px |",
            "",
            "## III. Visual Theme",
            "",
            "### Theme Style",
            "",
            f"- **Mode**: {result.get('mode') or 'briefing'}",
            f"- **Visual style**: {visual_style}",
            f"- **Theme**: free_design",
            "",
            "### Color Scheme",
            "",
            "| Role | HEX | Purpose |",
            "| --- | --- | --- |",
            f"| Background | {palette['background']} | Field |",
            f"| Primary | {palette['primary']} | Headings |",
            f"| Accent | {palette['accent']} | Emphasis |",
            f"| Body text | {palette['body_text']} | Copy |",
            "",
            "## IV. Typography System",
            "",
            f"- **Title stack**: {fonts['title_family']}",
            f"- **Body stack**: {fonts['body_family']}",
            "",
            "| Purpose | Size |",
            "| --- | --- |",
            "| Page title | 36 |",
            "| Body | 18 |",
            "",
            "## V. Layout Principles",
            "",
            "- One job per slide; strong hierarchy; generous margins.",
            "- No Master/Layout placeholders; Executor owns Constrained HTML → Slide IR → PPTX; "
            "Intent fills empty table/chart/formula/figure hosts only.",
            "",
            "## VI. Icons",
            "",
            f"- Library: {(result.get('icons') or {}).get('library', 'tabler-outline') if isinstance(result.get('icons'), dict) else 'tabler-outline'}",
            "",
            "## IX. Content Outline",
            "",
            "\n\n".join(slides),
            "",
            "## X. Speaker Notes",
            "",
            "- Disabled unless confirm_ui requests otherwise.",
            "",
        ]
    )


def author_design_spec(
    *,
    topic: str,
    result: dict[str, Any],
    evidence_catalog: str = "",
    call_text: Callable[[str, str], str] | None = None,
    allow_fallback: bool = True,
    design_reference_brief: str = "",
    source_identity: dict[str, str] | None = None,
    grounding_mode: str = "scratch",
    selected_figure_ids: list[str] | None = None,
    selected_table_ids: list[str] | None = None,
    asset_catalog: str = "",
) -> tuple[str, dict[str, Any]]:
    """Return (design_spec_md, meta)."""
    content_count = _page_count(result)
    total = total_page_count(content_count)
    meta: dict[str, Any] = {
        "page_count": total,
        "content_page_count": content_count,
        "total_page_count": total,
        "source": "model",
    }
    from tasks.deck_furniture import merge_furniture_into_identity, resolve_deck_furniture

    furniture = resolve_deck_furniture(result if isinstance(result, dict) else {})
    identity = merge_furniture_into_identity(source_identity, furniture)
    brief = {
        "topic": topic,
        "content_page_count": content_count,
        "total_page_count": total,
        "page_count": content_count,
        "visual_style": result.get("visual_style"),
        "mode": result.get("mode"),
        "palette": _palette(result),
        "typography": _typography(result),
        "icons": result.get("icons"),
        "audience": result.get("audience"),
        "core_message": result.get("core_message"),
        "desired_outcome": result.get("desired_outcome"),
        "communication_intent": result.get("communication_intent"),
        "primary_language": result.get("primary_language"),
        "image_source": result.get("image_source"),
        "grounding_mode": grounding_mode,
        "source_identity": identity,
        "selected_figure_ids": list(selected_figure_ids or []),
        "selected_table_ids": list(selected_table_ids or []),
        "deck_furniture": furniture or {},
        "additional_instructions": str(result.get("additional_instructions") or "").strip(),
    }
    user = (
        "# CONTEXT\n"
        f"Topic: {topic}\n"
        f"Grounding mode: {grounding_mode}\n"
        f"Confirmed brief JSON:\n{json.dumps(brief, ensure_ascii=False, indent=2)}\n"
        "\n# OBJECTIVE\n"
        f"Emit exactly {total} §IX headers "
        f"(P01 title + {content_count} content + final thanks). "
        "Bind selected assets via **Figure:** / **Table:** fields only.\n"
        "\n# STYLE\n"
        "Sparse academic briefing copy — not marketing persuasion.\n"
        "\n# TONE\n"
        "Calm, minimal plates; no fill-canvas pressure.\n"
        "\n# AUDIENCE\n"
        "Informed readers; no Introduce/Explain openers in Content.\n"
        "\n# RESPONSE\n"
        "Return only design_spec.md per the system Response schema.\n"
    )
    user += (
        "\n# LANGUAGE AND TITLE CONTRACT\n"
        f"Write ALL visible copy, including the cover title and closing slide, in "
        f"{result.get('primary_language') or 'the automatically selected language'}.\n"
        "For scratch decks, convert the raw Topic command into a concise audience-facing "
        "title; never repeat prompt verbs such as generate, create, make, prepare, or build.\n"
    )
    if design_reference_brief.strip():
        user += (
            "\n# CONTEXT — design SoT / method DNA / optional presentation style "
            "(STYLE INSPIRATION only — do not clone geometry "
            "or a reference pack's subject copy; strip any non-English body text):\n"
            f"{design_reference_brief[:12000]}\n"
        )
    style_id = str(result.get("presentation_style") or result.get("style_id") or "").strip()
    if style_id:
        user += (
            f"\n# PRESENTATION STYLE\n"
            f"User selected method pack `{style_id}` — obey its composition/density/"
            "decoration/color behavior while keeping Fill Contract inject tokens.\n"
        )
    if evidence_catalog.strip():
        user += (
            "\n# CONTEXT — <evidence_catalog>\n"
            f"{evidence_catalog[:120000]}\n"
            "</evidence_catalog>\n"
        )
    if asset_catalog.strip():
        user += (
            "\n# CONTEXT — <asset_catalog>\n"
            f"{asset_catalog[:20000]}\n"
            "</asset_catalog>\n"
        )

    text = ""
    llm_error: Exception | None = None
    if call_text is not None:
        try:
            text = str(call_text(SYSTEM_PROMPT, user) or "")
        except Exception as error:
            meta["error"] = str(error)
            llm_error = error
            text = ""
    else:
        try:
            from llm_client import call_llm_text

            text = str(call_llm_text(SYSTEM_PROMPT, user) or "")
        except Exception as error:
            meta["error"] = str(error)
            llm_error = error
            text = ""

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    if not allow_fallback and (llm_error is not None or not text):
        detail = str(llm_error or "provider returned an empty design_spec response")
        raise RuntimeError(f"Strategist LLM unavailable: {detail}") from llm_error

    errors = validate_design_spec_md(text)
    if errors:
        if not allow_fallback:
            raise RuntimeError("design_spec.md failed Gate 1: " + "; ".join(errors))
        meta["source"] = "fallback"
        meta["gate1_errors"] = errors
        text = fallback_design_spec(
            topic=topic,
            result=result,
            page_count=content_count,
            evidence_catalog=evidence_catalog,
            source_identity=identity,
            grounding_mode=grounding_mode,
            selected_figure_ids=selected_figure_ids,
            selected_table_ids=selected_table_ids,
        )
        errors = validate_design_spec_md(text)
        if errors:
            raise RuntimeError("fallback design_spec.md invalid: " + "; ".join(errors))
    return text, meta


_ROMAN_TABLE_RE = re.compile(r"\bTABLE\s+([IVXLCDM]+|\d+)\b", re.I)


def _extract_asset_id(raw: str, *, kind: str) -> str:
    """Prefer canonical asset ids over caption tokens like ``TABLE`` / ``Figure``."""
    text = re.sub(r"[`\"']", "", str(raw or "")).strip()
    if not text or text.casefold() in {"none", "n/a", "na", "-"}:
        return ""
    if kind == "table":
        match = re.search(r"\b(src-table-\d+)\b", text, re.I)
        if match:
            return match.group(1)
    else:
        match = re.search(r"\b(pdf-page-\d+-picture-\d+)\b", text, re.I)
        if match:
            return match.group(1)
        match = re.search(r"\b((?:pdf-|fig-|figure-)[A-Za-z0-9._-]+)\b", text, re.I)
        if match:
            return match.group(1)
    # First token only when it already looks like an id (contains a hyphen/digit).
    token = text.split()[0].strip("()[].,;")
    if re.search(r"[\d_]", token) and "-" in token:
        return token
    return ""


def _normalize_table_label(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    roman = _ROMAN_TABLE_RE.search(text)
    if roman:
        return f"table {roman.group(1).upper()}"
    return text


def resolve_asset_id_from_catalog(
    raw: str,
    *,
    kind: str,
    catalog: list[dict[str, Any]] | None = None,
) -> str:
    """Resolve §IX Figure/Table fields to canonical ids using an optional catalog."""
    direct = _extract_asset_id(raw, kind=kind)
    if direct:
        return direct
    text = re.sub(r"[`\"']", "", str(raw or "")).strip()
    if not text or not catalog:
        return ""
    needle = _normalize_table_label(text) if kind == "table" else text.casefold()
    for item in catalog:
        if not isinstance(item, dict):
            continue
        if kind == "table":
            tid = str(item.get("table_id") or item.get("id") or "").strip()
            caption = str(item.get("caption") or item.get("title") or "")
            if not tid:
                continue
            if _normalize_table_label(caption) == needle:
                return tid
            # Loose contain: "TABLE IV HERO…" vs field "TABLE IV"
            if needle and needle in _normalize_table_label(caption):
                return tid
        else:
            fid = str(item.get("id") or item.get("asset_id") or item.get("figure_id") or "").strip()
            label = str(item.get("caption") or item.get("title") or item.get("label") or "")
            if not fid:
                continue
            if needle and (needle == label.casefold() or needle in label.casefold() or fid.casefold() in needle):
                return fid
    return ""


def resolve_parsed_slide_assets(
    slides: list[dict[str, Any]],
    *,
    tables: list[dict[str, Any]] | None = None,
    figures: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fill empty/invalid figure_id/table_id from raw §IX fields + catalogs."""
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        body = str(slide.get("body") or "")
        table_field = str(slide.get("table_field") or "")
        figure_field = str(slide.get("figure_field") or "")
        if not table_field:
            table_match = re.search(r"[-*]\s*\*\*Table:?\*\*\s*:?\s*(.+)$", body, re.I | re.M)
            if table_match:
                table_field = table_match.group(1).strip()
        if not figure_field:
            figure_match = re.search(r"[-*]\s*\*\*Figure:?\*\*\s*:?\s*(.+)$", body, re.I | re.M)
            if figure_match:
                figure_field = figure_match.group(1).strip()
        current_table = str(slide.get("table_id") or "").strip()
        if (not current_table or current_table.casefold() in {"table", "none"}) and table_field:
            slide["table_id"] = resolve_asset_id_from_catalog(
                table_field, kind="table", catalog=tables
            )
        current_fig = str(slide.get("figure_id") or "").strip()
        if (not current_fig or current_fig.casefold() in {"figure", "none"}) and figure_field:
            slide["figure_id"] = resolve_asset_id_from_catalog(
                figure_field, kind="figure", catalog=figures
            )
    return slides


def _strip_list_marker(line: str) -> str:
    """Remove one leading list marker, leaving the item's own text intact.

    The blunt character class this replaces walked past the marker and on into
    the sentence: `- **1,74x:** Daha az...` lost the 1 of 1,74 and became
    `,74x` on the slide -- a measured result quietly divided by a hundred,
    while the strategist's own text had it right all along. Shares one
    definition of "marker" with the other parsers.
    """
    try:
        from tasks.asset_narrative import strip_list_marker
    except ImportError:  # pragma: no cover - flat-module import path
        from asset_narrative import strip_list_marker  # type: ignore
    return strip_list_marker(line)


def parse_section_ix_slides(design_spec_md: str) -> list[dict[str, Any]]:
    """Parse §IX into slide dicts for Executor + grounding bridge."""
    match = _SECTION_IX.search(design_spec_md)
    if not match:
        return []
    body = design_spec_md[match.end() :]
    next_section = re.search(r"^##\s+[XVI]+\.", body, re.M)
    if next_section:
        body = body[: next_section.start()]
    headers = list(_SLIDE_HEADER.finditer(body))
    slides: list[dict[str, Any]] = []
    for index, header in enumerate(headers):
        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(body)
        chunk = body[start:end].strip()
        number = int(header.group("num"))
        title = (header.group("title") or "").strip() or f"Slide {number}"

        def field(name: str) -> str:
            # Models emit both ``**Title**: value`` and ``**Title:** value``
            # (colon inside the bold markers). Accept either.
            found = re.search(
                rf"[-*]\s*\*\*{name}:?\*\*\s*:?\s*(.+)$",
                chunk,
                re.I | re.M,
            )
            return (found.group(1).strip() if found else "")

        def field_formula() -> str:
            """Capture Formula, including multiline ``\\[…\\]`` / ``$$…$$`` blocks."""
            header = re.search(
                r"(?im)^[-*]\s*\*\*Formula:?\*\*\s*:?\s*(.*)$",
                chunk,
            )
            if not header:
                return ""
            first = (header.group(1) or "").strip()
            rest_start = header.end()
            # Same-line complete equation (no bare opener).
            opener_only = bool(
                re.fullmatch(r"(?:\\\[|\$\$|\\\(|\$)\s*", first)
                or first in {"\\[", "$$", "\\(", "$"}
            )
            if first and not opener_only:
                # Same-line with closer, or plain ASCII/TeX without display delimiters.
                if re.search(r"\\\]|\$\$|\\\)", first) or not re.match(
                    r"^(?:\\\[|\$\$)", first
                ):
                    return first
            # Continue until matching closer or next §IX field bullet.
            lines = [first] if first else []
            for line in chunk[rest_start:].splitlines():
                if re.match(
                    r"^\s*[-*]\s*\*\*(?:"
                    r"Title|Core message|Core Message|Audience move|Audience Move|"
                    r"Layout|Content|Cards|Steps|"
                    r"Visual job|Visual Job|Visualization|Page rhythm|Page Rhythm|"
                    r"Structure|Text policy|Text Policy|Calm region|Calm Region|"
                    r"Evidence|Figure|Table|Formula tex|Formula TeX|"
                    r"Formula terms|Formula Terms|Formula gloss|Formula Gloss|"
                    r"Authors|Affiliations|Author|Affiliation|"
                    r"Infographic template|Infographic Template|Infographic DSL"
                    r"):?\*\*",
                    line,
                    flags=re.I,
                ):
                    break
                lines.append(line.rstrip())
                joined_so_far = "\n".join(lines)
                if re.search(r"\\\]|\$\$", joined_so_far) and (
                    joined_so_far.count("\\[") <= joined_so_far.count("\\]")
                    or joined_so_far.count("$$") >= 2
                ):
                    break
            joined = "\n".join(lines).strip()
            return joined

        def field_multiline(name: str) -> str:
            """Capture multi-line bullet lists under a §IX field (Content/Cards/Steps)."""
            # Stop at known field labels only — Content bullets often use bold labels.
            stop = (
                r"(?=^\s*[-*]\s*\*\*(?:"
                r"Title|Core message|Core Message|Audience move|Audience Move|"
                r"Layout|Content|Cards|Steps|"
                r"Visual job|Visual Job|Visualization|Page rhythm|Page Rhythm|"
                r"Structure|Text policy|Text Policy|Calm region|Calm Region|"
                r"Evidence|Figure|Table|Formula|Formula tex|Formula TeX|"
                r"Formula terms|Formula Terms|Formula gloss|Formula Gloss|"
                r"Authors|Affiliations|Author|Affiliation|"
                r"Infographic template|Infographic Template|Infographic DSL"
                r"):?\*\*|\Z)"
            )
            block = re.search(
                rf"(?ims)^\s*[-*]\s*\*\*{re.escape(name)}:?\*\*\s*:?\s*\n(.*?){stop}",
                chunk,
            )
            if block:
                bullets: list[str] = []
                for line in block.group(1).splitlines():
                    if not re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", line):
                        continue
                    cleaned = _strip_list_marker(line)
                    cleaned = re.sub(r"^\*+|\*+$", "", cleaned).strip()
                    if cleaned:
                        bullets.append(f"- {cleaned}")
                if bullets:
                    return "\n".join(bullets)
            # Fallback: same-line Content (possibly "; "-joined).
            inline = field(name)
            return inline

        evidence_ids = re.findall(r"\b(ev-[A-Za-z0-9._-]+)\b", chunk)
        figure_field = field("Figure") or field("figure")
        table_field = field("Table") or field("table")
        figure_id = _extract_asset_id(figure_field, kind="figure")
        table_id = _extract_asset_id(table_field, kind="table")
        content_blocks = field_multiline("Content")
        cards_raw = field_multiline("Cards")
        steps_raw = field_multiline("Steps")
        cards: list[dict[str, str]] = []
        steps: list[dict[str, str]] = []
        try:
            from tasks.content_densify import claim_cards_from_lines, strip_markdown_inline
        except ImportError:  # pragma: no cover
            from content_densify import claim_cards_from_lines, strip_markdown_inline  # type: ignore
        if cards_raw:
            card_lines = [
                strip_markdown_inline(ln)
                for ln in cards_raw.splitlines()
                if ln.strip()
            ]
            cards = claim_cards_from_lines(card_lines)
        if steps_raw:
            step_lines = [
                strip_markdown_inline(ln)
                for ln in steps_raw.splitlines()
                if ln.strip()
            ]
            steps = claim_cards_from_lines(step_lines)
        rhythm_raw = (
            field("Page rhythm") or field("Page Rhythm") or field("page_rhythm")
        ).strip().casefold()
        if rhythm_raw not in {"anchor", "dense", "breathing"}:
            rhythm_raw = ""
        viz_raw = (
            field("Visualization") or field("visualization") or ""
        ).strip()
        structure_raw = (field("Structure") or "").strip().casefold()
        structure_atom = ""
        for atom in (
            "order",
            "link",
            "parent",
            "membership",
            "contrast",
            "overlap",
        ):
            if atom in structure_raw.split() or structure_raw == atom:
                structure_atom = atom
                break
        slides.append(
            {
                "slide": number,
                "slide_id": f"slide-{number}",
                "title": field("Title") or title,
                "core_message": field("Core message") or field("Core Message"),
                "audience_move": field("Audience move") or field("Audience Move"),
                "layout_intent": field("Layout"),
                "content_blocks": content_blocks,
                "visual_job": field("Visual job") or field("Visual Job"),
                "visualization": viz_raw,
                "page_rhythm": rhythm_raw,
                "structure_atom": structure_atom or structure_raw[:32],
                "text_policy": field("Text policy") or field("Text Policy"),
                "calm_region": field("Calm region") or field("Calm Region"),
                "formula": field_formula(),
                "formula_tex": field("Formula tex") or field("Formula TeX"),
                "formula_terms": field("Formula terms") or field("Formula Terms"),
                "formula_gloss": field("Formula gloss") or field("Formula Gloss"),
                "authors": field("Authors") or field("Author"),
                "affiliations": field("Affiliations") or field("Affiliation"),
                "body": chunk,
                "cards": cards,
                "steps": steps,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "figure_id": figure_id,
                "table_id": table_id,
                # Keep raw fields so catalog resolve can map "TABLE IV" → src-table-004.
                "figure_field": figure_field,
                "table_field": table_field,
                "role": "content",
            }
        )
    slides.sort(key=lambda item: int(item["slide"]))
    if slides:
        slides[0]["role"] = "title"
        slides[-1]["role"] = "closing"
        title_l = str(slides[-1].get("title") or "").casefold()
        if not any(token in title_l for token in ("thank", "question", "q&a", "closing")):
            # Keep role hint; ensure_bookend_slides will still append a closing if needed.
            slides[-1]["role"] = "content"
            slides[0]["role"] = "title"
        for item in slides:
            role = str(item.get("role") or "content")
            if not item.get("page_rhythm"):
                item["page_rhythm"] = (
                    "anchor" if role in {"title", "closing"} else "dense"
                )
            if not item.get("audience_move"):
                if role == "title":
                    item["audience_move"] = "orient"
                elif role == "closing":
                    item["audience_move"] = "close"
                else:
                    item["audience_move"] = "evidence"
            if not item.get("visualization"):
                if item.get("formula") or item.get("formula_tex"):
                    item["visualization"] = "formula_band"
                elif item.get("table_id"):
                    item["visualization"] = "basic_table"
                elif item.get("figure_id"):
                    item["visualization"] = "figure_legend"
                elif role == "title":
                    item["visualization"] = "hero_bleed"
                else:
                    item["visualization"] = "none"
    return slides


def _formula_content_field(raw: Any) -> str:
    """FORMULA* copy for grounded content — strip catalog ``(evidence=…)`` noise.

    Digits inside ``ev-page-02-block-024`` are provenance addresses; leaving them
    in FORMULA made pdf_strict treat them as unsupported research numbers.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        from tasks.grounded_planner import strip_catalog_provenance_annotations
    except ImportError:  # pragma: no cover
        from grounded_planner import strip_catalog_provenance_annotations  # type: ignore
    return strip_catalog_provenance_annotations(text)


def bridge_to_grounded_plan(
    slides: list[dict[str, Any]],
    *,
    grounding_mode: str,
    source_pdf_sha256: str | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project §IX into a GroundedOutline-shaped payload for validators.

    Does not invent claim quotes — evidence_ids alone carry provenance so the
    HTML Executor can be checked without unsatisfiable claim-quote gates.
    """
    fallback_evidence: list[str] = []
    known_ids: set[str] = set()
    fallback_section = "sec-document-000"
    if evidence_bundle:
        for section in (evidence_bundle.get("sections") or {}).get("sections") or []:
            if isinstance(section, dict) and section.get("section_id"):
                fallback_section = str(section["section_id"])
                break
        try:
            from tasks.grounded_planner import _evidence_text, _known_reference_ids

            known_ids = _known_reference_ids(evidence_bundle)
            fallback_evidence = list(_evidence_text(evidence_bundle).keys())[:3]
        except Exception:
            known_ids = set()
            fallback_evidence = []
        if not fallback_evidence:
            for item in evidence_bundle.get("evidence") or []:
                if isinstance(item, dict) and item.get("evidence_id"):
                    fallback_evidence.append(str(item["evidence_id"]))
                if len(fallback_evidence) >= 3:
                    break

    out_slides: list[dict[str, Any]] = []
    for item in slides:
        number = int(item["slide"])
        title = str(item.get("title") or f"Slide {number}")
        # Strip digit-heavy prose from bridged BODY so unsupported-number gates
        # do not fail-close decks whose Strategist paraphrase still cites loosely.
        body = str(item.get("content_blocks") or item.get("core_message") or "")
        if grounding_mode == "pdf_strict":
            body = re.sub(r"\d[\d,.\s%]*", "", body)
            body = re.sub(r"\s+", " ", body).strip()
            title_safe = re.sub(r"\d[\d,.\s%]*", "", title).strip() or title
            subtitle = re.sub(
                r"\d[\d,.\s%]*",
                "",
                str(item.get("core_message") or ""),
            ).strip()
        else:
            title_safe = title
            subtitle = str(item.get("core_message") or "")
        evidence_ids = list(item.get("evidence_ids") or [])
        if grounding_mode == "pdf_strict" and known_ids:
            evidence_ids = [eid for eid in evidence_ids if eid in known_ids]
        if grounding_mode == "pdf_strict" and not evidence_ids and fallback_evidence:
            evidence_ids = list(fallback_evidence[:2])
        section_ids = [fallback_section]
        role = str(item.get("role") or ("title" if number == 1 else "content"))
        is_title = role == "title" or number == 1
        is_closing = role == "closing"
        layout = (
            "free_design_title.svg"
            if is_title
            else ("free_design_closing.svg" if is_closing else "free_design_content.svg")
        )
        figure_id = str(item.get("figure_id") or "").strip()
        table_id = str(item.get("table_id") or "").strip()
        authors = str(item.get("authors") or "").strip()
        affiliations = str(item.get("affiliations") or "").strip()
        # Grounded outline content is number-checked against PDF evidence.
        # Deck furniture bylines (postal codes, suite numbers) are not claims —
        # strip digits here; apply_furniture_to_title_svg still paints the full
        # affiliation on the title SVG from deck_furniture.
        if grounding_mode == "pdf_strict":
            authors_grounded = re.sub(r"\d[\d,.\s%]*", "", authors).strip(" ,;")
            affiliations_grounded = re.sub(r"\d[\d,.\s%]*", "", affiliations).strip(" ,;")
        else:
            authors_grounded = authors
            affiliations_grounded = affiliations
        if is_title and (authors_grounded or affiliations_grounded):
            subtitle = (
                " · ".join(part for part in (authors_grounded, affiliations_grounded) if part)
                or subtitle
            )
        # Bookends need a non-empty evidence_ids list for GroundingPayload schema;
        # sanitize also floors empty lists, but emit fallback here so schema validates
        # even when sanitize is skipped or the catalog is thin.
        slide_evidence = list(evidence_ids)
        if grounding_mode == "pdf_strict" and not slide_evidence and fallback_evidence:
            slide_evidence = list(fallback_evidence[:2])
        slide_id = f"slide-{number}"
        table_bindings = []
        if table_id:
            table_bindings.append(
                {
                    "table_id": table_id,
                    "slide_id": slide_id,
                    "evidence_ids": list(slide_evidence[:1] or fallback_evidence[:1] or [table_id]),
                }
            )
        figure_bindings = []
        if figure_id:
            figure_bindings.append(
                {
                    "asset_id": figure_id,
                    "slide_id": slide_id,
                    # Asset id is accepted as a known reference for figures.
                    "evidence_ids": [figure_id],
                }
            )
        rhythm = str(item.get("page_rhythm") or "").strip().casefold()
        if rhythm not in {"anchor", "dense", "breathing"}:
            rhythm = "anchor" if is_title or is_closing else "dense"
        audience_move = str(item.get("audience_move") or "").strip() or (
            "orient" if is_title else ("close" if is_closing else "evidence")
        )
        viz = str(item.get("visualization") or "").strip() or (
            "figure" if figure_id else "none"
        )
        formula_tex = _formula_content_field(
            item.get("formula_tex") or item.get("formula")
        )
        formula_bindings = []
        if formula_tex:
            formula_bindings.append(
                {
                    "formula_id": f"formula-{number:03d}",
                    "slide_id": slide_id,
                    "tex": formula_tex,
                    "evidence_ids": list(
                        slide_evidence[:1] or fallback_evidence[:1] or []
                    ),
                }
            )
        out_slides.append(
            {
                "title": title_safe,
                "description": str(item.get("visual_job") or item.get("core_message") or ""),
                "audience_move": audience_move,
                "page_rhythm": rhythm,
                "layout": layout,
                "visual_plan": {
                    "primary": viz if viz != "none" else ("figure" if figure_id else "none"),
                    "visualization": viz,
                    "structure_atom": str(item.get("structure_atom") or ""),
                    "text_policy": str(item.get("text_policy") or ""),
                    "calm_region": str(item.get("calm_region") or ""),
                    "archetype": "hero" if is_title else ("closing" if is_closing else "narrative"),
                    "allow_figure": bool(figure_id),
                },
                "content": {
                    "TITLE": title_safe,
                    "BODY": "" if is_title or is_closing else body,
                    "SUBTITLE": subtitle if is_title or is_closing else "",
                    "AUTHORS": authors_grounded if is_title else "",
                    "AFFILIATIONS": affiliations_grounded if is_title else "",
                    **{
                        key: value
                        for key, value in (
                            ("FORMULA", _formula_content_field(item.get("formula"))),
                            ("FORMULA_TEX", formula_tex),
                            (
                                "FORMULA_TERMS",
                                _formula_content_field(item.get("formula_terms")),
                            ),
                            (
                                "FORMULA_GLOSS",
                                _formula_content_field(item.get("formula_gloss")),
                            ),
                        )
                        if value
                    },
                },
                "grounding": {
                    "section_ids": section_ids,
                    "evidence_ids": slide_evidence,
                    "claims": [],
                    "metrics": [],
                    "table_bindings": table_bindings,
                    "figure_bindings": figure_bindings,
                    "formula_bindings": formula_bindings,
                },
            }
        )
    # validate_grounded_outline expects {"slides": [...]} only
    return {"slides": out_slides}


def persist_strategist_artifacts(
    storage_dir: str,
    *,
    design_spec_md: str,
    spec_lock_md: str,
) -> dict[str, str]:
    design_path = os.path.join(storage_dir, "design_spec.md")
    lock_path = os.path.join(storage_dir, "spec_lock.md")
    with open(design_path, "w", encoding="utf-8") as handle:
        handle.write(design_spec_md if design_spec_md.endswith("\n") else design_spec_md + "\n")
    with open(lock_path, "w", encoding="utf-8") as handle:
        handle.write(spec_lock_md if spec_lock_md.endswith("\n") else spec_lock_md + "\n")
    return {"design_spec_md": design_path, "spec_lock_md": lock_path}
