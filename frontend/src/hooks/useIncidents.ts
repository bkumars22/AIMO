import { useCallback, useEffect, useRef, useState } from 'react'
import { getIncidents } from '../api/api'
import type { Incident, IncidentStatus, IncidentType, Severity } from '../api/api'

interface Filters {
  pipeline_id?: string
  type?:        IncidentType
  severity?:    Severity
  status?:      IncidentStatus
  limit?:       number
}

interface UseIncidentsResult {
  incidents: Incident[]
  loading:   boolean
  error:     string | null
  refetch:   () => void
}

export function useIncidents(filters?: Filters): UseIncidentsResult {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const [tick,      setTick]      = useState(0)

  // Stable filter reference to avoid infinite re-renders
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getIncidents(filtersRef.current)
      .then((data) => {
        if (!cancelled) setIncidents(data.items || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.response?.data?.error ?? err?.message ?? 'Failed to load incidents')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [tick])

  const refetch = useCallback(() => setTick((t) => t + 1), [])

  return { incidents, loading, error, refetch }
}
