import { formatPercent, formatPrice, getAssetDetails } from '../lib/format'

const money = (value) => `${value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`

const tone = (value) => (value > 0 ? 'tone-up' : value < 0 ? 'tone-down' : '')

export default function HoldingsTable({ positions, onSellAll }) {
  if (positions.length === 0) {
    return (
      <div className="holdings-empty">
        No open positions yet. Place an order, or let the signal decide.
      </div>
    )
  }

  return (
    <div className="table-scroll">
      <table className="market-table holdings-table">
        <thead>
          <tr>
            <th>ASSET</th>
            <th>QUANTITY</th>
            <th>AVG COST</th>
            <th>PRICE</th>
            <th>VALUE</th>
            <th>P&amp;L</th>
            <th>WEIGHT</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const details = getAssetDetails(position.symbol)
            return (
              <tr key={position.symbol}>
                <td>
                  <div className="asset-cell">
                    <span
                      className="asset-icon"
                      style={{ color: details.color, borderColor: `${details.color}44`, background: `${details.color}12` }}
                    >
                      {position.symbol[0]}
                    </span>
                    <span><strong>{position.symbol}</strong><small>{details.name}</small></span>
                  </div>
                </td>
                <td className="price-cell">{position.quantity.toFixed(6)}</td>
                <td className="price-cell">{formatPrice(position.avg_cost, position.symbol)}</td>
                <td className="price-cell">
                  {formatPrice(position.price, position.symbol)}
                  {!position.live && <span className="row-stale">stale</span>}
                </td>
                <td className="price-cell">{money(position.market_value)}</td>
                <td className={`price-cell ${tone(position.unrealized_pnl)}`}>
                  {money(position.unrealized_pnl)}
                  <small className="pnl-pct">{formatPercent(position.unrealized_pnl_pct)}</small>
                </td>
                <td className="price-cell">{position.weight_pct.toFixed(1)}%</td>
                <td>
                  <button className="holding-sell" onClick={() => onSellAll(position.symbol)}>
                    Sell all
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
