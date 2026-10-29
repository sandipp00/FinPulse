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
