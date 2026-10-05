"""Strict contracts for PDF-grounded planning and rendering."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GroundingBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(GroundingBase):
    evidence_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    quote: str = ""


class EvidenceItem(GroundingBase):
    evidence_id: str
    kind: Literal[
        "heading", "paragraph", "list", "formula", "table",
        "table_caption", "figure", "figure_caption", "reference", "other",
    ]
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    bbox: list[float] | None = None
    section_id: str | None = None
    text: str = ""
    text_sha256: str
    source_pdf_sha256: str
    parser: str
    parser_version: str = "unknown"


class SectionNode(GroundingBase):
    section_id: str
    title: str
    level: int = Field(ge=1)
    parent_section_id: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    child_section_ids: list[str] = Field(default_factory=list)


class SourceCell(GroundingBase):
    cell_id: str
    text: str
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)
    evidence_id: str | None = None


class SourceTable(GroundingBase):
    table_id: str
    evidence_id: str
    section_id: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    caption: str = ""
    caption_evidence_id: str | None = None
    headers: list[SourceCell] = Field(default_factory=list)
    rows: list[list[SourceCell]] = Field(default_factory=list)
    source_bbox: list[float] | None = None
    source_pdf_sha256: str
    table_sha256: str
    validation_status: Literal["valid", "needs_review", "invalid"]


class SourceAsset(GroundingBase):
    asset_id: str
    file: str
    source_type: Literal["pdf_raster", "pdf_vector", "formula", "unknown"]
    page: int = Field(ge=1)
    source_pdf_sha256: str
    sha256: str
    width: int | None = None
    height: int | None = None
    placed_ratio: float | None = None
    bbox: list[float] | None = None
    caption_evidence_id: str | None = None
    source_asset_links: list[str] = Field(default_factory=list)
    status: Literal["verified", "needs_review", "invalid"] = "verified"


class SourceFormula(GroundingBase):
    formula_id: str
    evidence_id: str
    section_id: str | None = None
    page: int = Field(ge=1)
    latex: str
    source_pdf_sha256: str
    source_asset_id: str | None = None
    rendering_status: Literal["available", "source-image", "needs_review"] = "available"


class ClaimSpec(GroundingBase):
    claim_id: str
    text: str
    support_type: Literal["source_verbatim", "source_paraphrase", "derived"]
    evidence_ids: list[str] = Field(min_length=1)
    source_quote: str = ""
    citation_pages: list[int] = Field(default_factory=list)
    derivation: dict[str, Any] | None = None

    @field_validator("support_type", mode="before")
    @classmethod
    def normalize_support_type(cls, value: Any) -> str:
        raw = str(value or "source_paraphrase").casefold().replace("-", "_")
        if any(token in raw for token in ("verbatim", "exact", "quote")):
            return "source_verbatim"
        if any(token in raw for token in ("derived", "calculated", "calculation")):
            return "derived"
        # Models often emit "direct" / "directly_supported" for evidenced claims.
        # Unrecognized labels soft-coerce to paraphrase (same pattern as
        # TableBinding.transform → source_subset): vocabulary noise must not
        # hard-fail a deck; evidence/quote checks remain the real gate.
        return "source_paraphrase"


class MetricSpec(GroundingBase):
    metric_id: str
    label: str
    value: float | str
    unit: str = ""
    baseline: str = ""
    population: str = ""
    period: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    derivation: dict[str, Any] | None = None


class TableBinding(GroundingBase):
    table_id: str
    slide_id: str
    selected_columns: list[str] = Field(default_factory=list)
    selected_rows: list[str] = Field(default_factory=list)
    transform: Literal["source_full", "source_subset", "source_transpose", "derived"] = "source_full"
    evidence_ids: list[str] = Field(min_length=1)

    @field_validator("transform", mode="before")
    @classmethod
    def normalize_transform(cls, value: Any) -> str:
        aliases = {
            "full": "source_full",
            "source": "source_full",
            "subset": "source_subset",
            "rows_subset": "source_subset",
            "columns_subset": "source_subset",
            "transpose": "source_transpose",
            "calculated": "derived",
        }
        raw = str(value or "source_full").casefold().replace("-", "_")
        normalized = aliases.get(raw, raw)
        if "subset" in normalized or "select" in normalized:
            normalized = "source_subset"
        elif "transpose" in normalized:
            normalized = "source_transpose"
        elif "derive" in normalized or "calcul" in normalized:
            normalized = "derived"
        elif normalized in {"source", "full", "source_data", "source_table"}:
            normalized = "source_full"
        return "source_subset" if normalized not in {"source_full", "source_subset", "source_transpose", "derived"} else normalized


class FigureBinding(GroundingBase):
    asset_id: str
    slide_id: str
    role: str = "primary_figure"
    caption_evidence_id: str | None = None
    citation_pages: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class FormulaBinding(GroundingBase):
    formula_id: str
    slide_id: str
    render_policy: Literal["source_latex", "source_image"] = "source_latex"
    evidence_ids: list[str] = Field(min_length=1)


class SectionCoverage(GroundingBase):
    section_id: str
    slide_ids: list[str] = Field(min_length=1)
    coverage_mode: Literal["full", "grouped", "compressed", "summary"]
    required_evidence_ids: list[str] = Field(min_length=1)
    compression_level: Literal["none", "low", "medium", "high"] = "none"


class GroundedSlidePlan(GroundingBase):
    slide_id: str
    title: str
    section_ids: list[str] = Field(min_length=1)
    coverage_mode: Literal["full", "grouped", "compressed", "summary"]
    layout: str
    archetype: str
    claims: list[ClaimSpec] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)
    table_bindings: list[TableBinding] = Field(default_factory=list)
    figure_bindings: list[FigureBinding] = Field(default_factory=list)
    formula_bindings: list[FormulaBinding] = Field(default_factory=list)
    citations: list[EvidenceRef] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)


class GroundedDeckPlan(GroundingBase):
    schema_version: str = "sunairum.grounded-plan/v1"
    source_pdf_sha256: str
    grounding_mode: Literal["pdf_strict", "source_grounded", "scratch"]
    requested_slide_count: int = Field(ge=1)
    actual_slide_count: int = Field(ge=1)
    coverage_compressed: bool = False
    section_coverage: list[SectionCoverage] = Field(default_factory=list)
    slides: list[GroundedSlidePlan] = Field(min_length=1)
    evidence_manifest_sha256: str


class GroundingPayload(GroundingBase):
    # section_ids / evidence_ids may be empty before normalize floors them.
    # Semantic validate_grounded_outline still emits no-evidence / unknown-section;
    # min_length=1 here previously rejected free_design bookends and thin catalogs
    # as opaque "shape invalid" before any citation check ran.
    section_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[ClaimSpec] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)
    table_bindings: list[TableBinding] = Field(default_factory=list)
    figure_bindings: list[FigureBinding] = Field(default_factory=list)
    formula_bindings: list[FormulaBinding] = Field(default_factory=list)


class GroundedOutlineSlide(GroundingBase):
    title: str
    description: str = ""
    # validate_outline_plan requires these of every mode, so a pdf_strict outline
    # carries them too. The base model forbids extras, so they must be declared
    # here or the deck-level rhythm tags would read as schema violations.
    audience_move: str = ""
    page_rhythm: str = ""
    # Content planner + stamp_provisional_layouts always emit these before
    # validate_grounded_outline; without them, extra="forbid" aborts the run.
    slide_id: str = ""
    layout_source: str = ""
    layout: str
    visual_plan: dict[str, Any] = Field(default_factory=dict)
    diagram: dict[str, Any] | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    grounding: GroundingPayload


class GroundedOutline(GroundingBase):
    slides: list[GroundedOutlineSlide] = Field(min_length=1)
