"""Parser for evidence_dossier markdown produced by ``gather_evidence.py``.

The TICKET-047 template wraps each populated section in BEGIN/END HTML
comment markers (see :data:`SECTION_MARKERS`). The :func:`gather_evidence`
script edits the file in place between those markers; this parser reads
the same markers in reverse to recover structured sources, claims, and
the candidate id from frontmatter.

Parser policy: be tolerant of empty sections and free-form prose, but
strict about required markers. A dossier missing ``sources`` or ``claims``
markers is treated as malformed and surfaced via :class:`DossierParseError`
so the worker can mark the job ``failed`` with a useful message rather
than silently skipping data.

Output shape (:class:`ParsedDossier`):
    - candidate_id : str  (from frontmatter)
    - ticket_id    : str  (from frontmatter)
    - sources      : list[ParsedSource]
    - claims       : list[ParsedClaim]
    - payload_hash : str  (sha256 over canonical sources + claims; idempotency key)
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Section markers (must match LENS/templates/evidence_dossier.md exactly)
# ---------------------------------------------------------------------------

SECTION_MARKERS: dict[str, tuple[str, str]] = {
    "context": ("<!-- BEGIN: context -->", "<!-- END: context -->"),
    "search_plan": ("<!-- BEGIN: search_plan -->", "<!-- END: search_plan -->"),
    "sources": ("<!-- BEGIN: sources -->", "<!-- END: sources -->"),
    "claims": ("<!-- BEGIN: claims -->", "<!-- END: claims -->"),
    "confidence": ("<!-- BEGIN: confidence -->", "<!-- END: confidence -->"),
    "run_record": ("<!-- BEGIN: run_record -->", "<!-- END: run_record -->"),
}

REQUIRED_SECTIONS = ("sources", "claims")

VALID_VALENCES = {"supports", "refutes", "neutral"}

# Sources rendered by gather_evidence look like:
#   "1. [Title](https://example.com) — web — One-sentence summary."
# Optional leading list bullet ("- ") is also accepted because hand-written
# dossiers may use either.
_SOURCE_LINE_RE = re.compile(
    r"""
    ^\s*
    (?:\d+\.|-)\s*                       # bullet: "1." or "-"
    \[(?P<title>[^\]]+)\]                # [Title]
    \((?P<url>[^)\s]+)\)                 # (URL)
    \s*[—\-]\s*                          # em dash or hyphen
    (?P<kind>[a-zA-Z_]+)                 # kind word
    \s*[—\-]\s*                          # em dash or hyphen
    (?P<summary>.+?)                     # summary text
    \s*$
    """,
    re.VERBOSE,
)

# Claims rendered by gather_evidence look like:
#   "- Some atomic claim text — supports — based on sources [1, 3]"
_CLAIM_LINE_RE = re.compile(
    r"""
    ^\s*-\s*
    (?P<text>.+?)                        # claim body (non-greedy)
    \s*[—\-]\s*
    (?P<valence>supports|refutes|neutral)
    \s*[—\-]\s*
    based\ on\ sources\s*
    \[(?P<sources>[^\]]*)\]              # comma-separated indices or "—"
    \s*$
    """,
    re.VERBOSE,
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FRONTMATTER_KV_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$"
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedSource:
    title: str
    url: str
    kind: str
    summary: str

    def to_canonical(self) -> dict[str, str]:
        return {
            "url": self.url,
            "title": self.title,
            "kind": self.kind,
            "citation": self.summary,
        }


@dataclass(frozen=True)
class ParsedClaim:
    text: str
    valence: str
    source_indices: tuple[int, ...]

    def to_canonical(self) -> dict[str, object]:
        return {
            "text": self.text,
            "valence": self.valence,
            "source_indices": list(self.source_indices),
        }


@dataclass
class ParsedDossier:
    candidate_id: str
    ticket_id: str
    done: bool
    sources: list[ParsedSource] = field(default_factory=list)
    claims: list[ParsedClaim] = field(default_factory=list)

    @property
    def payload_hash(self) -> str:
        """sha256 of the canonical sources+claims structure.

        Used as an idempotency key. Two parses producing the same set of
        source URLs and the same set of claim (text, valence) entries
        produce the same hash.
        """
        canonical = {
            "sources": sorted(
                [s.to_canonical() for s in self.sources], key=lambda s: s["url"]
            ),
            "claims": sorted(
                [c.to_canonical() for c in self.claims],
                key=lambda c: (str(c["text"]), str(c["valence"])),
            ),
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class DossierParseError(ValueError):
    """Raised when a dossier file is missing required structure."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_dossier_file(path: Path) -> ParsedDossier:
    return parse_dossier_text(Path(path).read_text(encoding="utf-8"))


def parse_dossier_text(text: str) -> ParsedDossier:
    fm = _parse_frontmatter(text)

    candidate_id = (fm.get("candidate_id") or "").strip()
    ticket_id = (fm.get("ticket_id") or "").strip()
    done_raw = (fm.get("done") or "false").strip().lower()
    done = done_raw in {"true", "yes", "1"}

    if not candidate_id:
        raise DossierParseError("frontmatter is missing candidate_id")
    if not ticket_id:
        raise DossierParseError("frontmatter is missing ticket_id")

    for required in REQUIRED_SECTIONS:
        if not _has_section(text, required):
            raise DossierParseError(
                f"required section '{required}' is missing BEGIN/END markers"
            )

    sources_block = _extract_section(text, "sources")
    claims_block = _extract_section(text, "claims")

    sources = list(_parse_sources(sources_block.splitlines()))
    claims = list(_parse_claims(claims_block.splitlines()))

    return ParsedDossier(
        candidate_id=candidate_id,
        ticket_id=ticket_id,
        done=done,
        sources=sources,
        claims=claims,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    body = match.group(1)
    out: dict[str, str] = {}
    for line in body.splitlines():
        kv = _FRONTMATTER_KV_RE.match(line)
        if not kv:
            continue
        value = kv.group("value").strip()
        # Trim simple surrounding quotes (the renderer wraps scalar values).
        if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]
        out[kv.group("key")] = value
    return out


def _section_pattern(name: str) -> re.Pattern[str]:
    begin, end = SECTION_MARKERS[name]
    return re.compile(rf"{re.escape(begin)}(.*?){re.escape(end)}", re.DOTALL)


def _has_section(text: str, name: str) -> bool:
    return bool(_section_pattern(name).search(text))


def _extract_section(text: str, name: str) -> str:
    match = _section_pattern(name).search(text)
    if not match:
        raise DossierParseError(f"section {name!r} not found")
    return match.group(1).strip()


def _parse_sources(lines: Iterable[str]) -> Iterable[ParsedSource]:
    seen_urls: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("_"):
            continue
        m = _SOURCE_LINE_RE.match(line)
        if not m:
            continue
        url = m.group("url").strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        yield ParsedSource(
            title=m.group("title").strip(),
            url=url,
            kind=m.group("kind").strip().lower(),
            summary=m.group("summary").strip(),
        )


def _parse_claims(lines: Iterable[str]) -> Iterable[ParsedClaim]:
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("_"):
            continue
        m = _CLAIM_LINE_RE.match(line)
        if not m:
            continue
        valence = m.group("valence").strip().lower()
        if valence not in VALID_VALENCES:
            valence = "neutral"
        idx_str = m.group("sources").strip()
        indices: list[int] = []
        if idx_str and idx_str not in {"—", "-"}:
            for piece in idx_str.split(","):
                piece = piece.strip()
                if not piece or piece in {"—", "-"}:
                    continue
                try:
                    indices.append(int(piece))
                except ValueError:
                    continue
        yield ParsedClaim(
            text=m.group("text").strip(),
            valence=valence,
            source_indices=tuple(indices),
        )
