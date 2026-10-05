"""Independent page counting for uploaded PDFs.

The quality gate compares the parser's own page count against the PDF's, so the
count has to come from something other than the parser. ``pypdfium2`` is used
because it arrives with ``docling[format-pdf]`` and is a different code path
from the layout pipeline, which keeps the cross-check meaningful.
"""

from __future__ import annotations

from pathlib import Path


def count_pdf_pages(path: str | Path) -> int:
    """Return the page count, or raise when no PDF reader is available."""
    try:
        import pypdfium2
    except ImportError as exc:  # pragma: no cover - the image installs docling
        raise RuntimeError("pypdfium2 is required to validate PDF page count") from exc
    document = pypdfium2.PdfDocument(str(path))
    try:
        return len(document)
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()
