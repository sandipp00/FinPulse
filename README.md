# FinPulse

[![CI](https://github.com/sandipp00/FinPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/sandipp00/FinPulse/actions/workflows/ci.yml)

FinPulse is a Python-based financial analytics platform for exploring stock market and cryptocurrency data, comparing historical performance, and evaluating investment risk.

## Features

- Historical market data ingestion for NIFTY 50, Apple, Bitcoin, and Ethereum
- SQLite database for unified market data storage
- Financial metrics including daily returns, cumulative growth, annualized volatility, Sharpe ratio, and maximum drawdown
- Interactive Streamlit dashboard with Plotly charts
- React frontend with interactive financial charts
- Live candlestick charts (1m / 15m / 1h / 1d) with volume, SMA, EMA, Bollinger Bands, RSI and MACD; the current candle updates in real time
- FastAPI backend for serving historical market data and financial metrics
- Live crypto prices streamed from Binance over WebSockets (ticker bar, live cards with sparklines, flashing price changes)
- Buy/sell signals from six transparent indicator rules (trend, MA cross, RSI, MACD, Bollinger, volume), each with a plain-language reason, plus a historical backtest vs buy-and-hold beside every rating
- Email-and-password accounts (scrypt hashing, httpOnly session cookies) with optional email verification and emailed password reset, so every person gets their own paper account
- Paper trading with a virtual $100k account: market orders at live Binance prices (0.1% fee, long-only), holdings with live P&L, equity curve, order history, and a one-click "follow the signal" mode
- Asset-class and date-range filters
- CSV export of financial summaries
- Automated tests using pytest

## Technology Stack

Python · Pandas · NumPy · SQLite · SQLAlchemy · yfinance · CCXT · FastAPI · React · Vite · Tailwind CSS · Recharts · Plotly · Streamlit · scikit-learn · pytest

## Project Structure

```text
FinPulse/
├── backend/
│   ├── __init__.py
│   └── main.py
├── dashboard/
│   └── app.py
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── src/
│   ├── analytics/
│   └── data/
├── tests/
├── requirements.txt
├── .gitignore
└── README.md
```

## Run with Docker

The quickest way to run everything (free, no accounts needed):

```bash
docker compose up -d --build     # then open http://localhost:8080
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for HTTPS, free hosting options, backups and account administration.

## Setup (development)

### 1. Python Environment

Create and activate a Python virtual environment, then install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Prepare Market Data

Collect historical data using the data ingestion scripts and build the SQLite database using:

```bash
python src/data/build_database.py
```

### 3. Configure (optional)

Copy `.env.example` to `.env` (backend) and `frontend/.env.example` to `frontend/.env.local` to change the API URL, CORS origins, live symbols, or Binance endpoints. Defaults work for local development.

### 4. Start the FastAPI Backend

From the project root:

```bash
python -m uvicorn backend.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. On startup it connects to Binance's public streams (no API key) and exposes live prices at `ws://127.0.0.1:8000/ws/prices`, `GET /api/live/status` and `GET /api/live/ticks`. Closed 1-minute candles are stored in the `live_candles` table, and `GET /api/candles?symbol=BTC/USDT&interval=1h&limit=500` returns OHLCV history from Binance (intervals: `1m`, `15m`, `1h`, `1d`). `GET /api/signals?interval=1d[&symbol=BTC/USDT]` returns the ratings and reasons, and `GET /api/backtest?symbol=BTC/USDT&interval=1d&fee_pct=0.1` returns the backtest. Set `LIVE_FEED_ENABLED=false` to turn the feed off.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### 5. Start the React Frontend

Open a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The dev server forwards `/api` and `/ws` to the backend on port 8000, so the browser only ever sees one origin (this is what lets the login cookie work).

## Dashboard Preview

![FinPulse Dashboard](docs/finpulse-dashboard.png)

FinPulse displays historical market prices, asset performance, volatility, and maximum drawdown using locally stored market data.

### 6. Start the Streamlit Dashboard

From the project root:

```bash
python -m streamlit run dashboard/app.py
```

## Testing

Run the automated Python tests (the minimal dependencies for this are in `requirements-dev.txt`):

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Run the frontend unit tests (indicator math, live-candle logic, portfolio valuation, email-link parsing):

```bash
cd frontend
npm test
```

## Market data and freshness

Every number the API serves says where it came from and how fresh it is (models in `backend/schemas/market.py`):

- `GET /api/market/quotes` returns one normalized record per instrument: symbol, asset class, price, quote currency (crypto pairs are priced in USDT, not USD), unit, provider, provider timestamp, retrieval time, interval and a status. The status is `real_time` for a recent exchange tick, `stale` when the tick is older than 30 seconds or the feed is down, `historical` for a stored daily close, `cached` for a kept response, and `unavailable` when there is nothing. A currency that is not known is `null`, never guessed.
- `GET /api/candles` adds a `meta` object: provider, the endpoint that answered, retrieval time, the newest bar's time and the cache age.

- `GET /api/instruments` lists every instrument that can be charted: its asset class, quote currency, unit, whether it is live, the intervals it offers, and its stored coverage (bars, first and last date).
- `GET /api/instruments/history?symbol=AAPL&interval=1d&limit=500` returns OHLCV bars for any of them in one format, with `meta`. Live crypto comes from Binance (`1m`, `15m`, `1h`, `1d`; 50-1000 bars). Stored instruments are daily only (up to 5000 bars). Add `source=database` to get a live coin's stored history instead. If Binance fails on a daily request and stored bars exist, those are returned, `source` says `database`, and a note in `meta.notes` explains why.

In the explorer, a comparison keeps only the dates both instruments share (daily bars are matched by UTC day), and rebases both to 100. Prices are not converted between currencies, and the page says so when they differ.

### FX rates (ECB via Frankfurter)

- **Source:** euro foreign exchange reference rates from the European Central Bank, fetched through the free, open-source [Frankfurter](https://frankfurter.dev/) API (`providers=ecb`). No key is needed. `FX_BASE_URL` can point at a self-hosted Frankfurter.
- **Freshness:** the ECB publishes them around 16:00 CET on TARGET working days, "for information purposes only". They are labelled `HIST` with their date, never as live. Weekends and holidays have no rate, and none is filled in.
- **Derived pairs:** the ECB publishes only rates against the euro. GBP/USD, USD/JPY and USD/INR are cross rates that FinPulse calculates from the same day's two euro rates (for example USD/INR = EUR/INR ÷ EUR/USD). The ECB's reuse terms require changes to be stated, so these pairs are marked *Derived cross*, and their `method` field says how they were calculated.
- **Endpoints:** `GET /api/fx/pairs` returns each pair's latest and previous rate, the change, whether it is derived, and source metadata. `GET /api/fx/history?pair=USD/INR` returns ten years of daily rates.
- **Requests, caching and failures:** one request fetches every currency for the whole window. It is cached for an hour. When the source fails, the last response is served for up to three days, labelled `cached`. A 429 is honoured using its `Retry-After`.
- Frankfurter's default "blended" rate is its own mix of many providers and can differ from the ECB's (on 29 Oct 2026, EUR/USD was 1.1158 blended against 1.1130 from the ECB). FinPulse asks for the ECB's rate so that the source is a single, citable one.

### News

`GET /api/news` merges five sources, newest first, and `/news` shows them with filters for topic, instrument and source.

| Source | Feed | Terms |
|---|---|---|
| Federal Reserve | Monetary-policy press releases (RSS) | Public domain; cite the Board |
| European Central Bank | Press releases and speeches (RSS) | Reuse allowed with "Source: ECB" |
| U.S. Bureau of Economic Analysis | News releases (RSS) | US government, public domain |
| CoinDesk | All news (RSS) | Personal, informational, non-commercial use |
| SEC EDGAR | Apple's 8-K, 10-Q and 10-K filings (JSON) | Public. EDGAR requires a name and contact email in the User-Agent, so set `SEC_USER_AGENT` (for example `FinPulse/1.0 you@example.com`). Without it, filings are left out and EDGAR is not contacted |

- **What is stored:** only the headline, a short plain-text snippet, the link, the source and the publication time (UTC). Never full article text. Items are kept in memory for 15 minutes and not stored in the database.
- **Dropped items:** items without a title, an absolute `http(s)` link, or a publication time that includes a time zone are dropped and counted.
- **Coin and stock tags:** items are tagged by keyword. Tickers match only as whole uppercase words, so "SOL" is tagged but "solid" is not.
- **Failures:** a failing source is reported on its own, and its last items are kept for up to a day, labelled stale.
- **Rejected sources:** Cointelegraph was considered but left out, because its terms prohibit automated content pipelines. Reuters ended its RSS feeds in 2020. NewsAPI's free plan is delayed 24 hours and limited to development use.

### Economic calendar

`GET /api/calendar?days_back=14&days_ahead=60` lists, by date:

- **Release dates** for CPI and the Employment Situation (BLS), and GDP and Personal Income and Outlays (BEA), from FRED's release calendar (`include_release_dates_with_no_data=true` returns future dates). Uses `FRED_API_KEY`.
- **Release times** for the BEA's releases, from its `release_dates.json`. BLS releases show the date only: BLS's machine-readable schedule refuses clients without a contact address, and FinPulse does not guess a time.
- **FOMC and ECB policy meetings,** from a small list copied from the [Fed](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) and [ECB](https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html) calendars (checked 2026-10-30). Future FOMC dates are marked tentative until confirmed, as the Fed says.
- **No consensus forecasts.** No free, legitimate source publishes them, so the field is always empty. Released values are on the Macro page.

### Refreshing stock and index history

`python src/data/update_equities.py` brings AAPL, the NIFTY 50 (`^NSEI`) and the S&P 500 (`^GSPC`) up to date from Yahoo Finance (via yfinance). Yahoo data is for personal use, and FinPulse is run as a personal terminal.

- **Dry run by default:** it prints what it would add, per symbol, and writes nothing. Add `--apply` to write.
- **Backup first:** with `--apply`, the database is copied to `data/backups/` (git-ignored) with SQLite's backup API, and the copy is checked row by row and with an integrity check before anything is written.
- **Append-only:** only days after a symbol's newest stored bar are inserted, with `INSERT OR IGNORE`, so existing rows are not changed. A new symbol is downloaded from 2023-01-01.
- **Only finished days:** bars dated today (UTC) or later are ignored, since the session may still be running.
- **Adjustment check:** Yahoo's prices are dividend- and split-adjusted, and recalculated after each one. The script re-downloads the last ten days already stored and compares them. If they no longer match, that symbol is skipped and reported, rather than mixing two adjustment bases in one series.
- **`--replace-newest SYMBOL`:** the one exception to append-only. It replaces that symbol's newest stored bar with Yahoo's final values, but only when that bar is the sole mismatch and at least three older days match exactly. That is the signature of a bar saved before its session closed. The old and new values are printed.

### Crude oil (EIA)

- **Source:** WTI at Cushing, OK (`RWTC`) and Brent, Europe (`RBRTE`) daily spot prices, in US dollars per barrel, from the U.S. Energy Information Administration's API v2 (`petroleum/pri/spt`).
- **Setup:** get a free key at https://www.eia.gov/opendata/register.php and set `EIA_API_KEY` in `.env`. Without it, `/api/commodities` answers `"configured": false` and nothing is sent to EIA.
- **Freshness:** EIA releases these daily prices once a week, so the newest value can be several days old. Each price carries its date, labelled `HIST`, never as live.
- **Terms:** EIA data is in the public domain. EIA asks for the citation "Source: U.S. Energy Information Administration (date)", which the page shows.
- **Endpoints:** `GET /api/commodities` returns the latest and previous price, the change, units and source metadata. `GET /api/commodities/history?series=RWTC` returns ten years of daily prices, with missing values as `null`.
- **Requests, caching and failures:**
  - **Paging:** one request asks for both series, paging through EIA's 5,000-row limit (at most four pages).
  - **Caching:** responses are cached for an hour. When EIA fails, the last response is kept for up to three days, labelled `cached`.
  - **Rate limits:** after a 429, FinPulse waits 60 seconds before asking again.
- **The key:** it goes in the URL, as with FRED, so it is kept out of logs and error messages, and tests check this.
- **Not covered:** gold and silver are not included yet. FRED dropped its gold and silver series in 2022, and no source with verified display terms has been chosen.

### US macro (FRED)

Eight series from FRED: CPI (`CPIAUCSL`), core PCE prices (`PCEPILFE`), the effective Fed funds rate (`FEDFUNDS`), 2- and 10-year Treasury yields (`DGS2`, `DGS10`), real GDP (`GDPC1`), the unemployment rate (`UNRATE`) and nonfarm payrolls (`PAYEMS`).

- **Setup:** get a free key at https://fred.stlouisfed.org/docs/api/api_key.html and set `FRED_API_KEY` in `.env`. Without a key, `/api/macro/series` answers `"configured": false` and FinPulse sends nothing to FRED.
- **Endpoints:** `GET /api/macro/series` returns each series' latest and previous values, the change between them, units, frequency, FRED's `last_updated` and source metadata. `GET /api/macro/series/{id}` returns the last ten years of observations.
- **Missing values:** FRED's non-numeric values (such as `.`) are returned as `null`, counted, and drawn as gaps.
- **Allowed series:** only the series listed above can be requested, so the API is not an open proxy to FRED.
- **Caching and limits:** responses are cached for an hour. FRED allows 120 requests a minute; after a 429, FinPulse waits 60 seconds before asking again, and the API answers 503 with `Retry-After`. When FRED fails, the last response is served for up to a day, labelled `cached`.
- **The key:** it stays on the server. FRED takes it as a URL parameter, so httpx's request logging is held at WARNING, and error messages are built without the request URL. Tests check that the key never appears in logs or API responses.
- **Required notice:** This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. The Macro and Help pages show it, with a link to the [FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html).

How failures are handled when fetching Binance candles:

- **Malformed responses** (not a list, missing or non-numeric fields, NaN, negative prices, open/close outside the low-high range, out-of-order bars) are rejected, and the next endpoint in `BINANCE_REST_URLS` is tried.
- **Timeouts**: requests time out after 10 seconds.
- **Rate limits**: an endpoint that answers 429 or 418 is not asked again until its `Retry-After` has passed (60 seconds if the header is missing, at most 10 minutes). If every endpoint is rate limited, the API answers 503 with `Retry-After`; other failures are 502.
- **Caching**: responses are cached for 5 seconds. When every endpoint fails, the chart is served the last good response for up to 5 minutes, labelled `cached` with its age, and the page shows a banner. Signals and backtests never use a cached response.
- **Live feed**: one malformed live-feed message is dropped and counted (`rejected_messages` in `/api/live/status`) instead of dropping the connection.

## Paper trading

Orders fill server-side at the live Binance price (the client never supplies a price), with a flat fee (`PAPER_FEE_PCT`, default 0.1%) and no slippage, leverage or shorting. A stale or missing price rejects the order. State lives in four SQLite tables (`paper_account`, `paper_positions`, `paper_orders`, `paper_equity`) in `data/finpulse.db`.

Endpoints: `GET /api/paper/portfolio`, `GET /api/paper/orders`, `GET /api/paper/equity`, `POST /api/paper/orders` (size with exactly one of `quantity`, `notional_usd` or `percent`), `POST /api/paper/follow` and `POST /api/paper/reset`. "Follow the signal" mirrors the backtest policy: buy on a Buy rating when flat, sell everything on a Sell rating, otherwise do nothing. Every route requires a signed-in user and works on that user's own account.

## Pages

Everything below the sidebar is a real page with its own URL, so Back, Forward and direct links work:

| Page | URL | What is on it |
|---|---|---|
| Overview | `/` | Headline numbers, live crypto cards, asset mix, quick links |
| Equities | `/equities` | Stocks and indices with their stored daily history and how far it reaches |
| Crypto | `/crypto` | Live-streamed coins and stored crypto history, with data coverage |
| Instrument explorer | `/explorer?symbol=AAPL` | Search any supported instrument; candles with volume, interval and bar-count choices, return figures, and a comparison rebased to 100. The selection is kept in the URL so a view can be shared |
| FX rates | `/fx` | ECB euro reference rates (EUR/USD, EUR/GBP, EUR/JPY, EUR/INR) and cross rates derived from them (GBP/USD, USD/JPY, USD/INR), with a chart per pair. Daily, not live; no key needed |
| Commodities | `/commodities` | WTI and Brent crude oil spot prices from the EIA, with a chart per series. Needs a free `EIA_API_KEY` |
| News | `/news` | Headlines from the Fed, ECB, BEA, CoinDesk and SEC filings, filterable by topic, instrument and source, each linking to the original |
| Economic calendar | `/calendar` | Upcoming CPI, jobs, GDP and PCE releases and Fed and ECB policy meetings |
| US macro | `/macro` | Inflation, the Fed funds rate, Treasury yields, GDP and jobs from FRED, with a chart per series. Needs a free `FRED_API_KEY` |
| Markets | `/markets` | Live candlestick chart with indicators, stored price history, searchable watchlist |
| Portfolio | `/portfolio` | Paper trading: order ticket, holdings, equity curve, history |
| Analytics | `/analytics` | Buy/sell signals with backtests, and a side-by-side historical comparison |
| Research | `/research` | A plain-language brief per asset, written by fixed rules from live price, signals, risk figures and the backtest. It is not AI. |
| Risk Monitor | `/risk` | Volatility, drawdown, 1-in-20-day loss and a correlation heatmap for every asset, plus the concentration and estimated volatility of your own paper portfolio |
| Settings | `/settings` | Your account, a password-reset email, and live connection health |
| Help & support | `/help` | What each page does, a glossary, and where the data comes from |

FX, Commodities, Macro and News appear in the sidebar marked *Planned*. They are not links yet, because no data source for them is connected.

### Terminal layout

Every page shares one shell:

- **Top bar:** page title, search (Ctrl/⌘K), notification bell, account, and two status lights: whether the API answers (`/api/health`) and whether the exchange feed is connected.
- **Ticker:** live crypto from the feed, then the latest stored close for stocks and indices, tagged `HIST` with its date.
- **Right panel:** a compact watchlist plus details of the selected instrument (its source, when it was received or stored, 24h range or historical metrics). Below 1400px wide it moves under the page content.
- **Status bar:** API health and stored-bar count, feed state and time since the last tick, how old the stored history is, and local/UTC time.

Every price carries a freshness tag: `LIVE` for a recent tick while the feed is connected, `STALE` when a live symbol has had no tick for 30 seconds or the feed is down, `HIST` for a stored daily close, and `N/A` when nothing is available. Nothing is filled in when a source fails.

The risk figures come from `GET /api/risk` (about three years of daily Binance candles for the live crypto, stored history for stocks and indices; cached for a minute).

## Notifications and shortcuts

- **Bell:** the top-bar bell shows an unread count and opens a panel with two tabs. *Activity* lists what happened; *Price alerts* lets you set "tell me when BTC rises to or above $X" (or falls to or below). An alert fires once, when the live price reaches it, and a pop-up appears so you notice even with the bell closed. The bell also announces when an asset's **daily buy/sell rating changes**. An alert that is already true is refused, since it would fire instantly.
- **Saved in your browser only** (localStorage), not on the server and not synced between devices. Alerts are checked while FinPulse is open in a tab; they cannot reach you when it is closed.
- **Search shortcut:** press **Ctrl+K** (**⌘K** on a Mac) anywhere to jump to the search box. **Esc** clears the search, and a second press leaves the box. Typing a search opens the Markets page filtered to your match.

## Accounts

Sign-in and sign-up have their own pages at `/signin` and `/signup` (linked from the top bar and the paper-trading section); the rest of the dashboard is open to everyone. Sign up with an email and password (8-128 characters). Passwords are hashed with scrypt; the browser keeps only a random session token in an httpOnly, SameSite=Lax cookie, and the server stores just a hash of it. Login and registration are rate limited, and state-changing requests from other websites are rejected. Email is optional and free to set up with any SMTP account (see the deployment guide). With it configured, new accounts must confirm their address before paper trading, and anyone can reset a forgotten password from a one-time emailed link; without it, accounts work immediately and the person running the server handles resets with `python -m backend.admin`.

Login failures are counted per email *and* IP address, so a stranger guessing your address cannot lock you out. Guessing spread across many addresses hits a higher per-email ceiling, and while it is active only networks you have signed in from before are let through.

## How the signals work

Six rules vote bullish (+1), bearish (-1) or neutral (0) on each *closed* candle: price vs the 50-candle average, 20/50 average cross, RSI (oversold/overbought), MACD histogram, Bollinger Bands, and volume spikes. The weighted average of the votes is a score from -100 to +100: at least +20 is a Buy, at least +50 a Strong Buy, and the same on the negative side for Sell. There is no fitted model, so every rating can be re-checked on the chart.

The backtest is long-only: it buys at the *next* candle's open after a Buy rating, sells at the next open after a Sell rating, and pays a fee on each fill (default 0.1%). Results are mixed by design of the rules: on some coins and timeframes the strategy beats buy-and-hold and on others it does not, and shorter timeframes mostly lose to fees. Treat the signals as a way to organize indicator readings, not as advice.

## Limitations

Market data availability depends on external providers. Historical metrics exclude applicable trading fees, taxes, and dividends unless explicitly incorporated. Historical performance does not predict future results.

**Disclaimer:** This project is for educational and research purposes only. It is not investment advice.

## Continuous integration

Every push to `main` and every pull request runs [GitHub Actions](.github/workflows/ci.yml): the Python tests, the frontend lint, tests and build, and a Docker job that builds both images, starts the stack and smoke-tests it (health, security headers, login required, cross-site requests refused).

[Dependabot](.github/dependabot.yml) opens a monthly pull request when a Python or npm dependency, a GitHub Action or a Docker base image has a newer release, grouping routine updates into one PR per ecosystem. Each of those PRs runs the same CI, so a bad upgrade shows up as a failing check before it is merged.
