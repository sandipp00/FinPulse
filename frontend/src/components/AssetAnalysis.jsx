import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getAssetAnalysis } from '../api/finpulse'
import { useAssetRegistry } from '../hooks/useAsset'
import { CLASS_LABEL, assetHref } from '../lib/asset'
import { heatColor, heatmapRows, rsiZone, toPercentPoints } from '../lib/analysis'
import { formatPercent } from '../lib/format'
import AppLink from './AppLink'
import SeriesChart from './SeriesChart'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const PERF = ['1W', '1M', '3M', '6M', 'YTD', '1Y', '3Y', 'annualized']
const pct = (value, digits = 2) => (value == null ? '—' : formatPercent(value * 100, digits))
// Levels (volatility, share of days) have no direction, so no + sign.
const share = (value, digits = 1) => (value == null ? '—' : `${(value * 100).toFixed(digits)}%`)
const tone = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')
const num = (value, digits = 2) => (value == null ? '—' : value.toFixed(digits))
const level = (value) => (value == null ? '—' : value.toLocaleString('en-US', { maximumFractionDigits: value < 10 ? 4 : 2 }))

function Fig({ label, children, className = '', title }) {
  return (
    <div className="ix-stat" title={title}>
      <dt>{label}</dt>
      <dd className={`num ${className}`}>{children}</dd>
    </div>
  )
}

function Section({ title, children, note }) {
  return (
    <section className="panel aa-section">
      <h3 className="at-section-title">{title}</h3>
      {children}
      {note && <p className="ix-footnote">{note}</p>}
    </section>
  )
}

function Heatmap({ monthly }) {
  const rows = heatmapRows(monthly)
  if (rows.length === 0) return <p className="at-empty">Not enough history for monthly returns.</p>
  return (
    <div className="table-scroll">
      <table className="aa-heatmap">
        <thead><tr><th>Year</th>{MONTHS.map((m) => <th key={m}>{m}</th>)}<th>Year</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.year}>
              <th>{row.year}</th>
              {row.months.map((value, i) => (
                <td key={i} style={{ background: heatColor(value) }} className="num">{value == null ? '' : (value * 100).toFixed(1)}</td>
              ))}
              <td className={`num aa-year ${tone(row.total)}`}>{row.total == null ? '' : `${(row.total * 100).toFixed(1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Distribution({ distribution }) {
  const bars = useMemo(() => distribution.bins.map((bin) => ({
    mid: ((bin.from + bin.to) / 2) * 100, count: bin.count, label: `${(bin.from * 100).toFixed(2)}% to ${(bin.to * 100).toFixed(2)}%`,
  })), [distribution])
  if (bars.length === 0) return <p className="at-empty">Not enough daily returns.</p>
  return (
    <>
      <div className="aa-histogram">
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={bars} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
            <XAxis dataKey="mid" tickFormatter={(v) => `${v.toFixed(1)}%`} tick={{ fill: '#94A3B8', fontSize: 10 }} interval="preserveStartEnd" minTickGap={24} />
            <YAxis tick={{ fill: '#94A3B8', fontSize: 10 }} allowDecimals={false} />
            <Tooltip cursor={{ fill: '#1E293B55' }} contentStyle={{ background: '#0B1220', border: '1px solid #1E293B', fontSize: 11 }}
              formatter={(value) => [`${value} days`, 'Days']} labelFormatter={(_, payload) => payload?.[0]?.payload.label ?? ''} />
            <Bar dataKey="count" isAnimationActive={false}>
              {bars.map((bar) => <Cell key={bar.mid} fill={bar.mid >= 0 ? '#34D399' : '#F87171'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <dl className="ix-stats">
        <Fig label="Days">{distribution.count}</Fig>
        <Fig label="Average day" className={tone(distribution.mean)}>{pct(distribution.mean, 3)}</Fig>
        <Fig label="Median day" className={tone(distribution.median)}>{pct(distribution.median, 3)}</Fig>
        <Fig label="Skew" title="Below 0: big down days are more common than big up days">{num(distribution.skew)}</Fig>
        <Fig label="Excess kurtosis" title="Above 0: more extreme days than a normal distribution">{num(distribution.kurtosis)}</Fig>
      </dl>
    </>
  )
}

/** The full analysis of one asset: performance, risk, trend, charts and seasonality. */
export default function AssetAnalysis({ assetId, onSelect }) {
  const registry = useAssetRegistry()
  const [result, setResult] = useState({ id: null, data: null, error: '' })

  useEffect(() => {
    if (!assetId) return undefined
    let cancelled = false
    getAssetAnalysis(assetId)
      .then((data) => !cancelled && setResult({ id: assetId, data, error: '' }))
      .catch((err) => !cancelled && setResult({ id: assetId, data: null, error: err.message || 'Unable to analyse this asset.' }))
    return () => {
      cancelled = true
    }
  }, [assetId])

  const loading = result.id !== assetId
  const data = loading ? null : result.data
  const drawdown = useMemo(() => toPercentPoints(data?.series.drawdown), [data])
  const volatility = useMemo(() => toPercentPoints(data?.series.rolling_volatility), [data])

  const r = data?.risk
  const t = data?.technicals

  return (
    <div className="aa" id="asset-analysis">
      <section className="panel aa-head">
        <div>
          <p className="at-kicker">Asset analysis</p>
          <h2 className="at-name">{data?.asset.name ?? '…'}</h2>
          {data && (
            <p className="at-note">
              {CLASS_LABEL[data.asset.asset_class]} · {data.source.days.toLocaleString()} trading days from {data.source.provider}{' '}
              ({data.source.symbol}), {data.first_date} to {data.last_date}
            </p>
          )}
        </div>
        <div className="aa-controls">
          <select value={assetId} onChange={(event) => onSelect(event.target.value)} aria-label="Asset to analyse">
            {registry.assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}
          </select>
          {data && <AppLink href={assetHref(data.asset.id)} className="at-link">Live price, chart and news →</AppLink>}
        </div>
      </section>

      {loading && <section className="panel empty-panel">Analysing…</section>}
      {!loading && result.error && <section className="panel empty-panel ix-error">{result.error}</section>}

      {data && (
        <>
          <section className="aa-perf" aria-label="Performance">
            {PERF.map((key) => (
              <div key={key} className="panel aa-perf-cell">
                <span>{key === 'annualized' ? 'Per year' : key}</span>
                <strong className={`num ${tone(data.performance[key])}`}>{pct(data.performance[key], 1)}</strong>
              </div>
            ))}
          </section>

          <div className="aa-grid">
            <Section title="Risk" note={data.notes[1]}>
              <dl className="ix-stats">
                <Fig label="Volatility, 30 days">{share(r.volatility_30d)}</Fig>
                <Fig label="Volatility, 90 days">{share(r.volatility_90d)}</Fig>
                <Fig label="Volatility, 1 year">{share(r.volatility_1y)}</Fig>
                <Fig label="Sharpe ratio">{num(r.sharpe)}</Fig>
                <Fig label="Sortino ratio" title="Like Sharpe, but only counts down days as risk">{num(r.sortino)}</Fig>
                <Fig label="1-day VaR (95%)" className="down">{r.var_95 == null ? '—' : `-${(r.var_95 * 100).toFixed(2)}%`}</Fig>
                <Fig label="Average of worst 5% days" className="down">{r.cvar_95 == null ? '—' : `-${(r.cvar_95 * 100).toFixed(2)}%`}</Fig>
                <Fig label={`Best day${r.best_day_date ? ` (${r.best_day_date})` : ''}`} className="up">{pct(r.best_day)}</Fig>
                <Fig label={`Worst day${r.worst_day_date ? ` (${r.worst_day_date})` : ''}`} className="down">{pct(r.worst_day)}</Fig>
                <Fig label="Days up">{share(r.positive_days, 0)}</Fig>
                <Fig label="Deepest fall from a peak" className="down"
                  title={r.max_drawdown_peak ? `${r.max_drawdown_peak} to ${r.max_drawdown_trough}${r.recovered ? ', recovered' : ', not yet recovered'}` : undefined}>
                  {pct(r.max_drawdown, 1)}
                </Fig>
                <Fig label="Below its peak now" className={r.current_drawdown < 0 ? 'down' : ''}>{pct(r.current_drawdown, 1)}</Fig>
              </dl>
            </Section>

            <Section title="Trend and momentum" note="Moving averages and RSI from daily closes. Not investment advice.">
              <dl className="ix-stats">
                <Fig label="Trend (50 and 200-day averages)" className={t.trend === 'up' ? 'up' : t.trend === 'down' ? 'down' : ''}>{t.trend ?? '—'}</Fig>
                <Fig label="vs 20-day average" className={tone(t.vs_sma_20)}>{pct(t.vs_sma_20)}</Fig>
                <Fig label="vs 50-day average" className={tone(t.vs_sma_50)}>{pct(t.vs_sma_50)}</Fig>
                <Fig label="vs 200-day average" className={tone(t.vs_sma_200)}>{pct(t.vs_sma_200)}</Fig>
                <Fig label="RSI (14)" className={`sb-rsi-${rsiZone(t.rsi_14)}`}>{t.rsi_14 == null ? '—' : `${t.rsi_14.toFixed(0)} · ${rsiZone(t.rsi_14)}`}</Fig>
                <Fig label="MACD" className={t.macd_state === 'bullish' ? 'up' : t.macd_state === 'bearish' ? 'down' : ''}>{t.macd_state ?? '—'}</Fig>
                <Fig label="52-week high">{level(t.high_52w)}</Fig>
                <Fig label="52-week low">{level(t.low_52w)}</Fig>
                <Fig label="From 52-week high" className={tone(t.from_high_52w)}>{pct(t.from_high_52w, 1)}</Fig>
                <Fig label="From 52-week low" className={tone(t.from_low_52w)}>{pct(t.from_low_52w, 1)}</Fig>
                <Fig label="Last 50/200-day cross" className={t.last_cross?.type === 'golden' ? 'up' : t.last_cross ? 'down' : ''}>
                  {t.last_cross ? `${t.last_cross.type === 'golden' ? 'Golden' : 'Death'} · ${t.last_cross.date}` : '—'}
                </Fig>
              </dl>
            </Section>
          </div>

          <div className="aa-grid">
            <Section title="Fall from peak (drawdown)">
              <div className="ix-chart-wrap"><SeriesChart points={drawdown} percent precision={1} /></div>
            </Section>
            <Section title="Volatility, 30-day rolling (annualized)">
              <div className="ix-chart-wrap"><SeriesChart points={volatility} percent precision={1} /></div>
            </Section>
          </div>

          <Section title="Monthly returns (%)" note="Each month from the last close of the month before; the latest month is partial.">
            <Heatmap monthly={data.monthly_returns} />
          </Section>
          <Section title="Daily returns: how they spread">
            <Distribution distribution={data.distribution} />
          </Section>
          <p className="ix-footnote">{data.notes[0]}</p>
        </>
      )}
    </div>
  )
}
