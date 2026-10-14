# FinPulse

FinPulse is a Python-based financial analytics platform for exploring stock market and cryptocurrency data, comparing historical performance, and evaluating investment risk.

## Features

- Historical market data ingestion for NIFTY 50, Apple, Bitcoin, and Ethereum
- SQLite database for unified market data storage
- Financial metrics including daily returns, cumulative growth, annualized volatility, Sharpe ratio, and maximum drawdown
- Interactive Streamlit dashboard with Plotly charts
- React frontend with interactive financial charts
- FastAPI backend for serving historical market data and financial metrics
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

### 3. Start the FastAPI Backend

From the project root:

```bash
python -m uvicorn backend.main:app --reload
```

The API runs at `http://127.0.0.1:8000`.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### 4. Start the React Frontend

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

### 5. Start the Streamlit Dashboard

From the project root:

```bash
python -m streamlit run dashboard/app.py
```

## Testing

Run the automated Python tests:

```bash
python -m pytest -v
```

## Limitations

Market data availability depends on external providers. Historical metrics exclude applicable trading fees, taxes, and dividends unless explicitly incorporated. Historical performance does not predict future results.

**Disclaimer:** This project is for educational and research purposes only. It is not investment advice.