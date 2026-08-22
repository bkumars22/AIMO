import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_DEMO, WS_URL } from '../api/api'
import type { Incident } from '../api/api'

const RECONNECT_BASE_MS  = 1_000
const RECONNECT_MAX_MS   = 30_000
const MAX_INCIDENTS      = 200

export function useWebSocket(): { incidents: Incident[]; connected: boolean } {
  // No live ai-engine to connect to on GitHub Pages — report "connected"
  // without ever opening a socket. Incidents still flow in via the REST
  // fetch in useIncidents/Dashboard.tsx (mocked in api.ts).
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [connected, setConnected] = useState(IS_DEMO)
  const wsRef       = useRef<WebSocket | null>(null)
  const retryMs     = useRef(RECONNECT_BASE_MS)
  const retryTimer  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const destroyed   = useRef(false)

  const connect = useCallback(() => {
    if (destroyed.current || IS_DEMO) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryMs.current = RECONNECT_BASE_MS
    }

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        // Server can send a single incident or a {incidents:[...]} batch
        const incoming: Incident[] = Array.isArray(data.incidents)
          ? data.incidents
          : [data]
        setIncidents((prev) => [...incoming, ...prev].slice(0, MAX_INCIDENTS))
      } catch {
        /* malformed frame — ignore */
      }
    }

    ws.onclose = () => {
      setConnected(false)
      if (!destroyed.current) {
        retryTimer.current = setTimeout(() => {
          retryMs.current = Math.min(retryMs.current * 2, RECONNECT_MAX_MS)
          connect()
        }, retryMs.current)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  useEffect(() => {
    destroyed.current = false
    connect()
    return () => {
      destroyed.current = true
      if (retryTimer.current) clearTimeout(retryTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { incidents, connected }
}
