import { useMemo, useState } from 'react'
import { ArrowUpRight, FileText, Info } from 'lucide-react'
import AppLink from '../components/AppLink'
import LiveBadge from '../components/LiveBadge'
import { useResearchInputs } from '../hooks/useResearchInputs'
import { useRisk } from '../hooks/useRisk'
import { getAssetDetails } from '../lib/format'
import { buildBrief } from '../lib/research'
import { ROUTES } from '../lib/routes'

/** A written brief for one asset, assembled from live price, signals, risk and backtest data. */
export default function ResearchPage({ ticks, liveSymbols, liveStatus }) {
  const [symbol, setSymbol] = useState('BTC/USDT')
  const active = liveSymbols.includes(symbol) ? symbol : liveSymbols[0] ?? symbol

  const risk = useRisk()
  const inputs = useResearchInputs(active)
  const tick = ticks[active]

  const brief = useMemo(() => {
    if (inputs.loading || risk.loading) return null
    const peers = risk.data?.assets ?? []
    return buildBrief({
      symbol: active,
      name: getAssetDetails(active).name,
      tick,
      signals: inputs.signals,
      risk: peers.find((asset) => asset.symbol === active) ?? null,
      peers,
      backtest: inputs.backtest,
    })
  }, [active, tick, inputs.loading, inputs.signals, inputs.backtest, risk.loading, risk.data])

  return (
    <section className="panel research-panel">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Asset brief</h2>
          <p>Written from your own data with fixed rules. Pick an asset.</p>
        </div>
        <LiveBadge status={liveStatus} />
      </div>

      <div className="research-toolbar">
        <div className="range-control" role="tablist" aria-label="Asset">
          {liveSymbols.map((item) => (
            <button
              key={item}
              onClick={() => setSymbol(item)}
              className={item === active ? 'range-active' : ''}
            >
              {item.replace('/USDT', '')}
            </button>
          ))}
        </div>
      </div>

      {!brief ? (
        <p className="signal-loading">Gathering the latest price, signals, risk figures and backtest...</p>
      ) : (
        <article className="brief">
          <h3 className="brief-headline"><FileText size={17} /> {brief.headline}</h3>

          {risk.error && <p className="signal-error">Risk figures could not be loaded: {risk.error}</p>}

          {brief.sections.map((section) => (
            <section key={section.title} className="brief-section">
              <h4>{section.title}</h4>
              <ul>
                {section.points.map((point) => <li key={point}>{point}</li>)}
              </ul>
            </section>
          ))}

          {brief.cautions.length > 0 && (
            <section className="brief-cautions">
              <h4>Things to keep in mind</h4>
              <ul>
                {brief.cautions.map((caution) => <li key={caution}>{caution}</li>)}
              </ul>
            </section>
          )}

          <p className="brief-note"><Info size={14} /> {brief.note}</p>

          <div className="brief-links">
            <AppLink href={ROUTES.markets} className="insight-button">
              See the chart <ArrowUpRight size={14} />
            </AppLink>
            <AppLink href={ROUTES.analytics} className="insight-button">
              All signals <ArrowUpRight size={14} />
            </AppLink>
            <AppLink href={ROUTES.risk} className="insight-button">
              Risk monitor <ArrowUpRight size={14} />
            </AppLink>
          </div>
        </article>
      )}
    </section>
  )
}
