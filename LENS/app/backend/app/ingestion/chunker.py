"""Chunker (TICKET-020).

Strategy:
  1. Split on blank-line paragraphs (semantic primary).
  2. Pack consecutive paragraphs greedily up to ``target_tokens``.
  3. If a single paragraph exceeds ``target_tokens``, fall back to a sliding
     window (``target_tokens`` with ``overlap_tokens`` overlap).

Char offsets refer to the parsed text (post-extraction), not the raw file.
That is the correct level for provenance: we cite the chunk against the
extracted document, which is what we re-search against.

Why tiktoken: cheap, deterministic, language-agnostic across the encodings
we use. Voyage uses its own tokenizer for billing, but tiktoken is close
enough for chunk sizing and we already use it elsewhere for cost estimation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("app.ingestion.chunker")


DEFAULT_TARGET_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 100
TIKTOKEN_ENCODING = "cl100k_base"


@dataclass
class TextChunk:
    ord: int
    text: str
    char_start: int
    char_end: int
    tokens: int


_PARAGRAPH_RE = re.compile(r"\n\s*\n")


class Encoder:
    def encode(self, text: str) -> list[int]:
        raise NotImplementedError

    def count(self, text: str) -> int:
        return len(self.encode(text))


class _TiktokenEncoder(Encoder):
    def __init__(self, enc: Any) -> None:
        self._enc = enc

    def encode(self, text: str) -> list[int]:
        return list(self._enc.encode(text))


class _WhitespaceEncoder(Encoder):
    def encode(self, text: str) -> list[int]:
        # Treat every non-empty token as one id. Stable but coarse.
        return [1 for t in text.split() if t]


def _get_encoder() -> Encoder:
    try:
        import tiktoken

        enc = tiktoken.get_encoding(TIKTOKEN_ENCODING)
        return _TiktokenEncoder(enc)
    except Exception as exc:
        # Fall back to a whitespace token estimate. Sub-optimal but keeps
        # ingestion functional in environments without the tiktoken data files.
        logger.warning(
            "tiktoken unavailable; falling back to whitespace estimate: %s", exc
        )
        return _WhitespaceEncoder()


def _iter_paragraphs(text: str) -> list[tuple[str, int, int]]:
    """Yield ``(paragraph_text, char_start, char_end)`` over ``text``.

    Empty paragraphs are skipped. Char offsets are relative to ``text``.
    """
    paragraphs: list[tuple[str, int, int]] = []
    cursor = 0
    for match in _PARAGRAPH_RE.finditer(text):
        end = match.start()
        if end > cursor:
            block = text[cursor:end]
            if block.strip():
                paragraphs.append((block, cursor, end))
        cursor = match.end()
    if cursor < len(text):
        block = text[cursor:]
        if block.strip():
            paragraphs.append((block, cursor, len(text)))
    return paragraphs


def _sliding_window_split(
    paragraph: str,
    char_start: int,
    target_tokens: int,
    overlap_tokens: int,
    encoder: Encoder,
) -> list[tuple[str, int, int, int]]:
    """Split a single oversized paragraph into windows.

    Returns ``[(text, char_start_abs, char_end_abs, tokens), ...]``.

    The window slides over the encoded ids, then we map the id-window back to
    a char range via decode where the encoder supports it. For the whitespace
    fallback we slide on whitespace tokens directly.
    """
    if isinstance(encoder, _TiktokenEncoder):
        ids = encoder.encode(paragraph)
        results: list[tuple[str, int, int, int]] = []
        if not ids:
            return results
        step = max(target_tokens - overlap_tokens, 1)
        for window_start in range(0, len(ids), step):
            window = ids[window_start : window_start + target_tokens]
            if not window:
                break
            try:
                window_text = encoder._enc.decode(window)
            except Exception:  # noqa: BLE001
                window_text = ""
            if not window_text.strip():
                continue
            # Char offsets within paragraph: locate windowed text by best-effort
            # search starting from a heuristic position.
            heuristic_pos = int(len(paragraph) * window_start / max(len(ids), 1))
            local_start = paragraph.find(
                window_text.strip()[:64], max(0, heuristic_pos - 64)
            )
            if local_start < 0:
                local_start = heuristic_pos
            local_end = local_start + len(window_text)
            results.append(
                (
                    window_text.strip(),
                    char_start + local_start,
                    char_start + local_end,
                    len(window),
                )
            )
            if window_start + target_tokens >= len(ids):
                break
        return results

    # Whitespace fallback: window over words.
    words = paragraph.split()
    if not words:
        return []
    step = max(target_tokens - overlap_tokens, 1)
    out: list[tuple[str, int, int, int]] = []
    cursor = 0
    for window_start in range(0, len(words), step):
        word_window = words[window_start : window_start + target_tokens]
        if not word_window:
            break
        window_text = " ".join(word_window)
        local_start = paragraph.find(word_window[0], cursor)
        if local_start < 0:
            local_start = cursor
        local_end = local_start + len(window_text)
        cursor = local_end
        out.append(
            (
                window_text,
                char_start + local_start,
                char_start + local_end,
                len(word_window),
            )
        )
        if window_start + target_tokens >= len(words):
            break
    return out


def chunk_text(
    text: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Chunk ``text`` for embedding.

    Output invariants:
      * Every chunk has token count <= ``target_tokens`` (post-encoder).
      * Char offsets are non-decreasing across chunks (overlap windows may
        share ranges but ``ord`` is strictly increasing).
      * Chunks preserve insertion order; ``ord`` starts at 0.
    """
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be in [0, target_tokens)")

    encoder = _get_encoder()
    chunks: list[TextChunk] = []
    paragraphs = _iter_paragraphs(text)

    if not paragraphs:
        # Empty document; return no chunks. Caller should treat 0-chunk
        # docs as a soft failure but not crash.
        return chunks

    buffer_text: list[str] = []
    buffer_start: int | None = None
    buffer_end = 0
    buffer_tokens = 0
    ord_counter = 0

    def _flush() -> None:
        nonlocal buffer_text, buffer_start, buffer_end, buffer_tokens, ord_counter
        if not buffer_text:
            return
        joined = "\n\n".join(buffer_text).strip()
        if joined:
            chunks.append(
                TextChunk(
                    ord=ord_counter,
                    text=joined,
                    char_start=buffer_start or 0,
                    char_end=buffer_end,
                    tokens=buffer_tokens,
                )
            )
            ord_counter += 1
        buffer_text = []
        buffer_start = None
        buffer_end = 0
        buffer_tokens = 0

    for paragraph, p_start, p_end in paragraphs:
        p_tokens = encoder.count(paragraph)
        if p_tokens > target_tokens:
            _flush()
            for window_text, w_start, w_end, w_tokens in _sliding_window_split(
                paragraph, p_start, target_tokens, overlap_tokens, encoder
            ):
                chunks.append(
                    TextChunk(
                        ord=ord_counter,
                        text=window_text,
                        char_start=w_start,
                        char_end=w_end,
                        tokens=w_tokens,
                    )
                )
                ord_counter += 1
            continue

        if buffer_tokens + p_tokens > target_tokens and buffer_text:
            _flush()

        if buffer_start is None:
            buffer_start = p_start
        buffer_text.append(paragraph)
        buffer_end = p_end
        buffer_tokens += p_tokens

    _flush()

    return chunks
