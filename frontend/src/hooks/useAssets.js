import { useEffect, useState } from 'react'
import { getAssets } from '../api/finpulse'

/** Stored-asset metrics from /api/assets. */
export function useAssets() {
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    getAssets()
      .then((result) => {
        if (cancelled) return
        setAssets(Array.isArray(result.assets) ? result.assets : [])
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load market assets.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { assets, loading, error }
}
