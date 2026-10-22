import { useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Info, RotateCcw } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { usePaperTrading } from '../hooks/usePaperTrading'
import { formatPercent } from '../lib/format'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'
import EquityCurve from './EquityCurve'
import HoldingsTable from './HoldingsTable'
import LiveBadge from './LiveBadge'
import OrderHistory from './OrderHistory'
import OrderTicket from './OrderTicket'
import VerifyEmailPanel from './VerifyEmailPanel'

const money = (value, digits = 2) => `${value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString('en-US', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})}`

function Stat({ label, value, tone, note }) {
  return (
    <div className="bt-stat">
      <span>{label}</span>
      <strong className={tone ? `tone-${tone}` : ''}>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  )
}

const toneFor = (value) => (value > 0 ? 'up' : value < 0 ? 'down' : undefined)

function PaperAccount({ symbols, ticks, liveStatus }) {
  const { view, orders, equity, error, trade, follow, reset } = usePaperTrading(ticks)
  const [notice, setNotice] = useState(null)

  const totals = view?.totals

  const sellAll = async (symbol) => {
    try {
      const { order } = await trade({ symbol, side: 'sell', percent: 100 })
      setNotice({ tone: 'ok', text: `Sold ${order.quantity} ${symbol.replace('/USDT', '')}.` })
    } catch (err) {
      setNotice({ tone: 'error', text: err.message })
    }
  }

  const resetAccount = async () => {
    const confirmed = window.confirm(
      'Reset your paper account? This deletes all orders and positions and restores the starting cash.',
    )
    if (!confirmed) return
    try {
      await reset()
      setNotice({ tone: 'ok', text: 'Paper account reset.' })
    } catch (err) {
      setNotice({ tone: 'error', text: err.message })
    }
  }

  return (
    <section className="panel paper-panel" id="paper-trading">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Paper trading</h2>
          <p>Practice with virtual money at live prices. Nothing here is a real order.</p>
        </div>
        <div className="paper-actions">
          <LiveBadge status={liveStatus} />
          <button className="paper-reset" onClick={resetAccount} disabled={!view}>
            <RotateCcw size={13} /> Reset
          </button>
        </div>
      </div>

      <p className="signal-disclaimer">
        <Info size={14} />
        <span>
          <strong>Simulation only.</strong> Orders fill at the live Binance price with a {view?.fee_pct ?? 0.1}% fee and
          no slippage, so real trades would fill a little worse. Not investment advice.
        </span>
      </p>

      {error && <p className="signal-error">{error}</p>}

      {totals ? (
        <>
          <div className="paper-summary">
            <div className="paper-equity">
              <span>Total equity</span>
              <strong>{money(totals.equity)}</strong>
              <span className={`change-pill ${totals.total_pnl >= 0 ? 'positive' : 'negative'}`}>
                {totals.total_pnl >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                {money(totals.total_pnl)} ({formatPercent(totals.total_return_pct)})
              </span>
            </div>
            <div className="paper-stats">
              <Stat label="Cash" value={money(totals.cash)} />
              <Stat label="In positions" value={money(totals.positions_value)} />
              <Stat label="Unrealized P&L" value={money(totals.unrealized_pnl)} tone={toneFor(totals.unrealized_pnl)} />
              <Stat label="Realized P&L" value={money(totals.realized_pnl)} tone={toneFor(totals.realized_pnl)} />
              <Stat
                label="Win rate"
                value={view.stats.win_rate_pct == null ? '—' : `${view.stats.win_rate_pct.toFixed(0)}%`}
                note={`${view.stats.closed_trades} closed`}
              />
              <Stat label="Fees paid" value={money(totals.fees_paid)} />
            </div>
          </div>

          <div className="paper-grid">
            <OrderTicket
              symbols={symbols}
              ticks={ticks}
              view={view}
              onTrade={trade}
              onFollow={follow}
              notice={notice}
              onNotice={setNotice}
            />
            <div className="paper-main">
              <h3 className="paper-subhead">Equity curve</h3>
              <EquityCurve
                points={equity}
                startingCash={view.account.starting_cash}
              />
              <h3 className="paper-subhead">Holdings</h3>
              <HoldingsTable positions={view.positions} onSellAll={sellAll} />
            </div>
          </div>

          <h3 className="paper-subhead paper-history-head">Order history</h3>
          <OrderHistory orders={orders} />
        </>
      ) : (
        !error && <p className="signal-loading">Loading your paper account...</p>
      )}
    </section>
  )
}

/**
 * Paper trading needs an account. Each user's account lives in its own
 * component instance (keyed by user id), so signing out and in as someone else
 * can never briefly show the previous person's portfolio.
 */
export default function PaperTrading({ symbols, ticks, liveStatus }) {
  const { user, loading, verificationRequired, registrationOpen } = useAuth()

  if (user && !(verificationRequired && !user.email_verified)) {
    return <PaperAccount key={user.id} symbols={symbols} ticks={ticks} liveStatus={liveStatus} />
  }

  return (
    <section className="panel paper-panel" id="paper-trading">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Paper trading</h2>
          <p>Practice with virtual money at live prices. Nothing here is a real order.</p>
        </div>
        <LiveBadge status={liveStatus} />
      </div>
      {loading ? (
        <p className="signal-loading">Checking your session...</p>
      ) : user ? (
        <VerifyEmailPanel user={user} />
      ) : (
        <div className="signin-cta">
          <div>
            <h3>Sign in to start paper trading</h3>
            <p>
              Everything else on this page is open to everyone. An account gives you a private
              virtual portfolio to practice with, and nothing in it is real money.
            </p>
          </div>
          <div className="signin-cta-actions">
            <AppLink href={ROUTES.signin} className="auth-submit">Sign in</AppLink>
            {registrationOpen && (
              <AppLink href={ROUTES.signup} className="auth-secondary">Create account</AppLink>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
