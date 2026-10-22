# FinPulse

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

## Setup

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

Open `http://localhost:5173` in your browser.

## Dashboard Preview

![FinPulse Dashboard](docs/finpulse-dashboard.png)

FinPulse displays historical market prices, asset performance, volatility, and maximum drawdown using locally stored market data.

### 6. Start the Streamlit Dashboard

From the project root:

```bash
python -m streamlit run dashboard/app.py
```

## Testing

Run the automated Python tests:

```bash
python -m pytest -v
```

Run the frontend unit tests (indicator math and live-candle logic):

```bash
cd frontend
npm test
```

## How the signals work

Six rules vote bullish (+1), bearish (-1) or neutral (0) on each *closed* candle: price vs the 50-candle average, 20/50 average cross, RSI (oversold/overbought), MACD histogram, Bollinger Bands, and volume spikes. The weighted average of the votes is a score from -100 to +100: at least +20 is a Buy, at least +50 a Strong Buy, and the same on the negative side for Sell. There is no fitted model, so every rating can be re-checked on the chart.

The backtest is long-only: it buys at the *next* candle's open after a Buy rating, sells at the next open after a Sell rating, and pays a fee on each fill (default 0.1%). Results are mixed by design of the rules: on some coins and timeframes the strategy beats buy-and-hold and on others it does not, and shorter timeframes mostly lose to fees. Treat the signals as a way to organize indicator readings, not as advice.

## Limitations

Market data availability depends on external providers. Historical metrics exclude applicable trading fees, taxes, and dividends unless explicitly incorporated. Historical performance does not predict future results.

**Disclaimer:** This project is for educational and research purposes only. It is not investment advice.