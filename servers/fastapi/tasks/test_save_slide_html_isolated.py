"""Edits must overwrite one stem only — never reorder or touch siblings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tasks.deck_editor import save_slide_html


def _slide_html(title: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body><section class="slide"><h1>{title}</h1></section></body></html>
"""


def test_save_slide_html_does_not_touch_other_slides(tmp_path: Path):
    html_dir = tmp_path / "html_output"
    preview_dir = tmp_path / "preview"
    html_dir.mkdir()
    preview_dir.mkdir()
    (html_dir / "slide_01.html").write_text(_slide_html("One"), encoding="utf-8")
    (html_dir / "slide_02.html").write_text(_slide_html("Two"), encoding="utf-8")
    (html_dir / "slide_03.html").write_text(_slide_html("Three"), encoding="utf-8")
    before = {p.name: p.read_text(encoding="utf-8") for p in sorted(html_dir.glob("slide_*.html"))}

    result = save_slide_html(
        tmp_path,
        "slide_02.html",
        _slide_html("Two edited"),
        refresh_preview=False,
    )

    assert result["filename"] == "slide_02.html"
    after_names = sorted(p.name for p in html_dir.glob("slide_*.html"))
    assert after_names == ["slide_01.html", "slide_02.html", "slide_03.html"]
    assert "Two edited" in (html_dir / "slide_02.html").read_text(encoding="utf-8")
    assert (html_dir / "slide_01.html").read_text(encoding="utf-8") == before["slide_01.html"]
    assert (html_dir / "slide_03.html").read_text(encoding="utf-8") == before["slide_03.html"]


def test_save_slide_html_refuses_missing_stem(tmp_path: Path):
    html_dir = tmp_path / "html_output"
    html_dir.mkdir()
    (html_dir / "slide_01.html").write_text(_slide_html("One"), encoding="utf-8")
    try:
        save_slide_html(tmp_path, "slide_99.html", _slide_html("Nope"), refresh_preview=False)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
    assert list(html_dir.glob("slide_*.html")) == [html_dir / "slide_01.html"]


def test_save_slide_html_keeps_freeform_overflow_as_advisory(tmp_path: Path):
    html_dir = tmp_path / "html_output"
    html_dir.mkdir()
    (html_dir / "slide_01.html").write_text(_slide_html("One"), encoding="utf-8")
    report = {
        "ok": False,
        "hard": ["runtime_text_overflow: section[scene-title] scrolls (0px x, 34px y)"],
        "issues": ["runtime_text_overflow"],
    }

    with patch("tasks.html_layout_qa.audit_runtime_html_layout", return_value=report):
        result = save_slide_html(
            tmp_path,
            "slide_01.html",
            _slide_html("A deliberately oversized free-form title"),
            refresh_preview=False,
        )

    assert result["status"] == "ok"
    assert result["layout_valid"] is False
    assert result["layout_advisory"] is True
    assert "oversized" in (html_dir / "slide_01.html").read_text(encoding="utf-8")
