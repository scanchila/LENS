export type LensName =
  | "cross_domain_transfer"
  | "contradiction_surfacing"
  | "distance_from_focus"

export type CandidateStatus =
  | "speculative"
  | "supported"
  | "challenged"
  | "ready_to_validate"
  | "killed"
  | "merged_into"

export type ChallengeVerdict =
  | "kept"
  | "red_struck"
  | "needs_evidence"
  | "provenance_failed"
  | "held"

export type DossierStatus = "queued" | "running" | "complete" | "failed"

export interface Candidate {
  id: string
  statement: string
  lens: LensName
  status: CandidateStatus
  v_hat: number
  c_hat: number
  evidence_chunk_ids: string[]
  source_count: number
  dossier_grounded: boolean
  challenger_verdict?: ChallengeVerdict
  provenance_audited: boolean
  reinforces?: LensName[]
  merged_from?: string[]
  ahead_of_yc?: boolean
  pipeline_steps: string[]
  pain_owner?: string
  why_now?: string
  contradictions?: string[]
  open_assumptions?: string[]
  validation_path?: string[]
  evidence_sources?: { title: string; kind: "web" | "paper" | "forum" | "blog" | "doc"; url?: string }[]
}

export interface DiffEvent {
  id: string
  ts: number
  kind:
    | "candidate_added"
    | "candidate_v_hat_updated"
    | "candidate_killed"
    | "candidate_merged"
    | "dossier_queued"
    | "dossier_running"
    | "dossier_complete"
    | "candidate_challenged_held"
    | "candidate_red_struck"
    | "yc_revealed"
    | "ahead_of_yc"
  candidate_id?: string
  message: string
  delta?: { from: number; to: number }
}

export interface DossierTicket {
  ticket_id: string
  ticket_number: string
  candidate_id: string
  claim_summary: string
  status: DossierStatus
  queued_at: number
  started_at?: number
  completed_at?: number
}

export interface YcRfsItem {
  id: string
  title: string
  description: string
  tags: string[]
}

export interface YcMatch {
  prediction_id: string
  rfs_item_id: string | null
  match_kind: "direct" | "adjacent" | "none"
  rationale?: string
}

export interface YcScore {
  precision: number
  recall: number
  direct_matches: number
  adjacent: number
  missed: number
  excess: number
  history: { ts: number; precision: number; recall: number }[]
  matches: YcMatch[]
  revealed: boolean
}
