"""Evidence-aware planning helpers used by PDF-strict generation."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

try:
    from .grounding_models import (
        ClaimSpec,
        FigureBinding,
        FormulaBinding,
        GroundedOutline,
        TableBinding,
    )
except ImportError:  # pragma: no cover - supports direct task imports
    from grounding_models import (
        ClaimSpec,
        FigureBinding,
        FormulaBinding,
        GroundedOutline,
        TableBinding,
    )

# Read from the models so the two cannot drift: a field added to a binding is accepted
# by the normalizer the moment it exists.
_BINDING_FIELDS = {
    "table_bindings": frozenset(TableBinding.model_fields),
    "figure_bindings": frozenset(FigureBinding.model_fields),
    "formula_bindings": frozenset(FormulaBinding.model_fields),
}


NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d{1,3}(?:[,\s]\d{3})+|\d+)"
    r"(?:[.,]\d+)?"
    r"(?:\s*(?:%|[x×]))?"
    r"(?![A-Za-z0-9])",
    re.I,
)
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'%-]{2,}")

# Level-1 headings that are paper back-matter, not talk content. Requiring them
# on a fixed-length deck (e.g. Acknowledgment + References at 12 slides) fail-closes
# pdf_strict runs that otherwise covered every substantive section.
_BACKMATTER_SECTION_RE = re.compile(
    r"(^|[-_/])("
    r"acknowledg?e?ments?"
    r"|references?"
    r"|bibliograph(?:y|ies)"
    r"|appendi(?:x|ces)"
    r"|supplementary([-_]?materials?)?"
    r"|funding"
    r"|conflicts?([-_]?of)?([-_]?interest)?"
    r"|author([-_]?contributions?)?"
    r"|data([-_]?availability)?"
    r"|ethics?"
    r")($|[-_/])",
    re.I,
)


def is_backmatter_section(section: dict[str, Any] | str) -> bool:
    """True for Acknowledgment / References / Appendix-style sections."""
    if isinstance(section, str):
        blob = section
    else:
        blob = " ".join(
            str(section.get(key) or "")
            for key in ("section_id", "title", "heading", "name")
        )
    normalized = re.sub(r"\s+", "-", blob.strip().casefold())
    return bool(_BACKMATTER_SECTION_RE.search(normalized))


def content_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sections that must be covered on the talk; back-matter is optional."""
    primary = [item for item in sections if not is_backmatter_section(item)]
    return primary or list(sections)


#: A decimal point that a PDF's math font set apart from its digits. Extractors emit the
#: Adam hyperparameters of *Attention Is All You Need* as "β 1 = 0 . 9 , β 2 = 0 . 98", so
#: a slide citing 0.98 was judged to have invented it and the slide was dropped. Restricted
#: to a fractional part of at most three digits, which is what a spaced decimal looks like;
#: a full year after a sentence-ending digit ("300,000 steps . 2017") is left alone rather
#: than fused into a number the source never states.
_SPACED_DECIMAL_RE = re.compile(r"(?<=\d)(?:\s+\.\s*|\.\s+)(?=\d{1,3}(?!\d))")

# Strategist / catalog provenance addresses. Digits inside these are not research claims
# (``ev-page-02-block-024`` → 2, 24 would otherwise fail-close formula slides).
_EVIDENCE_ANNOTATION_RE = re.compile(r"\(\s*evidence\s*=\s*[^)]*\)", re.I)
_CATALOG_ID_RE = re.compile(
    r"`?("
    r"ev-page-\d+-(?:block|table)-\d+"
    r"|src-table-\d+"
    r"|pdf-page-\d+-picture-\d+"
    r"|formula-[A-Za-z0-9._-]+"
    r"|sec-[A-Za-z0-9._-]+"
    r")`?",
    re.I,
)


def normalize_source_text(value: Any) -> str:
    """Normalize PDF line-break and math-spacing artifacts without changing facts."""
    text = unicodedata.normalize("NFKC", str(value or "")).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _SPACED_DECIMAL_RE.sub(".", text)


def strip_catalog_provenance_annotations(value: Any) -> str:
    """Drop ``(evidence=...)`` parentheticals from slide content; keep the claim/formula."""
    text = str(value or "")
    if not text:
        return ""
    text = _EVIDENCE_ANNOTATION_RE.sub(" ", text)
    # Planner output is occasionally split into separate card strings before
    # authoring ("(evidence=ev-..." / "ev-...)").  Remove both incomplete
    # halves as well as any remaining bare catalog address.  These identifiers
    # belong in the evidence ledger, never in audience-visible slide copy.
    text = re.sub(r"\(\s*evidence\s*=\s*[^)]*$", " ", text, flags=re.I)
    text = re.sub(r"^\s*(?:`?ev-page-[^`)\s;,]+`?\s*[;,]?\s*)+\)\s*$", " ", text, flags=re.I)
    text = _CATALOG_ID_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def scrub_catalog_numeric_noise(value: Any) -> str:
    """Remove catalog IDs and evidence= annotations before numeric claim extraction.

    §IX often appends ``(evidence=ev-page-02-block-024; ev-page-03-block-041)`` to
    FORMULA lines. Those digit runs are provenance addresses, not quantities; treating
    them as unsupported numbers abort every formula-bearing free_design deck.
    """
    text = normalize_source_text(value)
    if not text:
        return ""
    text = _EVIDENCE_ANNOTATION_RE.sub(" ", text)
    text = _CATALOG_ID_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def scrub_content_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip catalog provenance from all audience-copy fields."""
    def _scrub(value: Any, *, key: str = "") -> Any:
        # Preserve machine-readable evidence ownership fields.  Everything
        # else is potentially rendered by an LLM or deterministic fallback.
        if key.endswith("_id") or key.endswith("_ids") or key == "source_pdf_sha256":
            return deepcopy(value)
        if isinstance(value, str):
            return strip_catalog_provenance_annotations(value)
        if isinstance(value, list):
            return [_scrub(item) for item in value]
        if isinstance(value, dict):
            return {name: _scrub(item, key=str(name)) for name, item in value.items()}
        return deepcopy(value)

    return _scrub(payload) if isinstance(payload, dict) else payload


def canonical_numeric_tokens(value: Any, unit_hint: str = "") -> set[tuple[Decimal, str]]:
    """Return numeric values independent of JSON float formatting or PDF glyphs."""
    text = scrub_catalog_numeric_noise(value)
    hint = str(unit_hint or "").casefold()
    hint_unit = "%" if "%" in hint else "x" if "x" in hint or "×" in hint else ""
    tokens: set[tuple[Decimal, str]] = set()
    for match in NUMBER_RE.finditer(text):
        raw = match.group(0).strip().replace(" ", "")
        suffix = ""
        if raw.endswith("%"):
            suffix, raw = "%", raw[:-1]
        elif raw.endswith(("x", "X", "×")):
            suffix, raw = "x", raw[:-1]
        if "," in raw and "." not in raw:
            if raw.count(",") == 1 and len(raw.rsplit(",", 1)[1]) != 3:
                raw = raw.replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", "")
        try:
            tokens.add((Decimal(raw), suffix or hint_unit))
        except InvalidOperation:
            continue
    return tokens


def numeric_tokens_supported(candidate: Any, source_text: str, unit_hint: str = "") -> bool:
    source_tokens = canonical_numeric_tokens(source_text)
    for value, unit in canonical_numeric_tokens(candidate, unit_hint):
        if any(
            value == source_value
            and (not unit or not source_unit or unit == source_unit)
            for source_value, source_unit in source_tokens
        ):
            continue
        return False
    return True


def claim_tokens(value: Any) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(normalize_source_text(value))}


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_evidence_bundle(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir) / "sources"
    evidence_payload = _read(root / "source_evidence.json", {"evidence": []})
    return {
        "manifest": _read(root / "evidence_manifest.json", {}),
        "evidence": evidence_payload.get("evidence", []) if isinstance(evidence_payload, dict) else [],
        "structure": _read(root / "source_structure.json", {"pages": []}),
        "sections": _read(root / "source_sections.json", {"sections": []}),
        "tables": _read(root / "source_tables.json", {"tables": []}),
        "formulas": _read(root / "source_formulas.json", {"formulas": []}),
        "assets": _read(root / "source_assets.json", {"assets": []}),
    }


def _evidence_text(bundle: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in bundle.get("evidence", []) if isinstance(bundle.get("evidence"), list) else []:
        if isinstance(item, dict) and item.get("evidence_id"):
            values[str(item["evidence_id"])] = str(item.get("text", ""))
    for page in bundle.get("structure", {}).get("pages", []):
        for block in page.get("blocks", []) if isinstance(page, dict) else []:
            if not isinstance(block, dict):
                continue
            evidence_id = block.get("evidence_id")
            if not evidence_id:
                continue
            parts = []
            for key in ("text", "content", "latex", "caption", "table_body"):
                value = block.get(key)
                if isinstance(value, list):
                    value = " ".join(str(item) for item in value)
                if isinstance(value, str) and value.strip():
                    parts.append(value)
            values[str(evidence_id)] = " ".join(parts)
    for table in bundle.get("tables", {}).get("tables", []):
        if not isinstance(table, dict):
            continue
        evidence_id = table.get("evidence_id")
        if not evidence_id:
            continue
        cells = []
        for cell in table.get("headers", []) + [cell for row in table.get("rows", []) for cell in row]:
            if isinstance(cell, dict):
                cells.append(str(cell.get("text", "")))
        values[str(evidence_id)] = " ".join([str(table.get("caption", "")), *cells])
    return values


def _reference_text(bundle: dict[str, Any], reference: str, evidence_text: dict[str, str]) -> str:
    """Resolve evidence text through table, formula, and figure identities."""
    if reference in evidence_text:
        return evidence_text[reference]
    for table in bundle.get("tables", {}).get("tables", []):
        if isinstance(table, dict) and str(table.get("table_id")) == reference:
            return evidence_text.get(str(table.get("evidence_id")), "")
    for formula in bundle.get("formulas", {}).get("formulas", []):
        if isinstance(formula, dict) and str(formula.get("formula_id")) == reference:
            return str(formula.get("latex", ""))
    for asset in bundle.get("assets", {}).get("assets", []):
        if isinstance(asset, dict) and str(asset.get("asset_id")) == reference:
            return evidence_text.get(str(asset.get("caption_evidence_id")), "")
    return ""


def _source_table_errors(bundle: dict[str, Any], cited: set[str] | None = None) -> list[str]:
    """Faults in the source's tables, limited to the tables a deck actually renders.

    Sparse tables are normal in real papers: Table 3 of *Attention Is All You Need* says
    outright that unlisted values match the base model, so a faithful parse of it has
    rows narrower than its header. Judging every table in the document meant one such
    table made every possible outline invalid, including outlines that never mentioned
    it -- a 15-page paper with four tables could not produce any deck at all. A table we
    do not draw cannot be drawn wrongly, so only cited tables are judged.
    """
    errors: list[str] = []
    for table in bundle.get("tables", {}).get("tables", []):
        if not isinstance(table, dict):
            errors.append("source-table-invalid:unknown")
            continue
        table_id = str(table.get("table_id"))
        if cited is not None and table_id not in cited:
            continue
        if table.get("validation_status") not in {None, "valid"}:
            errors.append(f"source-table-invalid:{table_id}")
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not isinstance(headers, list) or not isinstance(rows, list):
            errors.append(f"source-table-invalid:{table_id}")
            continue
        width = len(headers)
        for row in rows:
            if not isinstance(row, list) or (width and len(row) != width):
                errors.append(f"source-table-shape-invalid:{table_id}")
                break
            for cell in row:
                if not isinstance(cell, dict):
                    errors.append(f"source-table-cell-invalid:{table_id}")
                    break
                for span_key in ("rowspan", "colspan"):
                    try:
                        if int(cell.get(span_key, 1)) < 1:
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append(f"source-table-span-invalid:{table_id}")
                        break
        for cell in headers:
            if not isinstance(cell, dict):
                errors.append(f"source-table-cell-invalid:{table_id}")
                continue
            for span_key in ("rowspan", "colspan"):
                try:
                    if int(cell.get(span_key, 1)) < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"source-table-span-invalid:{table_id}")
    return sorted(set(errors))


def validate_metric_derivation(metric: Any, slide_index: int) -> list[str]:
    """Validate the simple deterministic derivations accepted by the planner."""
    derivation = metric.derivation
    if not isinstance(derivation, dict):
        return []
    operation = str(derivation.get("operation") or "").casefold().replace("-", "_")
    if not operation:
        return [f"slide-{slide_index}:metric-derivation-invalid:{metric.metric_id}"]
    if operation in {"percentage", "percent", "percentage_of", "percent_of"}:
        numerator = derivation.get("numerator")
        denominator = derivation.get("denominator")
        if numerator is None or denominator is None:
            return [f"slide-{slide_index}:metric-derivation-denominator-missing:{metric.metric_id}"]
        try:
            numerator_value = float(numerator)
            denominator_value = float(denominator)
            metric_tokens = canonical_numeric_tokens(metric.value, str(metric.unit))
            if len(metric_tokens) != 1:
                raise ValueError
            actual_value = float(next(iter(metric_tokens))[0])
        except (TypeError, ValueError):
            return [f"slide-{slide_index}:metric-derivation-invalid:{metric.metric_id}"]
        if denominator_value == 0:
            return [f"slide-{slide_index}:metric-derivation-denominator-invalid:{metric.metric_id}"]
        expected_value = (numerator_value / denominator_value) * 100
        if not math.isclose(actual_value, expected_value, rel_tol=1e-6, abs_tol=0.01):
            return [f"slide-{slide_index}:metric-derivation-invalid:{metric.metric_id}"]
    return []


def evidence_catalog(bundle: dict[str, Any], max_chars: int = 60000) -> str:
    """Create a compact, tagged source catalog for the planner prompt.

    Budget is reserved per category. The catalog used to be emitted in one list
    -- sections, then every evidence line, then tables, figures and formulas --
    and truncated from the tail, so on any substantial paper the body text (much
    of it bibliography) consumed the whole budget and the planner never learned
    the source had a single table or figure. Evidence is the one elastic
    category, so it absorbs the truncation instead.
    """
    header = [
        "SOURCE EVIDENCE CATALOG. Use only these IDs. Every TABLE, FIGURE and "
        'FORMULA line carries an "evidence=" ID: put that ID in the evidence_ids '
        "of its binding, and in the evidence_ids of any claim or metric that uses "
        "a number, cell or caption from it. Numbers taken from a table are only "
        "supported by that table's evidence ID, not by nearby prose."
    ]
    section_lines: list[str] = []
    for section in bundle.get("sections", {}).get("sections", []):
        if isinstance(section, dict):
            section_lines.append(
                f"SECTION {section.get('section_id')} level={section.get('level')} "
                f"pages={section.get('page_start')}-{section.get('page_end')}: {section.get('title')}"
            )
    evidence_lines = [
        f"EVIDENCE {evidence_id}: {text}" for evidence_id, text in _evidence_text(bundle).items()
    ]
    lines: list[str] = []
    for table in bundle.get("tables", {}).get("tables", []):
        if isinstance(table, dict):
            table_id = str(table.get("table_id"))
            if _source_table_errors(bundle, {table_id}):
                # Malformed extraction cannot be rendered faithfully. Keeping it in
                # the planner catalog invited a binding that deterministic grounding
                # was then required to reject.
                continue
            cells = [
                str(cell.get("text", ""))
                for cell in table.get("headers", []) + [cell for row in table.get("rows", []) for cell in row]
                if isinstance(cell, dict) and str(cell.get("text", "")).strip()
            ]
            lines.append(
                f"TABLE {table.get('table_id')} page={table.get('page_start')} "
                f"evidence={table.get('evidence_id')} "
                f"caption={table.get('caption')} headers="
                f"{[cell.get('text', '') for cell in table.get('headers', []) if isinstance(cell, dict)]} "
                f"cells={cells}"
            )
    for asset in bundle.get("assets", {}).get("assets", []):
        if isinstance(asset, dict):
            caption = str(asset.get("caption") or asset.get("image_caption") or "").strip()
            # State the ID to cite in figure_bindings.evidence_ids. Left to guess,
            # the planner invented "ev-page-NN-figure-NNN", which no bundle mints.
            citable = str(asset.get("caption_evidence_id") or asset.get("asset_id") or "")
            line = (
                f"FIGURE {asset.get('asset_id')} page={asset.get('page')} "
                f"evidence={citable} "
                f"file={asset.get('file')} hash={asset.get('sha256')}"
            )
            # Without the caption the planner sees an opaque filename and has no
            # basis for deciding which slide a figure belongs on.
            lines.append(f"{line} caption={caption}" if caption else line)
    for formula in bundle.get("formulas", {}).get("formulas", []):
        if isinstance(formula, dict):
            lines.append(
                f"FORMULA {formula.get('formula_id')} page={formula.get('page')} "
                f"evidence={formula.get('evidence_id')}: {formula.get('latex', '')[:800]}"
            )

    # Structure and visual inventory come first and are kept whole where they
    # fit: they are small, and losing them costs the planner far more than
    # losing some prose.
    priority = header + section_lines + lines
    selected: list[str] = []
    total = 0
    # Cap the inventory so a source with very large tables cannot starve the
    # prose entirely; evidence is guaranteed at least half the budget.
    priority_budget = max(max_chars // 2, max_chars - sum(len(l) + 1 for l in evidence_lines))
    for line in priority:
        size = len(line) + (1 if selected else 0)
        if total + size > priority_budget:
            continue
        selected.append(line)
        total += size
    for line in evidence_lines:
        size = len(line) + (1 if selected else 0)
        if total + size > max_chars:
            break
        selected.append(line)
        total += size
    dropped = (len(priority) + len(evidence_lines)) - len(selected)
    if dropped:
        # This used to be silent, which is why a deck built from a catalog
        # missing every figure looked like a planning failure.
        print(
            f"[evidence_catalog] budget {max_chars} exceeded: dropped {dropped} of "
            f"{len(priority) + len(evidence_lines)} line(s)"
        )
    return "\n".join(selected)


def allocate_section_coverage(bundle: dict[str, Any], slide_count: int) -> list[dict[str, Any]]:
    """Map sections onto exactly ``slide_count`` slides.

    Slide 1 is reserved as the title plate. Content sections are allocated to
    slides 2..N so a fixed budget is not spent dumping the introduction onto the
    cover. When slides outnumbered sections the surplus used to all fall through
    to ``sections[-1]``; surplus is now spread over the richest sections with
    disjoint evidence slices.
    """
    all_sections = [item for item in bundle.get("sections", {}).get("sections", []) if isinstance(item, dict)]
    # Allocate talk slides over content sections only; Acknowledgment/References
    # stay optional so a fixed slide budget is not spent on back-matter.
    sections = content_sections(all_sections)
    if slide_count <= 0:
        return []
    if not sections:
        return [
            {
                "slide_id": f"slide-{index + 1}",
                "section_ids": ["sec-document-000"],
                "coverage_mode": "title" if index == 0 else "summary",
                "role": "title" if index == 0 else "content",
            }
            for index in range(slide_count)
        ]

    title_entry = {
        "slide_id": "slide-1",
        "section_ids": [str(sections[0].get("section_id"))],
        "coverage_mode": "title",
        "role": "title",
        "required_evidence_ids": [
            str(eid) for eid in (sections[0].get("evidence_ids") or [])[:1]
        ],
    }
    if slide_count == 1:
        title_entry["section_ids"] = [str(s.get("section_id")) for s in sections]
        title_entry["coverage_mode"] = "compressed" if len(sections) > 1 else "title"
        return [title_entry]

    content_slots = slide_count - 1
    content_plan = _allocate_content_sections(sections, content_slots)
    for offset, entry in enumerate(content_plan):
        entry["slide_id"] = f"slide-{offset + 2}"
        entry["role"] = "content"
    return [title_entry, *content_plan]


def _allocate_content_sections(
    sections: list[dict[str, Any]],
    slide_count: int,
) -> list[dict[str, Any]]:
    """Allocate content sections across ``slide_count`` non-title slides."""
    if slide_count <= 0:
        return []
    if slide_count <= len(sections):
        allocations: list[list[dict[str, Any]]] = [[] for _ in range(slide_count)]
        for index, section in enumerate(sections):
            bucket = min(slide_count - 1, index * slide_count // len(sections))
            allocations[bucket].append(section)
        result: list[dict[str, Any]] = []
        for index, group in enumerate(allocations):
            group = group or [sections[min(index, len(sections) - 1)]]
            mode = "full" if len(group) == 1 else ("compressed" if len(group) > 2 else "grouped")
            result.append({
                "slide_id": f"slide-{index + 1}",
                "section_ids": [str(section.get("section_id")) for section in group],
                "coverage_mode": mode,
                "required_evidence_ids": [
                    evidence_id
                    for section in group
                    for evidence_id in section.get("evidence_ids", [])[:3]
                ],
            })
        return result

    shares = [1] * len(sections)
    weights = [max(len(section.get("evidence_ids", []) or []), 1) for section in sections]
    for _ in range(slide_count - len(sections)):
        target = max(range(len(sections)), key=lambda i: weights[i] / shares[i])
        shares[target] += 1

    result = []
    for section, share in zip(sections, shares):
        evidence = [str(item) for item in section.get("evidence_ids", []) or []]
        for part in range(share):
            slice_size = -(-len(evidence) // share) if evidence else 0
            chunk = evidence[part * slice_size:(part + 1) * slice_size] if slice_size else []
            result.append({
                "slide_id": f"slide-{len(result) + 1}",
                "section_ids": [str(section.get("section_id"))],
                "coverage_mode": "full" if share == 1 else "detail",
                "coverage_part": part + 1,
                "coverage_parts": share,
                "required_evidence_ids": chunk[:3],
            })
    return result


def normalize_grounded_outline_payload(payload: Any, bundle: dict[str, Any] | None = None) -> Any:
    """Fill only deterministic metadata omitted by an otherwise usable LLM outline.

    Claim text, metric values, table cells, figures, and formulas are never
    synthesized here. Missing factual references remain schema errors. With a
    bundle, a table or formula binding is also pointed at its own evidence: the
    binding already names the table_id or formula_id, so which evidence backs it
    is a fact read from the bundle rather than a guess, and leaving that lookup
    to the model produced table-evidence-missing on correctly bound tables.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("slides"), list):
        return payload
    normalized = deepcopy(payload)
    own_evidence: dict[str, dict[str, str]] = {"table_bindings": {}, "formula_bindings": {}}
    known_refs: set[str] = set()
    if bundle:
        own_evidence["table_bindings"] = {
            str(item.get("table_id")): str(item.get("evidence_id"))
            for item in bundle.get("tables", {}).get("tables", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        own_evidence["formula_bindings"] = {
            str(item.get("formula_id")): str(item.get("evidence_id"))
            for item in bundle.get("formulas", {}).get("formulas", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        known_refs = _known_reference_ids(bundle)
    for slide_index, slide in enumerate(normalized["slides"], start=1):
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding")
        if not isinstance(grounding, dict):
            continue
        for claim_index, claim in enumerate(grounding.get("claims", []), start=1):
            if not isinstance(claim, dict):
                continue
            claim.setdefault("claim_id", f"claim-slide-{slide_index:02d}-{claim_index:02d}")
            claim.setdefault("support_type", "source_paraphrase")
            # Models commonly describe exact table-backed claims as `table_cell`
            # or `table_value`.
            # The grounding schema expresses the same provenance as source_verbatim;
            # normalize the alias so a valid table slide is not dropped on syntax.
            if claim.get("support_type") in {"table_cell", "table_value"}:
                claim["support_type"] = "source_verbatim"
            # ClaimSpec owns synonym + unknown→paraphrase mapping; apply here so
            # planner and pydantic stay aligned before model_validate.
            claim["support_type"] = ClaimSpec.normalize_support_type(claim.get("support_type"))
            claim.setdefault("source_quote", "")
            claim.setdefault("citation_pages", [])
        for metric_index, metric in enumerate(grounding.get("metrics", []), start=1):
            if not isinstance(metric, dict):
                continue
            metric.setdefault("metric_id", f"metric-slide-{slide_index:02d}-{metric_index:02d}")
            metric.setdefault("label", metric.get("metric_id", "metric"))
            metric.setdefault("unit", "")
            metric.setdefault("baseline", "")
            metric.setdefault("population", "")
            metric.setdefault("period", None)
            metric.setdefault("derivation", None)
            # A metric usually has no baseline, and the neighbouring "period": null
            # in the prompt makes null the natural answer; a numeric baseline
            # ("1.0", "600") is equally natural. These are provenance descriptors
            # that nothing renders, so a null-or-number mismatch must not sink the
            # whole deck -- metric.value and metric.unit stay numerically validated.
            for field in ("label", "unit", "baseline", "population"):
                value = metric.get(field)
                if value is None:
                    metric[field] = ""
                elif isinstance(value, (int, float)):
                    metric[field] = str(value)
        # A correction pass rewrites the whole document and sometimes files a
        # binding under the wrong list. The identifier it carries says what it
        # actually is, so re-file it rather than rejecting the deck over the
        # placement.
        binding_key_for_id = {
            "table_id": "table_bindings",
            "asset_id": "figure_bindings",
            "formula_id": "formula_bindings",
        }
        for binding_key in ("table_bindings", "figure_bindings", "formula_bindings"):
            retained: list[Any] = []
            for binding in grounding.get(binding_key, []) or []:
                target = binding_key
                if isinstance(binding, dict):
                    for id_field, correct_key in binding_key_for_id.items():
                        if binding.get(id_field):
                            target = correct_key
                            break
                if target == binding_key:
                    retained.append(binding)
                else:
                    grounding.setdefault(target, []).append(binding)
            if binding_key in grounding:
                grounding[binding_key] = retained
        known_ids = {
            "table_bindings": {
                str(item.get("table_id"))
                for item in (bundle or {}).get("tables", {}).get("tables", [])
                if isinstance(item, dict)
            },
            "figure_bindings": {
                str(item.get("asset_id"))
                for item in (bundle or {}).get("assets", {}).get("assets", [])
                if isinstance(item, dict)
            },
            "formula_bindings": {
                str(item.get("formula_id"))
                for item in (bundle or {}).get("formulas", {}).get("formulas", [])
                if isinstance(item, dict)
            },
        }
        id_field_for_key = {value: key for key, value in binding_key_for_id.items()}
        for binding_key in ("table_bindings", "figure_bindings", "formula_bindings"):
            usable: list[Any] = []
            for binding_index, binding in enumerate(grounding.get(binding_key, []), start=1):
                if not isinstance(binding, dict):
                    usable.append(binding)
                    continue
                # Strip the fields that belong to a different binding kind, left
                # behind when the model copied a neighbouring example's shape.
                for id_field, owning_key in binding_key_for_id.items():
                    if owning_key != binding_key:
                        binding.pop(id_field, None)
                # The model sometimes names the identifier something else entirely --
                # a table binding arrived carrying "binding_id" and "purpose" but no
                # "table_id", which rejected a ten-slide deck over one slide's
                # paperwork. The id it means is the one the bundle recognises, so
                # recover it from whatever key holds it before giving up on the
                # binding.
                own_field = id_field_for_key[binding_key]
                if not binding.get(own_field):
                    recovered = next(
                        (
                            value
                            for key, value in binding.items()
                            if isinstance(value, str) and value in known_ids[binding_key]
                        ),
                        None,
                    )
                    if recovered:
                        binding[own_field] = recovered
                    elif known_ids[binding_key]:
                        # Nothing in it names a real subject, so it binds to nothing.
                        # Dropping the binding leaves the slide to be judged on its
                        # remaining evidence rather than failing the whole outline on a
                        # field name.
                        continue
                usable.append(binding)
            if binding_key in grounding:
                grounding[binding_key] = usable
        for binding_key in ("table_bindings", "figure_bindings", "formula_bindings"):
            for binding_index, binding in enumerate(grounding.get(binding_key, []), start=1):
                if not isinstance(binding, dict):
                    continue
                if binding_key != "figure_bindings":
                    for field in ("role", "caption_evidence_id", "citation_pages"):
                        binding.pop(field, None)
                binding.setdefault("slide_id", f"slide-{slide_index}")
                if binding_key == "table_bindings":
                    binding.setdefault("selected_columns", [])
                    binding.setdefault("selected_rows", [])
                    binding.setdefault("transform", "source_full")
                    # Row and column selectors are naturally returned as indices.
                    # Rejecting the whole deck over an int where a str was declared
                    # is a formatting quarrel, not a grounding failure.
                    for selector in ("selected_columns", "selected_rows"):
                        values = binding.get(selector)
                        if isinstance(values, list):
                            binding[selector] = [
                                str(value) if isinstance(value, (int, float)) else value
                                for value in values
                            ]
                elif binding_key == "figure_bindings":
                    binding.setdefault("role", "primary_figure")
                    binding.setdefault("caption_evidence_id", None)
                    binding.setdefault("citation_pages", [])
                else:
                    binding.setdefault("render_policy", "source_latex")
                subject = binding.get("table_id") or binding.get("formula_id")
                backing = own_evidence.get(binding_key, {}).get(str(subject))
                if backing:
                    evidence_ids = binding.get("evidence_ids")
                    if not isinstance(evidence_ids, list):
                        evidence_ids = []
                    if backing not in evidence_ids:
                        binding["evidence_ids"] = [*evidence_ids, backing]
                # Bindings often arrive with only the subject id.
                # - Figures: asset_id is valid provenance when in known_assets.
                # - Tables/formulas: need a real text evidence_id (own_evidence above);
                #   do not invent table_id/formula_id as evidence — that yields
                #   table-evidence-missing / formula-evidence-missing and empties
                #   the outline under pack_fill's outline=None-on-any-error contract.
                evidence_ids = binding.get("evidence_ids")
                if not isinstance(evidence_ids, list) or not evidence_ids:
                    if binding_key == "figure_bindings":
                        candidates: list[str] = []
                        caption_id = binding.get("caption_evidence_id")
                        if isinstance(caption_id, str) and caption_id.strip():
                            candidates.append(caption_id.strip())
                        asset_id = str(binding.get("asset_id") or "").strip()
                        if asset_id:
                            candidates.append(asset_id)
                        if bundle is None:
                            filled = candidates[:1]
                        else:
                            filled = [ref for ref in candidates if ref in known_refs]
                        if filled:
                            binding["evidence_ids"] = filled
                # Descriptive keys the model adds for its own benefit -- "purpose",
                # "notes", "binding_id" -- carry no facts and render nothing, but the
                # binding models forbid extras, so one of them refused an entire deck.
                # A field we do not read cannot be wrong; the fields we do read are still
                # fully validated below.
                allowed = _BINDING_FIELDS[binding_key]
                for extra in [key for key in binding if key not in allowed]:
                    binding.pop(extra)
        # Drop claims/metrics/bindings that still lack evidence_ids — empty lists are
        # schema-invalid (min_length=1) and must not sink the whole outline.
        for key in ("claims", "metrics", "table_bindings", "figure_bindings", "formula_bindings"):
            entries = grounding.get(key)
            if not isinstance(entries, list):
                continue
            grounding[key] = [
                entry
                for entry in entries
                if not isinstance(entry, dict)
                or (
                    isinstance(entry.get("evidence_ids"), list)
                    and len(entry.get("evidence_ids") or []) > 0
                )
            ]
        section_ids = grounding.get("section_ids")
        if not isinstance(section_ids, list) or not section_ids:
            fallback_section = "sec-document-000"
            if bundle:
                for section in (bundle.get("sections") or {}).get("sections") or []:
                    if isinstance(section, dict) and section.get("section_id"):
                        fallback_section = str(section["section_id"])
                        break
            grounding["section_ids"] = [fallback_section]
        evidence_ids = grounding.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        if not evidence_ids:
            collected: list[str] = []
            for key in ("claims", "metrics", "table_bindings", "figure_bindings", "formula_bindings"):
                for entry in grounding.get(key) or []:
                    if not isinstance(entry, dict):
                        continue
                    for ref in entry.get("evidence_ids") or []:
                        if ref and str(ref) not in collected:
                            collected.append(str(ref))
            if not collected and bundle:
                for item in bundle.get("evidence") or []:
                    if isinstance(item, dict) and item.get("evidence_id"):
                        collected.append(str(item["evidence_id"]))
                    if len(collected) >= 3:
                        break
            grounding["evidence_ids"] = collected[:3]
    return normalized


def remove_unsupported_metric_annotations(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Remove metric metadata proven absent from its cited source."""
    unsupported: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):unsupported-metric:([^:]+):.*", error)
        if match:
            unsupported.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not unsupported:
        return payload
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, metric_ids in unsupported.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        grounding = slide.get("grounding") if isinstance(slide, dict) else None
        if not isinstance(grounding, dict) or not isinstance(grounding.get("metrics"), list):
            continue
        grounding["metrics"] = [
            metric for metric in grounding["metrics"]
            if not isinstance(metric, dict) or str(metric.get("metric_id")) not in metric_ids
        ]
    return repaired


def _known_reference_ids(bundle: dict[str, Any]) -> set[str]:
    """IDs that may appear in evidence_ids lists (same universe as unknown-evidence checks)."""
    known_evidence = set(_evidence_text(bundle))
    known_tables = {
        str(item.get("table_id"))
        for item in bundle.get("tables", {}).get("tables", [])
        if isinstance(item, dict)
        and not _source_table_errors(bundle, {str(item.get("table_id"))})
    }
    known_assets = {
        str(item.get("asset_id"))
        for item in bundle.get("assets", {}).get("assets", [])
        if isinstance(item, dict)
    }
    known_formulas = {
        str(item.get("formula_id"))
        for item in bundle.get("formulas", {}).get("formulas", [])
        if isinstance(item, dict)
    }
    return known_evidence | known_tables | known_assets | known_formulas


def _claim_quote_containment_failed(
    claim: dict[str, Any],
    bundle: dict[str, Any],
    evidence_text: dict[str, str],
) -> bool:
    """True when source_quote is empty or not a literal substring of cited evidence."""
    evidence_ids = claim.get("evidence_ids") or []
    claim_evidence = " ".join(
        _reference_text(bundle, str(ref), evidence_text) for ref in evidence_ids
    )
    normalized_quote = normalize_source_text(claim.get("source_quote") or "").casefold()
    normalized_evidence = normalize_source_text(claim_evidence).casefold()
    support_type = claim.get("support_type")
    if support_type == "source_verbatim" and not normalized_quote:
        return True
    if normalized_quote and normalized_quote not in normalized_evidence:
        return True
    return False


def _payload_claims_needing_quote_restore(
    payload: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[int, set[str]]:
    """Slide-indexed claim_ids whose quotes are empty or not contained in cited evidence."""
    evidence_text = _evidence_text(bundle)
    rejected: dict[int, set[str]] = {}
    slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
    for slide_number, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding")
        if not isinstance(grounding, dict):
            continue
        claims = grounding.get("claims")
        if not isinstance(claims, list):
            continue
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or "")
            if not claim_id:
                continue
            if _claim_quote_containment_failed(claim, bundle, evidence_text):
                rejected.setdefault(slide_number, set()).add(claim_id)
    return rejected


def _allowlist_evidence_reference_ids(
    payload: dict[str, Any],
    known_ids: set[str],
) -> None:
    """Drop unknown IDs from every evidence_ids list in the payload (mutates in place)."""
    slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding")
        if not isinstance(grounding, dict):
            continue
        holders: list[dict[str, Any]] = [grounding]
        for key in ("claims", "metrics", "table_bindings", "figure_bindings", "formula_bindings"):
            entries = grounding.get(key)
            if isinstance(entries, list):
                holders.extend(entry for entry in entries if isinstance(entry, dict))
        for holder in holders:
            ids = holder.get("evidence_ids")
            if isinstance(ids, list):
                holder["evidence_ids"] = [
                    ref for ref in ids if str(ref) in known_ids
                ]


def _drop_unbound_or_unquoted_claims(
    payload: dict[str, Any],
    bundle: dict[str, Any],
) -> None:
    """Remove claims that still lack evidence or fail quote containment (mutates in place)."""
    evidence_text = _evidence_text(bundle)
    known_evidence = set(evidence_text)
    slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding")
        if not isinstance(grounding, dict) or not isinstance(grounding.get("claims"), list):
            continue
        kept: list[Any] = []
        for claim in grounding["claims"]:
            if not isinstance(claim, dict):
                kept.append(claim)
                continue
            support_type = claim.get("support_type")
            evidence_ids = claim.get("evidence_ids") or []
            if support_type != "derived":
                if not evidence_ids or not any(str(ref) in known_evidence for ref in evidence_ids):
                    continue
            if _claim_quote_containment_failed(claim, bundle, evidence_text):
                continue
            kept.append(claim)
        grounding["claims"] = kept


def _section_evidence_candidates(
    bundle: dict[str, Any],
    section_ids: list[str],
    known_ids: set[str],
) -> list[str]:
    """Evidence IDs from bundle sections, preserving order and known-ID membership."""
    sections_by_id = {
        str(item.get("section_id")): item
        for item in bundle.get("sections", {}).get("sections", [])
        if isinstance(item, dict) and item.get("section_id")
    }
    candidates: list[str] = []
    for section_id in section_ids:
        section = sections_by_id.get(str(section_id))
        if not isinstance(section, dict):
            continue
        for evidence_id in section.get("evidence_ids") or []:
            ref = str(evidence_id)
            if ref in known_ids:
                candidates.append(ref)
    return candidates


def _apply_slide_evidence_floor(
    payload: dict[str, Any],
    bundle: dict[str, Any],
    known_ids: set[str],
) -> None:
    """Attach 1–3 real catalog IDs when slide-level evidence_ids is empty (mutates in place)."""
    catalog_ids = [
        ref for ref in _evidence_text(bundle).keys() if ref in known_ids
    ]
    slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding")
        if not isinstance(grounding, dict):
            continue
        evidence_ids = grounding.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        if evidence_ids:
            continue
        section_ids = [
            str(item)
            for item in (grounding.get("section_ids") or slide.get("section_ids") or [])
            if item
        ]
        candidates = _section_evidence_candidates(bundle, section_ids, known_ids)
        if not candidates and catalog_ids:
            candidates = catalog_ids[:3]
        if candidates:
            grounding["evidence_ids"] = list(dict.fromkeys(candidates))[:3]


def sanitize_grounded_outline(
    payload: dict[str, Any],
    bundle: dict[str, Any],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic citation hygiene: allowlist IDs, restore quotes, drop unbound claims, strip bad metrics.

    Fixed order (do not reorder without updating pack_fill / free_design callers):
    1. Strip catalog provenance annotations from content (``evidence=ev-page-…``)
    2. Known-ID set from bundle + allowlist every evidence_ids list
    3. Restore exact claim quotes (payload-driven + optional prior errors)
    4. Drop claims still unbound or with bad quotes
    5. Strip unsupported metrics / unknown formulas / unsupported numbers (mid-pipeline validate)
    6. Slide evidence floor from section_ids or catalog (never ev-missing)

    Normalization and table/formula own-evidence attach remain on validate_grounded_outline outside
    this function.
    """
    cleaned = deepcopy(payload)
    known_ids = _known_reference_ids(bundle)

    # Provenance addresses on FORMULA/BODY (evidence=ev-page-…) are not claims.
    cleaned = scrub_content_provenance(cleaned)
    _allowlist_evidence_reference_ids(cleaned, known_ids)
    cleaned = restore_exact_claim_quotes(cleaned, bundle, errors or [])
    _drop_unbound_or_unquoted_claims(cleaned, bundle)
    # Allowlist can empty binding evidence_ids; re-floor subject ids / drop empties
    # before the mid-pipeline validate so pydantic does not abort the deck.
    cleaned = normalize_grounded_outline_payload(cleaned, bundle)

    _, validation_errors = validate_grounded_outline(cleaned, bundle)
    cleaned = remove_unsupported_metric_annotations(cleaned, validation_errors)
    cleaned = drop_unknown_formula_bindings(cleaned, validation_errors)
    cleaned = remove_unsupported_number_sentences(cleaned, validation_errors)

    _apply_slide_evidence_floor(cleaned, bundle, known_ids)
    cleaned = normalize_grounded_outline_payload(cleaned, bundle)
    return cleaned


def restore_exact_claim_quotes(
    payload: dict[str, Any],
    bundle: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Replace rejected quote annotations with exact text from their cited evidence."""
    rejected: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):claim-quote-not-found:([^:]+)", error)
        if match:
            rejected.setdefault(int(match.group(1)), set()).add(match.group(2))
        match = re.fullmatch(r"slide-(\d+):claim-quote-missing:([^:]+)", error)
        if match:
            rejected.setdefault(int(match.group(1)), set()).add(match.group(2))
    for slide_number, claim_ids in _payload_claims_needing_quote_restore(payload, bundle).items():
        rejected.setdefault(slide_number, set()).update(claim_ids)
    if not rejected:
        return payload
    evidence_text = _evidence_text(bundle)
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, claim_ids in rejected.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        grounding = slide.get("grounding") if isinstance(slide, dict) else None
        claims = grounding.get("claims") if isinstance(grounding, dict) else None
        if not isinstance(claims, list):
            continue
        for claim in claims:
            if not isinstance(claim, dict) or str(claim.get("claim_id")) not in claim_ids:
                continue
            exact = next(
                (
                    _reference_text(bundle, str(evidence_id), evidence_text).strip()
                    for evidence_id in claim.get("evidence_ids") or []
                    if _reference_text(bundle, str(evidence_id), evidence_text).strip()
                ),
                "",
            )
            if exact:
                claim["source_quote"] = exact
    return repaired


def drop_unknown_evidence_references(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Remove citations the source catalog cannot resolve, keeping the slide.

    A model sometimes mints an evidence ID that looks plausible ("ev-page-067-
    block-067" for a six-page paper) and two correction passes re-cite it rather
    than drop it. The reference is provably wrong -- the catalog is the whole
    universe of valid IDs -- so removing it is a mechanical fix, and the reduced
    citation set is revalidated the same as any other outline.
    """
    unknown: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):unknown-evidence:(.+)", error)
        if match:
            unknown.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not unknown:
        return payload
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, refs in unknown.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        grounding = slide.get("grounding") if isinstance(slide, dict) else None
        if not isinstance(grounding, dict):
            continue
        holders: list[dict[str, Any]] = [grounding]
        for key in ("claims", "metrics", "table_bindings", "figure_bindings", "formula_bindings"):
            entries = grounding.get(key)
            if isinstance(entries, list):
                holders.extend(entry for entry in entries if isinstance(entry, dict))
        for holder in holders:
            ids = holder.get("evidence_ids")
            if isinstance(ids, list):
                holder["evidence_ids"] = [ref for ref in ids if str(ref) not in refs]
    return repaired


def drop_unknown_formula_bindings(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Drop formula_bindings whose formula_id is not in the source catalog.

    Planners invent plausible IDs (formula-repair-complexity) when the PDF has
    few/no extracted formulas. Two LLM repair passes cannot mint catalog
    entries, so the honest fix is to remove the binding and keep the slide.
    """
    unknown: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):unknown-formula:(.+)", error)
        if match:
            unknown.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not unknown:
        return payload
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, formula_ids in unknown.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        grounding = slide.get("grounding") if isinstance(slide, dict) else None
        if not isinstance(grounding, dict) or not isinstance(grounding.get("formula_bindings"), list):
            continue
        grounding["formula_bindings"] = [
            binding
            for binding in grounding["formula_bindings"]
            if not isinstance(binding, dict)
            or str(binding.get("formula_id") or "") not in formula_ids
        ]
    return repaired


def drop_unresolvable_claim_quotes(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Remove claims whose source_quote still cannot be located after restore.

    Prefer restore_exact_claim_quotes first; this is the last-resort drop so a
    single bad quote cannot fail-close an otherwise grounded deck.
    """
    rejected: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):claim-quote-not-found:([^:]+)", error)
        if match:
            rejected.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not rejected:
        return payload
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, claim_ids in rejected.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        grounding = slide.get("grounding") if isinstance(slide, dict) else None
        if not isinstance(grounding, dict) or not isinstance(grounding.get("claims"), list):
            continue
        grounding["claims"] = [
            claim
            for claim in grounding["claims"]
            if not isinstance(claim, dict) or str(claim.get("claim_id") or "") not in claim_ids
        ]
    return repaired


_BYLINE_CONTENT_KEYS = frozenset({"AUTHORS", "AFFILIATIONS", "SUBTITLE", "AUTHOR", "AFFILIATION"})


def _strip_unsupported_number_tokens(text: str, bad_values: set[Decimal]) -> str:
    """Remove unsupported numeric tokens from a short field (e.g. postal codes)."""
    if not text or not bad_values:
        return text
    out = str(text)
    for match in reversed(list(NUMBER_RE.finditer(out))):
        raw = match.group(0).strip().replace(" ", "")
        suffix = ""
        if raw.endswith("%"):
            suffix, raw = "%", raw[:-1]
        elif raw.endswith(("x", "X", "×")):
            suffix, raw = "x", raw[:-1]
        if "," in raw and "." not in raw:
            if raw.count(",") == 1 and len(raw.rsplit(",", 1)[1]) != 3:
                raw = raw.replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if value not in bad_values:
            continue
        start, end = match.span()
        # Drop a preceding comma/space so "Turkey, 32200" → "Turkey".
        while start > 0 and out[start - 1] in " \t,;":
            start -= 1
        out = out[:start] + out[end:]
    return re.sub(r"\s+", " ", out).strip(" ,;")


def remove_unsupported_number_sentences(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Drop the sentence that asserts a number its cited sources do not contain.

    An unsupported number is the one defect a reader cannot detect, so it can
    never ship; but failing the whole deck over one quantified aside throws away
    seven grounded slides. The honest mechanical fix is to stop asserting the
    number: the sentence carrying it is removed, and a value that would become
    empty is left alone so validation keeps naming what a human must decide.

    Byline fields (AUTHORS / AFFILIATIONS / SUBTITLE) are different: a postal
    code in deck furniture is not a research claim. Strip the token there so
    free_design does not fail-close on ``Turkey, 32200``.
    """
    unsupported: dict[int, set[str]] = {}
    for error in errors:
        match = re.fullmatch(r"slide-(\d+):unsupported-number:(.+)", error)
        if match:
            unsupported.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not unsupported:
        return payload
    repaired = deepcopy(payload)
    slides = repaired.get("slides") if isinstance(repaired.get("slides"), list) else []
    for slide_number, numbers in unsupported.items():
        if not (1 <= slide_number <= len(slides)):
            continue
        slide = slides[slide_number - 1]
        content = slide.get("content") if isinstance(slide, dict) else None
        if not isinstance(content, dict):
            continue
        bad_values = {Decimal(number) for number in numbers if _decimal_or_none(number) is not None}
        for key, value in content.items():
            if not isinstance(value, str) or not value.strip():
                continue
            if str(key).upper() in _BYLINE_CONTENT_KEYS:
                stripped = _strip_unsupported_number_tokens(value, bad_values)
                if stripped != value:
                    content[key] = stripped
                continue
            sentences = re.split(r"(?<=[.!?;])\s+", value.strip())
            kept = [
                sentence for sentence in sentences
                if not {token for token, _unit in canonical_numeric_tokens(sentence)} & bad_values
            ]
            if kept and len(kept) < len(sentences):
                content[key] = " ".join(kept)
            elif not kept and len(sentences) == 1:
                # Single-clause field with only the bad number — strip tokens.
                stripped = _strip_unsupported_number_tokens(value, bad_values)
                if stripped != value:
                    content[key] = stripped
    return repaired


def _decimal_or_none(raw: str) -> Decimal | None:
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def validate_grounded_outline(payload: Any, bundle: dict[str, Any]) -> tuple[GroundedOutline | None, list[str]]:
    """Validate structure and evidence references before slide materialization."""
    payload = normalize_grounded_outline_payload(payload, bundle)
    try:
        outline = GroundedOutline.model_validate(payload)
    except ValidationError as exc:
        return None, [f"grounded-schema:{error['loc']}:{error['msg']}" for error in exc.errors()]
    known_evidence = set(_evidence_text(bundle))
    known_sections = {str(item.get("section_id")) for item in bundle.get("sections", {}).get("sections", []) if isinstance(item, dict)}
    known_tables = {
        str(item.get("table_id"))
        for item in bundle.get("tables", {}).get("tables", [])
        if isinstance(item, dict)
        and not _source_table_errors(bundle, {str(item.get("table_id"))})
    }
    known_assets = {str(item.get("asset_id")) for item in bundle.get("assets", {}).get("assets", []) if isinstance(item, dict)}
    known_formulas = {str(item.get("formula_id")) for item in bundle.get("formulas", {}).get("formulas", []) if isinstance(item, dict)}
    evidence_text = _evidence_text(bundle)
    cited_tables = {
        str(binding.table_id)
        for slide in outline.slides
        for binding in slide.grounding.table_bindings
    }
    errors: list[str] = _source_table_errors(bundle, cited_tables)
    tables_by_id = {
        str(item.get("table_id")): item
        for item in bundle.get("tables", {}).get("tables", [])
        if isinstance(item, dict)
    }
    assets_by_id = {
        str(item.get("asset_id")): item
        for item in bundle.get("assets", {}).get("assets", [])
        if isinstance(item, dict)
    }
    formulas_by_id = {
        str(item.get("formula_id")): item
        for item in bundle.get("formulas", {}).get("formulas", [])
        if isinstance(item, dict)
    }
    for slide_index, slide in enumerate(outline.slides, start=1):
        for section_id in slide.grounding.section_ids:
            if section_id not in known_sections and section_id != "sec-document-000":
                errors.append(f"slide-{slide_index}:unknown-section:{section_id}")
        refs = set(slide.grounding.evidence_ids)
        for claim in slide.grounding.claims:
            refs.update(claim.evidence_ids)
            if claim.support_type != "derived" and not any(ref in known_evidence for ref in claim.evidence_ids):
                errors.append(f"slide-{slide_index}:claim-evidence-missing:{claim.claim_id}")
        for metric in slide.grounding.metrics:
            refs.update(metric.evidence_ids)
            if not any(ref in known_evidence or ref in known_tables for ref in metric.evidence_ids):
                errors.append(f"slide-{slide_index}:metric-evidence-missing:{metric.metric_id}")
            errors.extend(validate_metric_derivation(metric, slide_index))
            metric_text = " ".join(_reference_text(bundle, str(ref), evidence_text) for ref in metric.evidence_ids)
            if not metric.derivation:
                if not numeric_tokens_supported(metric.value, metric_text, str(metric.unit)):
                    errors.append(f"slide-{slide_index}:unsupported-metric:{metric.metric_id}:{metric.value}")
        for binding in slide.grounding.table_bindings:
            if binding.table_id not in known_tables:
                errors.append(f"slide-{slide_index}:unknown-table:{binding.table_id}")
            refs.update(binding.evidence_ids)
            if not any(ref in known_evidence for ref in binding.evidence_ids):
                errors.append(f"slide-{slide_index}:table-evidence-missing:{binding.table_id}")
        for binding in slide.grounding.figure_bindings:
            if binding.asset_id not in known_assets:
                errors.append(f"slide-{slide_index}:unknown-figure:{binding.asset_id}")
                if not any(ref in known_evidence for ref in binding.evidence_ids):
                    errors.append(f"slide-{slide_index}:figure-evidence-missing:{binding.asset_id}")
            refs.update(binding.evidence_ids)
            # A figure in known_assets is its own provenance: the asset manifest
            # records its page and sha256 against the source PDF. Demanding a
            # separate text-evidence citation was unsatisfiable, because no
            # "-figure-" evidence ID is ever minted and caption_evidence_id is
            # null unless a caption matches a block verbatim -- so every deck
            # using a source figure was rejected, and it burned both correction
            # passes, leaving real errors elsewhere unrepaired.
            asset = assets_by_id.get(binding.asset_id)
            if asset and binding.citation_pages and int(asset.get("page") or 1) not in binding.citation_pages:
                errors.append(f"slide-{slide_index}:figure-page-mismatch:{binding.asset_id}")
            if binding.caption_evidence_id and binding.caption_evidence_id not in known_evidence:
                errors.append(f"slide-{slide_index}:figure-caption-not-found:{binding.asset_id}")
        for binding in slide.grounding.formula_bindings:
            if binding.formula_id not in known_formulas:
                errors.append(f"slide-{slide_index}:unknown-formula:{binding.formula_id}")
            refs.update(binding.evidence_ids)
            if not any(ref in known_evidence for ref in binding.evidence_ids):
                errors.append(f"slide-{slide_index}:formula-evidence-missing:{binding.formula_id}")
            formula = formulas_by_id.get(binding.formula_id)
            if formula and binding.render_policy == "source_latex" and formula.get("rendering_status") == "needs_review":
                errors.append(f"slide-{slide_index}:formula-rendering-unavailable:{binding.formula_id}")
        if "table" in slide.content and not slide.grounding.table_bindings:
            errors.append(f"slide-{slide_index}:table-source-binding-missing")
        unknown_refs = sorted(
            ref for ref in refs
            if ref not in known_evidence and ref not in known_tables and ref not in known_assets and ref not in known_formulas
        )
        for ref in unknown_refs:
            errors.append(f"slide-{slide_index}:unknown-evidence:{ref}")
        if not refs:
            errors.append(f"slide-{slide_index}:no-evidence")
        source_text = " ".join(_reference_text(bundle, ref, evidence_text) for ref in refs)
        for value in slide.content.values():
            if not isinstance(value, (str, int, float)):
                continue
            if not numeric_tokens_supported(value, source_text):
                for number in sorted(canonical_numeric_tokens(value) - canonical_numeric_tokens(source_text)):
                    errors.append(f"slide-{slide_index}:unsupported-number:{number[0]}")
        for claim in slide.grounding.claims:
            claim_text = normalize_source_text(claim.text)
            claim_evidence = " ".join(_reference_text(bundle, ref, evidence_text) for ref in claim.evidence_ids)
            normalized_quote = normalize_source_text(claim.source_quote).casefold()
            normalized_evidence = normalize_source_text(claim_evidence).casefold()
            if claim.support_type == "source_verbatim" and not normalized_quote:
                errors.append(f"slide-{slide_index}:claim-quote-missing:{claim.claim_id}")
            elif normalized_quote and normalized_quote not in normalized_evidence:
                errors.append(f"slide-{slide_index}:claim-quote-not-found:{claim.claim_id}")
            if not numeric_tokens_supported(claim_text, claim_evidence):
                for number in sorted(canonical_numeric_tokens(claim_text) - canonical_numeric_tokens(claim_evidence)):
                    errors.append(f"slide-{slide_index}:claim-unsupported-number:{claim.claim_id}:{number[0]}")
            claim_token_set = claim_tokens(claim_text)
            source_tokens = claim_tokens(claim_evidence)
            if claim.support_type == "source_paraphrase" and not normalized_quote and claim_token_set:
                overlap = len(claim_token_set & source_tokens) / len(claim_token_set)
                if overlap < 0.2:
                    errors.append(f"slide-{slide_index}:weak-claim-support:{claim.claim_id}:overlap={overlap:.2f}")
    return (outline if not errors else None), errors


_SLIDE_ERROR_RE = re.compile(r"^slide-(\d+):")
_SCHEMA_SLIDE_ERROR_RE = re.compile(r"^grounded-schema:\('slides', (\d+)")


def partition_grounding_errors(errors: list[str]) -> tuple[dict[int, list[str]], list[str]]:
    """Group errors by the slide they belong to, plus the deck-level remainder.

    Lets a correction pass rewrite only the slides that failed. Regenerating the
    whole document fixed the listed errors while breaking slides that already
    validated, so the bounded loop oscillated instead of converging.

    Slide numbers are 1-based, matching the `slide-N:` prefix; the Pydantic
    location in a `grounded-schema` error is 0-based and is shifted to match.
    """
    per_slide: dict[int, list[str]] = {}
    deck_level: list[str] = []
    for error in errors:
        slide_match = _SLIDE_ERROR_RE.match(error)
        if slide_match:
            per_slide.setdefault(int(slide_match.group(1)), []).append(error)
            continue
        schema_match = _SCHEMA_SLIDE_ERROR_RE.match(error)
        if schema_match:
            per_slide.setdefault(int(schema_match.group(1)) + 1, []).append(error)
            continue
        deck_level.append(error)
    return per_slide, deck_level


def validate_section_coverage(outline: GroundedOutline, bundle: dict[str, Any]) -> list[str]:
    """Require major *content* sections on at least one slide.

    Acknowledgment, References, Appendix, and similar back-matter headings are
    optional: they are level-1 in the PDF but are not required talk beats.

    Sections that do not exist in the source bundle are never required — papers
    without Discussion/Conclusion simply omit those IDs.
    """
    sections = [item for item in bundle.get("sections", {}).get("sections", []) if isinstance(item, dict)]
    content = content_sections(sections)
    major = {
        str(item.get("section_id"))
        for item in content
        if int(item.get("level") or 1) == 1 and not is_backmatter_section(item)
    }
    if not major:
        major = {
            str(item.get("section_id"))
            for item in content
            if not is_backmatter_section(item)
        }
    covered = {
        section_id
        for slide in outline.slides
        for section_id in slide.grounding.section_ids
    }
    return [f"section-coverage-missing:{section_id}" for section_id in sorted(major - covered)]


def _evidence_to_section_map(bundle: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    sections = [
        item
        for item in (bundle.get("sections") or {}).get("sections") or []
        if isinstance(item, dict)
    ]
    for section in sections:
        sid = str(section.get("section_id") or "").strip()
        if not sid:
            continue
        for eid in section.get("evidence_ids") or []:
            key = str(eid or "").strip()
            if key and key not in mapping:
                mapping[key] = sid
    return mapping


def derive_section_coverage_from_slides(
    slides: list[dict[str, Any]],
    bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build coverage_plan from cited evidence (narrative order), not PDF index stamp."""
    ev_map = _evidence_to_section_map(bundle)
    all_sections = [
        item
        for item in (bundle.get("sections") or {}).get("sections") or []
        if isinstance(item, dict)
    ]
    content = content_sections(all_sections)
    title_section = str(content[0].get("section_id") or "") if content else ""
    plan: list[dict[str, Any]] = []
    for index, slide in enumerate(slides or [], start=1):
        if not isinstance(slide, dict):
            continue
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        evidence_ids = [str(e) for e in (grounding.get("evidence_ids") or []) if e]
        derived: list[str] = []
        for eid in evidence_ids:
            sid = ev_map.get(eid)
            if sid and sid not in derived and not is_backmatter_section(sid):
                # Drop paper-title section from content slides unless sole signal.
                if sid == title_section and index > 1:
                    continue
                derived.append(sid)
        role = "title" if index == 1 else "content"
        if index == 1 and title_section:
            derived = [title_section, *[s for s in derived if s != title_section]]
        mode = "title" if index == 1 else ("full" if len(derived) <= 1 else "grouped")
        if not derived and index == len(slides or []) and content:
            # Closing plate: prefer conclusion-like trailing content section.
            for section in reversed(content):
                sid = str(section.get("section_id") or "")
                title = str(section.get("title") or "").casefold()
                if sid and ("conclusion" in title or "summary" in title):
                    derived = [sid]
                    mode = "full"
                    break
        plan.append(
            {
                "slide_id": str(slide.get("slide_id") or f"slide-{index}"),
                "section_ids": derived,
                "coverage_mode": mode,
                "role": role,
                "required_evidence_ids": evidence_ids[:6],
            }
        )
    return gap_fill_section_coverage(plan, bundle, slides)


def gap_fill_section_coverage(
    coverage_plan: list[dict[str, Any]],
    bundle: dict[str, Any],
    slides: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach uncovered major L1 content sections to the nearest slide by page proximity."""
    sections = [
        item
        for item in (bundle.get("sections") or {}).get("sections") or []
        if isinstance(item, dict)
    ]
    content = content_sections(sections)
    major = [
        item
        for item in content
        if int(item.get("level") or 1) == 1 and not is_backmatter_section(item)
    ]
    covered = {
        sid
        for entry in coverage_plan
        for sid in (entry.get("section_ids") or [])
        if sid
    }
    if not coverage_plan:
        return coverage_plan

    def _slide_pages(entry: dict[str, Any], index: int) -> list[int]:
        pages: list[int] = []
        for eid in entry.get("required_evidence_ids") or []:
            match = re.search(r"page-(\d+)", str(eid))
            if match:
                pages.append(int(match.group(1)))
        if not pages and slides and 0 <= index < len(slides):
            grounding = slides[index].get("grounding") if isinstance(slides[index], dict) else {}
            for eid in (grounding or {}).get("evidence_ids") or []:
                match = re.search(r"page-(\d+)", str(eid))
                if match:
                    pages.append(int(match.group(1)))
        return pages

    for section in major:
        sid = str(section.get("section_id") or "")
        if not sid or sid in covered:
            continue
        page = int(section.get("page_start") or section.get("page") or 1)
        best_i = max(0, min(len(coverage_plan) - 1, 1 if len(coverage_plan) > 1 else 0))
        best_dist = 10**9
        for index, entry in enumerate(coverage_plan):
            if entry.get("role") == "title":
                continue
            pages = _slide_pages(entry, index)
            if not pages:
                continue
            dist = min(abs(p - page) for p in pages)
            if dist < best_dist:
                best_dist = dist
                best_i = index
        ids = list(coverage_plan[best_i].get("section_ids") or [])
        if sid not in ids:
            ids.append(sid)
            coverage_plan[best_i]["section_ids"] = ids
            mode = str(coverage_plan[best_i].get("coverage_mode") or "full")
            if mode == "full":
                coverage_plan[best_i]["coverage_mode"] = "gap_fill"
            covered.add(sid)
    return coverage_plan


def apply_coverage_plan_section_ids(
    presentation_data: dict[str, Any] | Any,
    coverage_plan: list[dict[str, Any]] | None,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Apply coverage-plan section_ids onto slides.

    Default unions (pack-fill omission repair). Free-design evidence-first
    coverage uses ``replace=True`` so narrative labels are not polluted by the
    paper-title fallback on every slide.
    """
    if not isinstance(presentation_data, dict):
        return presentation_data
    if not coverage_plan:
        return presentation_data
    result = deepcopy(presentation_data)
    slides = result.get("slides")
    if not isinstance(slides, list):
        return result

    by_id: dict[str, list[str]] = {}
    by_index: dict[int, list[str]] = {}
    for offset, entry in enumerate(coverage_plan):
        if not isinstance(entry, dict):
            continue
        ids = [str(item) for item in (entry.get("section_ids") or []) if item]
        if not ids and not replace:
            continue
        slide_id = str(entry.get("slide_id") or "").strip()
        if slide_id:
            by_id[slide_id] = ids
        # coverage_plan is ordered slide-1..N
        by_index[offset + 1] = ids

    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slide_id") or f"slide-{index}").strip()
        if slide_id in by_id:
            allocated = by_id[slide_id]
        elif index in by_index:
            allocated = by_index[index]
        else:
            allocated = []
        if not allocated and not replace:
            continue
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        existing = [
            str(item)
            for item in (grounding.get("section_ids") or slide.get("section_ids") or [])
            if item
        ]
        merged = list(allocated) if replace else list(dict.fromkeys([*existing, *allocated]))
        grounding = dict(grounding)
        grounding["section_ids"] = merged
        slide["grounding"] = grounding
        if "section_ids" in slide:
            slide["section_ids"] = merged
    return result


def materialize_source_tables(outline: GroundedOutline, bundle: dict[str, Any]) -> dict[str, Any]:
    """Copy bound source cells into slide content; never trust LLM table cells."""
    def selector_key(value: Any) -> str:
        # PDF extraction often inserts spaces around decimal points and commas
        # (`(0 . 6 , 0 . 4)`) while the planner writes the human-normal form
        # (`(0.6, 0.4)`). They identify the same source row.
        return re.sub(r"\s+", "", str(value)).casefold()

    tables = {
        str(table.get("table_id")): table
        for table in bundle.get("tables", {}).get("tables", [])
        if isinstance(table, dict)
    }
    result = outline.model_dump(mode="json")
    # Slides used to be stamped with "PDF p. 4" in their footer slot. Page
    # provenance belongs in grounded_plan.json and the review panel, which is
    # where it is audited; printing it on the deck itself only clutters the slide
    # the audience is reading. The evidence-to-page map that produced that string
    # was this function's only other work, so it went with it.
    for slide in result.get("slides", []):
        grounding = slide.get("grounding", {}) if isinstance(slide.get("grounding"), dict) else {}
        formula_bindings = grounding.get("formula_bindings", [])
        if formula_bindings and isinstance(slide.get("content"), dict):
            formulas = {
                str(formula.get("formula_id")): formula
                for formula in bundle.get("formulas", {}).get("formulas", [])
                if isinstance(formula, dict)
            }
            formula = formulas.get(str(formula_bindings[0].get("formula_id")))
            if formula:
                slide["content"]["FORMULA"] = str(formula.get("latex", ""))
        bindings = slide.get("grounding", {}).get("table_bindings", [])
        if not bindings:
            continue
        binding = bindings[0]
        slide.setdefault("grounding", {})["table_bindings"] = [binding]
        table = tables.get(str(binding.get("table_id")))
        if not table:
            continue
        selected_columns = {
            selector_key(value) for value in (binding.get("selected_columns") or [])
        }
        headers = table.get("headers", [])
        header_names = [str(cell.get("text", "")) for cell in headers if isinstance(cell, dict)]
        if len(header_names) > 3 and (not selected_columns or len(selected_columns) > 3):
            # The current protected table carrier has three stable columns.
            # Select exact source columns rather than shrinking or inventing a
            # denser table representation.
            selected_columns = {selector_key(value) for value in header_names[:3]}
            binding["selected_columns"] = header_names[:3]
            binding["transform"] = "source_subset"
        column_indexes = [
            index for index, name in enumerate(header_names)
            if not selected_columns or selector_key(name) in selected_columns
        ]
        selected_rows = {
            selector_key(value) for value in (binding.get("selected_rows") or [])
        }
        matched_rows: set[str] = set()
        rows = []
        for row in table.get("rows", []):
            if not isinstance(row, list):
                continue
            values = [str(cell.get("text", "")) for cell in row if isinstance(cell, dict)]
            if selected_rows and values:
                row_key = selector_key(values[0])
                if row_key not in selected_rows or row_key in matched_rows:
                    continue
                # A selector identifies one source row. Repeated labels often mark
                # different experimental blocks; expanding one requested label to
                # every occurrence silently turned four-row subsets into 20 rows.
                matched_rows.add(row_key)
            rows.append([row[index] for index in column_indexes if index < len(row)])
        slide.setdefault("content", {})["table"] = {
            "columns": [headers[index] for index in column_indexes if index < len(headers)],
            "rows": rows,
            "source_table_id": table.get("table_id"),
        }
        # Table layouts have a compact message slot. Use the source caption;
        # the exact source cells carry the detailed factual content.
        caption = str(table.get("caption") or "")
        table_label = re.search(r"\bTABLE\s+[IVXLCDM]+\b", caption, re.I)
        slide["content"]["BODY"] = (
            f"{table_label.group(0)}"
            if table_label else f"Table {table.get('table_id')}"
        )
        slide.setdefault("visual_plan", {})["archetype"] = "table"
        slide["visual_plan"]["primary"] = "table"
    return result


def compact_grounded_titles(plan: dict[str, Any], max_chars: int = 48) -> dict[str, Any]:
    """Shorten only presentation titles while preserving source wording."""
    for slide in plan.get("slides", []):
        title = str(slide.get("title") or "").strip()
        if len(title) <= max_chars:
            continue
        pieces = re.split(r"\s*[:|]\s*", title, maxsplit=1)
        if len(pieces) == 2:
            compact = f"{pieces[0]}: {' '.join(pieces[1].split()[:2])}"
        else:
            words = title.split()
            compact = " ".join(words[:3]).rstrip(" ,;:")
        slide["title"] = compact[:max_chars].rstrip()
        if isinstance(slide.get("content"), dict):
            slide["content"]["TITLE"] = slide["title"]
    return plan
