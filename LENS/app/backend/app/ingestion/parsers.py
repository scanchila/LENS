"""Parser dispatch for ingestion (TICKET-020).

The dispatcher picks an extractor by extension or MIME type. Each extractor
returns ``(text, metadata)`` where metadata is JSON-serializable and lands
in ``documents.parsed_metadata``.

Extractors:
  - PDF: ``pypdf`` primary, ``pdfminer.six`` fallback on parse failure.
  - HTML: ``trafilatura`` (clean main-content extraction).
  - Markdown: strip YAML frontmatter, return body.
  - Plain text: passthrough.

Failure mode: ``UnsupportedDocumentError`` for unknown types,
``ParserError`` for hard parse failures (after fallback).
"""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("app.ingestion.parsers")


class UnsupportedDocumentError(ValueError):
    """Raised when the file type cannot be ingested."""


class ParserError(RuntimeError):
    """Raised when a supported file cannot be parsed (incl. fallbacks)."""


@dataclass
class ParseOutput:
    text: str
    metadata: dict[str, Any]
    source_type: str  # "pdf" | "markdown" | "html" | "text"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _parse_pdf_pypdf(data: bytes) -> ParseOutput | None:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        logger.warning("pypdf unavailable: %s", exc)
        return None

    try:
        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as page_exc:  # noqa: BLE001
                # Per-page extraction can fail on malformed streams; preserve
                # ord but skip content for this page.
                logger.debug("pypdf page extract failed: %s", page_exc)
                pages.append("")
        text = "\n\n".join(p.strip() for p in pages if p)
        if not text.strip():
            # Empty extraction is not a "success" — fall back to pdfminer.
            return None
        metadata: dict[str, Any] = {
            "page_count": len(reader.pages),
            "char_count": len(text),
            "extractor": "pypdf",
        }
        return ParseOutput(text=text, metadata=metadata, source_type="pdf")
    except Exception as exc:
        logger.info("pypdf parse failed; will try pdfminer: %s", exc)
        return None


def _parse_pdf_pdfminer(data: bytes) -> ParseOutput:
    try:
        from pdfminer.high_level import extract_text
    except Exception as exc:
        raise ParserError(f"pdfminer.six not installed: {exc}") from exc

    try:
        text = extract_text(io.BytesIO(data)) or ""
    except Exception as exc:
        raise ParserError(f"pdfminer extraction failed: {exc}") from exc

    if not text.strip():
        raise ParserError("PDF produced no extractable text via pdfminer")

    return ParseOutput(
        text=text.strip(),
        metadata={
            "page_count": text.count("\f") + 1,  # pdfminer separates pages with \f
            "char_count": len(text),
            "extractor": "pdfminer",
        },
        source_type="pdf",
    )


def parse_pdf(data: bytes) -> ParseOutput:
    primary = _parse_pdf_pypdf(data)
    if primary is not None:
        return primary
    return _parse_pdf_pdfminer(data)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def parse_markdown(data: bytes) -> ParseOutput:
    text = data.decode("utf-8", errors="replace")
    stripped = _FRONTMATTER_RE.sub("", text, count=1).strip()
    return ParseOutput(
        text=stripped,
        metadata={
            "char_count": len(stripped),
            "had_frontmatter": stripped != text.strip(),
            "extractor": "markdown",
        },
        source_type="markdown",
    )


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def parse_html(data: bytes) -> ParseOutput:
    try:
        import trafilatura
    except Exception as exc:
        raise ParserError(f"trafilatura not installed: {exc}") from exc

    raw = data.decode("utf-8", errors="replace")
    extracted = trafilatura.extract(
        raw,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not extracted or not extracted.strip():
        raise ParserError("HTML produced no extractable text via trafilatura")

    return ParseOutput(
        text=extracted.strip(),
        metadata={
            "char_count": len(extracted),
            "extractor": "trafilatura",
        },
        source_type="html",
    )


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def parse_text(data: bytes) -> ParseOutput:
    text = data.decode("utf-8", errors="replace").strip()
    return ParseOutput(
        text=text,
        metadata={"char_count": len(text), "extractor": "text"},
        source_type="text",
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def detect_kind(filename: str, mime_type: str | None) -> str:
    """Return one of: pdf, markdown, html, text. Raises on unsupported."""
    ext = os.path.splitext(filename)[1].lower()
    mt = (mime_type or "").lower().split(";", 1)[0].strip()

    if ext == ".pdf" or mt == "application/pdf":
        return "pdf"
    if ext in (".md", ".markdown") or mt in ("text/markdown", "text/x-markdown"):
        return "markdown"
    if ext in (".html", ".htm") or mt in ("text/html", "application/xhtml+xml"):
        return "html"
    if ext == ".txt" or mt == "text/plain":
        return "text"

    raise UnsupportedDocumentError(
        f"Unsupported file type for {filename!r} (mime={mime_type!r})"
    )


def parse_document(
    data: bytes,
    filename: str,
    mime_type: str | None = None,
) -> ParseOutput:
    """Parse ``data`` into normalized text + metadata.

    Args:
        data: raw file bytes
        filename: original upload filename; used for extension dispatch
        mime_type: optional Content-Type hint
    """
    kind = detect_kind(filename, mime_type)
    if kind == "pdf":
        return parse_pdf(data)
    if kind == "markdown":
        return parse_markdown(data)
    if kind == "html":
        return parse_html(data)
    if kind == "text":
        return parse_text(data)
    raise UnsupportedDocumentError(f"Unknown kind {kind!r}")
