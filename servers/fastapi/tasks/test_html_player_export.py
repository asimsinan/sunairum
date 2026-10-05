"""Unit tests for Deckflow-style HTML player export."""

from __future__ import annotations

import base64
import gzip
import io
import json
import re
import zipfile
from pathlib import Path

from tasks.html_player_export import (
    HtmlPlayerExportError,
    build_html_player_zip,
    build_player_data,
    compress_page_html,
    render_player_index_html,
)


def test_compress_page_roundtrip():
    html = "<!doctype html><html><body><h1>Hello</h1></body></html>"
    encoded = compress_page_html(html)
    raw = gzip.decompress(base64.b64decode(encoded))
    assert raw.decode("utf-8") == html


def test_build_player_zip_contains_index(tmp_path: Path):
    html_dir = tmp_path / "html_output"
    html_dir.mkdir()
    (html_dir / "slide_01.html").write_text(
        "<!doctype html><html><body><div>One</div></body></html>", encoding="utf-8"
    )
    (html_dir / "slide_02.html").write_text(
        "<!doctype html><html><body><div>Two</div></body></html>", encoding="utf-8"
    )

    zip_bytes, filename = build_html_player_zip(
        tmp_path, title="My Deck Title", project_id="proj_test"
    )
    assert filename.endswith("-html.zip")
    assert "My-Deck-Title" in filename or "My" in filename

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].endswith("/index.html")
        index = zf.read(names[0]).decode("utf-8")

    assert "My Deck Title" in index
    assert "Sunairum" in index
    match = re.search(r"const playerData = (\{.*?\});", index, re.DOTALL)
    assert match, "playerData missing from index.html"
    data = json.loads(match.group(1))
    assert data["pageWidth"] == 1280
    assert data["pageHeight"] == 720
    assert len(data["pages"]) == 2
    page0 = gzip.decompress(base64.b64decode(data["pages"][0])).decode("utf-8")
    assert "One" in page0


def test_missing_html_raises(tmp_path: Path):
    try:
        build_html_player_zip(tmp_path, title="Empty")
        raise AssertionError("expected HtmlPlayerExportError")
    except HtmlPlayerExportError:
        pass


def test_render_player_embeds_pages():
    data = build_player_data(["<html><body>A</body></html>"])
    html = render_player_index_html(title="T", player_data=data)
    assert "const playerData =" in html
    assert "DecompressionStream" in html


def test_player_chrome_is_outside_slide_canvas_and_reserved_in_scale():
    html = render_player_index_html(
        title="T", player_data=build_player_data(["<html><body>A</body></html>"])
    )

    canvas_end = html.index('</div>\n      <div id="playerChrome"')
    frame_start = html.index('<div id="playerCanvas">')
    frame_end = html.index('</div>', frame_start)
    assert frame_start < frame_end <= canvas_end
    assert 'const playerChromeHeight = 32;' in html
    assert 'const playerHeight = pageHeight + playerChromeHeight;' in html
    assert 'viewportHeight / playerHeight' in html
    assert '#playerChrome {' in html
    assert 'position: static;' in html
