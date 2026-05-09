import { useEffect, useRef, useState } from "react"

export interface SessionEvent {
  type: string
  payload: Record<string, unknown>
}

export interface UseSessionEvents {
  events: SessionEvent[]
  connected: boolean
  error: string | null
}

// Relative URL → Vite proxy in dev; same-origin in prod (nginx + backend).
const apiBase = () => ""

export function useSessionEvents(
  sessionId: string,
  enabled: boolean,
): UseSessionEvents {
  const [events, setEvents] = useState<SessionEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!enabled || !sessionId) {
      sourceRef.current?.close()
      sourceRef.current = null
      setConnected(false)
      return
    }

    const url = `${apiBase()}/api/v1/sessions/${sessionId}/events`
    const es = new EventSource(url)
    sourceRef.current = es
    setError(null)

    es.onopen = () => {
      setConnected(true)
    }
    es.onerror = () => {
      setConnected(false)
      setError("connection lost")
    }

    const channels = [
      "candidate_updated",
      "ingestion",
      "dossier_ready",
      "pending_user_questions",
    ]
    for (const ch of channels) {
      es.addEventListener(ch, (e: MessageEvent) => {
        try {
          const parsed = JSON.parse(e.data) as SessionEvent
          setEvents((prev) => [parsed, ...prev].slice(0, 250))
        } catch {
          // ignore non-JSON heartbeats
        }
      })
    }

    return () => {
      es.close()
      sourceRef.current = null
      setConnected(false)
    }
  }, [sessionId, enabled])

  return { events, connected, error }
}
