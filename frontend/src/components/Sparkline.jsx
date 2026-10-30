const WIDTH = 120
const HEIGHT = 36

/** Minimal inline-SVG line for a short series of prices. */
export default function Sparkline({ values, positive }) {
  if (!values || values.length < 2) {
    return <div className="live-spark live-spark-empty" aria-hidden="true" />
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1

  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * WIDTH
      const y = HEIGHT - 3 - ((value - min) / span) * (HEIGHT - 6)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      className="live-spark"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={positive ? '#2FD16B' : '#FF4D4D'}
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
