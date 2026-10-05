"""TableVisualIntent LLM → constrained sample.json-shaped intent."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

TABLE_INTENT_MODES = frozenset(
    {
        "full_table",
        "table_with_insight",
        "ranked_bars",
        "top_k_table",
    }
)

TABLE_INTENT_SYSTEM = """You author TableVisualIntent JSON for Sunairum.

Emit a single JSON object only (no markdown). Hard rules:
- Never invent or change cell values — source cells are immutable.
- strategy.mode must be one of: full_table, table_with_insight, ranked_bars, top_k_table.
- Prefer top_k_table (top_k≤5) or ranked_bars over full dense grids when row_count>4 or col_count>5.
- Only use full_table / dense table_with_insight when the grid is small (≤4 rows and ≤5 columns).
- strategy.style: academic | bold | compact.
- emphasis.rules column names MUST exist in the provided columns list.
- insight.enabled may be true/false; do not write insight text (code templates it).
- content may set show_all_rows/show_all_columns or top_k / columns view (projection only).
"""


def _rank_column_name(analysis: dict[str, Any]) -> str | None:
    """Single clear numeric ranking column (cost/time/score), if any."""
    numeric = list(analysis.get("numeric_columns") or [])
    if not numeric:
        for st in analysis.get("column_stats") or []:
            if isinstance(st, dict) and st.get("dtype") == "number":
                name = str(st.get("name") or "")
                if name:
                    numeric.append(name)
    if len(numeric) != 1:
        # Prefer a named cost/time/score column when several numerics exist.
        for name in numeric:
            if re.search(r"(?i)\b(cost|time|score|latency|evals?|reduction)\b", name):
                return name
        return None
    return str(numeric[0])


def default_table_intent(
    analysis: dict[str, Any],
    table_id: str,
    *,
    preferred_patterns: list[str] | None = None,
    density: str = "medium",
) -> dict[str, Any]:
    rules = []
    for st in analysis.get("column_stats") or []:
        if not isinstance(st, dict) or st.get("dtype") != "number":
            continue
        name = str(st.get("name") or "")
        # Prefer min for cost-like, max for score-like
        direction = "max" if re.search(r"(?i)jain|score|acc|precision|recall", name) else "min"
        rules.append({"column": name, "direction": direction})
    patterns = [str(p).casefold() for p in (preferred_patterns or [])]
    row_count = int(analysis.get("row_count") or 0)
    col_count = len(analysis.get("columns") or [])
    mode = "table_with_insight"
    cell_bars = False
    content: dict[str, Any] = {"show_all_rows": True, "show_all_columns": True}
    rank_col = _rank_column_name(analysis)

    if any("consulting" in p or "harvey" in p for p in patterns):
        cell_bars = True
    elif any("basic_table" in p for p in patterns):
        mode = "table_with_insight"
        cell_bars = False
    elif row_count > 4 or col_count > 5:
        # Dense grids → compact top-k projection (pipeline paints insight).
        mode = "top_k_table"
        content = {
            "show_all_rows": False,
            "show_all_columns": True,
            "top_k": min(5, max(1, row_count)),
        }
    elif rank_col and row_count >= 3 and col_count <= 6:
        mode = "ranked_bars"
        content = {"show_all_rows": True, "show_all_columns": True}
    elif row_count <= 4 and col_count <= 5:
        mode = "table_with_insight"

    return {
        "table_id": table_id,
        "semantic_type": "performance_comparison",
        "purpose": "compare_methods",
        "strategy": {
            "mode": mode,
            "style": "academic",
            "density": density or "medium",
        },
        "content": content,
        "emphasis": {"strategy": "best_per_metric", "rules": rules[:6]},
        "visualization": {"cell_bars": cell_bars, "heatmap": False},
        "insight": {"enabled": True, "position": "bottom"},
    }


def validate_table_intent(
    intent: dict[str, Any], analysis: dict[str, Any], table_id: str
) -> dict[str, Any]:
    """Clamp Intent to allowlist + Analyzer facts."""
    base = default_table_intent(analysis, table_id)
    if not isinstance(intent, dict):
        return base
    out = dict(base)
    out["table_id"] = table_id
    for key in ("semantic_type", "purpose"):
        if intent.get(key):
            out[key] = str(intent[key])[:80]
    strat = intent.get("strategy") if isinstance(intent.get("strategy"), dict) else {}
    mode = str(strat.get("mode") or out["strategy"]["mode"]).strip()
    if mode not in TABLE_INTENT_MODES:
        mode = "table_with_insight"
    # ranked_bars needs numeric columns
    if mode == "ranked_bars" and not analysis.get("numeric_columns"):
        mode = str(base["strategy"]["mode"])
    row_count = int(analysis.get("row_count") or 0)
    col_count = len(analysis.get("columns") or [])
    # Refuse dense full grids for large tables — force top_k.
    if mode in {"full_table", "table_with_insight"} and (row_count > 4 or col_count > 5):
        mode = "top_k_table"
    style = str(strat.get("style") or "academic").strip().casefold() or "academic"
    density = str(strat.get("density") or "medium").strip() or "medium"
    out["strategy"] = {"mode": mode, "style": style, "density": density}

    content = intent.get("content") if isinstance(intent.get("content"), dict) else {}
    out_content: dict[str, Any] = {
        "show_all_rows": bool(content.get("show_all_rows", True)),
        "show_all_columns": bool(content.get("show_all_columns", True)),
    }
    top_k = content.get("top_k")
    if mode == "top_k_table":
        k = int(top_k) if isinstance(top_k, int) and top_k > 0 else min(5, max(1, row_count))
        out_content["top_k"] = min(5, k, max(1, row_count))
        out_content["show_all_rows"] = False
    elif isinstance(top_k, int) and top_k > 0:
        out_content["top_k"] = min(top_k, int(analysis.get("row_count") or top_k))
        out_content["show_all_rows"] = False
    cols = content.get("columns")
    known = set(analysis.get("columns") or [])
    if isinstance(cols, list):
        filtered = [str(c) for c in cols if str(c) in known]
        if filtered:
            out_content["columns"] = filtered
            out_content["show_all_columns"] = False
    out["content"] = out_content

    emph = intent.get("emphasis") if isinstance(intent.get("emphasis"), dict) else {}
    rules_in = emph.get("rules") if isinstance(emph.get("rules"), list) else []
    rules_out = []
    for rule in rules_in:
        if not isinstance(rule, dict):
            continue
        col = str(rule.get("column") or "")
        if col not in known:
            continue
        direction = str(rule.get("direction") or "min").casefold()
        if direction not in {"min", "max"}:
            direction = "min"
        rules_out.append({"column": col, "direction": direction})
    if not rules_out:
        rules_out = list(base["emphasis"]["rules"])
    out["emphasis"] = {
        "strategy": str(emph.get("strategy") or "best_per_metric"),
        "rules": rules_out,
    }
    insight = intent.get("insight") if isinstance(intent.get("insight"), dict) else {}
    out["insight"] = {
        "enabled": bool(insight.get("enabled", True)),
        "position": str(insight.get("position") or "bottom"),
    }
    viz = intent.get("visualization") if isinstance(intent.get("visualization"), dict) else {}
    out["visualization"] = {
        "cell_bars": bool(viz.get("cell_bars", False)),
        "heatmap": bool(viz.get("heatmap", False)),
    }
    return out


def author_table_visual_intent(
    analysis: dict[str, Any],
    *,
    table_id: str,
    slide: dict[str, Any] | None = None,
    aabb: tuple[float, float, float, float] | None = None,
    call_text: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """LLM Intent with deterministic default + validation."""
    slide = slide or {}
    preferred = slide.get("pack_table_patterns") or slide.get("pack_chart_pattern")
    if isinstance(preferred, str):
        preferred = [preferred]
    if not isinstance(preferred, list):
        preferred = None
    fallback = default_table_intent(
        analysis,
        table_id,
        preferred_patterns=preferred,
        density=str(slide.get("density") or "medium"),
    )
    if call_text is None:
        return fallback
    payload = {
        "table_id": table_id,
        "caption": analysis.get("caption"),
        "columns": analysis.get("columns"),
        "row_count": analysis.get("row_count"),
        "numeric_columns": analysis.get("numeric_columns"),
        "slide_title": slide.get("title"),
        "core_message": slide.get("core_message"),
        "aabb": {"x": aabb[0], "y": aabb[1], "w": aabb[2], "h": aabb[3]} if aabb else None,
        "modes": sorted(TABLE_INTENT_MODES),
        "hint": "Prefer top_k_table or ranked_bars for large grids.",
    }
    try:
        raw = str(
            call_text(
                TABLE_INTENT_SYSTEM,
                "Author TableVisualIntent for:\n" + json.dumps(payload, ensure_ascii=False),
            )
            or ""
        ).strip()
    except Exception:
        # Transport / budget failures must stop the run (no silent default Intent).
        raise
    if not raw:
        raise RuntimeError("provider returned an empty TableVisualIntent response")
    try:
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
        parsed = json.loads(raw)
    except Exception:
        return fallback
    return validate_table_intent(parsed, analysis, table_id)
