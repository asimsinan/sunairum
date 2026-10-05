"""Typed Strategist slide IR + leak sanitize (pre-paint hard gate)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RoleName = Literal["title", "content", "closing", "hero"]

_ASSET_IN_CONTENT_RE = re.compile(
    r"^\s*[-*]?\s*(?:\*\*)?(?:table|figure)(?:\*\*)?\s*:?\s*`?"
    r"(src-table-\d+|pdf-page-[A-Za-z0-9._-]+)`?"
    r"|^\s*[-*]?\s*`?(src-table-\d+|pdf-page-[A-Za-z0-9._-]+)`?\s*$"
    r"|\bsrc-table-\d+\b"
    r"|\bpdf-page-[A-Za-z0-9._-]+\b",
    re.I,
)
_TABLE_ID_RE = re.compile(r"\b(src-table-\d+)\b", re.I)
_FIGURE_ID_RE = re.compile(r"\b(pdf-page-[A-Za-z0-9._-]+)\b", re.I)
_HERO_DUMP_RE = re.compile(
    r"^\s*[-*]?\s*(?:\*\*)?(?:HERO|contribution(?:s)?|key contribution|"
    r"our contributions?|agenda|outline)(?:\*\*)?\b",
    re.I,
)
_INSTRUCTIONAL_OPENER_RE = re.compile(
    r"^\s*(Introduce|Explain|Describe|Present|Cover|Highlight|Mention|Compare)\b",
    re.I,
)
_BULLET_LINE_RE = re.compile(r"^\s*[-*]\s+", re.M)


class StrategistSlideIR(BaseModel):
    model_config = ConfigDict(extra="allow")

    slide: int = Field(ge=1)
    slide_id: str = ""
    role: RoleName = "content"
    title: str = ""
    core_message: str = ""
    layout_intent: str = ""
    content_blocks: str = ""
    visual_job: str = ""
    formula: str = ""
    formula_terms: str = ""
    formula_gloss: str = ""
    authors: str = ""
    affiliations: str = ""
    body: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    figure_id: str = ""
    table_id: str = ""
    figure_field: str = ""
    table_field: str = ""


class StrategistDeckIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "sunairum.strategist-ir/v1"
    slides: list[StrategistSlideIR] = Field(min_length=1)

    @classmethod
    def from_parsed(cls, parsed: list[dict[str, Any]]) -> "StrategistDeckIR":
        slides: list[StrategistSlideIR] = []
        for item in parsed or []:
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            role = str(payload.get("role") or "content").strip().casefold()
            if role not in {"title", "content", "closing", "hero"}:
                role = "content"
            payload["role"] = role
            try:
                slides.append(StrategistSlideIR.model_validate(payload))
            except Exception:
                # Best-effort: coerce slide number.
                try:
                    payload["slide"] = int(payload.get("slide") or len(slides) + 1)
                except (TypeError, ValueError):
                    payload["slide"] = len(slides) + 1
                slides.append(StrategistSlideIR.model_validate(payload))
        if not slides:
            raise ValueError("StrategistDeckIR.from_parsed: empty slide list")
        return cls(slides=slides)

    def to_slide_dicts(self) -> list[dict[str, Any]]:
        return [slide.model_dump() for slide in self.slides]


def _is_instructional(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    first = re.split(r"(?<=[.!?])\s+", raw, maxsplit=1)[0]
    return bool(
        _INSTRUCTIONAL_OPENER_RE.search(first) or _INSTRUCTIONAL_OPENER_RE.search(raw)
    )


def _content_lines(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    # Multi-line Content or single blob with embedded newlines / "; ".
    if "\n" in raw:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    # Single-line " - a; - b" style rarely appears; keep as one line.
    return [raw]


def _join_content(lines: list[str]) -> str:
    if not lines:
        return ""
    if all(ln.lstrip().startswith(("-", "*")) for ln in lines):
        return "\n".join(lines)
    if len(lines) == 1:
        return lines[0]
    return "\n".join(f"- {ln.lstrip('-* ').strip()}" for ln in lines)


def validate_and_sanitize_deck(
    deck: StrategistDeckIR,
    *,
    evidence_bundle: dict[str, Any] | None = None,
) -> tuple[StrategistDeckIR, dict[str, Any]]:
    """Hard-gate text leaks; return sanitized deck + report."""
    del evidence_bundle  # reserved for future catalog checks
    errors: list[str] = []
    warnings: list[dict[str, Any]] = []
    sanitizations: list[dict[str, Any]] = []

    if not deck.slides:
        errors.append("empty_deck")
        return deck, {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "sanitizations": sanitizations,
        }

    # Re-assert bookend roles when present.
    first = deck.slides[0]
    last = deck.slides[-1]
    if first.role not in {"title", "hero"}:
        warnings.append(
            {"slide": first.slide, "code": "bookend_first_not_title", "detail": first.role}
        )
    if last.role != "closing" and len(deck.slides) >= 2:
        # ensure_bookend_slides may still fix; flag only.
        warnings.append(
            {"slide": last.slide, "code": "bookend_last_not_closing", "detail": last.role}
        )

    out_slides: list[StrategistSlideIR] = []
    for slide in deck.slides:
        data = slide.model_dump()
        role = str(data.get("role") or "content")
        content = str(data.get("content_blocks") or "")
        lines = _content_lines(content)
        kept: list[str] = []

        for line in lines:
            plain = re.sub(r"[*`]", "", line).strip()
            table_m = _TABLE_ID_RE.search(line)
            figure_m = _FIGURE_ID_RE.search(line)
            looks_asset = bool(_ASSET_IN_CONTENT_RE.search(line) or table_m or figure_m)

            if looks_asset and (table_m or figure_m or re.search(r"(?i)\b(?:table|figure)\b", plain)):
                if table_m and not str(data.get("table_id") or "").strip():
                    data["table_id"] = table_m.group(1)
                    if not str(data.get("table_field") or "").strip():
                        data["table_field"] = table_m.group(1)
                if figure_m and not str(data.get("figure_id") or "").strip():
                    data["figure_id"] = figure_m.group(1)
                    if not str(data.get("figure_field") or "").strip():
                        data["figure_field"] = figure_m.group(1)
                sanitizations.append(
                    {
                        "slide": data["slide"],
                        "code": "strip_asset_from_content",
                        "detail": line[:120],
                    }
                )
                continue

            if role in {"title", "hero"} and _HERO_DUMP_RE.search(line):
                sanitizations.append(
                    {
                        "slide": data["slide"],
                        "code": "strip_title_contribution_dump",
                        "detail": line[:120],
                    }
                )
                continue

            kept.append(line)

        if role == "closing":
            bullet_n = sum(1 for ln in kept if _BULLET_LINE_RE.match(ln) or len(kept) > 1)
            if len(kept) > 1 or bullet_n > 1:
                # Collapse extras into core_message if empty.
                extras = [
                    re.sub(r"^\s*[-*]\s*", "", ln).strip()
                    for ln in kept
                    if ln.strip()
                ]
                if not str(data.get("core_message") or "").strip() and extras:
                    # Prefer a non-title line.
                    title_l = str(data.get("title") or "").casefold()
                    pick = next(
                        (e for e in extras if e.casefold() != title_l),
                        extras[0],
                    )
                    data["core_message"] = pick[:240]
                kept = []
                sanitizations.append(
                    {
                        "slide": data["slide"],
                        "code": "collapse_closing_content",
                        "detail": f"dropped_{len(extras)}_lines",
                    }
                )

        data["content_blocks"] = _join_content(kept)

        if role == "content" and _is_instructional(data["content_blocks"]):
            warnings.append(
                {
                    "slide": data["slide"],
                    "code": "instructional_content",
                    "detail": data["content_blocks"][:80],
                }
            )

        out_slides.append(StrategistSlideIR.model_validate(data))

    out = StrategistDeckIR(slides=out_slides)
    ok = not errors
    return out, {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "sanitizations": sanitizations,
    }


def persist_strategist_ir(
    storage_dir: str,
    deck: StrategistDeckIR,
    report: dict[str, Any],
) -> dict[str, str]:
    """Write validation/strategist_ir.json + strategist_ir_report.json."""
    validation_dir = os.path.join(storage_dir, "validation")
    os.makedirs(validation_dir, exist_ok=True)
    ir_path = os.path.join(validation_dir, "strategist_ir.json")
    report_path = os.path.join(validation_dir, "strategist_ir_report.json")
    with open(ir_path, "w", encoding="utf-8") as handle:
        json.dump(deck.model_dump(), handle, ensure_ascii=False, indent=2)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return {"strategist_ir": ir_path, "strategist_ir_report": report_path}


def sanitize_parsed_slides(
    parsed: list[dict[str, Any]],
    *,
    storage_dir: str | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse-dict helper used by free_design after parse_section_ix_slides."""
    if not parsed:
        return parsed
    deck = StrategistDeckIR.from_parsed(parsed)
    deck, report = validate_and_sanitize_deck(deck, evidence_bundle=evidence_bundle)
    if storage_dir:
        try:
            persist_strategist_ir(storage_dir, deck, report)
        except OSError as error:
            print(f"[strategist_ir] persist failed: {error}")
    n = len(report.get("sanitizations") or [])
    w = len(report.get("warnings") or [])
    if n or w:
        print(f"[strategist_ir] sanitized={n} warnings={w}")
    return deck.to_slide_dicts()
