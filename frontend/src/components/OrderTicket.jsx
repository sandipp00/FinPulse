import { useState } from 'react'
import { Zap } from 'lucide-react'
import { useSignals } from '../hooks/useSignals'
import { INTERVALS } from '../lib/candles'
import { formatPrice, getAssetDetails } from '../lib/format'
import { estimateOrder } from '../lib/portfolio'
import LivePrice from './LivePrice'

const QUICK_PERCENTS = [25, 50, 75, 100]
const FOLLOW_PERCENTS = [10, 25, 50]

const RATING_CLASS = {
  'Strong Buy': 'rating-strong-buy',
  Buy: 'rating-buy',
  Hold: 'rating-hold',
  Sell: 'rating-sell',
  'Strong Sell': 'rating-strong-sell',
}

export default function OrderTicket({ symbols, ticks, view, onTrade, onFollow, notice, onNotice }) {
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [side, setSide] = useState('buy')
  const [size, setSize] = useState({ kind: 'usd', value: '' })
  const [busy, setBusy] = useState(false)

  const [followInterval, setFollowInterval] = useState('1d')
  const [followPercent, setFollowPercent] = useState(25)
  const { signals } = useSignals(followInterval)

  const tick = ticks[symbol]
  const price = tick?.price
  const cash = view?.totals.cash ?? 0
  const held = view?.positions.find((p) => p.symbol === symbol)
  const feeRate = (view?.fee_pct ?? 0.1) / 100

  const amount = Number(size.value)
  const estimate = estimateOrder({
    side,
    size: { kind: size.kind, value: amount },
    price,
    cash,
    heldQuantity: held?.quantity ?? 0,
    feeRate,
  })

  // Catch obvious over-sizing here instead of waiting for the server to reject it.
  const overLimit = estimate && (side === 'buy'
    ? estimate.notional + estimate.fee > cash * (1 + 1e-9)
    : estimate.quantity > (held?.quantity ?? 0) * (1 + 1e-9))
  const canSubmit = Boolean(view && price && amount > 0 && !busy && !overLimit)
  const coin = symbol.replace('/USDT', '')

  const run = async (action, describe) => {
    setBusy(true)
    onNotice(null)
    try {
      const result = await action()
      onNotice({ tone: 'ok', text: describe(result) })
      return result
    } catch (err) {
      onNotice({ tone: 'error', text: err.message })
      return null
    } finally {
      setBusy(false)
    }
  }

  const submit = async () => {
    const body = { symbol, side }
    if (size.kind === 'percent') body.percent = amount
    else body.notional_usd = amount

    const result = await run(
      () => onTrade(body),
      ({ order }) => `${order.side === 'buy' ? 'Bought' : 'Sold'} ${order.quantity} ${coin} at ${formatPrice(order.price, symbol)}`,
    )
    if (result) setSize({ kind: 'usd', value: '' })
  }

  const sellAll = () => run(
    () => onTrade({ symbol, side: 'sell', percent: 100 }),
    ({ order }) => `Sold ${order.quantity} ${coin} at ${formatPrice(order.price, symbol)}`,
  )

  const followSignal = () => run(
    () => onFollow(symbol, followInterval, followPercent),
    (result) => (result.order
      ? `${result.reason} ${result.order.side === 'buy' ? 'Bought' : 'Sold'} ${result.order.quantity} ${coin} at ${formatPrice(result.order.price, symbol)}`
      : result.reason),
  )

  const rating = signals.find((item) => item.symbol === symbol)?.rating

  return (
    <div className="ticket">
      <h3>Order ticket</h3>

      <div className="range-control ticket-symbols" role="tablist" aria-label="Symbol">
        {symbols.map((item) => (
          <button
            key={item}
            onClick={() => setSymbol(item)}
            className={item === symbol ? 'range-active' : ''}
          >
            {item.replace('/USDT', '')}
          </button>
        ))}
      </div>

      <div className="ticket-price">
        <span>{getAssetDetails(symbol).name}</span>
        {tick ? <LivePrice tick={tick} className="ticket-price-value" /> : <b>—</b>}
      </div>

      <div className="ticket-side" role="tablist" aria-label="Side">
        <button className={side === 'buy' ? 'side-buy' : ''} onClick={() => setSide('buy')}>Buy</button>
        <button className={side === 'sell' ? 'side-sell' : ''} onClick={() => setSide('sell')}>Sell</button>
      </div>

      <label className="ticket-field">
        <span>Amount (USD)</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          placeholder={size.kind === 'percent' ? `${size.value}% of ${side === 'buy' ? 'cash' : 'position'}` : '0.00'}
          value={size.kind === 'percent' ? '' : size.value}
          onChange={(event) => setSize({ kind: 'usd', value: event.target.value })}
        />
      </label>

      <div className="ticket-quick">
        {QUICK_PERCENTS.map((percent) => (
          <button
            key={percent}
            className={size.kind === 'percent' && Number(size.value) === percent ? 'quick-on' : ''}
            onClick={() => setSize({ kind: 'percent', value: String(percent) })}
          >
            {percent}%
          </button>
        ))}
      </div>

      <p className={`ticket-estimate ${overLimit ? 'ticket-estimate-over' : ''}`}>
        {overLimit
          ? (side === 'buy' ? 'Exceeds your available cash.' : `Exceeds the ${coin} you hold.`)
          : estimate
          ? <>≈ <b>{estimate.quantity.toFixed(6)} {coin}</b> · ${estimate.notional.toLocaleString('en-US', { maximumFractionDigits: 2 })} · fee ≈ ${estimate.fee.toFixed(2)}</>
          : <>Cash available: <b>${cash.toLocaleString('en-US', { maximumFractionDigits: 2 })}</b></>}
      </p>

      <button
        className={`ticket-submit ${side === 'buy' ? 'submit-buy' : 'submit-sell'}`}
        disabled={!canSubmit}
        onClick={submit}
      >
        {busy ? 'Placing...' : `${side === 'buy' ? 'Buy' : 'Sell'} ${coin}`}
      </button>
      {held && (
        <button className="ticket-sellall" disabled={busy} onClick={sellAll}>
          Sell all {coin} ({held.quantity.toFixed(6)})
        </button>
      )}

      <div className="ticket-follow">
        <div className="ticket-follow-head">
          <Zap size={14} />
          <strong>Follow the signal</strong>
          {rating && <span className={`rating-pill ${RATING_CLASS[rating] ?? 'rating-hold'}`}>{rating}</span>}
        </div>
        <div className="ticket-follow-controls">
          <select value={followInterval} onChange={(event) => setFollowInterval(event.target.value)} aria-label="Signal timeframe">
            {INTERVALS.map((item) => <option key={item} value={item}>{item} signal</option>)}
          </select>
          <select value={followPercent} onChange={(event) => setFollowPercent(Number(event.target.value))} aria-label="Cash to use">
            {FOLLOW_PERCENTS.map((item) => <option key={item} value={item}>{item}% of cash</option>)}
          </select>
        </div>
        <button className="ticket-follow-btn" disabled={busy || !view} onClick={followSignal}>
          Trade {coin} per its {followInterval} signal
        </button>
        <small>
          Buys on Buy ratings when flat; sells everything on Sell ratings; otherwise does nothing.
        </small>
      </div>

      {notice && (
        <p className={`ticket-message ticket-${notice.tone}`} role="status">{notice.text}</p>
      )}
    </div>
  )
}
