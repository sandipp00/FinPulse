import { useEffect, useMemo, useRef, useState, memo } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
} from 'lightweight-charts'
import { ArrowDownRight, ArrowUpRight, RefreshCw } from 'lucide-react'
import { useCandles } from '../hooks/useCandles'
import { INTERVALS } from '../lib/candles'
import { describeSource, formatAge, isCachedFallback } from '../lib/dataStatus'
import { formatPercent, formatPrice, getAssetDetails } from '../lib/format'
import { bollinger, ema, macd, rsi, sma } from '../lib/indicators'
import DataTag from './DataTag'
import LiveBadge from './LiveBadge'

const UP = '#34D399'
const DOWN = '#F87171'
const VISIBLE_CANDLES = 150

// Overlay indicators draw on the price pane; RSI and MACD get their own panes.
const INDICATORS = [
  { id: 'volume', label: 'Volume', color: '#64748B' },
  { id: 'sma20', label: 'SMA 20', color: '#FBBF24' },
  { id: 'sma50', label: 'SMA 50', color: '#818CF8' },
  { id: 'ema20', label: 'EMA 20', color: '#38BDF8' },
  { id: 'bb', label: 'Bollinger', color: '#94A3B8' },
  { id: 'rsi', label: 'RSI 14', color: '#A78BFA' },
  { id: 'macd', label: 'MACD', color: '#38BDF8' },
]

const DEFAULT_ENABLED = { volume: true, sma20: true, sma50: false, ema20: false, bb: false, rsi: false, macd: false }

const LINE_DEFAULTS = {
  lineWidth: 2,
  priceLineVisible: false,
  lastValueVisible: false,
  crosshairMarkerVisible: false,
}

function priceFormatFor(price) {
  const precision = price < 10 ? 4 : 2
  return { type: 'price', precision, minMove: 1 / 10 ** precision }
}

// Everything the chart draws other than the candles, keyed by series name.
function computeSeriesData(candles, enabled) {
  const closes = candles.map((candle) => candle.close)
  const pair = (values) => values
    .map((value, i) => (value == null ? null : { time: candles[i].time, value }))
    .filter(Boolean)
  const data = {}

  if (enabled.volume) {
    data.volume = candles.map((candle) => ({
      time: candle.time,
      value: candle.volume,
      color: candle.close >= candle.open ? `${UP}55` : `${DOWN}55`,
    }))
  }
  if (enabled.sma20) data.sma20 = pair(sma(closes, 20))
  if (enabled.sma50) data.sma50 = pair(sma(closes, 50))
  if (enabled.ema20) data.ema20 = pair(ema(closes, 20))
  if (enabled.bb) {
    const bands = bollinger(closes, 20, 2)
    data.bbUpper = pair(bands.upper)
    data.bbMiddle = pair(bands.middle)
    data.bbLower = pair(bands.lower)
  }
  if (enabled.rsi) data.rsi = pair(rsi(closes, 14))
  if (enabled.macd) {
    const result = macd(closes)
    data.macdLine = pair(result.line)
    data.macdSignal = pair(result.signal)
    data.macdHist = result.histogram
      .map((value, i) => (value == null ? null : {
        time: candles[i].time,
        value,
        color: value >= 0 ? `${UP}99` : `${DOWN}99`,
      }))
      .filter(Boolean)
  }
  return data
}

function addSeriesSet(chart, enabled, price) {
  const color = (id) => INDICATORS.find((item) => item.id === id).color
  const series = {
    candle: chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
      borderVisible: false,
      priceFormat: priceFormatFor(price),
    }),
  }

  if (enabled.volume) {
    series.volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      priceLineVisible: false,
      lastValueVisible: false,
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } })
  }

  for (const id of ['sma20', 'sma50', 'ema20']) {
    if (enabled[id]) {
      series[id] = chart.addSeries(LineSeries, { ...LINE_DEFAULTS, color: color(id), lineWidth: 1.5 })
    }
  }
  if (enabled.bb) {
    const edge = { ...LINE_DEFAULTS, color: `${color('bb')}CC`, lineWidth: 1 }
    series.bbUpper = chart.addSeries(LineSeries, edge)
    series.bbLower = chart.addSeries(LineSeries, edge)
    series.bbMiddle = chart.addSeries(LineSeries, { ...edge, lineStyle: 2 })
  }

  let pane = 1
  if (enabled.rsi) {
    series.rsi = chart.addSeries(LineSeries, { ...LINE_DEFAULTS, color: color('rsi'), lineWidth: 1.5 }, pane)
    series.rsi.createPriceLine({ price: 70, color: `${DOWN}88`, lineWidth: 1, lineStyle: 2, axisLabelVisible: false })
    series.rsi.createPriceLine({ price: 30, color: `${UP}88`, lineWidth: 1, lineStyle: 2, axisLabelVisible: false })
    pane += 1
  }
  if (enabled.macd) {
    series.macdHist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane)
    series.macdLine = chart.addSeries(LineSeries, { ...LINE_DEFAULTS, color: color('macd'), lineWidth: 1.5 }, pane)
    series.macdSignal = chart.addSeries(LineSeries, { ...LINE_DEFAULTS, color: '#FBBF24', lineWidth: 1.5 }, pane)
  }

  // Give the price pane most of the height.
  const panes = chart.panes()
  panes[0].setStretchFactor(3)
  panes.slice(1).forEach((item) => item.setStretchFactor(1))

  return series
}

function CandleChart({ symbols, symbol, onSymbolChange, tick, liveStatus }) {
  const [timeframe, setTimeframe] = useState('1h')
  const [enabled, setEnabled] = useState(DEFAULT_ENABLED)
  const [hover, setHover] = useState(null)

  const { base, candles, meta, loading, error, reload } = useCandles(symbol, timeframe, tick)
  const source = describeSource(meta)

  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const loadedRef = useRef({ base: null, structure: null })

  // Changes whenever the set of drawn series must be rebuilt.
  const structureKey = useMemo(
    () => INDICATORS.filter((item) => enabled[item.id]).map((item) => item.id).join(','),
    [enabled],
  )

  // 1. Create the chart once.
  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94A3B8',
        fontSize: 11,
        panes: { separatorColor: '#1E293B', separatorHoverColor: '#34D39933' },
      },
      grid: {
        vertLines: { color: '#1E293B55' },
        horzLines: { color: '#1E293B' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1E293B' },
      timeScale: { borderColor: '#1E293B', timeVisible: true, secondsVisible: false },
    })
    chartRef.current = chart

    return () => {
      chartRef.current = null
      seriesRef.current = null
      loadedRef.current = { base: null, structure: null }
      chart.remove()
    }
  }, [])

  // 2. Rebuild the series set when indicators are toggled (or data first arrives).
  const hasData = base.length > 0
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !hasData) return undefined

    if (seriesRef.current) {
      Object.values(seriesRef.current).forEach((item) => chart.removeSeries(item))
    }
    seriesRef.current = addSeriesSet(chart, enabled, base.at(-1).close)
    loadedRef.current = { base: null, structure: null } // force a full data load

    const onMove = (param) => {
      const point = param.seriesData?.get(seriesRef.current?.candle)
      setHover(point && param.time ? point : null)
    }
    chart.subscribeCrosshairMove(onMove)
    return () => chart.unsubscribeCrosshairMove(onMove)
    // `base` is only read for the initial price precision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey, hasData])

  // 3. Push data: a full load when the fetch or series set changed, otherwise
  //    just update the latest point for live ticks.
  useEffect(() => {
    const series = seriesRef.current
    const chart = chartRef.current
    if (!series || !chart || candles.length === 0) return

    const data = computeSeriesData(candles, enabled)
    const fullLoad = loadedRef.current.base !== base || loadedRef.current.structure !== structureKey

    if (fullLoad) {
      const baseChanged = loadedRef.current.base !== base
      series.candle.setData(candles)
      for (const [name, points] of Object.entries(data)) series[name]?.setData(points)
      series.candle.applyOptions({ priceFormat: priceFormatFor(candles.at(-1).close) })
      loadedRef.current = { base, structure: structureKey }

      if (baseChanged) {
        chart.timeScale().setVisibleLogicalRange({
          from: Math.max(0, candles.length - VISIBLE_CANDLES),
          to: candles.length + 6,
        })
      }
      return
    }

    series.candle.update(candles.at(-1))
    for (const [name, points] of Object.entries(data)) {
      const last = points.at(-1)
      if (last) series[name]?.update(last)
    }
  }, [candles, base, enabled, structureKey])

  const latest = candles.at(-1)
  const shown = hover ?? latest
  const periodOpen = candles[0]?.open
  const periodChange = latest && periodOpen ? (latest.close / periodOpen - 1) * 100 : null
  const details = getAssetDetails(symbol)

  const toggle = (id) => setEnabled((current) => ({ ...current, [id]: !current[id] }))

  return (
    <section className="panel candle-panel">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Live chart · {details.name}</h2>
          <p>Candlesticks from Binance, with the current candle updating in real time</p>
        </div>
        <LiveBadge status={liveStatus} />
      </div>

      <div className="candle-toolbar">
        <div className="range-control" role="tablist" aria-label="Symbol">
          {symbols.map((item) => (
            <button
              key={item}
              onClick={() => onSymbolChange(item)}
              className={item === symbol ? 'range-active' : ''}
            >
              {item.replace('/USDT', '')}
            </button>
          ))}
        </div>
        <div className="range-control" role="tablist" aria-label="Timeframe">
          {INTERVALS.map((item) => (
            <button
              key={item}
              onClick={() => setTimeframe(item)}
              className={item === timeframe ? 'range-active' : ''}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="candle-toggles" aria-label="Indicators">
        {INDICATORS.map((item) => (
          <button
            key={item.id}
            onClick={() => toggle(item.id)}
            className={enabled[item.id] ? 'indicator-on' : ''}
            aria-pressed={enabled[item.id]}
          >
            <i style={{ background: item.color }} />
            {item.label}
          </button>
        ))}
      </div>

      <div className="chart-summary candle-summary">
        <strong>{latest ? formatPrice(latest.close, symbol) : '—'}</strong>
        {periodChange != null && (
          <span className={`change-pill ${periodChange >= 0 ? 'positive' : 'negative'}`}>
            {periodChange >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {formatPercent(periodChange)}
          </span>
        )}
        {shown && (
          <span className="ohlc-readout">
            O <b>{formatPrice(shown.open, symbol)}</b>
            H <b>{formatPrice(shown.high, symbol)}</b>
            L <b>{formatPrice(shown.low, symbol)}</b>
            C <b>{formatPrice(shown.close, symbol)}</b>
          </span>
        )}
      </div>

      <div className="candle-chart-wrap">
        <div ref={containerRef} className="candle-chart" />
        {isCachedFallback(meta) && (
          <div className="candle-cached" role="status">
            <DataTag status="cached" />
            The exchange is not answering. These candles were fetched {formatAge((meta.cache_age_seconds ?? 0) * 1000)}.
          </div>
        )}
        {loading && <div className="candle-overlay">Loading {symbol} {timeframe} candles...</div>}
        {error && (
          <div className="candle-overlay candle-error">
            <span>{error}</span>
            <button onClick={reload}><RefreshCw size={13} /> Retry</button>
          </div>
        )}
      </div>

      <div className="chart-footnote">
        <span><i className="status-dot" /> Scroll to zoom, drag to pan, hover for exact values</span>
        <span>Indicators are computed in your browser from the candles shown</span>
        {source && <span className="candle-source">Source: {source}</span>}
      </div>
    </section>
  )
}

export default memo(CandleChart)
