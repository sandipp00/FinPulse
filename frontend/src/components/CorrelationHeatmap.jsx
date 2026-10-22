const shortName = (symbol) => symbol.replace('/USDT', '').replace('^', '')

// Positive correlation is teal, negative is amber; the stronger it is, the more opaque.
function cellColor(value) {
  if (value == null) return 'transparent'
  const strength = Math.min(Math.abs(value), 1)
  return value >= 0 ? `rgba(45, 212, 191, ${0.08 + strength * 0.62})` : `rgba(251, 191, 36, ${0.08 + strength * 0.62})`
}

function describe(a, b, value) {
  if (value == null) return `${a} and ${b}: not enough shared history`
  const strength = Math.abs(value) >= 0.7 ? 'strongly' : Math.abs(value) >= 0.3 ? 'moderately' : 'barely'
  const direction = value >= 0 ? 'together' : 'in opposite directions'
  return `${a} and ${b}: correlation ${value.toFixed(2)}. Their daily moves ${strength === 'barely' ? 'barely relate' : `${strength} go ${direction}`}.`
}

/** How assets' daily returns move together. 1 = in lockstep, 0 = unrelated, -1 = opposite. */
export default function CorrelationHeatmap({ correlation }) {
  const { symbols, matrix } = correlation

  return (
    <div className="table-scroll">
      <table className="heatmap" aria-label="Correlation of daily returns">
        <thead>
          <tr>
            <th />
            {symbols.map((symbol) => <th key={symbol} scope="col">{shortName(symbol)}</th>)}
          </tr>
        </thead>
        <tbody>
          {symbols.map((row, i) => (
            <tr key={row}>
              <th scope="row">{shortName(row)}</th>
              {symbols.map((column, j) => {
                const value = matrix[i][j]
                return (
                  <td
                    key={column}
                    className={i === j ? 'heat-self' : ''}
                    style={{ background: i === j ? undefined : cellColor(value) }}
                    title={i === j ? row : describe(row, column, value)}
                  >
                    {value == null ? '—' : i === j ? '1' : value.toFixed(2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="heat-legend" aria-hidden="true">
        <span><i style={{ background: cellColor(-0.8) }} /> moves opposite</span>
        <span><i style={{ background: cellColor(0) }} /> unrelated</span>
        <span><i style={{ background: cellColor(0.8) }} /> moves together</span>
      </div>
    </div>
  )
}
