import { useCallback, useEffect, useState } from "react"

import {
  createLensSession,
  deleteLensSession,
  listLensSessions,
} from "@/components/LensSessions/api"
import type { LensSessionRow } from "@/components/LensSessions/types"

export function useLensSessions() {
  const [sessions, setSessions] = useState<LensSessionRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listLensSessions()
      setSessions(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const create = useCallback(
    async (input: { title: string; goal_query?: string; description?: string }) => {
      setLoading(true)
      setError(null)
      try {
        const created = await createLensSession(input)
        setSessions((prev) => [created, ...prev])
        return created
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const remove = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      await deleteLensSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      throw e
    } finally {
      setLoading(false)
    }
  }, [])

  return { sessions, loading, error, refresh, create, remove }
}
