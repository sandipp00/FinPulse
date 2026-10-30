import { useEarnings } from '../hooks/useEarnings'
import { CERTAINTY_LABEL, TIMING_LABEL, formatDay, formatEps, growthVsLastYear } from '../lib/earnings'

/** One stock's next report and its last quarters' EPS against the consensus (Nasdaq). */
export default function EarningsPanel({ symbol }) {
  const { data, error, loading } = useEarnings(symbol)

  return (
    <section className="panel at-figures" aria-label="Earnings">
      <h3 className="at-section-title">Earnings</h3>
      {loading && <p className="pulse-empty">Loading earnings from Nasdaq…</p>}
      {error && <p className="pulse-empty">Earnings are unavailable: {error}</p>}
      {data && (
        <>
          {data.stale && <p className="pulse-empty ix-warn">Nasdaq is not answering ({data.stale}); showing the last figures.</p>}
          {data.next ? (
            <p className="earn-next">
              Next report: <b>{formatDay(data.next.date)}</b>
              {data.next.timing && `, ${TIMING_LABEL[data.next.timing].toLowerCase()}`}
              <span className={`earn-badge earn-${data.next.certainty}`}>{CERTAINTY_LABEL[data.next.certainty]}</span>
              {data.next.eps_forecast != null && (
                <span className="earn-detail">
                  Consensus EPS {formatEps(data.next.eps_forecast)}
                  {data.next.analysts != null && ` from ${data.next.analysts} analysts`}
                  {data.next.fiscal_quarter && ` for the quarter ending ${data.next.fiscal_quarter}`}
                  {growthVsLastYear(data.next) && ` (${growthVsLastYear(data.next)})`}.
                </span>
              )}
            </p>
          ) : (
            <p className="earn-next">No upcoming report date yet{data.history[0] ? `; it last reported on ${formatDay(data.history[0].date)}` : ''}.</p>
          )}
          {data.history.length > 0 ? (
            <div className="table-scroll">
              <table className="rel-table">
                <thead><tr><th>Quarter</th><th>Reported</th><th className="num">EPS</th><th className="num">Consensus</th><th className="num">Surprise</th></tr></thead>
                <tbody>
                  {data.history.map((q) => (
                    <tr key={q.fiscal_quarter}>
                      <td>{q.fiscal_quarter}</td>
                      <td>{formatDay(q.date)}</td>
                      <td className="num">{formatEps(q.eps)}</td>
                      <td className="num">{formatEps(q.eps_forecast)}</td>
                      <td className={`num ${q.surprise_pct == null ? '' : q.surprise_pct >= 0 ? 'up' : 'down'}`}>
                        {q.surprise_pct == null ? '—' : `${q.surprise_pct > 0 ? '+' : ''}${q.surprise_pct.toFixed(1)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="pulse-empty">Nasdaq has no past quarters with an analyst consensus for this company.</p>}
          <p className="deriv-note">{data.notes[0]} {data.notes[1]}</p>
        </>
      )}
    </section>
  )
}
