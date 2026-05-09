#!/usr/bin/env python3
"""
One-way push sync from CAR tickets to GitHub Issues.

Tickets live in `car-hub/lens/.codex-autorunner/tickets/TICKET-*.md`. They are the
source of truth. GH Issues on `scanchila/LENS` are a read-only mirror.

For each ticket:
  - If frontmatter has no `gh_issue` field → create issue, stamp `gh_issue: N` and
    `gh_synced_hash: H` into frontmatter.
  - If `gh_issue: N` exists and content has changed → `gh issue edit` to update.
  - If `done: true` and issue is open → close.
  - If `done: false` and issue is closed → reopen.

The script is idempotent: re-running with no ticket changes is a no-op.

Usage:
  python LENS/scripts/sync_tickets_to_gh.py [--dry-run] [--tickets-dir PATH] [--repo OWNER/REPO]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_DEFAULT = "scanchila/LENS"
TICKETS_DIR_DEFAULT = Path(
    "/home/santiago/Neuryta/hackathon/car-hub/lens/.codex-autorunner/tickets"
)
TICKET_NAME_RE = re.compile(r"^TICKET-(\d{3,})(?:[^/]*)\.md$", re.IGNORECASE)
LABEL_LENS_BUILD = "lens-build"


@dataclass
class Ticket:
    path: Path
    number: int
    frontmatter: dict[str, Any]
    body: str
    raw: str

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title", f"TICKET-{self.number:03d}"))

    @property
    def done(self) -> bool:
        return bool(self.frontmatter.get("done", False))

    @property
    def agent(self) -> str:
        return str(self.frontmatter.get("agent", "unknown"))

    @property
    def ticket_id(self) -> str:
        return str(self.frontmatter.get("ticket_id", ""))

    @property
    def gh_issue(self) -> int | None:
        v = self.frontmatter.get("gh_issue")
        return int(v) if isinstance(v, int) else None

    @property
    def synced_hash(self) -> str | None:
        v = self.frontmatter.get("gh_synced_hash")
        return str(v) if v else None


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        raise ValueError("missing leading ---")
    lines = raw.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        raise ValueError("frontmatter not closed")
    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ValueError("frontmatter is not a mapping")
    return fm, body


def render_ticket(fm: dict[str, Any], body: str) -> str:
    fm_yaml = yaml.safe_dump(fm, sort_keys=False).rstrip()
    return f"---\n{fm_yaml}\n---\n{body}"


def load_ticket(path: Path) -> Ticket | None:
    m = TICKET_NAME_RE.match(path.name)
    if not m:
        return None
    raw = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)
    return Ticket(
        path=path, number=int(m.group(1)), frontmatter=fm, body=body, raw=raw
    )


def phase_label(num: int) -> str:
    if num <= 48:
        return "phase-foundation"
    if num <= 92:
        return "phase-agents-ui"
    return "phase-demo"


def labels_for(ticket: Ticket) -> list[str]:
    labels = [LABEL_LENS_BUILD, phase_label(ticket.number)]
    if ticket.agent == "user":
        labels.append("agent-user")
    return labels


def issue_title(ticket: Ticket) -> str:
    return f"[{ticket.number:03d}] {ticket.title}"


def issue_body(ticket: Ticket, source_relpath: str) -> str:
    status = "✅ Done" if ticket.done else "⏳ Open"
    return (
        f"> 🤖 Auto-synced from CAR ticket. Source of truth: `{source_relpath}` "
        f"(one-way push, do not edit this issue directly).\n"
        f"\n"
        f"**Status:** {status} · `agent: {ticket.agent}` · "
        f"`ticket_id: {ticket.ticket_id}`\n"
        f"\n"
        f"---\n"
        f"\n"
        f"{ticket.body.strip()}\n"
    )


def content_hash(ticket: Ticket, body_rendered: str) -> str:
    h = hashlib.sha256()
    h.update(issue_title(ticket).encode("utf-8"))
    h.update(b"\0")
    h.update(body_rendered.encode("utf-8"))
    h.update(b"\0")
    h.update(b"done" if ticket.done else b"open")
    return h.hexdigest()


def run_gh(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=capture,
        text=True,
        check=False,
    )


def ensure_label(repo: str, name: str, color: str, description: str) -> None:
    payload = {"name": name, "color": color, "description": description}
    res = run_gh(
        [
            "api",
            "-X",
            "POST",
            f"repos/{repo}/labels",
            "-f",
            f"name={name}",
            "-f",
            f"color={color}",
            "-f",
            f"description={description}",
        ]
    )
    if res.returncode != 0 and "already_exists" not in (res.stderr or ""):
        # 422 already_exists is fine; anything else log.
        if "already_exists" not in (res.stdout + res.stderr):
            print(f"  ! ensure_label({name}) returned: {res.stderr.strip()}", file=sys.stderr)


def issue_state(repo: str, number: int) -> str | None:
    res = run_gh(
        ["api", f"repos/{repo}/issues/{number}", "-q", ".state"]
    )
    if res.returncode != 0:
        return None
    return (res.stdout or "").strip() or None


def gh_create(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> int | None:
    res = run_gh(
        [
            "issue",
            "create",
            "-R",
            repo,
            "--title",
            title,
            "--body",
            body,
            *(arg for label in labels for arg in ("--label", label)),
        ]
    )
    if res.returncode != 0:
        print(f"  ! gh issue create failed: {res.stderr.strip()}", file=sys.stderr)
        return None
    url = (res.stdout or "").strip().splitlines()[-1]
    m = re.search(r"/issues/(\d+)$", url)
    return int(m.group(1)) if m else None


def gh_edit_body(repo: str, number: int, title: str, body: str) -> bool:
    res = run_gh(
        [
            "issue",
            "edit",
            str(number),
            "-R",
            repo,
            "--title",
            title,
            "--body",
            body,
        ]
    )
    if res.returncode != 0:
        print(f"  ! gh issue edit #{number} failed: {res.stderr.strip()}", file=sys.stderr)
        return False
    return True


def gh_close(repo: str, number: int) -> bool:
    res = run_gh(["issue", "close", str(number), "-R", repo])
    return res.returncode == 0


def gh_reopen(repo: str, number: int) -> bool:
    res = run_gh(["issue", "reopen", str(number), "-R", repo])
    return res.returncode == 0


def sync_ticket(
    ticket: Ticket,
    *,
    repo: str,
    source_relpath: str,
    dry_run: bool,
) -> str:
    body_rendered = issue_body(ticket, source_relpath)
    title = issue_title(ticket)
    new_hash = content_hash(ticket, body_rendered)
    labels = labels_for(ticket)

    actions: list[str] = []

    if ticket.gh_issue is None:
        # Create
        if dry_run:
            actions.append(f"CREATE [{title}]")
            return ", ".join(actions)
        number = gh_create(repo, title, body_rendered, labels)
        if number is None:
            return "ERROR creating issue"
        ticket.frontmatter["gh_issue"] = number
        ticket.frontmatter["gh_synced_hash"] = new_hash
        ticket.path.write_text(render_ticket(ticket.frontmatter, ticket.body), encoding="utf-8")
        actions.append(f"CREATED #{number}")
        # Open issues are open by default; close if ticket already done.
        if ticket.done:
            gh_close(repo, number)
            actions.append("CLOSED")
        return ", ".join(actions)

    # Update path
    number = ticket.gh_issue
    state = issue_state(repo, number)
    if state is None:
        actions.append(f"WARN issue #{number} not found")
        return ", ".join(actions)

    if ticket.synced_hash != new_hash:
        if dry_run:
            actions.append(f"UPDATE #{number}")
        else:
            if gh_edit_body(repo, number, title, body_rendered):
                ticket.frontmatter["gh_synced_hash"] = new_hash
                ticket.path.write_text(
                    render_ticket(ticket.frontmatter, ticket.body), encoding="utf-8"
                )
                actions.append(f"UPDATED #{number}")
            else:
                actions.append(f"ERROR editing #{number}")

    if ticket.done and state == "open":
        if dry_run:
            actions.append(f"CLOSE #{number}")
        else:
            if gh_close(repo, number):
                actions.append(f"CLOSED #{number}")
    elif not ticket.done and state == "closed":
        if dry_run:
            actions.append(f"REOPEN #{number}")
        else:
            if gh_reopen(repo, number):
                actions.append(f"REOPENED #{number}")

    if not actions:
        actions.append(f"OK #{number} (no change)")
    return ", ".join(actions)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=REPO_DEFAULT)
    ap.add_argument("--tickets-dir", type=Path, default=TICKETS_DIR_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--source-prefix",
        default="car-hub/lens/.codex-autorunner/tickets",
        help="Path printed in issue body as the source-of-truth pointer",
    )
    args = ap.parse_args()

    if not args.tickets_dir.exists():
        print(f"tickets dir not found: {args.tickets_dir}", file=sys.stderr)
        return 2

    if not args.dry_run:
        # Best-effort label setup.
        ensure_label(args.repo, LABEL_LENS_BUILD, "0e8a16", "LENS build ticket (auto-synced)")
        ensure_label(args.repo, "phase-foundation", "5319e7", "Foundation tickets 001-048")
        ensure_label(args.repo, "phase-agents-ui", "1d76db", "Agent + UI tickets 050-092")
        ensure_label(args.repo, "phase-demo", "fbca04", "Demo prep + signoff tickets 100-200")
        ensure_label(args.repo, "agent-user", "d93f0b", "Requires human signoff (agent: user)")

    tickets: list[Ticket] = []
    for path in sorted(args.tickets_dir.iterdir()):
        try:
            t = load_ticket(path)
        except Exception as exc:
            print(f"  ! parse error in {path.name}: {exc}", file=sys.stderr)
            continue
        if t is not None:
            tickets.append(t)

    print(f"Found {len(tickets)} tickets in {args.tickets_dir}")
    if args.dry_run:
        print("(dry-run — no GH calls or file writes)")
    print()

    for t in tickets:
        rel = f"{args.source_prefix}/{t.path.name}"
        result = sync_ticket(t, repo=args.repo, source_relpath=rel, dry_run=args.dry_run)
        marker = "PLAN" if args.dry_run else "DONE"
        print(f"  [{t.number:03d}] {marker}: {result}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
