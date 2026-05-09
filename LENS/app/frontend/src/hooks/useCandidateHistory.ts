import { useCallback, useEffect, useState } from "react"

import { getCandidateHistory } from "@/components/LensSessions/api"
import type { CandidateHistory } from "@/components/LensSessions/types"

export function useCandidateHistory(
  sessionId: string,
  candidateId: string | null,
) {
  const [history, setHistory] = useState<CandidateHistory | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHistory = useCallback(async () => {
    if (!candidateId) {
      setHistory(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await getCandidateHistory(sessionId, candidateId)
      setHistory(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [candidateId, sessionId])

  useEffect(() => {
    void fetchHistory()
  }, [fetchHistory])

  return { history, loading, error, refresh: fetchHistory }
}
