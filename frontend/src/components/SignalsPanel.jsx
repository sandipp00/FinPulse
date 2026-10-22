import { useState, memo } from 'react'
import { ArrowDown, ArrowUp, Info, Minus } from 'lucide-react'
import { useSignals } from '../hooks/useSignals'
import { INTERVALS } from '../lib/candles'
import { formatPrice, getAssetDetails } from '../lib/format'
import BacktestCard from './BacktestCard'

const RATING_CLASS = {
  'Strong Buy': 'rating-strong-buy',
  Buy: 'rating-buy',
  Hold: 'rating-hold',
  Sell: 'rating-sell',
  'Strong Sell': 'rating-strong-sell',
}

function RatingPill({ rating }) {
  return <span className={`rating-pill ${RATING_CLASS[rating] ?? 'rating-hold'}`}>{rating}</span>
}

// A bar that fills right (green) for bullish scores and left (red) for bearish.
function ScoreGauge({ score }) {
  const width = Math.min(Math.abs(score), 100) / 2
  return (
    <div className="score-gauge" aria-label={`Score ${score}`}>
      <i className="score-mid" />
      <b
        className={score >= 0 ? 'score-pos' : 'score-neg'}
        style={score >= 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
      />
    </div>
  )
}

function VoteIcon({ vote }) {
  if (vote > 0) return <span className="vote vote-up"><ArrowUp size={12} /></span>
  if (vote < 0) return <span className="vote vote-down"><ArrowDown size={12} /></span>
  return <span className="vote vote-flat"><Minus size={12} /></span>
}

function SignalsPanel({ selectedSymbol, onSelect }) {
  const [interval, setTimeframe] = useState('1d')
  const { signals, loading, error } = useSignals(interval)

  const selected = signals.find((item) => item.symbol === selectedSymbol) ?? signals[0]

  return (
    <section className="panel signals-panel">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Buy / sell signals</h2>
          <p>Six transparent indicator rules vote on each closed candle. Pick a coin to see why.</p>
        </div>
        <div className="range-control" role="tablist" aria-label="Signal timeframe">
          {INTERVALS.map((item) => (
            <button
              key={item}
              onClick={() => setTimeframe(item)}
              className={item === interval ? 'range-active' : ''}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <p className="signal-disclaimer">
        <Info size={14} />
        <span>
          <strong>Educational signals, not investment advice.</strong> They summarize what technical
          indicators say about recent price action and do not predict future returns. Check the
          backtest before giving any signal weight.
        </span>
      </p>

      {error && <p className="signal-error">{error}</p>}

      {loading ? (
        <p className="signal-loading">Calculating signals from the latest closed candles...</p>
      ) : (
        <div className="signals-grid">
          <div className="signal-list" role="list">
            {signals.map((item) => {
              const details = getAssetDetails(item.symbol)
              const rated = item.score != null
              return (
                <button
                  key={item.symbol}
                  role="listitem"
                  className={`signal-row ${item.symbol === selected?.symbol ? 'signal-row-selected' : ''}`}
                  style={{ '--accent': details.color }}
                  onClick={() => onSelect(item.symbol)}
                >
                  <span className="signal-asset">
                    <i style={{ background: details.color }} />
                    <strong>{item.symbol.replace('/USDT', '')}</strong>
                    <small title="Close of the last completed candle">
                      {rated ? `close ${formatPrice(item.price, item.symbol)}` : '—'}
                    </small>
                  </span>
                  <RatingPill rating={item.rating} />
                  {rated ? (
                    <>
                      <ScoreGauge score={item.score} />
                      <span className="signal-meta">
                        <b>{item.score > 0 ? '+' : ''}{item.score}</b>
                        <small>
                          {item.confidence == null ? 'no direction' : `${item.confidence}% agree`}
                        </small>
                      </span>
                    </>
                  ) : (
                    <span className="signal-meta signal-meta-wide">
                      <small>Needs {item.candles_required} candles</small>
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {selected && selected.score != null && (
            <div className="signal-detail">
              <div className="signal-detail-head">
                <h3>
                  {getAssetDetails(selected.symbol).name} · {interval}
                </h3>
                <RatingPill rating={selected.rating} />
              </div>
              <p className="signal-votes">
                {selected.votes.bullish} bullish · {selected.votes.bearish} bearish ·{' '}
                {selected.votes.neutral} neutral
              </p>
              <ul className="reason-list">
                {selected.reasons.map((reason) => (
                  <li key={reason.rule}>
                    <VoteIcon vote={reason.vote} />
                    <span>{reason.text}</span>
                    <small>×{reason.weight}</small>
                  </li>
                ))}
              </ul>
              <p className="signal-footnote">
                Rating uses the last <em>closed</em> candle (prices shown are that candle&apos;s close), so it will not flicker mid-candle. The
                score is the weighted average of the six votes (−100 to +100); ±20 makes a Buy/Sell,
                ±50 a Strong call.
              </p>
            </div>
          )}

          {selected && <BacktestCard symbol={selected.symbol} interval={interval} />}
        </div>
      )}
    </section>
  )
}

export default memo(SignalsPanel)
