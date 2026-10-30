import { useNow } from '../hooks/useNow'
import { tickStatus } from '../lib/dataStatus'
import { formatPercent, getAssetDetails } from '../lib/format'
import { BOARD, boardLabel } from '../lib/overview'
import DataTag from './DataTag'
import LivePrice from './LivePrice'

/** Where every market stands now: four benchmarks each for six regions and asset classes. */
export default function MarketBoard({ ticks, liveStatus, onOpenAsset }) {
  const now = useNow(5000)

  return (
    <section className="market-board" aria-label="Markets now">
      {BOARD.map((panel) => (
        <div key={panel.title} className="panel board-panel">
          <h2>{panel.title}</h2>
          <table className="board-table">
            <tbody>
              {panel.symbols.map((symbol) => {
                const tick = ticks[symbol]
                const change = tick ? Number(tick.change_pct_24h) : null
                return (
                  <tr key={symbol} onClick={() => onOpenAsset(symbol)} title={`Open the ${getAssetDetails(symbol).name} asset page`}>
                    <th scope="row">{boardLabel(symbol, getAssetDetails(symbol).name)}</th>
                    <td className="num">{tick ? <LivePrice tick={tick} /> : '—'}</td>
                    <td className={`num ${change == null || !Number.isFinite(change) ? '' : change >= 0 ? 'up' : 'down'}`}>
                      {change == null || !Number.isFinite(change) ? '—' : formatPercent(change)}
                    </td>
                    <td className="board-tag"><DataTag status={tickStatus(tick, liveStatus, now)} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  )
}
