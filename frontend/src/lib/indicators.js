// Technical indicators over an array of closing prices. Every function returns
// an array of the same length with `null` where the value is not yet defined,
// so results line up index-for-index with the candles.
//
// Conventions follow TradingView: EMA is seeded with the SMA of the first
// `period` values, RSI uses Wilder's smoothing, and Bollinger Bands use the
// population standard deviation.

export function sma(values, period) {
  const result = new Array(values.length).fill(null)
  let sum = 0

  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) result[i] = sum / period
  }
  return result
}

export function ema(values, period) {
  const result = new Array(values.length).fill(null)
  if (values.length < period) return result

  const k = 2 / (period + 1)
  let previous = values.slice(0, period).reduce((a, b) => a + b, 0) / period
  result[period - 1] = previous

  for (let i = period; i < values.length; i++) {
    previous = values[i] * k + previous * (1 - k)
    result[i] = previous
  }
  return result
}

export function bollinger(values, period = 20, multiplier = 2) {
  const middle = sma(values, period)
  const upper = new Array(values.length).fill(null)
  const lower = new Array(values.length).fill(null)

  for (let i = period - 1; i < values.length; i++) {
    let variance = 0
    for (let j = i - period + 1; j <= i; j++) {
      variance += (values[j] - middle[i]) ** 2
    }
    const deviation = Math.sqrt(variance / period)
    upper[i] = middle[i] + multiplier * deviation
    lower[i] = middle[i] - multiplier * deviation
  }
  return { upper, middle, lower }
}

export function rsi(values, period = 14) {
  const result = new Array(values.length).fill(null)
  if (values.length <= period) return result

  let gain = 0
  let loss = 0
  for (let i = 1; i <= period; i++) {
    const change = values[i] - values[i - 1]
    if (change >= 0) gain += change
    else loss -= change
  }
  let averageGain = gain / period
  let averageLoss = loss / period

  const toRsi = () => (averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss))
  result[period] = toRsi()

  for (let i = period + 1; i < values.length; i++) {
    const change = values[i] - values[i - 1]
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period
    result[i] = toRsi()
  }
  return result
}

export function macd(values, fast = 12, slow = 26, signalPeriod = 9) {
  const fastEma = ema(values, fast)
  const slowEma = ema(values, slow)
  const line = values.map((_, i) => (
    fastEma[i] == null || slowEma[i] == null ? null : fastEma[i] - slowEma[i]
  ))

  // The signal line is an EMA of the MACD line, starting where it is defined.
  const firstDefined = line.findIndex((value) => value != null)
  const signal = new Array(values.length).fill(null)
  if (firstDefined !== -1) {
    const smoothed = ema(line.slice(firstDefined), signalPeriod)
    smoothed.forEach((value, i) => {
      signal[firstDefined + i] = value
    })
  }

  const histogram = line.map((value, i) => (
    value == null || signal[i] == null ? null : value - signal[i]
  ))
  return { line, signal, histogram }
}
