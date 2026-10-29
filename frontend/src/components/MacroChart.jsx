import { memo, useEffect, useRef } from 'react'
import { ColorType, LineSeries, createChart } from 'lightweight-charts'

/** One macro series as a line; missing observations are drawn as gaps. */
function MacroChart({ points, percent }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94A3B8', fontSize: 11 },
      grid: { vertLines: { color: '#1E293B55' }, horzLines: { color: '#1E293B' } },
      rightPriceScale: { borderColor: '#1E293B' },
      timeScale: { borderColor: '#1E293B' },
    })
    seriesRef.current = chart.addSeries(LineSeries, { color: '#38BDF8', lineWidth: 2, priceLineVisible: false })
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
        ? { type: 'custom', formatter: (value) => `${value.toFixed(2)}%`, minMove: 0.01 }
        : { type: 'price', precision: 2, minMove: 0.01 },
    })
    seriesRef.current.setData(points)
    chartRef.current?.timeScale().fitContent()
  }, [points, percent])

  return <div ref={containerRef} className="macro-chart" />
}

export default memo(MacroChart)
