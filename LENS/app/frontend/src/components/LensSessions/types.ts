export type RunKind =
  | "seed_ideas"
  | "document_upload"
  | "hn_search"
  | "contradiction_lens"
  | "cross_domain_lens"

export type RunMode = "scripted" | "real"

export type RunStatus = "pending" | "running" | "complete" | "failed"

export type ChangeKind =
  | "created"
  | "updated"
  | "killed"
  | "merged"
  | "restored"
  | "reinforced"
  | "red_struck"

export interface LensSessionRow {
  id: string
  title: string
  description: string | null
  goal_query: string | null
  created_at: string
  updated_at: string
}

export interface RunRow {
  id: string
  session_id: string
  kind: RunKind
  status: RunStatus
  mode: RunMode
  input: Record<string, unknown>
  summary: {
    candidates_added?: number
    candidates_updated?: number
    candidates_killed?: number
    candidates_merged?: number
    notes?: string[]
  }
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface FieldDiff {
  from: unknown
  to: unknown
}

export interface CandidateChangeRow {
  id: string
  run_id: string
  candidate_id: string
  change_kind: ChangeKind
  field_diffs: Record<string, FieldDiff>
  reason: string | null
  created_at: string
}

export interface RunDetail {
  run: RunRow
  changes: CandidateChangeRow[]
}

export interface CandidateHistory {
  candidate_id: string
  changes: CandidateChangeRow[]
  runs: Record<string, RunRow>
}

export const RUN_KIND_META: Record<
  RunKind,
  { label: string; icon: string; description: string }
> = {
  seed_ideas: {
    label: "Seed ideas",
    icon: "✨",
    description: "Generate ~10 initial candidates from the session goal.",
  },
  document_upload: {
    label: "Upload document",
    icon: "📄",
    description: "Ingest a document and rescore candidates against it.",
  },
  hn_search: {
    label: "Hacker News search",
    icon: "🟧",
    description: "Scan recent HN posts for reinforcement and new pain.",
  },
  contradiction_lens: {
    label: "Contradiction lens",
    icon: "⚖️",
    description: "Adversarial review — kill weak claims, hold the strong.",
  },
  cross_domain_lens: {
    label: "Cross-domain lens",
    icon: "💡",
    description: "Surface structurally analogous problems from other domains.",
  },
}
