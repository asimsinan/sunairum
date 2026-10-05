"""Deterministic analysis of immutable source table cells."""

from __future__ import annotations

import re
from typing import Any


def _cell_text(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get("text") or "").strip()
    return str(cell or "").strip()


def _header_names(table: dict[str, Any]) -> list[str]:
    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
    names: list[str] = []
    for h in headers:
        names.append(_cell_text(h) or f"Col{len(names)+1}")
    if not names:
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        if rows and isinstance(rows[0], list):
            names = [f"Col{i+1}" for i in range(len(rows[0]))]
    return names


def _parse_number(text: str) -> float | None:
    raw = str(text or "").strip().replace(",", "")
    # Whole-cell numeric only (avoid matching "1" inside "C1").
    m = re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", raw)
    if not m:
        return None
    try:
        return float(raw.rstrip("%"))
    except ValueError:
        return None


def analyze_table(table: dict[str, Any]) -> dict[str, Any]:
    """Return types, column stats, best/worst row indices. Never mutates table."""
    columns = _header_names(table)
    rows_raw = table.get("rows") if isinstance(table.get("rows"), list) else []
    matrix: list[list[str]] = []
    for row in rows_raw:
        if not isinstance(row, list):
            continue
        matrix.append([_cell_text(c) for c in row])

    col_stats: list[dict[str, Any]] = []
    for ci, name in enumerate(columns):
        nums: list[tuple[int, float]] = []
        for ri, row in enumerate(matrix):
            if ci >= len(row):
                continue
            n = _parse_number(row[ci])
            if n is not None:
                nums.append((ri, n))
        is_numeric = len(nums) >= max(1, len(matrix) // 2) and len(nums) > 0
        entry: dict[str, Any] = {
            "name": name,
            "index": ci,
            "dtype": "number" if is_numeric else "text",
        }
        if is_numeric and nums:
            vals = [v for _, v in nums]
            entry["min"] = min(vals)
            entry["max"] = max(vals)
            entry["min_row"] = min(nums, key=lambda t: t[1])[0]
            entry["max_row"] = max(nums, key=lambda t: t[1])[0]
        col_stats.append(entry)

    return {
        "table_id": str(table.get("table_id") or ""),
        "caption": str(table.get("caption") or ""),
        "columns": columns,
        "row_count": len(matrix),
        "col_count": len(columns),
        "matrix": matrix,
        "column_stats": col_stats,
        "numeric_columns": [c["name"] for c in col_stats if c.get("dtype") == "number"],
    }


def template_insight(analysis: dict[str, Any], intent: dict[str, Any]) -> str:
    """Build insight text from Analyzer facts only (no free LLM prose)."""
    insight = intent.get("insight") if isinstance(intent.get("insight"), dict) else {}
    if not insight.get("enabled", True):
        return ""
    emphasis = intent.get("emphasis") if isinstance(intent.get("emphasis"), dict) else {}
    rules = emphasis.get("rules") if isinstance(emphasis.get("rules"), list) else []
    matrix = analysis.get("matrix") or []
    columns = analysis.get("columns") or []
    stats_by_name = {
        str(s.get("name")): s
        for s in (analysis.get("column_stats") or [])
        if isinstance(s, dict)
    }
    parts: list[str] = []
    for rule in rules[:3]:
        if not isinstance(rule, dict):
            continue
        col = str(rule.get("column") or "").strip()
        direction = str(rule.get("direction") or "min").strip().casefold()
        st = stats_by_name.get(col)
        if not st or st.get("dtype") != "number":
            continue
        ri = int(st["min_row"] if direction == "min" else st["max_row"])
        if ri < 0 or ri >= len(matrix):
            continue
        row = matrix[ri]
        method = row[0] if row else f"row {ri+1}"
        ci = columns.index(col) if col in columns else -1
        val = row[ci] if 0 <= ci < len(row) else st.get(direction)
        word = "lowest" if direction == "min" else "highest"
        parts.append(f"{method} has {word} {col} ({val})")
    if parts:
        return "; ".join(parts)
    # Fail soft: grounded one-liner from headers / first numeric extremum.
    for st in analysis.get("column_stats") or []:
        if not isinstance(st, dict) or st.get("dtype") != "number":
            continue
        col = str(st.get("name") or "")
        ri = int(st.get("min_row", -1))
        if ri < 0 or ri >= len(matrix) or not col:
            continue
        row = matrix[ri]
        method = row[0] if row else f"row {ri + 1}"
        ci = columns.index(col) if col in columns else -1
        val = row[ci] if 0 <= ci < len(row) else st.get("min")
        return f"{method} has lowest {col} ({val})"
    caption = str(analysis.get("caption") or "").strip()
    if caption:
        return caption[:160]
    if columns:
        return f"Comparison across {', '.join(str(c) for c in columns[:4])}"
    return ""


def project_chart_series(
    analysis: dict[str, Any], *, column: str = ""
) -> list[tuple[str, float]]:
    """Project a numeric column to (label, value) for Infographic chart modes."""
    columns = analysis.get("columns") or []
    matrix = analysis.get("matrix") or []
    stats = analysis.get("column_stats") or []
    target = column
    if not target:
        for s in stats:
            if isinstance(s, dict) and s.get("dtype") == "number":
                target = str(s.get("name") or "")
                break
    if not target or target not in columns:
        return []
    ci = columns.index(target)
    out: list[tuple[str, float]] = []
    for row in matrix:
        if ci >= len(row):
            continue
        n = _parse_number(row[ci])
        if n is None:
            continue
        label = row[0] if row else target
        out.append((label[:40], n))
    return out[:8]
