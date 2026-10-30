import { useEffect, useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { getMarketHours, getNews } from '../api/finpulse'
import { useNow } from '../hooks/useNow'
import { CLASS_LABEL } from '../lib/asset'
import { formatPercent, getAssetDetails } from '../lib/format'
import { formatCountdown } from '../lib/marketHours'
import { marketsOpen, movers } from '../lib/overview'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

const HOURS_REFRESH_MS = 5 * 60_000
const NEWS_REFRESH_MS = 2 * 60_000
const HEADLINES = 6

/** Fetch `load` now and every `everyMs`; keeps the last good result if a refresh fails. */
function usePolled(load, everyMs) {
  const [state, setState] = useState({ data: null, error: '' })
  useEffect(() => {
    let cancelled = false
    const run = () => load()
      .then((data) => { if (!cancelled) setState({ data, error: '' }) })
      .catch((error) => { if (!cancelled) setState((s) => ({ ...s, error: error.message || 'Unavailable' })) })
    run()
    const timer = setInterval(run, everyMs)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [load, everyMs])
  return state
}

const loadHours = () => getMarketHours()
const loadNews = () => getNews(HEADLINES)

function MoverList({ title, rows, onOpenAsset }) {
  return (
    <div>
      <h3>{title}</h3>
      {rows.length === 0 ? <p className="pulse-empty">None right now.</p> : (
        <ul className="pulse-list">
          {rows.map((m) => (
            <li key={m.symbol}>
              <button onClick={() => onOpenAsset(m.symbol)} title={`Open the ${getAssetDetails(m.symbol).name} asset page`}>
                <span className="pulse-name"><strong>{m.symbol.replace('/USDT', '')}</strong><small title={m.window === '1d' ? 'Change since the previous close' : 'Change over 24 hours'}>{CLASS_LABEL[m.assetClass]}</small></span>
                <span className={`num ${m.change >= 0 ? 'up' : 'down'}`}>{formatPercent(m.change)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ago(iso, now) {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000))
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)}h ago`
  return `${Math.round(minutes / 1440)}d ago`
}

/** Biggest movers, which markets are open, and the latest headlines. */
export default function OverviewPulse({ ticks, onOpenAsset }) {
  const now = useNow(30_000)
  const hours = usePolled(loadHours, HOURS_REFRESH_MS)
  const news = usePolled(loadNews, NEWS_REFRESH_MS)
  const { gainers, losers } = movers(ticks)
  const markets = marketsOpen(hours.data?.exchanges, now / 1000)

  return (
    <section className="pulse-grid">
      <div className="panel pulse-panel">
        <div className="panel-heading">
          <div>
            <h2>Biggest movers</h2>
            <p>Among the 30 stocks, 20 coins, gold, silver and oil: stocks since the previous close, the rest over 24 hours</p>
          </div>
        </div>
        <div className="pulse-movers">
          <MoverList title="Up" rows={gainers} onOpenAsset={onOpenAsset} />
          <MoverList title="Down" rows={losers} onOpenAsset={onOpenAsset} />
        </div>
      </div>

      <div className="panel pulse-panel">
        <div className="panel-heading">
          <div>
            <h2>Markets open now</h2>
            <p>Regular trading sessions of {markets.total || 'the followed'} exchanges</p>
          </div>
          <AppLink href={ROUTES.hours} className="pulse-more">Hours <ArrowUpRight size={13} /></AppLink>
        </div>
        {!hours.data && <p className="pulse-empty">{hours.error ? `Unavailable: ${hours.error}` : 'Loading…'}</p>}
        {hours.data && (
          <>
            <p className="pulse-big"><strong className="num">{markets.open.length}</strong> of {markets.total} open</p>
            {markets.open.length > 0 && (
              <ul className="pulse-tags">
                {markets.open.map((exchange) => <li key={exchange.id}>{exchange.name}</li>)}
              </ul>
            )}
            {markets.next && (
              <p className="pulse-note">
                Next to open: <b>{markets.next.exchange.name}</b> ({markets.next.exchange.city}) in {formatCountdown(markets.next.seconds)}.
              </p>
            )}
            <p className="pulse-note">Crypto trades around the clock.</p>
          </>
        )}
      </div>

      <div className="panel pulse-panel">
        <div className="panel-heading">
          <div>
            <h2>Latest headlines</h2>
            <p>Newest first, each linking to the original</p>
          </div>
          <AppLink href={ROUTES.news} className="pulse-more">All news <ArrowUpRight size={13} /></AppLink>
        </div>
        {!news.data && <p className="pulse-empty">{news.error ? `Unavailable: ${news.error}` : 'Loading…'}</p>}
        {news.data && (
          <ul className="pulse-news">
            {news.data.items.map((item) => (
              <li key={item.id}>
                <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                <small>{item.source_name} · {ago(item.published_at, now)}</small>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
