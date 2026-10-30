import { memo, useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
} from 'lightweight-charts'

const UP = '#2FD16B'
const DOWN = '#FF4D4D'
const PRIMARY = '#2FD16B'
const OTHER = '#4FC3F7'

function priceFormatFor(price) {
  const precision = price < 10 ? 4 : 2
  return { type: 'price', precision, minMove: 1 / 10 ** precision }
}

/**
 * The explorer's chart: candlesticks (plus volume when the source reports it), or,
 * when `comparison` is given, both instruments rebased to 100 on shared dates. With
 * `asLine`, closes are drawn as a line, for sources whose bars are single prices.
 * Times are UTC, as the API sends them.
 */
function ExplorerChart({ candles, showVolume, comparison, intraday, asLine = false }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef([])

  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8C8C8C',
        fontSize: 11,
      },
      grid: { vertLines: { color: '#1F1F1F80' }, horzLines: { color: '#1F1F1F' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1F1F1F' },
      timeScale: { borderColor: '#1F1F1F', secondsVisible: false },
    })
    chartRef.current = chart
    return () => {
      chartRef.current = null
      seriesRef.current = []
      chart.remove()
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    seriesRef.current.forEach((series) => chart.removeSeries(series))
    seriesRef.current = []
    chart.applyOptions({ timeScale: { timeVisible: intraday } })

    if (comparison) {
      const line = { lineWidth: 2, priceLineVisible: false, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }
      const primary = chart.addSeries(LineSeries, { ...line, color: PRIMARY })
      const other = chart.addSeries(LineSeries, { ...line, color: OTHER })
      primary.setData(comparison.points.map((point) => ({ time: point.time, value: point.primary })))
      other.setData(comparison.points.map((point) => ({ time: point.time, value: point.other })))
      primary.createPriceLine({ price: 100, color: '#5A5A5A', lineWidth: 1, lineStyle: 2, axisLabelVisible: false })
      seriesRef.current = [primary, other]
    } else if (candles.length > 0 && asLine) {
      const line = chart.addSeries(LineSeries, { color: PRIMARY, lineWidth: 2, priceFormat: priceFormatFor(candles.at(-1).close) })
      line.setData(candles.map((item) => ({ time: item.time, value: item.close })))
      seriesRef.current = [line]
    } else if (candles.length > 0) {
      const candle = chart.addSeries(CandlestickSeries, {
        upColor: UP,
        downColor: DOWN,
        wickUpColor: UP,
        wickDownColor: DOWN,
        borderVisible: false,
        priceFormat: priceFormatFor(candles.at(-1).close),
      })
      candle.setData(candles)
      seriesRef.current = [candle]

      if (showVolume) {
        const volume = chart.addSeries(HistogramSeries, {
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
          priceLineVisible: false,
          lastValueVisible: false,
        })
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
        volume.setData(candles.map((item) => ({
          time: item.time,
          value: item.volume,
          color: item.close >= item.open ? `${UP}55` : `${DOWN}55`,
        })))
        seriesRef.current.push(volume)
      }
    }
    chart.timeScale().fitContent()
  }, [candles, showVolume, comparison, intraday, asLine])

  return <div ref={containerRef} className="ix-chart" />
}

export default memo(ExplorerChart)
