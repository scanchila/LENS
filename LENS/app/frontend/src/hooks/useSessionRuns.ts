import { useCallback, useEffect, useState } from "react"

import {
  createRun,
  listCandidates,
  listRuns,
  type BackendCandidate,
} from "@/components/LensSessions/api"
import type { Candidate } from "@/components/Board/types"
import type { RunKind, RunMode, RunRow } from "@/components/LensSessions/types"

import { useSessionEvents } from "./useSessionEvents"

const toCandidate = (c: BackendCandidate): Candidate => ({
  id: c.id,
  statement: c.statement,
  lens: (c.lens as Candidate["lens"]) ?? "cross_domain_transfer",
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

export function useSessionRuns(sessionId: string) {
  const [runs, setRuns] = useState<RunRow[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState<RunKind | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { events: sse, connected } = useSessionEvents(sessionId, true)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [runsData, candData] = await Promise.all([
        listRuns(sessionId),
        listCandidates(sessionId),
      ])
      setRuns(runsData)
      setCandidates(candData.map(toCandidate))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Refetch on SSE events
  useEffect(() => {
    if (sse.length === 0) return
    void refresh()
  }, [sse, refresh])

  const trigger = useCallback(
    async (
      kind: RunKind,
      opts: { mode?: RunMode; input?: Record<string, unknown> } = {},
    ) => {
      setRunning(kind)
      setError(null)
      try {
        const detail = await createRun(sessionId, {
          kind,
          mode: opts.mode ?? "scripted",
          input: opts.input,
        })
        await refresh()
        return detail
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      } finally {
        setRunning(null)
      }
    },
    [refresh, sessionId],
  )

  return {
    runs,
    candidates,
    loading,
    running,
    error,
    connected,
    refresh,
    trigger,
  }
}
