"""Closed-loop PPTX visual fidelity: rasterize PPTX and diff vs HTML previews.

Pipeline:
  presentation.pptx
    → LibreOffice headless PDF (with embedded/staged fonts)
    → pdftoppm PNGs
    → SSIM + MAE vs preview/slide_XX.png
    → attribute worst regions via presentation.pptx.shape-map.json
    → exports/fidelity_report.json

Final release compilation is fidelity-blocking by default. Callers may still
run this module directly for diagnostics without raising.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Default noise floor from LibreOffice ↔ PowerPoint calibration
# (see vendor/deckhtml/FIDELITY_CALIBRATION.md). Override via env.
# Sparse slide rasters are dominated by platform font antialiasing, which can
# yield global SSIM around 0.60 even when geometry and MAE are excellent. The
# semantic shape gate below owns placement; this floor only catches major
# visual corruption/missing content.
DEFAULT_SSIM_FLOOR = float(os.environ.get("PPTX_FIDELITY_SSIM_FLOOR") or "0.55")
SCENE_SSIM_FLOOR = float(os.environ.get("PPTX_FIDELITY_SCENE_SSIM_FLOOR") or "0.30")
# Structure below this cannot be excused by low pixel error. MAE is area-weighted, so a
# sparse slide whose title renders at the wrong size still averages under the ceiling:
# slide_01 of one deck reported ssim 0.15 with mae 16.3 and passed the gate while the PPTX
# was visibly wrong. Measured decks put a faithful slide at 0.78-0.99 and a broken one at
# 0.15-0.39, so the two populations separate well clear of this line.
SCENE_SSIM_HARD_FLOOR = float(os.environ.get("PPTX_FIDELITY_SCENE_SSIM_HARD_FLOOR") or "0.50")
DEFAULT_MAE_CEIL = float(os.environ.get("PPTX_FIDELITY_MAE_CEIL") or "18.0")
CANVAS_W = 1280
CANVAS_H = 720
SLIDE_W_IN = 10.0
SLIDE_H_IN = 5.625
MIN_LAYOUT_FAITHFUL_FONT_SCALE = 0.92
MAX_PEER_FONT_SCALE_SPREAD = 0.02
MAX_PEER_EFFECTIVE_FONT_SPREAD_PX = 1.0


def _pdftoppm_bin() -> str | None:
    return shutil.which("pdftoppm")


def mean_absolute_error(a, b) -> float:
    """Mean absolute pixel difference on float [0,255] arrays."""
    import numpy as np

    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if aa.shape != bb.shape:
        raise ValueError(f"shape mismatch {aa.shape} vs {bb.shape}")
    return float(np.mean(np.abs(aa - bb)))


def ssim_grayscale(a, b) -> float:
    """Structural similarity (single-channel) without scikit-image.

    Uses the classic SSIM formulation with a stable Gaussian-free window
    (global statistics) — good enough for slide-level gate thresholds.
    """
    import numpy as np

    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    if aa.ndim == 3:
        aa = aa.mean(axis=2)
    if bb.ndim == 3:
        bb = bb.mean(axis=2)
    if aa.shape != bb.shape:
        raise ValueError(f"shape mismatch {aa.shape} vs {bb.shape}")
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a = aa.mean()
    mu_b = bb.mean()
    var_a = aa.var()
    var_b = bb.var()
    cov = ((aa - mu_a) * (bb - mu_b)).mean()
    num = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
    den = (mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2)
    if den <= 0:
        return 1.0 if num == 0 else 0.0
    return float(num / den)


def load_shape_map(pptx_path: Path) -> list[dict[str, Any]]:
    side = Path(f"{pptx_path}.shape-map.json")
    if not side.is_file():
        return []
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    shapes = data.get("shapes") if isinstance(data, dict) else data
    return shapes if isinstance(shapes, list) else []


def rasterize_pptx_slides(pptx_path: Path, out_dir: Path, dpi: int = 192) -> list[Path]:
    """PPTX → PDF (LibreOffice) → PNG pages. Returns sorted PNG paths.

    Default 192 dpi (~1920×1080 for 10×5.625in) so SSIM vs hi-DPI previews
    stays meaningful after downscale to the working canvas. Poppler is the
    preferred process-isolated rasterizer; pypdfium2 is the deterministic
    in-process fallback already shipped in the application image.
    """
    from tasks.release_export import _pdf_from_pptx

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sunairum-fidelity-pdf-") as tmp:
        pdf_path = Path(tmp) / f"{pptx_path.stem}.pdf"
        _pdf_from_pptx(pptx_path, pdf_path)
        pdftoppm = _pdftoppm_bin()
        if pdftoppm:
            prefix = out_dir / "slide"
            subprocess.run(
                [
                    pdftoppm,
                    "-png",
                    "-r",
                    str(int(dpi)),
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
        else:
            try:
                import pypdfium2 as pdfium
            except ImportError as exc:  # pragma: no cover - image contract
                raise RuntimeError(
                    "no PDF rasterizer available (pdftoppm or pypdfium2 required)"
                ) from exc
            document = pdfium.PdfDocument(str(pdf_path))
            try:
                scale = max(1.0, float(dpi) / 72.0)
                for index in range(len(document)):
                    page = document[index]
                    bitmap = page.render(scale=scale)
                    try:
                        # Match pdftoppm's sortable numbering. Unpadded names
                        # sort 1,10,11,...,2 and silently compare every preview
                        # to the wrong PPTX page once a deck reaches 10 slides.
                        bitmap.to_pil().save(out_dir / f"slide-{index + 1:04d}.png")
                    finally:
                        bitmap.close()
                        page.close()
            finally:
                document.close()
    pages = sorted(out_dir.glob("slide-*.png"))
    if not pages:
        pages = sorted(out_dir.glob("slide*.png"))
    if not pages:
        raise RuntimeError(f"PDF rasterizer produced no PNGs under {out_dir}")
    return pages


def _resize_to(img, size: tuple[int, int]):
    from PIL import Image

    if img.size == size:
        return img
    return img.resize(size, Image.Resampling.LANCZOS)


def _region_mae(ref, cand, box_px: tuple[int, int, int, int]) -> float:
    import numpy as np

    x0, y0, x1, y1 = box_px
    h, w = ref.shape[:2]
    x0 = max(0, min(w - 1, x0))
    x1 = max(x0 + 1, min(w, x1))
    y0 = max(0, min(h - 1, y0))
    y1 = max(y0 + 1, min(h, y1))
    return mean_absolute_error(ref[y0:y1, x0:x1], cand[y0:y1, x0:x1])


def _inch_box_to_px(
    box: dict[str, float],
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int]:
    sx = img_w / SLIDE_W_IN
    sy = img_h / SLIDE_H_IN
    x = float(box.get("x") or 0) * sx
    y = float(box.get("y") or 0) * sy
    w = float(box.get("w") or 0) * sx
    h = float(box.get("h") or 0) * sy
    return int(x), int(y), int(x + max(w, 1)), int(y + max(h, 1))


#: Overlap area (px²) the export may add before it counts as a defect. Two
#: adjacent text frames legitimately share a hairline after inch→EMU rounding.
_OVERLAP_TOLERANCE_PX2 = 20.0


def export_introduced_overlaps(
    shapes: list[dict[str, Any]],
    slide_index: int,
) -> list[dict[str, Any]]:
    """Text frames that collide in the PPTX but not in the HTML they came from.

    The conversion is only faithful if it adds no collisions of its own. Comparing
    each pair's overlap in both spaces separates the two failures that look
    identical in a raster: copy that already overlapped when Chromium laid it out
    (a content-budget problem the layout QA owns) and copy the export pushed on
    top of its neighbour (a converter problem). Only the second is reported here.
    """
    px_per_inch = CANVAS_W / SLIDE_W_IN
    frames: list[tuple[str, tuple[float, float, float, float], tuple[float, float, float, float]]] = []
    for shape in shapes:
        if shape.get("type") != "text":
            continue
        if int(shape.get("slideIndex") or 0) != slide_index:
            continue
        html_box = shape.get("html")
        pptx_box = shape.get("pptx")
        if not isinstance(html_box, dict) or not isinstance(pptx_box, dict):
            continue
        try:
            html_rect = (
                float(html_box["x"]),
                float(html_box["y"]),
                float(html_box["w"]),
                float(html_box["h"]),
            )
            pptx_rect = (
                float(pptx_box["x"]) * px_per_inch,
                float(pptx_box["y"]) * px_per_inch,
                float(pptx_box["w"]) * px_per_inch,
                float(pptx_box["h"]) * px_per_inch,
            )
        except (KeyError, TypeError, ValueError):
            continue
        frames.append((str(shape.get("elementId") or "element"), html_rect, pptx_rect))

    def _area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
            0.0, min(ay + ah, by + bh) - max(ay, by)
        )

    failures: list[dict[str, Any]] = []
    for index, (left_id, left_html, left_pptx) in enumerate(frames):
        for right_id, right_html, right_pptx in frames[index + 1 :]:
            authored = _area(left_html, right_html)
            exported = _area(left_pptx, right_pptx)
            if exported > authored + _OVERLAP_TOLERANCE_PX2:
                failures.append(
                    {
                        "type": "export_introduced_overlap",
                        "a": left_id,
                        "b": right_id,
                        "html_overlap_px2": round(authored, 1),
                        "pptx_overlap_px2": round(exported, 1),
                    }
                )
    return failures


def semantic_shape_geometry_failures(
    shapes: list[dict[str, Any]],
    slide_index: int,
    *,
    tolerance_px: float = 4.0,
) -> list[dict[str, Any]]:
    """Enforce stable identity, drawable geometry, lines, clips, and bounds."""
    failures: list[dict[str, Any]] = []
    slide_shapes = [
        shape
        for shape in shapes
        if int(shape.get("slideIndex") or 0) == slide_index
    ]
    ids = [str(shape.get("elementId") or "").strip() for shape in slide_shapes]
    for position, element_id in enumerate(ids):
        if not element_id:
            failures.append({"type": "missing_stable_identity", "shape_index": position})
    duplicates = sorted({element_id for element_id in ids if element_id and ids.count(element_id) > 1})
    for element_id in duplicates:
        failures.append({"type": "duplicate_stable_identity", "elementId": element_id})

    paint_sequence = [
        (position, float(shape["paintOrder"]))
        for position, shape in enumerate(slide_shapes)
        if shape.get("paintOrder") is not None
    ]
    for (prev_index, prev), (cur_index, cur) in zip(paint_sequence, paint_sequence[1:]):
        if cur + 1e-6 < prev:
            failures.append(
                {
                    "type": "paint_order_drift",
                    "previous_shape_index": prev_index,
                    "shape_index": cur_index,
                    "previous_paint_order": prev,
                    "paint_order": cur,
                }
            )
    for shape in slide_shapes:
        fragment_ids = shape.get("inlineFragmentIds")
        if isinstance(fragment_ids, list):
            normalized_fragments = [str(value).strip() for value in fragment_ids]
            if any(not value for value in normalized_fragments) or len(set(normalized_fragments)) != len(normalized_fragments):
                failures.append(
                    {
                        "elementId": shape.get("elementId"),
                        "type": "unstable_inline_fragment_identity",
                        "fragment_ids": fragment_ids,
                    }
                )
        shape_type = str(shape.get("type") or "")
        html_box = shape.get("html") if isinstance(shape.get("html"), dict) else None
        pptx_box = shape.get("pptx") if isinstance(shape.get("pptx"), dict) else None
        if not html_box or not pptx_box:
            continue
        converted = {
            "x": float(pptx_box.get("x") or 0) * CANVAS_W / SLIDE_W_IN,
            "y": float(pptx_box.get("y") or 0) * CANVAS_H / SLIDE_H_IN,
            "w": float(pptx_box.get("w") or 0) * CANVAS_W / SLIDE_W_IN,
            "h": float(pptx_box.get("h") or 0) * CANVAS_H / SLIDE_H_IN,
        }
        html_w = float(html_box.get("w") or 0)
        html_h = float(html_box.get("h") or 0)
        atomic_geometry = (
            shape_type in {"text", "image", "table", "line"}
            or html_w <= 14
            or html_h <= 14
        )
        if atomic_geometry:
            deltas = {
                "x": abs(float(html_box.get("x") or 0) - converted["x"]),
                "y": abs(float(html_box.get("y") or 0) - converted["y"]),
                "w": abs(html_w - converted["w"]),
                "h": abs(float(html_box.get("h") or 0) - converted["h"]),
            }
            thresholds = {key: tolerance_px for key in deltas}
        else:
            deltas = {}
            thresholds = {}
        # ``object-fit:contain`` deliberately emits the painted image inside
        # its larger CSS host.  Comparing that painted box to the container
        # produced symmetric y/h (or x/w) "drift" and blocked correct figures.
        # Accept only a centered, aspect-preserving containment: the emitted
        # image must stay inside the authored box and touch one full dimension.
        contained_image = False
        if shape_type == "image" and str(shape.get("objectFit") or "").casefold() == "contain":
            html_x = float(html_box.get("x") or 0)
            html_y = float(html_box.get("y") or 0)
            html_right = html_x + html_w
            html_bottom = html_y + html_h
            converted_right = converted["x"] + converted["w"]
            converted_bottom = converted["y"] + converted["h"]
            center_dx = abs((html_x + html_right) / 2 - (converted["x"] + converted_right) / 2)
            center_dy = abs((html_y + html_bottom) / 2 - (converted["y"] + converted_bottom) / 2)
            inside = (
                converted["x"] >= html_x - tolerance_px
                and converted["y"] >= html_y - tolerance_px
                and converted_right <= html_right + tolerance_px
                and converted_bottom <= html_bottom + tolerance_px
            )
            touches_axis = (
                abs(converted["w"] - html_w) <= tolerance_px
                or abs(converted["h"] - html_h) <= tolerance_px
            )
            contained_image = inside and touches_axis and center_dx <= tolerance_px and center_dy <= tolerance_px
        if deltas and not contained_image and any(deltas[key] > thresholds[key] for key in deltas):
            failures.append(
                {
                    "elementId": shape.get("elementId"),
                    "type": shape.get("type"),
                    "deltas_px": {key: round(value, 2) for key, value in deltas.items()},
                    "tolerance_px": {key: round(value, 2) for key, value in thresholds.items()},
                    "html": html_box,
                    "pptx": pptx_box,
                }
            )
        for axis, value, lower, upper in (
            ("x", converted["x"], 0.0, float(CANVAS_W)),
            ("y", converted["y"], 0.0, float(CANVAS_H)),
            ("right", converted["x"] + converted["w"], 0.0, float(CANVAS_W)),
            ("bottom", converted["y"] + converted["h"], 0.0, float(CANVAS_H)),
        ):
            if value < lower - tolerance_px or value > upper + tolerance_px:
                failures.append(
                    {
                        "elementId": shape.get("elementId"),
                        "type": "safe_area_violation",
                        "axis": axis,
                        "value_px": round(value, 2),
                    }
                )
        clip = shape.get("clip") if isinstance(shape.get("clip"), dict) else None
        if clip:
            cx = float(clip.get("x") or 0)
            cy = float(clip.get("y") or 0)
            cr = cx + float(clip.get("w") or 0)
            cb = cy + float(clip.get("h") or 0)
            if (
                converted["x"] < cx - tolerance_px
                or converted["y"] < cy - tolerance_px
                or converted["x"] + converted["w"] > cr + tolerance_px
                or converted["y"] + converted["h"] > cb + tolerance_px
            ):
                failures.append(
                    {
                        "elementId": shape.get("elementId"),
                        "type": "clip_boundary_violation",
                        "clip": clip,
                        "pptx_px": converted,
                    }
                )
        if shape_type == "text":
            try:
                font_scale = float(shape.get("fontScale", 1))
            except (TypeError, ValueError):
                font_scale = 0.0
            if font_scale + 1e-6 < MIN_LAYOUT_FAITHFUL_FONT_SCALE:
                failures.append(
                    {
                        "elementId": shape.get("elementId"),
                        "type": "text_font_scale",
                        "font_scale": round(font_scale, 4),
                        "minimum_font_scale": MIN_LAYOUT_FAITHFUL_FONT_SCALE,
                        "html_line_count": shape.get("htmlLineCount"),
                    }
                )
            html_lines = shape.get("htmlLineCount")
            pptx_lines = shape.get("pptxLineCount")
            if html_lines is not None and pptx_lines is not None:
                try:
                    line_mismatch = int(html_lines) != int(pptx_lines)
                except (TypeError, ValueError):
                    line_mismatch = True
                if line_mismatch:
                    failures.append(
                        {
                            "elementId": shape.get("elementId"),
                            "type": "text_line_count_drift",
                            "html_line_count": html_lines,
                            "pptx_line_count": pptx_lines,
                        }
                    )
    return failures


def peer_typography_failures(
    shapes: list[dict[str, Any]], slide_index: int
) -> list[dict[str, Any]]:
    """Reject inconsistent typography among repeated semantic peers."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for shape in shapes:
        if int(shape.get("slideIndex") or 0) != slide_index:
            continue
        if str(shape.get("type") or "") != "text":
            continue
        tag = str(shape.get("tag") or "").strip().casefold()
        element_id = str(shape.get("sourceElementId") or shape.get("elementId") or "").strip().casefold()
        # Plain p/span/div tags do not constitute a semantic peer group.  They
        # accidentally grouped unrelated copy across a slide.  Use authored
        # class roles, or explicit stable IDs normalized across ordinal cards.
        peer_role = tag if "." in tag else ""
        if not peer_role and element_id and not element_id.startswith("dh-auto"):
            normalized_id = re.sub(r"(?<=-)(?:\d+)(?=-|$)", "*", element_id)
            if normalized_id != element_id:
                peer_role = f"id:{normalized_id}"
        if not peer_role:
            continue
        # Inspector tags include classes (for example div.row-copy). That is
        # the semantic peer role; pair it with the authored source size so a
        # deliberate heading/body distinction is not treated as drift.
        source_size = str(shape.get("fontSize") or "").strip().casefold()
        groups.setdefault((peer_role, source_size), []).append(shape)

    failures: list[dict[str, Any]] = []
    for (tag, source_size), peers in groups.items():
        if len(peers) < 2:
            continue
        scales: list[float] = []
        effective_sizes: list[float] = []
        families: set[str] = set()
        for peer in peers:
            try:
                scale = float(peer.get("fontScale", 1))
            except (TypeError, ValueError):
                scale = 0.0
            scales.append(scale)
            try:
                px = float(str(peer.get("fontSize") or "").replace("px", "").strip())
            except ValueError:
                px = 0.0
            if px > 0:
                effective_sizes.append(px * scale)
            family = str(peer.get("fontFamily") or "").strip().casefold()
            if family:
                families.add(family)
        spread = max(scales) - min(scales)
        effective_spread = (
            max(effective_sizes) - min(effective_sizes) if effective_sizes else 0.0
        )
        # A ratio difference below one rendered pixel is not a visible type
        # mismatch.  Require both relative and absolute drift; family
        # substitution remains independently blocking.
        if (
            (
                spread > MAX_PEER_FONT_SCALE_SPREAD + 1e-6
                and effective_spread > MAX_PEER_EFFECTIVE_FONT_SPREAD_PX + 1e-6
            )
            or len(families) > 1
        ):
            failures.append(
                {
                    "type": "peer_typography_drift",
                    "peer_role": tag,
                    "source_font_size": source_size,
                    "element_ids": [peer.get("elementId") for peer in peers],
                    "font_scale_spread": round(spread, 4),
                    "effective_font_spread_px": round(effective_spread, 3),
                    "font_families": sorted(families),
                }
            )
    return failures


def semantic_ownership_failures(
    shapes: list[dict[str, Any]], slide_index: int
) -> list[dict[str, Any]]:
    """Enforce one native/object-level owner for complex semantic hosts."""
    owners: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for shape in shapes:
        if int(shape.get("slideIndex") or 0) != slide_index:
            continue
        owner = str(shape.get("semanticOwner") or "").strip()
        kind = str(shape.get("semanticKind") or "").strip().casefold()
        if owner and kind in {"table", "figure", "chart", "formula"}:
            owners.setdefault((owner, kind), []).append(shape)

    failures: list[dict[str, Any]] = []
    primary_types = {
        "table": {"table"},
        "figure": {"image"},
        "chart": {"chart", "image"},
        "formula": {"math", "image"},
    }
    for (owner, kind), members in owners.items():
        primaries = [
            shape
            for shape in members
            if str(shape.get("type") or "").casefold() in primary_types[kind]
        ]
        if len(primaries) != 1:
            failures.append(
                {
                    "elementId": owner,
                    "type": "semantic_owner_count",
                    "semantic_kind": kind,
                    "primary_count": len(primaries),
                    "member_ids": [shape.get("elementId") for shape in members],
                }
            )
            continue

        if kind != "table":
            # Decorative children inside a figure/chart/formula host are preview-only.
            unexpected = [
                shape.get("elementId")
                for shape in members
                if shape is not primaries[0]
            ]
            if unexpected:
                failures.append(
                    {
                        "elementId": owner,
                        "type": "semantic_owner_leak",
                        "semantic_kind": kind,
                        "unexpected_members": unexpected,
                    }
                )
            continue

        table = primaries[0]
        html_cells = [str(value) for value in (table.get("tableCells") or [])]
        pptx_cells = [str(value) for value in (table.get("pptxTableCells") or [])]
        if html_cells != pptx_cells:
            failures.append(
                {
                    "elementId": table.get("elementId"),
                    "type": "table_cell_content_drift",
                    "html_cells": html_cells,
                    "pptx_cells": pptx_cells,
                }
            )
        row_count = int(table.get("tableRows") or 0)
        row_heights = table.get("tableRowHeights") or []
        pptx_row_heights = table.get("pptxTableRowHeights") or []
        if row_count <= 0 or len(row_heights) != row_count or len(pptx_row_heights) != row_count:
            failures.append(
                {
                    "elementId": table.get("elementId"),
                    "type": "table_row_contract",
                    "rows": row_count,
                    "html_row_heights": row_heights,
                    "pptx_row_heights": pptx_row_heights,
                }
            )
        column_count = int(table.get("tableCols") or 0)
        column_widths = table.get("tableColumnWidths") or []
        pptx_column_widths = table.get("pptxTableColumnWidths") or []
        if (
            column_count <= 0
            or len(column_widths) != column_count
            or len(pptx_column_widths) != column_count
        ):
            failures.append(
                {
                    "elementId": table.get("elementId"),
                    "type": "table_column_contract",
                    "columns": column_count,
                    "html_column_widths": column_widths,
                    "pptx_column_widths": pptx_column_widths,
                }
            )
    return failures


#: Symbol faces OOXML names structurally (bullet glyphs), not text metrics.
#: Text faces are deliberately absent — an unembedded "Arial" is the drift this
#: check exists to find, not an exemption, because the reader's Arial wins over
#: anything we ship under that name.
_UNEMBEDDABLE_EXEMPT = frozenset({"Wingdings", "Wingdings 2", "Wingdings 3", "Symbol"})


def unembedded_typefaces(pptx: Path) -> list[str]:
    """Typefaces the slides name but the file does not carry.

    A face that is not inside the .pptx is resolved by whoever opens it. Their
    copy has different advance widths from the one Chromium measured, so the
    text re-wraps and lands over its neighbour — the drift is created at open
    time, long after every gate here has passed, which is why it has to be
    reported on the artifact itself rather than trusted to the exporter's log.
    """
    import zipfile

    try:
        with zipfile.ZipFile(pptx) as bundle:
            names = bundle.namelist()
            embedded = {
                entry.rsplit("/", 1)[-1]
                for entry in names
                if entry.startswith("ppt/fonts/")
            }
            declared: set[str] = set()
            for entry in names:
                if not re.fullmatch(r"ppt/slides/slide\d+\.xml", entry):
                    continue
                xml = bundle.read(entry).decode("utf-8", "replace")
                declared.update(re.findall(r'typeface="([^"+][^"]*)"', xml))
            if not declared:
                return []
            presentation = ""
            if "ppt/presentation.xml" in names:
                presentation = bundle.read("ppt/presentation.xml").decode(
                    "utf-8", "replace"
                )
    except (OSError, KeyError, zipfile.BadZipFile):
        return []

    if not embedded:
        return sorted(face for face in declared if face not in _UNEMBEDDABLE_EXEMPT)
    # ``embeddedFont`` entries name the typeface they carry; a face missing from
    # that list is not in the package whatever ppt/fonts happens to hold.
    carried = set(re.findall(r'<p:embeddedFont>.*?typeface="([^"]*)"', presentation, re.S))
    return sorted(
        face
        for face in declared
        if face not in carried and face not in _UNEMBEDDABLE_EXEMPT
    )


def scene_raster_is_credible(ssim: float, mae: float, *, mae_ceil: float) -> bool:
    """Return true unless both structure and pixel error indicate corruption.

    Chromium and LibreOffice can disagree on gradients, antialiasing, and
    clip-path decomposition while retaining the same composition. Strong
    structure passes on its own, and low absolute error covers the rasterizer
    noise that depresses SSIM on text-heavy slides.

    Low pixel error is not itself evidence of a faithful slide: MAE averages
    over the whole canvas, so ink that moved or resized on an otherwise empty
    slide barely moves it. Below ``SCENE_SSIM_HARD_FLOOR`` the composition has
    demonstrably diverged and no MAE rescues it.
    """
    if float(ssim) < SCENE_SSIM_HARD_FLOOR:
        return False
    return float(ssim) >= SCENE_SSIM_FLOOR or float(mae) <= float(mae_ceil)


def semantic_scene_missing_ids(
    scene: dict[str, Any],
    shapes: list[dict[str, Any]],
    slide_index: int,
) -> list[str]:
    """Require exported drawable content in every non-footer Scene region.

    Identity attributes are diagnostic hints, not a one-element/one-shape
    contract: transparent region roots frequently emit no native shape, while
    their children export correctly. Spatial content coverage is stable across
    CSS decomposition and still detects a blank title, figure, formula, table,
    or content panel.
    """
    slide_shapes = [
        shape for shape in shapes
        if int(shape.get("slideIndex") or 0) == slide_index
        and isinstance(shape.get("html"), dict)
    ]
    missing: list[str] = []
    for region in scene.get("regions") or []:
        if not isinstance(region, dict) or region.get("role") == "footer":
            continue
        rid = str(region.get("id") or "")
        role = str(region.get("role") or "")
        try:
            rx, ry = float(region["x"]), float(region["y"])
            rw, rh = float(region["w"]), float(region["h"])
        except (KeyError, TypeError, ValueError):
            missing.append(f"scene-{rid}:invalid_geometry")
            continue
        allowed = {"text", "image"}
        if role == "chart":
            allowed.update({"chart", "rect"})
        elif role == "table":
            allowed.add("table")
        elif role == "formula":
            # Editable Office Math is a first-class drawable. Requiring a text
            # or image surrogate falsely marks a correct native formula region
            # empty after semantic ownership has already passed.
            allowed.add("math")
        found = False
        for shape in slide_shapes:
            if str(shape.get("type") or "") not in allowed:
                continue
            box = shape["html"]
            try:
                sx, sy = float(box.get("x") or 0), float(box.get("y") or 0)
                sw, sh = float(box.get("w") or 0), float(box.get("h") or 0)
            except (TypeError, ValueError):
                continue
            cx, cy = sx + sw / 2.0, sy + sh / 2.0
            if rx - 1 <= cx <= rx + rw + 1 and ry - 1 <= cy <= ry + rh + 1:
                found = True
                break
        if not found:
            missing.append(f"scene-{rid}:drawable_content")
    return sorted(set(missing))


def attribute_failures(
    ref,
    cand,
    shapes: list[dict[str, Any]],
    slide_index: int,
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rank shape-map entries by regional MAE on this slide."""
    h, w = ref.shape[:2]
    scored: list[dict[str, Any]] = []
    for shape in shapes:
        if int(shape.get("slideIndex") or 0) != slide_index:
            continue
        pptx_box = shape.get("pptx") or {}
        if not isinstance(pptx_box, dict):
            continue
        box = _inch_box_to_px(pptx_box, w, h)
        try:
            mae = _region_mae(ref, cand, box)
        except Exception:  # noqa: BLE001
            continue
        scored.append(
            {
                "elementId": shape.get("elementId"),
                "tag": shape.get("tag"),
                "type": shape.get("type"),
                "mae": round(mae, 3),
                "pptx": pptx_box,
                "html": shape.get("html"),
            }
        )
    scored.sort(key=lambda s: float(s["mae"]), reverse=True)
    return scored[:top_k]


def compare_slide_pair(
    preview_png: Path,
    pptx_png: Path,
    *,
    shapes: list[dict[str, Any]] | None = None,
    slide_index: int = 0,
    ssim_floor: float = DEFAULT_SSIM_FLOOR,
    mae_ceil: float = DEFAULT_MAE_CEIL,
) -> dict[str, Any]:
    from PIL import Image
    import numpy as np

    if not preview_png.is_file():
        return {
            "ok": False,
            "skipped": "missing_preview",
            "preview": str(preview_png),
            "pptx_raster": str(pptx_png),
        }
    if not pptx_png.is_file():
        return {
            "ok": False,
            "skipped": "missing_pptx_raster",
            "preview": str(preview_png),
            "pptx_raster": str(pptx_png),
        }

    ref_img = Image.open(preview_png).convert("RGB")
    cand_img = Image.open(pptx_png).convert("RGB")
    # Normalize both to the CSS canvas (1280×720) so hi-DPI previews and
    # LibreOffice PDF rasters share one working grid.
    target = (CANVAS_W, CANVAS_H)
    ref_img = _resize_to(ref_img, target)
    cand_img = _resize_to(cand_img, target)
    ref = np.asarray(ref_img)
    cand = np.asarray(cand_img)
    ssim = ssim_grayscale(ref, cand)
    mae = mean_absolute_error(ref, cand)
    ok = ssim >= ssim_floor and mae <= mae_ceil
    finding: dict[str, Any] = {
        "ok": ok,
        "ssim": round(ssim, 5),
        "mae": round(mae, 3),
        "ssim_floor": ssim_floor,
        "mae_ceil": mae_ceil,
        "preview": str(preview_png),
        "pptx_raster": str(pptx_png),
        "size": list(target),
    }
    if not ok and shapes:
        finding["top_regions"] = attribute_failures(
            ref, cand, shapes, slide_index
        )
    return finding


def verify_pptx_against_previews(
    storage_dir: str | Path,
    *,
    pptx_path: str | Path | None = None,
    ssim_floor: float | None = None,
    mae_ceil: float | None = None,
    dpi: int = 192,
) -> dict[str, Any]:
    """Compare each PPTX slide raster to preview/slide_XX.png.

    Writes ``exports/fidelity_report.json``. Does not raise on failure —
    callers decide warn vs block via ``report["ok"]``.
    """
    root = Path(storage_dir)
    exports = root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    pptx = Path(pptx_path) if pptx_path else exports / "presentation.pptx"
    preview_dir = root / "preview"
    html_dir = root / "html_output"
    floor = DEFAULT_SSIM_FLOOR if ssim_floor is None else float(ssim_floor)
    ceil = DEFAULT_MAE_CEIL if mae_ceil is None else float(mae_ceil)

    report: dict[str, Any] = {
        "ok": True,
        "pptx": str(pptx),
        "ssim_floor": floor,
        "mae_ceil": ceil,
        "slides": [],
        "failures": [],
    }

    if not pptx.is_file():
        report["ok"] = False
        report["error"] = "pptx_missing"
        _write_report(exports / "fidelity_report.json", report)
        return report

    shapes = load_shape_map(pptx)
    report["shape_map_count"] = len(shapes)

    # Text the reader's renderer will re-measure. Nothing later in this run can
    # detect it: our own rasters use the container's fonts, so the deck looks
    # correct here and drifts only when it is opened elsewhere.
    missing_faces = unembedded_typefaces(pptx)
    report["unembedded_typefaces"] = missing_faces
    if missing_faces:
        report["ok"] = False
        report["failures"].append(
            {
                "stem": "deck",
                "type": "unembedded_typefaces",
                "typefaces": missing_faces,
                "detail": (
                    "these faces are named by the slides but not carried in the file, "
                    "so text set in them re-wraps on machines with a different copy"
                ),
            }
        )

    from tasks.html_to_pptx import list_html_slides

    slides = list_html_slides(html_dir)
    if not slides:
        report["ok"] = False
        report["error"] = "no_html_slides"
        _write_report(exports / "fidelity_report.json", report)
        return report

    try:
        with tempfile.TemporaryDirectory(prefix="sunairum-fidelity-png-") as tmp:
            pages = rasterize_pptx_slides(pptx, Path(tmp), dpi=dpi)
            for index, html_path in enumerate(slides):
                preview = preview_dir / f"{html_path.stem}.png"
                pptx_png = pages[index] if index < len(pages) else Path("/dev/null")
                finding = compare_slide_pair(
                    preview,
                    pptx_png,
                    shapes=shapes,
                    slide_index=index,
                    ssim_floor=floor,
                    mae_ceil=ceil,
                )
                finding["stem"] = html_path.stem
                finding["slide_index"] = index
                geometry_failures = semantic_shape_geometry_failures(shapes, index)
                geometry_failures.extend(export_introduced_overlaps(shapes, index))
                typography_failures = peer_typography_failures(shapes, index)
                ownership_failures = semantic_ownership_failures(shapes, index)
                scene_path = root / "scene" / f"{html_path.stem}.json"
                missing_ids: list[str] = []
                scene_is_v2 = False
                if scene_path.is_file():
                    try:
                        scene = json.loads(scene_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        scene = {}
                    scene_is_v2 = (
                        isinstance(scene, dict)
                        and scene.get("version") == "scene_layout_v2"
                    )
                    if scene_is_v2:
                        missing_ids = semantic_scene_missing_ids(scene, shapes, index)
                if not scene_is_v2:
                    missing_ids = ["scene_manifest_missing_or_invalid"]
                finding["semantic"] = {
                    "ok": not geometry_failures and not typography_failures and not ownership_failures and not missing_ids,
                    "geometry_failures": geometry_failures,
                    "typography_failures": typography_failures,
                    "ownership_failures": ownership_failures,
                    "missing_element_ids": missing_ids,
                }
                if scene_is_v2:
                    # Scene identity and exact CSS→PPTX boxes own placement.
                    # Raster SSIM remains a gross-corruption check only because
                    # LibreOffice/Chromium font rasterization differs heavily.
                    semantic_ok = not geometry_failures and not typography_failures and not ownership_failures and not missing_ids
                    raster_ok = scene_raster_is_credible(
                        float(finding.get("ssim") or 0),
                        float(finding.get("mae") or 10**9),
                        mae_ceil=ceil,
                    )
                    finding["scene_ssim_floor"] = SCENE_SSIM_FLOOR
                    finding["scene_ssim_hard_floor"] = SCENE_SSIM_HARD_FLOOR
                    finding["ok"] = semantic_ok and raster_ok
                else:
                    finding["ok"] = False
                report["slides"].append(finding)
                if not finding.get("ok"):
                    report["ok"] = False
                    report["failures"].append(
                        {
                            "stem": html_path.stem,
                            "ssim": finding.get("ssim"),
                            "mae": finding.get("mae"),
                            "top_regions": finding.get("top_regions") or [],
                            "skipped": finding.get("skipped"),
                            "semantic": finding.get("semantic"),
                        }
                    )
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["error"] = str(exc)[:1000]

    if not report.get("ok"):
        from tasks.layout_findings import native_fidelity_remediation_plan

        report["remediation"] = native_fidelity_remediation_plan(report)
    _write_report(exports / "fidelity_report.json", report)
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
