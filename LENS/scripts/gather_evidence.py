#!/usr/bin/env python3
"""Evidence-gathering CLI for an ``evidence_dossier`` CAR ticket.

Given a candidate id, a claim, and the path to a ticket file produced from
``LENS/templates/evidence_dossier.md``, this script:

1. Searches a ranked set of backends (Tavily → Semantic Scholar → HN Algolia →
   Reddit) for sources relevant to the claim.
2. Fetches each source (HTML via ``trafilatura``, PDFs via ``pypdf``).
3. Summarizes each source in one sentence with Anthropic Sonnet.
4. Extracts 5–10 atomic claims (with valence + source citations) via Sonnet.
5. Edits the ticket file in place, replacing content between the
   ``<!-- BEGIN: x --> / <!-- END: x -->`` markers placed by 047.
6. Aborts (with a budget note in ``## Run record``) if cumulative cost crosses
   ``--cost-cap`` (default $1.00).

Crucially, this script never flips ``done: true``. The reviewing agent
(Hermes/Codex) is responsible for that after a manual or LLM review pass.

Required deps (declared as a requirements snippet so this can be run as a
standalone tool from CAR without having the LENS backend env active):

    anthropic>=0.39.0       # direct Messages API client (NOT the agent SDK)
    requests>=2.31          # Semantic Scholar / HN Algolia / general fetch
    trafilatura>=1.12       # HTML extraction
    pypdf>=4.0              # PDF text extraction
    # optional:
    tavily-python>=0.5      # used if installed; raw requests fallback exists
    praw>=7.7               # used if all REDDIT_* env vars present, else skipped

Environment variables consumed:
    ANTHROPIC_API_KEY    - required for live runs (mocked in tests)
    TAVILY_API_KEY       - if missing, Tavily backend is skipped
    SEMANTIC_SCHOLAR_API_KEY - optional; SS API works unauthenticated too
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
                         - all three required to enable the Reddit backend
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_COST_CAP_USD = 1.00
DEFAULT_PER_SOURCE_TIMEOUT = 15  # seconds
DEFAULT_SOURCES_PER_BACKEND = 10
DEFAULT_FETCH_BYTES_LIMIT = 2_000_000  # 2 MB hard cap per source

# Sonnet pricing (per million tokens) — approximate, used for budget tracking.
# Real cost is reported by the API; we fall back to these only if the API
# response lacks usage info.
SONNET_INPUT_USD_PER_MTOK = 3.00
SONNET_OUTPUT_USD_PER_MTOK = 15.00

SECTION_MARKERS = {
    "sources": ("<!-- BEGIN: sources -->", "<!-- END: sources -->"),
    "claims": ("<!-- BEGIN: claims -->", "<!-- END: claims -->"),
    "run_record": ("<!-- BEGIN: run_record -->", "<!-- END: run_record -->"),
    "context": ("<!-- BEGIN: context -->", "<!-- END: context -->"),
    "search_plan": ("<!-- BEGIN: search_plan -->", "<!-- END: search_plan -->"),
    "confidence": ("<!-- BEGIN: confidence -->", "<!-- END: confidence -->"),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Source:
    title: str
    url: str
    kind: str  # web | paper | forum | blog
    backend: str
    raw_text: str = ""
    summary: str = ""

    def as_markdown(self) -> str:
        title = self.title.replace("[", "(").replace("]", ")") or self.url
        summary = self.summary or "(no summary)"
        return f"- [{title}]({self.url}) — {self.kind} — {summary}"


@dataclass
class Claim:
    text: str
    valence: str  # supports | refutes | neutral
    source_indices: list[int]

    def as_markdown(self) -> str:
        valence = (
            self.valence
            if self.valence in {"supports", "refutes", "neutral"}
            else "neutral"
        )
        cites = ", ".join(str(i) for i in self.source_indices) or "—"
        return f"- {self.text} — {valence} — based on sources [{cites}]"


@dataclass
class CostLedger:
    cap_usd: float
    spend_usd: float = 0.0
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, *, label: str, usd: float, **meta: Any) -> None:
        self.spend_usd += max(0.0, usd)
        entry = {"label": label, "usd": round(usd, 6)}
        entry.update(meta)
        self.entries.append(entry)

    def would_exceed(self, projected_usd: float = 0.0) -> bool:
        return (self.spend_usd + max(0.0, projected_usd)) > self.cap_usd

    @property
    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spend_usd)


class BudgetExceeded(Exception):
    pass


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------


def search_tavily(
    claim: str, *, top_k: int = DEFAULT_SOURCES_PER_BACKEND
) -> list[Source]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": claim,
                "max_results": top_k,
                "search_depth": "advanced",
            },
            timeout=DEFAULT_PER_SOURCE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    results: list[Source] = []
    for hit in (data.get("results") or [])[:top_k]:
        url = hit.get("url") or ""
        if not url:
            continue
        results.append(
            Source(
                title=hit.get("title") or url,
                url=url,
                kind="web",
                backend="tavily",
                raw_text=(hit.get("content") or "")[:DEFAULT_FETCH_BYTES_LIMIT],
            )
        )
    return results


def search_semantic_scholar(
    claim: str, *, top_k: int = DEFAULT_SOURCES_PER_BACKEND
) -> list[Source]:
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return []
    headers = {}
    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    params = {
        "query": claim,
        "limit": top_k,
        "fields": "title,abstract,url,year,citationCount,authors,openAccessPdf",
    }
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
            headers=headers,
            timeout=DEFAULT_PER_SOURCE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    out: list[Source] = []
    for paper in (data.get("data") or [])[:top_k]:
        url = paper.get("url") or ""
        pdf = paper.get("openAccessPdf") or {}
        if pdf.get("url"):
            url = pdf["url"]
        if not url:
            continue
        title = paper.get("title") or url
        abstract = paper.get("abstract") or ""
        out.append(
            Source(
                title=title,
                url=url,
                kind="paper",
                backend="semantic_scholar",
                raw_text=abstract,
            )
        )
    return out


def search_hn_algolia(
    claim: str, *, top_k: int = DEFAULT_SOURCES_PER_BACKEND
) -> list[Source]:
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return []
    params = {"query": claim, "tags": "(story,comment)", "hitsPerPage": top_k}
    try:
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params=params,
            timeout=DEFAULT_PER_SOURCE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    out: list[Source] = []
    for hit in (data.get("hits") or [])[:top_k]:
        url = hit.get("url") or (
            f"https://news.ycombinator.com/item?id={hit['objectID']}"
            if hit.get("objectID")
            else ""
        )
        if not url:
            continue
        title = hit.get("title") or hit.get("story_title") or url
        text = hit.get("comment_text") or hit.get("story_text") or ""
        out.append(
            Source(
                title=title,
                url=url,
                kind="forum",
                backend="hn_algolia",
                raw_text=text,
            )
        )
    return out


def search_reddit(
    claim: str, *, top_k: int = DEFAULT_SOURCES_PER_BACKEND
) -> list[Source]:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT")
    if not (client_id and client_secret and user_agent):
        return []
    try:
        import praw  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        reddit.read_only = True
    except Exception:
        return []
    subreddits = ("startups", "programming", "technology")
    sub = reddit.subreddit("+".join(subreddits))
    out: list[Source] = []
    try:
        for submission in sub.search(claim, limit=top_k):
            out.append(
                Source(
                    title=submission.title or submission.url or "",
                    url=submission.url or f"https://reddit.com{submission.permalink}",
                    kind="forum",
                    backend="reddit",
                    raw_text=(submission.selftext or "")[:DEFAULT_FETCH_BYTES_LIMIT],
                )
            )
    except Exception:
        return out
    return out


SearchBackend = Callable[[str], list[Source]]

DEFAULT_BACKENDS: list[tuple[str, SearchBackend]] = [
    ("tavily", search_tavily),
    ("semantic_scholar", search_semantic_scholar),
    ("hn_algolia", search_hn_algolia),
    ("reddit", search_reddit),
]


# ---------------------------------------------------------------------------
# Source extraction (HTML / PDF)
# ---------------------------------------------------------------------------


def extract_text(source: Source) -> str:
    if source.raw_text and len(source.raw_text) > 200:
        return source.raw_text[:DEFAULT_FETCH_BYTES_LIMIT]

    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return source.raw_text
    try:
        resp = requests.get(source.url, timeout=DEFAULT_PER_SOURCE_TIMEOUT, stream=True)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        body = resp.raw.read(DEFAULT_FETCH_BYTES_LIMIT, decode_content=True)
    except Exception:
        return source.raw_text

    if "pdf" in ctype.lower() or source.url.lower().endswith(".pdf"):
        return _extract_pdf_text(body)
    return _extract_html_text(body)


def _extract_html_text(body: bytes) -> str:
    try:
        import trafilatura  # type: ignore[import-not-found]
    except ImportError:
        try:
            return body.decode("utf-8", errors="replace")[:DEFAULT_FETCH_BYTES_LIMIT]
        except Exception:
            return ""
    try:
        text = trafilatura.extract(body.decode("utf-8", errors="replace")) or ""
    except Exception:
        return ""
    return text[:DEFAULT_FETCH_BYTES_LIMIT]


def _extract_pdf_text(body: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(body))
        chunks: list[str] = []
        for page in reader.pages[:30]:
            chunks.append(page.extract_text() or "")
        return ("\n".join(chunks))[:DEFAULT_FETCH_BYTES_LIMIT]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Anthropic LLM glue
# ---------------------------------------------------------------------------


class LLMClient:
    """Thin wrapper around the Anthropic Messages API.

    Tests inject a mock by passing ``client=`` to the public functions below.
    """

    def __init__(self, *, model: str = DEFAULT_MODEL):
        self.model = model
        self._client: Any | None = None

    def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK is required for live runs. `pip install anthropic`"
            ) from exc
        self._client = Anthropic()
        return self._client

    def messages_create(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 256,
    ) -> tuple[str, dict[str, Any]]:
        client = self._ensure()
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text
            for block in resp.content
            if getattr(block, "type", None) == "text"
        )
        usage = {
            "input_tokens": getattr(resp.usage, "input_tokens", 0),
            "output_tokens": getattr(resp.usage, "output_tokens", 0),
        }
        return text, usage


def _estimate_call_cost_usd(usage: dict[str, Any]) -> float:
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)
    return (
        in_tok * SONNET_INPUT_USD_PER_MTOK / 1_000_000
        + out_tok * SONNET_OUTPUT_USD_PER_MTOK / 1_000_000
    )


def summarize_source(
    source: Source, *, claim: str, llm: LLMClient, ledger: CostLedger
) -> str:
    if ledger.would_exceed(0.01):
        raise BudgetExceeded(f"summarize_source: cap ${ledger.cap_usd} exceeded")
    excerpt = (source.raw_text or "")[:4000]
    if not excerpt.strip():
        excerpt = source.title
    user = (
        "Claim under investigation:\n"
        f"  {claim}\n\n"
        f"Source title: {source.title}\nSource URL: {source.url}\n"
        "Source content (truncated):\n"
        f"---\n{excerpt}\n---\n\n"
        "Summarize this source in EXACTLY ONE sentence (max 35 words). "
        "Focus on whether/how it bears on the claim. No prefatory phrasing."
    )
    text, usage = llm.messages_create(
        system="You produce dense one-sentence source summaries for an evidence dossier.",
        user=user,
        max_tokens=120,
    )
    ledger.add(
        label=f"summary:{source.backend}",
        usd=_estimate_call_cost_usd(usage),
        url=source.url,
    )
    return text.strip().splitlines()[0] if text.strip() else ""


def extract_claims(
    sources: list[Source],
    *,
    claim: str,
    llm: LLMClient,
    ledger: CostLedger,
) -> list[Claim]:
    if not sources:
        return []
    if ledger.would_exceed(0.05):
        raise BudgetExceeded(f"extract_claims: cap ${ledger.cap_usd} exceeded")
    indexed = "\n".join(
        f"[{i + 1}] ({s.kind}) {s.title} — {s.summary or '(no summary)'} — {s.url}"
        for i, s in enumerate(sources)
    )
    user = (
        f"Original claim under investigation:\n  {claim}\n\n"
        "Sources (1-indexed):\n"
        f"{indexed}\n\n"
        "Extract 5–10 ATOMIC sub-claims from these sources. "
        "Each sub-claim must:\n"
        "  - state ONE testable proposition,\n"
        "  - have valence one of supports|refutes|neutral relative to the original claim,\n"
        "  - cite source indices it derives from.\n\n"
        'Return strictly as JSON: {"claims":[{"text":"...","valence":"supports","sources":[1,3]}, ...]} '
        "with no prose outside the JSON."
    )
    text, usage = llm.messages_create(
        system="You extract atomic claims with valence + provenance for an evidence dossier.",
        user=user,
        max_tokens=1500,
    )
    ledger.add(label="claims_extraction", usd=_estimate_call_cost_usd(usage))
    return _parse_claims_json(text)


def _parse_claims_json(raw: str) -> list[Claim]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []
    raw_claims = parsed.get("claims") if isinstance(parsed, dict) else None
    if not isinstance(raw_claims, list):
        return []
    out: list[Claim] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            continue
        text_val = str(item.get("text") or "").strip()
        if not text_val:
            continue
        valence = str(item.get("valence") or "neutral").lower().strip()
        if valence not in {"supports", "refutes", "neutral"}:
            valence = "neutral"
        srcs = item.get("sources") or []
        idx_list: list[int] = []
        if isinstance(srcs, list):
            for s in srcs:
                try:
                    idx_list.append(int(s))
                except (TypeError, ValueError):
                    continue
        out.append(Claim(text=text_val, valence=valence, source_indices=idx_list))
    return out[:10]


# ---------------------------------------------------------------------------
# Ticket editing
# ---------------------------------------------------------------------------


def replace_section(text: str, section_key: str, new_body: str) -> str:
    if section_key not in SECTION_MARKERS:
        raise KeyError(f"Unknown section: {section_key}")
    begin, end = SECTION_MARKERS[section_key]
    pattern = re.compile(rf"({re.escape(begin)})(.*?)({re.escape(end)})", re.DOTALL)
    if not pattern.search(text):
        raise ValueError(
            f"Section markers for {section_key!r} not found in ticket file. "
            "Did you render from LENS/templates/evidence_dossier.md?"
        )
    return pattern.sub(
        lambda m: f"{m.group(1)}\n{new_body.strip()}\n{m.group(3)}", text, count=1
    )


def render_sources_block(sources: list[Source]) -> str:
    if not sources:
        return "_No sources found._"
    lines = []
    for i, s in enumerate(sources):
        lines.append(f"{i + 1}. {s.as_markdown()[2:]}")
    return "\n".join(lines)


def render_claims_block(claims: list[Claim]) -> str:
    if not claims:
        return "_No claims extracted._"
    return "\n".join(c.as_markdown() for c in claims)


def render_run_record(
    *,
    backends_used: list[str],
    backend_counts: dict[str, int],
    duration_s: float,
    ledger: CostLedger,
    termination: str,
    note: str = "",
) -> str:
    counts = ", ".join(f"{k}={v}" for k, v in backend_counts.items()) or "(no hits)"
    lines = [
        f"- Termination: **{termination}**",
        f"- Duration: {duration_s:.1f}s",
        f"- Cost cap: ${ledger.cap_usd:.2f}",
        f"- Cost spent: ${ledger.spend_usd:.4f}",
        f"- Backends used: {', '.join(backends_used) if backends_used else '(none)'}",
        f"- Per-backend hit counts: {counts}",
    ]
    if note:
        lines.append(f"- Note: {note}")
    if ledger.entries:
        lines.append("")
        lines.append("<details><summary>cost ledger</summary>")
        lines.append("")
        for entry in ledger.entries:
            extra = ", ".join(
                f"{k}={v}" for k, v in entry.items() if k not in {"label", "usd"}
            )
            extra_part = f" ({extra})" if extra else ""
            lines.append(f"- ${entry['usd']:.6f} — {entry['label']}{extra_part}")
        lines.append("")
        lines.append("</details>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


@dataclass
class GatherConfig:
    candidate_id: str
    claim: str
    ticket_path: Path
    cost_cap_usd: float = DEFAULT_COST_CAP_USD
    sources_per_backend: int = DEFAULT_SOURCES_PER_BACKEND
    model: str = DEFAULT_MODEL


@dataclass
class GatherResult:
    sources: list[Source]
    claims: list[Claim]
    ledger: CostLedger
    duration_s: float
    termination: str
    backend_counts: dict[str, int]


def gather_evidence(
    config: GatherConfig,
    *,
    backends: Iterable[tuple[str, SearchBackend]] | None = None,
    llm: LLMClient | None = None,
    extract_text_fn: Callable[[Source], str] = extract_text,
) -> GatherResult:
    ledger = CostLedger(cap_usd=config.cost_cap_usd)
    sources: list[Source] = []
    backend_counts: dict[str, int] = {}
    backends_used: list[str] = []
    started_at = time.monotonic()
    termination = "completed"
    note = ""

    actual_backends = list(backends) if backends is not None else DEFAULT_BACKENDS
    seen_urls: set[str] = set()

    try:
        for name, fn in actual_backends:
            try:
                hits = fn(config.claim) or []
            except Exception as exc:
                hits = []
                note = (note + f" [{name}: {type(exc).__name__}]").strip()
            backend_counts[name] = 0
            if not hits:
                continue
            backends_used.append(name)
            for s in hits[: config.sources_per_backend]:
                if not s.url or s.url in seen_urls:
                    continue
                seen_urls.add(s.url)
                sources.append(s)
                backend_counts[name] += 1

        actual_llm = llm or LLMClient(model=config.model)

        for s in sources:
            if not s.raw_text:
                s.raw_text = extract_text_fn(s) or ""
            if ledger.would_exceed(0.01):
                termination = "budget_aborted"
                note = (note + " budget exceeded during summary phase").strip()
                raise BudgetExceeded(note)
            try:
                s.summary = summarize_source(
                    s, claim=config.claim, llm=actual_llm, ledger=ledger
                )
            except BudgetExceeded:
                termination = "budget_aborted"
                note = "budget exceeded during summary phase"
                raise

        if termination == "completed" and not ledger.would_exceed(0.05):
            try:
                claims = extract_claims(
                    sources, claim=config.claim, llm=actual_llm, ledger=ledger
                )
            except BudgetExceeded:
                claims = []
                termination = "budget_aborted"
                note = "budget exceeded during claim extraction"
        elif termination == "completed":
            claims = []
            termination = "budget_aborted"
            note = "budget exhausted before claim extraction"
        else:
            claims = []

    except BudgetExceeded:
        claims = []
        if termination == "completed":
            termination = "budget_aborted"

    duration = time.monotonic() - started_at
    write_ticket_sections(
        config.ticket_path,
        sources=sources,
        claims=claims,
        ledger=ledger,
        backends_used=backends_used,
        backend_counts=backend_counts,
        duration_s=duration,
        termination=termination,
        note=note,
    )
    return GatherResult(
        sources=sources,
        claims=claims,
        ledger=ledger,
        duration_s=duration,
        termination=termination,
        backend_counts=backend_counts,
    )


def write_ticket_sections(
    ticket_path: Path,
    *,
    sources: list[Source],
    claims: list[Claim],
    ledger: CostLedger,
    backends_used: list[str],
    backend_counts: dict[str, int],
    duration_s: float,
    termination: str,
    note: str = "",
) -> None:
    text = ticket_path.read_text(encoding="utf-8")
    text = replace_section(text, "sources", render_sources_block(sources))
    text = replace_section(text, "claims", render_claims_block(claims))
    text = replace_section(
        text,
        "run_record",
        render_run_record(
            backends_used=backends_used,
            backend_counts=backend_counts,
            duration_s=duration_s,
            ledger=ledger,
            termination=termination,
            note=note,
        ),
    )
    ticket_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--ticket-path", required=True, type=Path)
    parser.add_argument(
        "--cost-cap",
        type=float,
        default=DEFAULT_COST_CAP_USD,
        help=f"Hard USD cap (default ${DEFAULT_COST_CAP_USD:.2f}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model id (default {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--sources-per-backend",
        type=int,
        default=DEFAULT_SOURCES_PER_BACKEND,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.ticket_path.exists():
        print(
            f"gather_evidence: ticket path does not exist: {args.ticket_path}",
            file=sys.stderr,
        )
        return 2
    config = GatherConfig(
        candidate_id=args.candidate_id,
        claim=args.claim,
        ticket_path=args.ticket_path,
        cost_cap_usd=args.cost_cap,
        sources_per_backend=args.sources_per_backend,
        model=args.model,
    )
    try:
        result = gather_evidence(config)
    except RuntimeError as exc:
        print(f"gather_evidence: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "termination": result.termination,
                "sources": len(result.sources),
                "claims": len(result.claims),
                "spend_usd": round(result.ledger.spend_usd, 6),
                "duration_s": round(result.duration_s, 3),
                "backend_counts": result.backend_counts,
            },
            indent=2,
        )
    )
    return 0 if result.termination == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
