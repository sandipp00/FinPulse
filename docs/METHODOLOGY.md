# Methodology

How FinPulse calculates every figure it shows. Everything here describes the past
data it is given. None of it predicts future prices, and none of it is investment
advice.

## Conventions

| Topic | Rule |
|---|---|
| Prices | Daily **closing** prices. Stocks and indices use Yahoo Finance's dividend- and split-adjusted closes. Crypto uses exchange closes at 00:00 UTC. |
| Dates | Every timestamp is UTC. A daily bar is labelled with its trading day. |
| Missing data | Never filled in. A day without a value is skipped or drawn as a gap. A measure that cannot be calculated is shown as "—" (`null` in the API), not as zero. |
| Fees, taxes, dividends | Not included, unless the price itself is adjusted (stock closes are). |
| Currency | No conversion. When two compared instruments are quoted in different currencies, the page says so. |
| Sample statistics | Standard deviation, variance and covariance use the sample formula (divide by *n − 1*). |
| Periods per year | **365** for crypto, which trades every day, and **252** for stocks and indices. When two series are compared, 365 is used only if **both** are crypto; otherwise their shared dates are weekdays, so 252. |

## Returns

| Measure | Formula | Notes |
|---|---|---|
| Simple return | r_t = P_t / P_{t−1} − 1 | Used for volatility, correlation and beta |
| Log return | l_t = ln(P_t / P_{t−1}) | Log returns add up over time: Σ l_t = ln(P_end / P_start) |
| Total return | P_end / P_start − 1 | |
| Annualized return (CAGR) | (P_end / P_start)^(365.25 / days) − 1 | Uses **calendar days**, so it means the same for a 7-day crypto series and a weekday stock series. Not given for spans under 30 days. |

## Risk

| Measure | Formula |
|---|---|
| Annualized volatility | sd(r) × √(periods per year) |
| Rolling volatility | The same, over each trailing window (20, 60 or 120 days). Undefined until the window is full. |
| Drawdown | P_t / max(P_0 … P_t) − 1: the fall from the running peak |
| Maximum drawdown | The lowest drawdown. FinPulse also reports the **peak** before it, the **trough**, the **recovery** date (the first close back at or above the peak, if any) and the **duration** from peak to recovery, or from peak to the latest date if it has not recovered. |
| Sharpe ratio | mean(r) / sd(r) × √(periods per year), with a risk-free rate of zero |
| Value at risk (1 day in 20) | The 5th percentile of daily returns, so a loss at least this large happened on 1 day in 20 |
| Expected shortfall | The average return on those worst 1-in-20 days |

## Comparing two assets

Two series are compared **only on the dates both have**, and returns are taken
between those shared dates. A stock and a coin are therefore both measured over
the same holding periods. A Monday stock return and a Monday coin return both
cover the weekend.

| Measure | Formula |
|---|---|
| Correlation | Pearson correlation of the two daily return series (−1 to 1) |
| R² | correlation² |
| Beta | cov(r_asset, r_benchmark) / var(r_benchmark) |
| Excess return | annualized return of the asset − annualized return of the benchmark, over the shared window |
| Tracking error | sd(r_asset − r_benchmark) × √(periods per year) |
| Information ratio | mean(r_asset − r_benchmark) × periods per year / tracking error |
| Rolling correlation | Correlation over each trailing window |

- **Too little data:** at least 30 shared dates are needed. With fewer, every relative measure is undefined.
- **Undefined beta:** beta is undefined when the benchmark did not move (zero variance).
- **No difference at all:** the information ratio is undefined when the tracking error is zero.

**Correlation is not causation.** A high correlation says two prices moved
together in the data. It does not say that one moved the other, or that they
will keep moving together.

## The instrument explorer's comparison chart

- **Rebasing:** both series are rebased to 100 on their first shared bar. Daily bars are matched by UTC calendar day, and intraday bars by exact time.
- **Window figures:** returns in the explorer's figures use the bars on screen.
- **Bar volatility:** the explorer's "bar volatility" is the sample standard deviation of bar-to-bar returns. It is **not** annualized.

## Signals and backtests

- **Signals:** six indicator rules vote on each **closed** candle (see the README). They use the same indicator conventions in Python and in the browser: the EMA is seeded with the simple average of its first *n* values, RSI uses Wilder's smoothing, and Bollinger Bands use the population standard deviation.
- **Backtests:** a backtest trades at the **next** candle's open after a signal and pays a fee on every fill. This means it never uses a price it could not have known.

## Where the code is

| What | File |
|---|---|
| Returns, CAGR, rolling measures, drawdown details, beta, tracking error | `src/analytics/quant.py` |
| Snapshot metrics (latest price, total return, volatility, Sharpe, max drawdown) | `src/analytics/financial_metrics.py` |
| Risk report (VaR, expected shortfall, correlation matrix) | `src/analytics/risk.py` |
| Relative statistics API | `backend/quant_api.py` (`GET /api/quant/relative`) |
| Indicators | `src/signals/indicators.py`, `frontend/src/lib/indicators.js` |

Each formula is checked in `tests/test_quant.py`, `tests/test_risk.py` and
`tests/test_financial_metrics.py`, against hand-calculated values and edge cases.
