import { useEffect, useState } from 'react'
import { getCommodities, getCommodityHistory } from '../api/finpulse'

/** Crude oil spot prices with their latest values (/api/commodities). */
export function useCommodities() {
  const [state, setState] = useState({ data: null, loading: true, error: '' })

  useEffect(() => {
    let cancelled = false
    getCommodities()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message || 'Unable to load commodities.' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

/** Daily history for one series; an empty id loads nothing. */
export function useCommodityHistory(seriesId) {
  const [result, setResult] = useState({ id: null, data: null, error: '' })

  useEffect(() => {
    if (!seriesId) return undefined
    let cancelled = false
    getCommodityHistory(seriesId)
      .then((data) => {
        if (!cancelled) setResult({ id: seriesId, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ id: seriesId, data: null, error: err.message || 'Unable to load the history.' })
      })
    return () => {
      cancelled = true
    }
  }, [seriesId])

  const loading = Boolean(seriesId) && result.id !== seriesId
  return { data: loading ? null : result.data, loading, error: loading ? '' : result.error }
}
