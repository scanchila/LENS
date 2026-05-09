import type {
  CandidateHistory,
  LensSessionRow,
  RunDetail,
  RunKind,
  RunMode,
  RunRow,
} from "./types"

const authHeaders = (): Record<string, string> => {
  const tok = localStorage.getItem("access_token") ?? ""
  return tok ? { Authorization: `Bearer ${tok}` } : {}
}

const jsonHeaders = (): Record<string, string> => ({
  ...authHeaders(),
  "Content-Type": "application/json",
})

const handleResponse = async <T,>(res: Response): Promise<T> => {
  if (!res.ok) {
    const txt = await res.text().catch(() => "")
    throw new Error(`${res.status} ${res.statusText}: ${txt.slice(0, 200)}`)
  }
  return (await res.json()) as T
}

export async function listLensSessions(): Promise<LensSessionRow[]> {
  const res = await fetch("/api/v1/lens-sessions", { headers: authHeaders() })
  const json = await handleResponse<{ data: LensSessionRow[]; count: number }>(res)
  return json.data
}

export async function getLensSession(id: string): Promise<LensSessionRow> {
  const res = await fetch(`/api/v1/lens-sessions/${id}`, { headers: authHeaders() })
  return handleResponse<LensSessionRow>(res)
}

export async function createLensSession(input: {
  title: string
  description?: string
  goal_query?: string
}): Promise<LensSessionRow> {
  const res = await fetch("/api/v1/lens-sessions", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<LensSessionRow>(res)
}

export async function deleteLensSession(id: string): Promise<void> {
  const res = await fetch(`/api/v1/lens-sessions/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  })
  if (!res.ok && res.status !== 204) {
    const txt = await res.text().catch(() => "")
    throw new Error(`${res.status}: ${txt}`)
  }
}

export async function listRuns(sessionId: string): Promise<RunRow[]> {
  const res = await fetch(`/api/v1/lens-sessions/${sessionId}/runs`, {
    headers: authHeaders(),
  })
  const json = await handleResponse<{ data: RunRow[]; count: number }>(res)
  return json.data
}

export async function getRun(
  sessionId: string,
  runId: string,
): Promise<RunDetail> {
  const res = await fetch(
    `/api/v1/lens-sessions/${sessionId}/runs/${runId}`,
    { headers: authHeaders() },
  )
  return handleResponse<RunDetail>(res)
}

export async function createRun(
  sessionId: string,
  input: {
    kind: RunKind
    mode: RunMode
    input?: Record<string, unknown>
  },
): Promise<RunDetail> {
  const res = await fetch(`/api/v1/lens-sessions/${sessionId}/runs`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ ...input, input: input.input ?? {} }),
  })
  return handleResponse<RunDetail>(res)
}

export async function getCandidateHistory(
  sessionId: string,
  candidateId: string,
): Promise<CandidateHistory> {
  const res = await fetch(
    `/api/v1/lens-sessions/${sessionId}/candidates/${candidateId}/history`,
    { headers: authHeaders() },
  )
  return handleResponse<CandidateHistory>(res)
}

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

export async function listCandidates(
  sessionId: string,
): Promise<BackendCandidate[]> {
  const res = await fetch(
    `/api/v1/sessions/${sessionId}/candidates`,
    { headers: authHeaders() },
  )
  const json = await handleResponse<{ data: BackendCandidate[]; count: number }>(res)
  return json.data
}

export type { BackendCandidate }
