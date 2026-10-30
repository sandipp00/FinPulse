import { memo, useEffect, useRef } from 'react'
import { ColorType, LineSeries, createChart } from 'lightweight-charts'

/**
 * One daily-or-slower series as a line (macro data, FX rates). Whitespace points
 * (time only) are drawn as gaps. `percent` adds a % sign; `precision` sets decimals.
 */
function SeriesChart({ points, percent = false, precision = 2 }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8C8C8C', fontSize: 11 },
      grid: { vertLines: { color: '#1F1F1F80' }, horzLines: { color: '#1F1F1F' } },
      rightPriceScale: { borderColor: '#1F1F1F' },
      // Small bar spacing lets fitContent show a long daily history (10 years is ~2,500
      // points) in a narrow panel; the library's default stops at half a pixel per bar.
      timeScale: { borderColor: '#1F1F1F', minBarSpacing: 0.05 },
    })
    seriesRef.current = chart.addSeries(LineSeries, { color: '#FFA028', lineWidth: 2, priceLineVisible: false })
    chartRef.current = chart
    return () => {
      chartRef.current = null
      seriesRef.current = null
      chart.remove()
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current) return
    seriesRef.current.applyOptions({
      priceFormat: percent
        ? { type: 'custom', formatter: (value) => `${value.toFixed(precision)}%`, minMove: 1 / 10 ** precision }
        : { type: 'price', precision, minMove: 1 / 10 ** precision },
    })
    seriesRef.current.setData(points)
    chartRef.current?.timeScale().fitContent()
  }, [points, percent, precision])

  return <div ref={containerRef} className="macro-chart" />
}

export default memo(SeriesChart)
