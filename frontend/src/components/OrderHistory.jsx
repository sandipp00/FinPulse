import { formatPrice } from '../lib/format'

const timeFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
})

const tone = (value) => (value > 0 ? 'tone-up' : value < 0 ? 'tone-down' : '')

const money = (value) => `${value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`

export default function OrderHistory({ orders }) {
  if (orders.length === 0) {
    return <div className="holdings-empty">Your orders will appear here.</div>
  }

  return (
    <div className="table-scroll">
      <table className="market-table holdings-table">
        <thead>
          <tr>
            <th>TIME</th>
            <th>SIDE</th>
            <th>ASSET</th>
            <th>QUANTITY</th>
            <th>PRICE</th>
            <th>FEE</th>
            <th>REALIZED P&amp;L</th>
            <th>SOURCE</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id}>
              <td className="price-cell">
                {timeFormat.format(new Date(order.ts))}
              </td>
              <td>
                <span className={`order-side ${order.side === 'buy' ? 'order-buy' : 'order-sell'}`}>
                  {order.side.toUpperCase()}
                </span>
              </td>
              <td className="price-cell">{order.symbol}</td>
              <td className="price-cell">{order.quantity.toFixed(6)}</td>
              <td className="price-cell">{formatPrice(order.price, order.symbol)}</td>
              <td className="price-cell">${order.fee.toFixed(2)}</td>
              <td className={`price-cell ${tone(order.realized_pnl)}`}>
                {order.realized_pnl == null ? '—' : money(order.realized_pnl)}
              </td>
              <td>
                {order.source === 'signal'
                  ? <span className="source-badge source-signal">SIGNAL · {order.signal_rating}</span>
                  : <span className="source-badge">MANUAL</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
