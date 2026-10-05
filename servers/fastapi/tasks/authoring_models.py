"""Shared Pydantic contracts for the authoring pipeline.

Source of truth for content_plan / design_spec / QA gate reports.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthoringBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Content plan ────────────────────────────────────────────────────────────


class ContentSlide(AuthoringBase):
    slide_id: str
    title: str
    core_message: str = ""
    audience_move: str = ""
    page_rhythm: str = ""
    description: str = ""
    section_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    table_bindings: list[dict[str, Any]] = Field(default_factory=list)
    figure_bindings: list[dict[str, Any]] = Field(default_factory=list)
    formula_bindings: list[dict[str, Any]] = Field(default_factory=list)
    # Provisional copy keys (TITLE/BODY/…) before layout-bound components exist.
    content: dict[str, Any] = Field(default_factory=dict)


class ContentPlan(AuthoringBase):
    schema_version: str = "sunairum.content-plan/v1"
    locale: str = "en"
    grounding_mode: Literal["pdf_strict", "source_grounded", "scratch"] = "scratch"
    source_pdf_sha256: str | None = None
    requested_slide_count: int = Field(default=1, ge=1)
    coverage_compressed: bool = False
    coverage_plan: list[dict[str, Any]] = Field(default_factory=list)
    slides: list[ContentSlide] = Field(min_length=1)


# ── Design spec ─────────────────────────────────────────────────────────────


CopyTexture = Literal["bullets", "cards", "prose", "callout+figure", "title", "metrics"]
DeckMode = Literal["template", "scratch", "design_reference", "free_design"]
Density = Literal["low", "medium", "high"]
ImageStrategyMode = Literal["pdf", "ai", "both", "none", "auto"]


class ImageStrategy(AuthoringBase):
    mode: ImageStrategyMode = "auto"
    # Distinguish design assets (allowed) from pack subject JPEGs (TCS-withheld).
    allow_pack_subject_photos: bool = False
    ai_prompt_prefix: str = ""
    prefer_pdf_figures: bool = True


class DeckDesignLock(AuthoringBase):
    mode: DeckMode = "scratch"
    canvas: dict[str, Any] = Field(default_factory=lambda: {"width": 1280, "height": 720})
    theme_tone: str = ""
    palette: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    margins: dict[str, float] = Field(default_factory=dict)
    chrome_rules: list[str] = Field(default_factory=list)
    image_strategy: ImageStrategy = Field(default_factory=ImageStrategy)
    icon_stroke: str = "rounded"
    density_default: Density = "medium"
    authority: Literal["pack", "user", "agent", "default", "fallback"] = "default"
    fill_pack_id: str | None = None
    design_pack_id: str | None = None
    source: Literal["model", "fallback", "pack", "user"] = "fallback"


class SlideDesignPlan(AuthoringBase):
    slide_id: str
    layout_pattern: str = "narrative"
    zones: dict[str, str] = Field(
        default_factory=lambda: {"figure": "none", "legend": "none", "copy": "main"}
    )
    density: Density = "medium"
    icons: list[str] = Field(default_factory=list)
    copy_texture: CopyTexture = "prose"
    forbidden_overlays: list[str] = Field(
        default_factory=lambda: ["synthesize-over-figure", "architecture-over-image"]
    )
    figure_role: str | None = None
    ornament_kind: str = "none"
    accent_role: str = "accent1"


class DesignSpec(AuthoringBase):
    schema_version: str = "sunairum.design-spec/v1"
    deck: DeckDesignLock = Field(default_factory=DeckDesignLock)
    slides: list[SlideDesignPlan] = Field(default_factory=list)


# ── Pre-PPTX QA report wrapper ──────────────────────────────────────────────


class QaReport(AuthoringBase):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "sunairum.qa-report/v1"
    status: Literal["pass", "fail", "advisory"] = "pass"
    blocking: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    gate_green: bool = True
    require_user_generate: bool = False


# ── Pre-storyboard authoring gate ───────────────────────────────────────────


class AuthoringGateIssue(AuthoringBase):
    code: str
    severity: Literal["blocking", "soft"] = "blocking"
    message: str
    slide_id: str | None = None
    repair_target: str | None = None


class AuthoringGateReport(AuthoringBase):
    schema_version: str = "sunairum.authoring-gate/v1"
    gate_green: bool = True
    blocking: bool = False
    issues: list[AuthoringGateIssue] = Field(default_factory=list)
    repair_targets: list[str] = Field(default_factory=list)
    repairs_applied: list[str] = Field(default_factory=list)
    repair_attempted: bool = False


# ── I/O helpers ─────────────────────────────────────────────────────────────


def write_json(path: str, payload: BaseModel | dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, ensure_ascii=False, indent=2, fp=handle)
    os.replace(tmp, path)


def content_plan_path(validation_dir: str) -> str:
    return os.path.join(validation_dir, "content_plan.json")


def design_spec_path(validation_dir: str) -> str:
    return os.path.join(validation_dir, "design_spec.json")


def authoring_gate_path(validation_dir: str) -> str:
    return os.path.join(validation_dir, "authoring_gate.json")


def content_plan_to_presentation_slides(plan: ContentPlan) -> list[dict[str, Any]]:
    """Bridge ContentPlan → presentation_data['slides'] shape."""
    slides: list[dict[str, Any]] = []
    for item in plan.slides:
        content = dict(item.content) if item.content else {}
        if "TITLE" not in content and item.title:
            content["TITLE"] = item.title
        if "BODY" not in content and item.core_message:
            content["BODY"] = item.core_message
        slide: dict[str, Any] = {
            "slide_id": item.slide_id,
            "title": item.title,
            "description": item.description or item.core_message,
            "audience_move": item.audience_move,
            "page_rhythm": item.page_rhythm,
            "content": content,
            "grounding": {
                "section_ids": list(item.section_ids),
                "evidence_ids": list(item.evidence_ids),
                "claims": list(item.claims),
                "metrics": list(item.metrics),
                "table_bindings": list(item.table_bindings),
                "figure_bindings": list(item.figure_bindings),
                "formula_bindings": list(item.formula_bindings),
            },
        }
        slides.append(slide)
    return slides


def presentation_slides_to_content_plan(
    slides: list[dict[str, Any]],
    *,
    locale: str = "en",
    grounding_mode: str = "scratch",
    source_pdf_sha256: str | None = None,
    requested_slide_count: int | None = None,
    coverage_plan: list[dict[str, Any]] | None = None,
    coverage_compressed: bool = False,
) -> ContentPlan:
    """Extract a ContentPlan from legacy outline slides (strip layout/visual)."""
    content_slides: list[ContentSlide] = []
    for index, slide in enumerate(slides, start=1):
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        # Prefer components if present but store as flat content keys only.
        components = content.get("components") if isinstance(content.get("components"), dict) else None
        flat = dict(components) if components else {k: v for k, v in content.items() if k != "components"}
        slide_id = str(slide.get("slide_id") or f"slide-{index}")
        content_slides.append(
            ContentSlide(
                slide_id=slide_id,
                title=str(slide.get("title") or flat.get("TITLE") or f"Slide {index}"),
                core_message=str(slide.get("description") or flat.get("BODY") or "")[:2000],
                audience_move=str(slide.get("audience_move") or ""),
                page_rhythm=str(slide.get("page_rhythm") or ""),
                description=str(slide.get("description") or ""),
                section_ids=[str(s) for s in grounding.get("section_ids") or []],
                evidence_ids=[str(e) for e in grounding.get("evidence_ids") or []],
                claims=list(grounding.get("claims") or []),
                metrics=list(grounding.get("metrics") or []),
                table_bindings=list(grounding.get("table_bindings") or []),
                figure_bindings=list(grounding.get("figure_bindings") or []),
                formula_bindings=list(grounding.get("formula_bindings") or []),
                content=flat,
            )
        )
    return ContentPlan(
        locale=locale or "en",
        grounding_mode=grounding_mode if grounding_mode in {"pdf_strict", "source_grounded", "scratch"} else "scratch",
        source_pdf_sha256=source_pdf_sha256,
        requested_slide_count=requested_slide_count or len(content_slides),
        coverage_compressed=coverage_compressed,
        coverage_plan=list(coverage_plan or []),
        slides=content_slides,
    )
