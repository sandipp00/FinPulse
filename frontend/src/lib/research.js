import { formatPercent, formatPrice } from './format'
import { rankBy } from './risk'

// Turns the numbers this app already has (live price, signals, risk figures and the
// backtest) into a plain-language brief. It is a set of fixed rules, not a model: every
// sentence below is produced from one number, so nothing is guessed or invented.

const DIRECTION = { 'Strong Buy': 1, Buy: 1, Hold: 0, Sell: -1, 'Strong Sell': -1 }
const FRAME_NAME = { '1d': 'daily', '1h': 'hourly' }
const NEAR_THRESHOLD = [15, 25] // |score| in this band is close to the Buy/Sell line at 20

const percent = (value, digits = 1) => `${Number(value).toFixed(digits)}%`

function describeRank({ rank, of }) {
  if (rank === 1) return `the most volatile of the ${of} assets tracked`
  if (rank === of) return `the least volatile of the ${of} assets tracked`
  return `number ${rank} of ${of} by volatility (1 is the most volatile)`
}

function nowSection(symbol, name, tick) {
  if (!tick) return ['Waiting for a live price. Check the live feed badge at the top of the page.']

  const change = tick.change_pct_24h
  const points = [
    `${name} is trading at ${formatPrice(tick.price, symbol)}, ${change >= 0 ? 'up' : 'down'} `
    + `${Math.abs(change).toFixed(2)}% over the last 24 hours.`,
  ]

  if (tick.high_24h > tick.low_24h) {
    const position = (tick.price - tick.low_24h) / (tick.high_24h - tick.low_24h)
    const where = position >= 2 / 3 ? 'upper third' : position <= 1 / 3 ? 'lower third' : 'middle'
    points.push(
      `That is in the ${where} of its 24-hour range (${formatPrice(tick.low_24h, symbol)} to `
      + `${formatPrice(tick.high_24h, symbol)}).`,
    )
  }
  return points
}

function signalSection(signals) {
  const points = []

  for (const [interval, signal] of [['1d', signals['1d']], ['1h', signals['1h']]]) {
    const frame = FRAME_NAME[interval]
    if (!signal) {
      points.push(`The ${frame} rating is not available right now.`)
      continue
    }
    if (signal.score == null) {
      points.push(`There are not enough ${frame} candles yet to rate it.`)
      continue
    }

    const sign = signal.score > 0 ? '+' : ''
    points.push(
      `On the ${frame} chart the rules rate it ${signal.rating} (score ${sign}${signal.score} on a `
      + `-100 to +100 scale): ${signal.votes.bullish} of 6 rules are bullish, `
      + `${signal.votes.bearish} bearish and ${signal.votes.neutral} neutral.`,
    )

    const drivers = signal.reasons
      .filter((reason) => reason.vote !== 0)
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 2)
      .map((reason) => reason.text)
    if (drivers.length) points.push(`Main ${frame} drivers: ${drivers.join('; ')}.`)
  }

  const daily = DIRECTION[signals['1d']?.rating]
  const hourly = DIRECTION[signals['1h']?.rating]
  if (daily !== undefined && hourly !== undefined) {
    if (daily === 0 && hourly === 0) points.push('Neither timeframe shows a clear direction.')
    else if (daily === 0 || hourly === 0) points.push('Only one of the two timeframes has a clear direction.')
    else if (daily === hourly) points.push('Both timeframes point the same way.')
    else points.push('The two timeframes disagree: the shorter-term move is running against the longer trend.')
  }
  return points
}

function riskSection(name, risk, peers) {
  if (!risk) return ['Risk figures are not available yet.']

  const rank = rankBy(peers, risk.symbol, 'annualized_volatility_pct')
  const recent = risk.recent_volatility_pct
  const points = [
    `Across ${risk.observations} daily closes since ${risk.start_date}, ${name}'s annualized volatility is `
    + `${percent(risk.annualized_volatility_pct)}`
    + (recent != null ? ` (${percent(recent)} over the last 30 days)` : '')
    + (rank ? `. That makes it ${describeRank(rank)}.` : '.'),
  ]

  if (recent != null && risk.annualized_volatility_pct > 0) {
    const ratio = recent / risk.annualized_volatility_pct
    if (ratio > 1.3) points.push('Recent volatility is well above its long-run level.')
    else if (ratio < 0.7) points.push('Recent volatility is well below its long-run level, so it has been calmer than usual.')
  }

  points.push(
    `Its deepest fall from a peak was ${percent(risk.max_drawdown_pct)} (the low came on ${risk.max_drawdown_date}). `
    + (risk.current_drawdown_pct === 0
      ? 'It is at a new high right now.'
      : `It is currently ${percent(Math.abs(risk.current_drawdown_pct))} below its highest close.`),
  )

  points.push(
    `On roughly 1 day in 20 it has lost ${percent(Math.abs(risk.var_95_pct), 2)} or more; on those days the average loss `
    + `was ${percent(Math.abs(risk.expected_shortfall_pct), 2)}. Its worst single day was `
    + `${percent(risk.worst_day_pct, 2)} on ${risk.worst_day_date}.`,
  )
  return points
}

function backtestSection(backtest) {
  if (!backtest) return ['The backtest is not available right now.']

  const { trades } = backtest
  const wins = trades.win_rate_pct != null ? ` (${trades.win_rate_pct}% of them winners)` : ''
  const beat = backtest.strategy_return_pct >= backtest.buy_hold_return_pct

  const points = [
    `Following these rules over the last ${backtest.period.candles} daily candles would have returned `
    + `${formatPercent(backtest.strategy_return_pct, 1)}, against ${formatPercent(backtest.buy_hold_return_pct, 1)} `
    + `for simply holding, across ${trades.count} trades${wins}.`,
    `The rules' worst decline was ${percent(backtest.strategy_max_drawdown_pct)} versus `
    + `${percent(backtest.buy_hold_max_drawdown_pct)} for holding. They ${beat ? 'beat' : 'trailed'} holding in this stretch of history.`,
  ]
  if (backtest.sample_warning) {
    points.push(`With only ${trades.count} trades this is too small a sample to conclude much.`)
  }
  return points
}

function cautions(name, risk, peers, signals, backtest) {
  const items = []

  const rank = risk ? rankBy(peers, risk.symbol, 'annualized_volatility_pct') : null
  if (rank && rank.of >= 4 && rank.rank <= 2) {
    items.push(`${name} is among the most volatile assets tracked, so even a small position can swing sharply.`)
  }

  for (const interval of ['1d', '1h']) {
    const score = signals[interval]?.score
    if (score != null && Math.abs(score) >= NEAR_THRESHOLD[0] && Math.abs(score) <= NEAR_THRESHOLD[1]) {
      items.push(`The ${FRAME_NAME[interval]} rating sits close to the Buy/Sell threshold, so a small price move could change it.`)
    }
  }

  if (backtest && backtest.strategy_return_pct < backtest.buy_hold_return_pct) {
    items.push('On this history the rules did worse than simply holding, so give their rating less weight.')
  }
  return items
}

/**
 * @param {object} input
 *   symbol, name   the asset
 *   tick           latest live tick, or undefined
 *   signals        { '1d': signal | null, '1h': signal | null }   from /api/signals
 *   risk           this asset's entry from /api/risk, or null
 *   peers          every asset's entry from /api/risk (for ranking)
 *   backtest       /api/backtest result for the daily timeframe, or null
 * @returns {{ headline: string, sections: {title: string, points: string[]}[], cautions: string[], note: string }}
 */
export function buildBrief({ symbol, name, tick, signals, risk, peers = [], backtest }) {
  const rating = signals['1d']?.score != null ? signals['1d'].rating : null
  const rank = risk ? rankBy(peers, risk.symbol, 'annualized_volatility_pct') : null
  // Top third of the assets by volatility is "high", bottom third "low", the rest "moderate".
  const position = rank && rank.of >= 3 ? (rank.rank - 1) / (rank.of - 1) : null
  const volatilityWord = position === null ? null : position <= 1 / 3 ? 'high' : position >= 2 / 3 ? 'low' : 'moderate'

  const headline = `${name}: ${rating ?? 'no daily rating yet'} on the daily chart`
    + (volatilityWord ? `, ${volatilityWord} volatility relative to the other assets` : '')

  return {
    headline,
    sections: [
      { title: 'Right now', points: nowSection(symbol, name, tick) },
      { title: 'Trend and momentum', points: signalSection(signals) },
      { title: 'Risk profile', points: riskSection(name, risk, peers) },
      { title: 'How the rules have worked here', points: backtestSection(backtest) },
    ],
    cautions: cautions(name, risk, peers, signals, backtest),
    note: 'This brief is produced by fixed rules from the data in this app. It is not AI, includes no news, '
      + 'and is educational, not investment advice.',
  }
}
