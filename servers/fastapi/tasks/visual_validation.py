"""Deterministic visual provenance, placement, and visibility validation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from PIL import Image, ImageStat
except Exception:  # pragma: no cover
    Image = None
    ImageStat = None

try:
    from layout_geometry import bounds as shared_bounds
    from layout_geometry import effective_scales as shared_scales
    from layout_geometry import multiply as shared_multiply
    from layout_geometry import parse_transform as shared_parse_transform
except Exception:  # pragma: no cover
    shared_bounds = shared_scales = shared_multiply = shared_parse_transform = None


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash(path: str | Path) -> str | None:
    if Image is None:
        return None
    try:
        image = Image.open(path).convert("L").resize((16, 16))
        pixels = list(image.getdata())
        average = sum(pixels) / max(len(pixels), 1)
        return "".join("1" if pixel >= average else "0" for pixel in pixels)
    except Exception:
        return None


def build_pdf_figure_manifest(source_pdf: str, figures: list[dict], output_dir: str) -> dict:
    """Verify extracted PDF figures and write their complete provenance manifest."""
    pdf_path = Path(source_pdf)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"source PDF not found: {source_pdf}")
    manifest = {
        "source_pdf": {
            "path": str(pdf_path),
            "sha256": sha256_file(pdf_path),
            "pages": 0,
        },
        "figures": [],
    }
    try:
        from .pdf_pages import count_pdf_pages
    except ImportError:  # pragma: no cover - supports direct task imports
        from pdf_pages import count_pdf_pages
    try:
        manifest["source_pdf"]["pages"] = count_pdf_pages(source_pdf)
    except Exception:
        pass
    for index, figure in enumerate(figures):
        file_path = Path(output_dir) / str(figure.get("file", ""))
        if not file_path.is_file():
            raise FileNotFoundError(f"extracted PDF figure missing: {file_path}")
        if Image is None:
            width = int(figure.get("width", 0))
            height = int(figure.get("height", 0))
        else:
            with Image.open(file_path) as image:
                width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid extracted figure dimensions: {file_path}")
        item = dict(figure)
        placed_width = item.get("placed_width")
        placed_height = item.get("placed_height")
        item.update({
            "id": figure.get("id") or f"pdf-page-{figure.get('page', 0)}-xref-{figure.get('xref', index)}",
            "width": width,
            "height": height,
            "intrinsic_width": width,
            "intrinsic_height": height,
            "intrinsic_ratio": round(width / height, 4),
            "ratio": round(width / height, 4),
            "placed_ratio": (
                round(float(placed_width) / float(placed_height), 4)
                if placed_width and placed_height else item.get("placed_ratio")
            ),
            "sha256": sha256_file(file_path),
            "perceptual_hash": perceptual_hash(file_path),
            "status": "verified",
        })
        manifest["figures"].append(item)
    os.makedirs(output_dir, exist_ok=True)
    for manifest_name in ("figure_manifest.json", "source_asset_manifest.json"):
        with open(Path(output_dir) / manifest_name, "w", encoding="utf-8") as stream:
            json.dump({**manifest, "schema_version": "sunairum.source-assets/v1"}, stream, ensure_ascii=False, indent=2)
    return manifest


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_TRANSFORM = re.compile(rf"([a-zA-Z]+)\s*\(([^)]*)\)")
_TRANSFORM_NUMBER = re.compile(_NUMBER)
_MATRIX_TOLERANCE = 1e-6
_RATIO_TOLERANCE = 0.02


def _identity_matrix() -> tuple[float, float, float, float, float, float]:
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply_matrix(
    left: tuple[float, float, float, float, float, float],
    right: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    if shared_multiply is not None:
        return shared_multiply(left, right)
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def _parse_svg_transform(value: str | None) -> tuple[float, float, float, float, float, float]:
    """Parse SVG transforms into one affine matrix in document order."""
    if shared_parse_transform is not None:
        return shared_parse_transform(value)
    if not value:
        return _identity_matrix()
    result = _identity_matrix()
    for match in _TRANSFORM.finditer(value):
        name = match.group(1).lower()
        numbers = [float(number) for number in _TRANSFORM_NUMBER.findall(match.group(2))]
        if name == "matrix" and len(numbers) >= 6:
            operation = tuple(numbers[:6])
        elif name == "translate" and numbers:
            operation = (1.0, 0.0, 0.0, 1.0, numbers[0], numbers[1] if len(numbers) > 1 else 0.0)
        elif name == "scale" and numbers:
            operation = (numbers[0], 0.0, 0.0, numbers[1] if len(numbers) > 1 else numbers[0], 0.0, 0.0)
        elif name == "rotate" and numbers:
            radians = math.radians(numbers[0])
            cosine, sine = math.cos(radians), math.sin(radians)
            operation = (cosine, sine, -sine, cosine, 0.0, 0.0)
            if len(numbers) >= 3:
                cx, cy = numbers[1], numbers[2]
                operation = _multiply_matrix(
                    _multiply_matrix((1.0, 0.0, 0.0, 1.0, cx, cy), operation),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
        elif name == "skewx" and numbers:
            operation = (1.0, 0.0, math.tan(math.radians(numbers[0])), 1.0, 0.0, 0.0)
        elif name == "skewy" and numbers:
            operation = (1.0, math.tan(math.radians(numbers[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        result = _multiply_matrix(result, operation)
    return result


def _transformed_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    matrix: tuple[float, float, float, float, float, float],
) -> dict[str, float]:
    if shared_bounds is not None:
        return shared_bounds(x, y, width, height, matrix)
    a, b, c, d, e, f = matrix
    points = [
        (a * px + c * py + e, b * px + d * py + f)
        for px, py in ((x, y), (x + width, y), (x, y + height), (x + width, y + height))
    ]
    xs, ys = zip(*points)
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _transform_characteristics(
    matrix: tuple[float, float, float, float, float, float],
) -> dict[str, Any]:
    a, b = matrix[0], matrix[1]
    if shared_scales is not None:
        x_scale, y_scale, dot = shared_scales(matrix)
    else:
        a, b, c, d, _e, _f = matrix
        x_scale = math.hypot(a, b)
        y_scale = math.hypot(c, d)
        dot = a * c + b * d
    scale_product = max(x_scale * y_scale, _MATRIX_TOLERANCE)
    return {
        "nonuniform": abs(x_scale - y_scale) > _MATRIX_TOLERANCE * max(x_scale, y_scale, 1.0),
        "shear": abs(dot) > _MATRIX_TOLERANCE * scale_product,
        "angle": math.degrees(math.atan2(b, a)) if x_scale > _MATRIX_TOLERANCE else 0.0,
    }


def _is_quarter_turn(angle: float) -> bool:
    normalized = abs(angle) % 180.0
    return abs(normalized - 90.0) <= 1e-4


def _image_from_attributes(
    tag: str,
    start: int,
    matrix: tuple[float, float, float, float, float, float],
) -> dict:
    def value(name: str, default: float = 0.0) -> float:
        found = re.search(rf'\b{re.escape(name)}="({_NUMBER})', tag)
        return float(found.group(1)) if found else default

    x, y, width, height = (value(name) for name in ("x", "y", "width", "height"))
    return {
        "tag": tag,
        "start": start,
        "href": (re.search(r'\b(?:href|xlink:href)="([^"]+)"', tag) or [None, ""])[1],
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "visual_id": (re.search(r'data-sunairum-visual-id="([^"]+)"', tag) or [None, None])[1],
        "source_type": (re.search(r'data-sunairum-source-type="([^"]+)"', tag) or [None, None])[1],
        "source_file": (re.search(r'data-sunairum-source-file="([^"]+)"', tag) or [None, None])[1],
        "source_page": (re.search(r'data-sunairum-source-page="([^"]+)"', tag) or [None, None])[1],
        "plan_slot": (re.search(r'data-sunairum-plan-slot="([^"]+)"', tag) or [None, None])[1],
        "transform": (re.search(r'\btransform="([^"]+)"', tag) or [None, ""])[1],
        "preserve_aspect_ratio": (re.search(r'\bpreserveAspectRatio="([^"]+)"', tag) or [None, ""])[1],
        "clip_path": (re.search(r'\bclip-path="([^"]+)"', tag) or [None, ""])[1],
        "effective_matrix": matrix,
        "effective_geometry": _transformed_bounds(x, y, width, height, matrix),
        "transform_characteristics": _transform_characteristics(matrix),
    }


def _image_tags(svg: str) -> list[dict]:
    """Extract image metadata and resolve transforms inherited from ancestors."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        result = []
        for match in re.finditer(r"<image\b([^>]*?)(?:/>|>.*?</image>)", svg, re.S):
            tag = match.group(0)
            local = _parse_svg_transform((re.search(r'\btransform="([^"]+)"', tag) or [None, ""])[1])
            result.append(_image_from_attributes(tag, match.start(), local))
        return result

    result = []

    def visit(element: ET.Element, parent_matrix: tuple[float, float, float, float, float, float]) -> None:
        local_matrix = _parse_svg_transform(element.attrib.get("transform"))
        matrix = _multiply_matrix(parent_matrix, local_matrix)
        if element.tag.rsplit("}", 1)[-1] == "image":
            attrs = dict(element.attrib)
            href = next((value for key, value in attrs.items() if key.rsplit("}", 1)[-1] == "href"), "")
            serialized = ET.tostring(element, encoding="unicode")
            item = _image_from_attributes(serialized, 0, matrix)
            item["href"] = href
            for name in ("visual-id", "source-type", "source-file", "source-page", "plan-slot"):
                item[name.replace("-", "_")] = attrs.get(f"data-sunairum-{name}")
            item["transform"] = attrs.get("transform", "")
            item["preserve_aspect_ratio"] = attrs.get("preserveAspectRatio", "")
            result.append(item)
        for child in element:
            visit(child, matrix)

    visit(root, _identity_matrix())
    return result


def _planned_slots(slide_plan: dict) -> list[dict]:
    return slide_plan.get("visual_slots", []) if isinstance(slide_plan, dict) else []


def build_visual_manifest(storage_dir: str, slide_plans: list[dict]) -> dict:
    """Record every final slide image and its planned slot/source metadata.

    Under zero-SVG this returns an empty slides list (SVG tags no longer exist).
    """
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    if html_sot_enabled(storage_dir):
        return {"slides": [], "skipped_html_sot": True}
    manifest = {"slides": []}
    for index, plan in enumerate(slide_plans, start=1):
        svg_path = Path(storage_dir) / "svg_output" / f"slide_{index:02d}.svg"
        if not svg_path.is_file():
            continue
        visuals = []
        for tag in _image_tags(svg_path.read_text(encoding="utf-8")):
            visuals.append({
                "visual_id": tag["visual_id"] or f"visual-{len(visuals) + 1}",
                "source_type": tag["source_type"] or "unknown",
                "source_file": tag["source_file"] or os.path.basename(tag["href"]),
                "source_page": tag["source_page"],
                "plan_slot": tag["plan_slot"],
                "actual_svg_geometry": {
                    key: tag[key] for key in ("x", "y", "width", "height")
                },
                "effective_svg_geometry": dict(tag["effective_geometry"]),
                "transform": tag.get("transform", ""),
                "transform_characteristics": dict(tag.get("transform_characteristics", {})),
                "fit_policy": tag.get("preserve_aspect_ratio", "") or "xMidYMid meet",
                "clip_path": tag.get("clip_path", ""),
            })
        manifest["slides"].append({
            "slide": index,
            "title": plan.get("title", ""),
            "visuals": visuals,
            "planned_slots": _planned_slots(plan),
        })
    return manifest


def validate_provenance(storage_dir: str, slide_plans: list[dict], image_source: str) -> list[dict]:
    issues = []
    pdf_manifest_path = Path(storage_dir) / "sources" / "pdf_images" / "source_asset_manifest.json"
    if not pdf_manifest_path.is_file():
        pdf_manifest_path = Path(storage_dir) / "sources" / "pdf_images" / "figure_manifest.json"
    pdf_manifest = json.loads(pdf_manifest_path.read_text(encoding="utf-8")) if pdf_manifest_path.is_file() else {"figures": []}
    pdf_files = {item.get("file"): item for item in pdf_manifest.get("figures", [])}
    for index, plan in enumerate(slide_plans, start=1):
        svg_path = Path(storage_dir) / "svg_output" / f"slide_{index:02d}.svg"
        if not svg_path.is_file():
            continue
        tags = _image_tags(svg_path.read_text(encoding="utf-8"))
        visual = plan.get("visual_plan", {})
        if not visual.get("allow_figure", True) and tags:
            issues.append({"slide": index, "category": "visual-unplanned", "severity": "error", "detail": "plan forbids visuals but SVG contains image elements"})
        requires_primary_pdf = image_source == "pdf" and visual.get("allow_figure", True) and (
            visual.get("primary") in {"figure", "single-figure"}
            or (plan.get("primary_visual_source") == "pdf" and visual.get("archetype") in {"single-figure", "narrative"})
        )
        if requires_primary_pdf:
            non_background = [
                tag for tag in tags
                if tag["effective_geometry"]["width"] * tag["effective_geometry"]["height"] < 0.7 * 1280 * 720
                and tag.get("source_type") != "background"
            ]
            if not non_background:
                issues.append({"slide": index, "category": "pdf-source-unavailable", "severity": "error", "detail": "PDF-only mode has no primary PDF visual for this planned figure slot"})
        for tag in tags:
            geometry = tag["effective_geometry"]
            is_background = geometry["width"] * geometry["height"] >= 0.7 * 1280 * 720
            is_primary = not is_background or tag.get("visual_id") == "primary_visual"
            is_pdf_primary = _is_primary_visual(tag, plan, is_background)
            if image_source == "pdf" and tag["source_type"] == "ai" and (is_pdf_primary or not is_background):
                issues.append({"slide": index, "category": "pdf-fallback-forbidden", "severity": "error", "detail": "AI visual used in PDF-only mode"})
            if not is_primary:
                continue
            if visual.get("allow_figure", True) and not tag["visual_id"]:
                issues.append({"slide": index, "category": "visual-provenance-missing", "severity": "error", "detail": "primary visual lacks Sunairum provenance metadata"})
            href = tag["href"]
            target = (svg_path.parent / href).resolve() if href and not href.startswith("data:") else None
            if href and not href.startswith("data:") and not target.is_file():
                issues.append({"slide": index, "category": "visual-missing", "severity": "error", "detail": f"image source missing: {href}"})
            if tag["source_type"] == "pdf":
                item = pdf_files.get(tag["source_file"])
                if item is None:
                    issues.append({"slide": index, "category": "visual-source-mismatch", "severity": "error", "detail": f"PDF figure not found in manifest: {tag['source_file']}"})
                elif target and sha256_file(target) != item.get("sha256"):
                    issues.append({"slide": index, "category": "pdf-source-hash-mismatch", "severity": "error", "detail": f"PDF figure hash mismatch: {tag['source_file']}"})
                if is_pdf_primary:
                    _append_pdf_image_issues(issues, index, tag, item)
    return issues


def _is_primary_visual(tag: dict, plan: dict, is_background: bool) -> bool:
    if tag.get("visual_id") == "primary_visual":
        return True
    if is_background:
        return False
    if tag.get("source_type") == "pdf" and plan.get("visual_plan", {}).get("allow_figure", True):
        return True
    return plan.get("primary_visual_source") == "pdf"


def _source_ratio(item: dict) -> float | None:
    ratio = item.get("intrinsic_ratio", item.get("ratio"))
    if ratio is None:
        width = item.get("intrinsic_width", item.get("width", 0))
        height = item.get("intrinsic_height", item.get("height", 0))
        try:
            ratio = float(width) / float(height)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return None
    return ratio if math.isfinite(ratio) and ratio > 0 else None


def _append_pdf_image_issues(issues: list[dict], slide: int, tag: dict, item: dict | None) -> None:
    characteristics = tag["transform_characteristics"]
    if characteristics["nonuniform"] or characteristics["shear"]:
        detail = "PDF visual has shear in its effective transform" if characteristics["shear"] else "PDF visual has non-uniform effective scale"
        issues.append({"slide": slide, "category": "image-nonuniform-transform", "severity": "error", "detail": detail})

    preserve = (tag.get("preserve_aspect_ratio") or "").strip().lower().split()
    if preserve and preserve[0] == "none":
        issues.append({"slide": slide, "category": "image-invalid-fit-policy", "severity": "error", "detail": 'PDF visual uses preserveAspectRatio="none"'})

        source_ratio = _source_ratio(item) if item is not None else None
        geometry = tag["effective_geometry"]
        if source_ratio and geometry["height"] > 0:
            expected_ratio = 1.0 / source_ratio if _is_quarter_turn(characteristics["angle"]) else source_ratio
            placed_ratio = geometry["width"] / geometry["height"]
            if abs(placed_ratio / expected_ratio - 1.0) > _RATIO_TOLERANCE:
                issues.append({"slide": slide, "category": "image-aspect-ratio-mismatch", "severity": "error", "detail": f"PDF visual ratio {placed_ratio:.4g} differs from source ratio {expected_ratio:.4g}"})


# Subject fills that must stay inside planned figure slots. Template/design
# chrome is excluded so Presenton decorative carriers never fail placement QA.
_CONTENT_VISUAL_SOURCES = frozenset({"pdf", "chart", "ai", "stock", "authored"})


def validate_placement(storage_dir: str, slide_plans: list[dict], tolerance: float = 2.0) -> list[dict]:
    issues = []
    for index, plan in enumerate(slide_plans, start=1):
        svg_path = Path(storage_dir) / "svg_output" / f"slide_{index:02d}.svg"
        if not svg_path.is_file():
            continue
        tags = [
            tag for tag in _image_tags(svg_path.read_text(encoding="utf-8"))
            if not (tag["effective_geometry"]["width"] * tag["effective_geometry"]["height"] >= 0.7 * 1280 * 720)
            and tag["source_type"] != "background"
            and (tag.get("source_type") in _CONTENT_VISUAL_SOURCES or tag.get("plan_slot"))
        ]
        slots = [
            slot for slot in _planned_slots(plan)
            if not slot.get("is_background") and not slot.get("is_design")
        ]
        maximum = int(plan.get("rules", {}).get("max_non_background_images", 1))
        if len(tags) > maximum:
            issues.append({"slide": index, "category": "duplicate-primary-visual", "severity": "error", "detail": f"planned {maximum} non-background visual(s), found {len(tags)}"})
        for tag in tags:
            geometry = tag["effective_geometry"]
            if not slots:
                issues.append({"slide": index, "category": "visual-wrong-slot", "severity": "error", "detail": "visual exists without a planned visual slot"})
                continue
            slot = min(slots, key=lambda item: abs(float(item.get("x", 0)) - geometry["x"]) + abs(float(item.get("y", 0)) - geometry["y"]))
            left, top = geometry["x"], geometry["y"]
            right, bottom = left + geometry["width"], top + geometry["height"]
            sx, sy = float(slot.get("x", 0)), float(slot.get("y", 0))
            sr, sb = sx + float(slot.get("width", 0)), sy + float(slot.get("height", 0))
            if left < sx - tolerance or top < sy - tolerance or right > sr + tolerance or bottom > sb + tolerance:
                issues.append({"slide": index, "category": "visual-zone-overflow", "severity": "error", "detail": f"visual exceeds planned slot: actual ({left:g},{top:g},{geometry['width']:g},{geometry['height']:g})"})
            fit_policy = (tag.get("preserve_aspect_ratio") or "xMidYMid meet").lower()
            expected_letterbox = "meet" in fit_policy and "none" not in fit_policy
            if (
                not expected_letterbox
                and geometry["width"] * geometry["height"] < float(slot.get("width", 0)) * float(slot.get("height", 0)) * 0.6
            ):
                issues.append({"slide": index, "category": "visual-too-small", "severity": "error", "detail": "visual occupies less than 60% of its planned slot"})
    return issues


def validate_visibility(storage_dir: str, slide_plans: list[dict]) -> list[dict]:
    issues = []
    images_dir = Path(storage_dir) / "images"
    for index, plan in enumerate(slide_plans, start=1):
        svg_path = Path(storage_dir) / "svg_output" / f"slide_{index:02d}.svg"
        if not svg_path.is_file():
            continue
        for tag in _image_tags(svg_path.read_text(encoding="utf-8")):
            if tag["href"].startswith("data:"):
                continue
            geometry = tag["effective_geometry"]
            if not _is_primary_visual(
                tag,
                plan,
                geometry["width"] * geometry["height"] >= 0.7 * 1280 * 720,
            ):
                continue
            path = (svg_path.parent / tag["href"]).resolve()
            if not path.is_file() or Image is None:
                continue
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    if width < max(64, int(geometry["width"] * 0.25)) or height < max(64, int(geometry["height"] * 0.25)):
                        issues.append({"slide": index, "category": "visual-low-resolution", "severity": "error", "detail": f"image resolution {width}x{height} is too low for its rendered zone"})
                    stat = ImageStat.Stat(image.convert("L"))
                    if stat.mean[0] > 245 and stat.stddev[0] < 12:
                        issues.append({"slide": index, "category": "visual-near-blank", "severity": "error", "detail": "visual has almost no luminance variation"})
            except Exception as exc:
                issues.append({"slide": index, "category": "visual-unavailable", "severity": "error", "detail": str(exc)})
    return issues


def validate_source_visual_uptake(storage_dir: str, slide_plans: list[dict], image_source: str) -> list[dict]:
    """Flag a deck that ignores every figure the source document offers.

    A text-only deck built from a paper full of figures is a silent failure:
    each slide passes on its own, so nothing else in QA notices.
    """
    if image_source != "pdf":
        return []
    manifest_path = Path(storage_dir) / "sources" / "pdf_images" / "source_asset_manifest.json"
    if not manifest_path.is_file():
        manifest_path = Path(storage_dir) / "sources" / "pdf_images" / "figure_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        available = json.loads(manifest_path.read_text(encoding="utf-8")).get("figures", [])
    except (json.JSONDecodeError, OSError):
        return []
    if not available:
        return []
    used = 0
    for index in range(1, len(slide_plans) + 1):
        svg_path = Path(storage_dir) / "svg_output" / f"slide_{index:02d}.svg"
        if svg_path.is_file():
            used += len(_image_tags(svg_path.read_text(encoding="utf-8")))
    if used:
        return []
    return [{
        "slide": 0,
        "category": "source-visuals-unused",
        "severity": "error",
        "detail": (
            f"source provides {len(available)} figure(s) but the deck uses none"
        ),
    }]


def validate_visuals(storage_dir: str, slide_plans: list[dict], image_source: str) -> dict:
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    if html_sot_enabled(storage_dir):
        return {
            "status": "skipped",
            "issues": [],
            "error_count": 0,
            "skipped_html_sot": True,
        }
    issues = (
        validate_provenance(storage_dir, slide_plans, image_source)
        + validate_placement(storage_dir, slide_plans)
        + validate_visibility(storage_dir, slide_plans)
        + validate_source_visual_uptake(storage_dir, slide_plans, image_source)
    )
    return {
        "status": "failed" if issues else "passed",
        "issues": issues,
        "error_count": len(issues),
    }
