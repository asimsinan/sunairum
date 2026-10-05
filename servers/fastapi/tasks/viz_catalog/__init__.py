"""Index-only chart/table vocabulary for Strategist/Executor (no SVG scaffolds)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parent
_CHART_KEY_RE = re.compile(r"^chart/([A-Za-z0-9_-]+)$")
_TABLE_KEY_RE = re.compile(r"^table/([A-Za-z0-9_-]+)$")


@lru_cache(maxsize=1)
def charts_index() -> dict[str, Any]:
    return _load_index(CATALOG_DIR / "charts_index.json", "charts")


@lru_cache(maxsize=1)
def tables_index() -> dict[str, Any]:
    return _load_index(CATALOG_DIR / "tables_index.json", "tables")


def _load_index(path: Path, key: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    section = data.get(key)
    return section if isinstance(section, dict) else {}


def chart_keys() -> list[str]:
    return sorted(charts_index().keys())


def table_keys() -> list[str]:
    return sorted(tables_index().keys())


def summary_for(visualization: str | None) -> str:
    """Bounded Pick-for / Skip-if summary for a catalog Visualization key."""
    raw = str(visualization or "").strip()
    m = _CHART_KEY_RE.match(raw)
    if m:
        meta = charts_index().get(m.group(1))
        if isinstance(meta, dict):
            return str(meta.get("summary") or "")
        return ""
    m = _TABLE_KEY_RE.match(raw)
    if m:
        meta = tables_index().get(m.group(1))
        if isinstance(meta, dict):
            return str(meta.get("summary") or "")
        return ""
    return ""


def is_catalog_key(visualization: str | None) -> bool:
    return bool(summary_for(visualization))


def catalog_menu_block(*, limit: int = 40) -> str:
    """Compact Strategist menu of legal chart/table keys (summaries truncated)."""
    lines = [
        "## Visualization catalog (index-only — pick a key, never paste SVG scaffolds)",
        "Allowed forms: `chart/<key>` or `table/<key>` in addition to existing Visualization tokens.",
    ]
    charts = chart_keys()[: max(1, limit // 2)]
    tables = table_keys()[: max(1, limit // 2)]
    if charts:
        lines.append("Charts:")
        for key in charts:
            summary = str((charts_index().get(key) or {}).get("summary") or "")[:140]
            lines.append(f"- chart/{key} — {summary}")
    if tables:
        lines.append("Tables:")
        for key in tables:
            summary = str((tables_index().get(key) or {}).get("summary") or "")[:140]
            lines.append(f"- table/{key} — {summary}")
    lines.append("")
    return "\n".join(lines)


def page_viz_hint(visualization: str | None) -> str:
    summary = summary_for(visualization)
    if not summary:
        return ""
    return (
        f"## Catalog visualization ({visualization})\n"
        f"- {summary}\n"
        "- Author original Constrained HTML geometry for THIS page's data; "
        "do not paste demo scaffolds. Leave bound hosts empty for Intent.\n"
    )
