import { useEffect, useState } from 'react'
import { getMacroSeries, getMacroSeriesDetail } from '../api/finpulse'

/** The curated FRED series with their latest values (/api/macro/series). */
export function useMacroSeries() {
  const [state, setState] = useState({ data: null, loading: true, error: '' })

  useEffect(() => {
    let cancelled = false
    getMacroSeries()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message || 'Unable to load macro data.' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

/** One series with its observations; an empty id loads nothing. */
export function useMacroDetail(seriesId) {
  const [result, setResult] = useState({ id: null, data: null, error: '' })

  useEffect(() => {
    if (!seriesId) return undefined
    let cancelled = false
    getMacroSeriesDetail(seriesId)
      .then((data) => {
        if (!cancelled) setResult({ id: seriesId, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ id: seriesId, data: null, error: err.message || 'Unable to load the series.' })
      })
    return () => {
      cancelled = true
    }
  }, [seriesId])

  const loading = Boolean(seriesId) && result.id !== seriesId
  return { data: loading ? null : result.data, loading, error: loading ? '' : result.error }
}
