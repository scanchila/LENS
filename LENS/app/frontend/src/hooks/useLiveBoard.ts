import { useCallback, useEffect, useMemo, useState } from "react"

import type {
  Candidate,
  DiffEvent,
  DossierTicket,
  YcScore,
} from "@/components/Board/types"
import { getYcRfsItems } from "@/components/Board/demoScript"

import { useSessionEvents } from "./useSessionEvents"

// Use relative URLs so the Vite dev-server proxy (vite.config.ts -> /api ->
// backend) handles routing. Avoids CORS in dev and removes the dependency on
// VITE_API_URL pointing to the right host:port.
const apiBase = () => ""

const authHeaders = (): Record<string, string> => {
  const tok = localStorage.getItem("access_token") ?? ""
  return tok ? { Authorization: `Bearer ${tok}` } : {}
}

const jsonHeaders = (): Record<string, string> => ({
  ...authHeaders(),
  "Content-Type": "application/json",
})

interface BackendCandidate {
  id: string
  session_id: string
  lens: string
  statement: string
  evidence_chunk_ids: string[]
  v_hat: number
  c_hat: number
  pipeline_steps: unknown[]
  status: string
  challenger_verdict: string | null
  dossier_grounded: boolean
  provenance_audited: boolean
  source_count: number
  reinforces: string[]
  merged_from: string[]
  ahead_of_yc: boolean
  pain_owner: string | null
  why_now: string | null
  contradictions: unknown[]
  open_assumptions: unknown[]
  validation_path: unknown[]
  evidence_sources: unknown[]
  created_at: string
  updated_at: string
}

const toCandidate = (c: BackendCandidate): Candidate => ({
  id: c.id,
  statement: c.statement,
  lens:
    (c.lens as Candidate["lens"]) ??
    "cross_domain_transfer",
  status: (c.status as Candidate["status"]) ?? "speculative",
  v_hat: c.v_hat,
  c_hat: c.c_hat,
  evidence_chunk_ids: c.evidence_chunk_ids,
  source_count: c.source_count,
  dossier_grounded: c.dossier_grounded,
  challenger_verdict:
    (c.challenger_verdict as Candidate["challenger_verdict"]) ?? undefined,
  provenance_audited: c.provenance_audited,
  reinforces:
    c.reinforces.length > 0
      ? (c.reinforces as Candidate["reinforces"])
      : undefined,
  merged_from: c.merged_from.length > 0 ? c.merged_from : undefined,
  ahead_of_yc: c.ahead_of_yc,
  pipeline_steps: c.pipeline_steps.map((s) =>
    typeof s === "string" ? s : JSON.stringify(s),
  ),
  pain_owner: c.pain_owner ?? undefined,
  why_now: c.why_now ?? undefined,
  contradictions: c.contradictions as string[],
  open_assumptions: c.open_assumptions as string[],
  validation_path: c.validation_path as string[],
  evidence_sources: c.evidence_sources as Candidate["evidence_sources"],
})

interface LiveBoardState {
  candidates: Candidate[]
  events: DiffEvent[]
  dossierTickets: DossierTicket[]
  ycScore: YcScore
  ycRevealed: boolean
  fullReeval: boolean
  briefCandidateId: string | null
}

const initialYcScore = (): YcScore => ({
  precision: 0,
  recall: 0,
  direct_matches: 0,
  adjacent: 0,
  missed: getYcRfsItems().length,
  excess: 0,
  history: [],
  matches: [],
  revealed: false,
})

const stageNarrations: Record<string, string> = {
  "00-cold-start":
    "Generic predictions, low confidence, no dossier badges. The system starts uncertain.",
  "01-hn-drop":
    "Board churns. Complaint-shaped opportunities appear from messy user pain.",
  "02-arxiv-drop":
    "Cross-domain transfer surfaces a structurally analogous candidate; 💡 chip pulses.",
  "03-dossier-queue":
    "High-V̂ candidate triggers an evidence_dossier CAR ticket.",
  "04-founder-transcripts":
    "Reinforced candidate emerges across multiple sources.",
  "05-dossier-complete":
    "Dossier completes; confidence jumps because every claim is grounded.",
  "06-synthesizer-merge":
    "Two candidates share evidence sources — they merge into one stronger prediction.",
  "07-challenger-pass":
    "Weak candidates are red-struck; one dossier-grounded candidate survives.",
  "08-yc-reveal":
    "Held-out YC RFS Summer 2026 reveal — precision/recall against ground truth.",
  "09-ahead-of-yc":
    "Defensible non-overlap — excess is leading indicator, not noise.",
  "10-open-brief":
    "Problem, pain owner, evidence, contradictions, assumptions, validation steps.",
}

export interface UseLiveBoard {
  state: LiveBoardState
  connected: boolean
  stageIndex: number
  totalStages: number
  currentStage: { key: string; label: string; narration: string } | null
  next: () => Promise<void>
  prev: () => Promise<void>
  reset: () => Promise<void>
  jumpTo: (i: number) => Promise<void>
  setBriefCandidate: (id: string | null) => void
  setFullReeval: (v: boolean) => void
  runLens: (lens: string, modelOverride?: string) => Promise<number>
  auditAll: () => Promise<number>
  loading: boolean
  error: string | null
}

export function useLiveBoard(sessionId: string): UseLiveBoard {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [events, setEvents] = useState<DiffEvent[]>([])
  const [dossierTickets, setDossierTickets] = useState<DossierTicket[]>([])
  const [ycScore, setYcScore] = useState<YcScore>(initialYcScore())
  const [ycRevealed, setYcRevealed] = useState(false)
  const [fullReeval, setFullReeval] = useState(false)
  const [briefCandidateId, setBriefCandidateId] = useState<string | null>(null)
  const [stageIndex, setStageIndex] = useState(0)
  const [stages, setStages] = useState<{ key: string; label: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { events: sse, connected } = useSessionEvents(sessionId, true)

  const refreshCandidates = useCallback(async () => {
    try {
      const res = await fetch(
        `${apiBase()}/api/v1/sessions/${sessionId}/candidates`,
        { headers: authHeaders() },
      )
      if (!res.ok) throw new Error(`fetch candidates ${res.status}`)
      const json = (await res.json()) as { data: BackendCandidate[] }
      setCandidates(json.data.map(toCandidate))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [sessionId])

  // Initial load
  useEffect(() => {
    void refreshCandidates()
  }, [refreshCandidates])

  // Stages list
  useEffect(() => {
    const run = async () => {
      try {
        const res = await fetch(
          `${apiBase()}/api/v1/sessions/${sessionId}/demo/stages`,
          { headers: authHeaders() },
        )
        if (!res.ok) throw new Error(`fetch stages ${res.status}`)
        const json = (await res.json()) as {
          stages: { index: number; key: string; label: string }[]
        }
        setStages(
          json.stages.map((s) => ({ key: s.key, label: s.label })),
        )
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    }
    void run()
  }, [sessionId])

  // SSE handler — for each event, refetch candidates and append a DiffEvent.
  useEffect(() => {
    if (sse.length === 0) return
    const last = sse[0]
    const kind = (last.payload?.kind as string | undefined) ?? last.type
    const candidate_id = last.payload?.candidate_id as string | undefined

    setEvents((prev) => {
      const id = `${last.type}-${prev.length}`
      const message = humanizeEvent(kind, last.payload)
      const next: DiffEvent = {
        id,
        ts: Date.now(),
        kind: (kindMap(kind) ??
          "candidate_added") as DiffEvent["kind"],
        candidate_id,
        message,
      }
      return [next, ...prev].slice(0, 100)
    })

    if (kind === "dossier_queued" || kind === "dossier_running" || kind === "dossier_complete") {
      const ticketId =
        (last.payload?.ticket_id as string | undefined) ??
        (candidate_id ? `tkt_${candidate_id}` : `tkt_${Date.now()}`)
      setDossierTickets((prev) => {
        const existing = prev.find((t) => t.ticket_id === ticketId)
        if (existing) {
          if (kind === "dossier_running")
            return prev.map((t) =>
              t.ticket_id === ticketId
                ? { ...t, status: "running", started_at: t.started_at ?? Date.now() }
                : t,
            )
          if (kind === "dossier_complete")
            return prev.map((t) =>
              t.ticket_id === ticketId
                ? { ...t, status: "complete", completed_at: Date.now() }
                : t,
            )
          return prev
        }
        return [
          ...prev,
          {
            ticket_id: ticketId,
            ticket_number: (last.payload?.ticket_number as string | undefined) ?? "TICKET-D-???",
            candidate_id: candidate_id ?? "?",
            claim_summary: "",
            status: kind === "dossier_complete" ? "complete" : kind === "dossier_running" ? "running" : "queued",
            queued_at: Date.now(),
          },
        ]
      })
    }

    if (kind === "yc_revealed") {
      setYcRevealed(true)
    }

    void refreshCandidates()
  }, [sse, refreshCandidates])

  // Re-score YC against the latest candidates whenever they change AND we're revealed
  useEffect(() => {
    if (!ycRevealed) {
      setYcScore((s) => ({ ...s, history: [...s.history, { ts: Date.now(), precision: 0, recall: 0 }].slice(-100) }))
      return
    }
    void (async () => {
      try {
        const res = await fetch(
          `${apiBase()}/api/v1/sessions/${sessionId}/yc_reveal?top_k=10`,
          { method: "POST", headers: authHeaders() },
        )
        if (!res.ok) return
        const json = (await res.json()) as {
          revealed: boolean
          precision: number
          recall: number
          direct_matches: number
          adjacent: number
          missed: number
          excess: number
          matches: { prediction_id: string; rfs_item_id: string | null; match_kind: string; rationale?: string }[]
        }
        setYcScore((s) => ({
          ...s,
          precision: json.precision,
          recall: json.recall,
          direct_matches: json.direct_matches,
          adjacent: json.adjacent,
          missed: json.missed,
          excess: json.excess,
          revealed: true,
          matches: json.matches.map((m) => ({
            prediction_id: m.prediction_id,
            rfs_item_id: m.rfs_item_id,
            match_kind: (m.match_kind as "direct" | "adjacent" | "none") ?? "none",
            rationale: m.rationale,
          })),
          history: [
            ...s.history,
            { ts: Date.now(), precision: json.precision, recall: json.recall },
          ].slice(-100),
        }))
      } catch {
        // ignore
      }
    })()
  }, [candidates, ycRevealed, sessionId])

  const briefCandidate = useMemo(
    () => candidates.find((c) => c.dossier_grounded && c.status === "ready_to_validate") ?? null,
    [candidates],
  )

  // Auto-set brief once a candidate becomes ready
  useEffect(() => {
    if (briefCandidate && !briefCandidateId) {
      // do not auto-open; the route component decides — just expose
    }
  }, [briefCandidate, briefCandidateId])

  const next = useCallback(async () => {
    if (stageIndex >= stages.length) return
    setLoading(true)
    try {
      await fetch(`${apiBase()}/api/v1/sessions/${sessionId}/demo/next`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ stage_index: stageIndex }),
      })
      setStageIndex((i) => i + 1)
    } finally {
      setLoading(false)
    }
  }, [sessionId, stageIndex, stages.length])

  const reset = useCallback(async () => {
    setLoading(true)
    try {
      await fetch(`${apiBase()}/api/v1/sessions/${sessionId}/demo/reset`, {
        method: "POST",
        headers: authHeaders(),
      })
      setStageIndex(0)
      setEvents([])
      setDossierTickets([])
      setYcRevealed(false)
      setYcScore(initialYcScore())
      setBriefCandidateId(null)
      await refreshCandidates()
    } finally {
      setLoading(false)
    }
  }, [refreshCandidates, sessionId])

  const prev = useCallback(async () => {
    const target = Math.max(0, stageIndex - 1)
    setLoading(true)
    try {
      await fetch(`${apiBase()}/api/v1/sessions/${sessionId}/demo/jump`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ target_index: target }),
      })
      setStageIndex(target)
    } finally {
      setLoading(false)
    }
  }, [sessionId, stageIndex])

  const jumpTo = useCallback(
    async (i: number) => {
      const t = Math.max(0, Math.min(stages.length, i))
      setLoading(true)
      try {
        await fetch(`${apiBase()}/api/v1/sessions/${sessionId}/demo/jump`, {
          method: "POST",
          headers: jsonHeaders(),
          body: JSON.stringify({ target_index: t }),
        })
        setStageIndex(t)
      } finally {
        setLoading(false)
      }
    },
    [sessionId, stages.length],
  )

  const currentStage = useMemo(() => {
    if (stageIndex === 0) return null
    const s = stages[stageIndex - 1]
    if (!s) return null
    return {
      key: s.key,
      label: s.label,
      narration: stageNarrations[s.key] ?? "",
    }
  }, [stageIndex, stages])

  const runLens = useCallback(
    async (lens: string, modelOverride?: string) => {
      setLoading(true)
      try {
        const res = await fetch(
          `${apiBase()}/api/v1/sessions/${sessionId}/run-lens`,
          {
            method: "POST",
            headers: jsonHeaders(),
            body: JSON.stringify({
              lens,
              model_override: modelOverride,
              timeout_seconds: 600,
            }),
          },
        )
        if (!res.ok) {
          const txt = await res.text().catch(() => "")
          setError(`run-lens ${res.status}: ${txt.slice(0, 240)}`)
          return 0
        }
        const json = (await res.json()) as { candidate_ids: string[] }
        await refreshCandidates()
        return json.candidate_ids.length
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        return 0
      } finally {
        setLoading(false)
      }
    },
    [sessionId, refreshCandidates],
  )

  const auditAll = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(
        `${apiBase()}/api/v1/sessions/${sessionId}/audit-all`,
        { method: "POST", headers: authHeaders() },
      )
      if (!res.ok) {
        setError(`audit-all ${res.status}`)
        return 0
      }
      const json = (await res.json()) as { candidate_id: string }[]
      await refreshCandidates()
      return json.length
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return 0
    } finally {
      setLoading(false)
    }
  }, [sessionId, refreshCandidates])

  return {
    state: {
      candidates,
      events,
      dossierTickets,
      ycScore,
      ycRevealed,
      fullReeval,
      briefCandidateId,
    },
    connected,
    stageIndex,
    totalStages: stages.length,
    currentStage,
    next,
    prev,
    reset,
    jumpTo,
    setBriefCandidate: setBriefCandidateId,
    setFullReeval,
    runLens,
    auditAll,
    loading,
    error,
  }
}

function kindMap(kind: string): string | undefined {
  if (kind === "candidate_added") return "candidate_added"
  if (kind === "candidate_v_hat_updated") return "candidate_v_hat_updated"
  if (kind === "candidate_killed") return "candidate_killed"
  if (kind === "candidate_red_struck") return "candidate_red_struck"
  if (kind === "candidate_merged") return "candidate_merged"
  if (kind === "candidate_merged_into") return "candidate_merged"
  if (kind === "dossier_queued") return "dossier_queued"
  if (kind === "dossier_running") return "dossier_running"
  if (kind === "dossier_complete") return "dossier_complete"
  if (kind === "candidate_challenged_held") return "candidate_challenged_held"
  if (kind === "yc_revealed") return "yc_revealed"
  if (kind === "ahead_of_yc") return "ahead_of_yc"
  return undefined
}

function humanizeEvent(kind: string, payload: Record<string, unknown>): string {
  switch (kind) {
    case "candidate_added":
      return "+ candidate added"
    case "candidate_v_hat_updated":
      return `↑ V̂ updated → ${(payload.to as number | undefined)?.toFixed(2) ?? "?"}`
    case "candidate_killed":
      return "✗ candidate killed"
    case "candidate_red_struck":
      return "✗ provenance failed"
    case "candidate_merged":
      return "⤲ candidates merged"
    case "candidate_merged_into":
      return "⤲ merged into another"
    case "dossier_queued":
      return "📚 dossier queued"
    case "dossier_running":
      return "📚 dossier running"
    case "dossier_complete":
      return "📚 dossier complete"
    case "candidate_challenged_held":
      return "✓ challenged & held"
    case "yc_revealed":
      return "▣ YC RFS revealed"
    case "ahead_of_yc":
      return "🚀 ahead of YC"
    default:
      return kind
  }
}
