import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { getAssetNews, getAssetRegistry } from '../api/finpulse'

/** Every asset the terminal page covers (/api/asset-registry). */
export function useAssetRegistry() {
  const [state, setState] = useState({ assets: [], loading: true, error: '' })

  useEffect(() => {
    let cancelled = false
    getAssetRegistry()
      .then((data) => {
        if (!cancelled) setState({ assets: data.assets, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ assets: [], loading: false, error: err.message || 'Unable to load assets.' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

const DEFAULT_REFRESH_SECONDS = 120

/** Headlines for one asset, refreshed as often as the server refreshes its feeds. */
export function useAssetNews(assetId) {
  const [result, setResult] = useState({ id: null, data: null, error: '' })

  useEffect(() => {
    if (!assetId) return undefined
    let cancelled = false
    let timer = null
    const load = () => {
      getAssetNews(assetId)
        .then((data) => {
          if (cancelled) return
          setResult({ id: assetId, data, error: '' })
          timer = setTimeout(load, (data.refresh_seconds ?? DEFAULT_REFRESH_SECONDS) * 1000)
        })
        .catch((err) => {
          if (cancelled) return
          // Keep the headlines already shown; say the refresh failed.
          setResult((current) => ({
            id: assetId, data: current.id === assetId ? current.data : null, error: err.message || 'Unable to load news.',
          }))
          timer = setTimeout(load, DEFAULT_REFRESH_SECONDS * 1000)
        })
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [assetId])

  const loading = Boolean(assetId) && result.id !== assetId
  return { data: loading ? null : result.data, loading, error: loading ? '' : result.error }
}

function subscribe(callback) {
  window.addEventListener('popstate', callback)
  return () => window.removeEventListener('popstate', callback)
}

/** The asset in the address bar (?asset=gold), so a page can be bookmarked. */
export function useAssetQuery() {
  const search = useSyncExternalStore(subscribe, () => window.location.search, () => '')
  const asset = new URLSearchParams(search).get('asset') ?? ''

  const setAsset = useCallback((id) => {
    window.history.replaceState(null, '', `${window.location.pathname}?asset=${encodeURIComponent(id)}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, [])

  return [asset, setAsset]
}
