import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "finpulse.db"

sys.path.insert(0, str(ROOT))

from src.analytics.financial_metrics import (  # noqa: E402
    calculate_daily_returns,
    calculate_summary,
)


st.set_page_config(
    page_title="FinPulse | Financial Intelligence",
    page_icon="??",
    layout="wide",
)


@st.cache_data
def load_data():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT timestamp, symbol, asset_type, open, high,
                   low, close, volume
            FROM market_prices
            ORDER BY timestamp
            """,
            conn,
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


st.title("?? FinPulse")
st.subheader("Multi-Asset Financial Intelligence Platform")
st.caption(
    "Explore historical stock and cryptocurrency performance, "
    "returns, and risk metrics."
)

if not DB_PATH.exists():
    st.error(f"Database not found: {DB_PATH}")
    st.stop()

raw = load_data()

if raw.empty:
    st.warning("No market data found in the database.")
    st.stop()

asset_types = sorted(raw["asset_type"].unique().tolist())

st.sidebar.header("Dashboard Filters")

selected_types = st.sidebar.multiselect(
    "Asset classes",
    options=asset_types,
    default=asset_types,
)

filtered = raw[raw["asset_type"].isin(selected_types)].copy()

symbols = sorted(filtered["symbol"].unique().tolist())

selected_symbols = st.sidebar.multiselect(
    "Assets",
    options=symbols,
    default=symbols,
)

filtered = filtered[filtered["symbol"].isin(selected_symbols)].copy()

if filtered.empty:
    st.info("Select at least one asset to display analytics.")
    st.stop()

minimum_date = filtered["timestamp"].min().date()
maximum_date = filtered["timestamp"].max().date()

date_range = st.sidebar.date_input(
    "Date range",
    value=(minimum_date, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date,
)

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        (filtered["timestamp"].dt.date >= start_date)
        & (filtered["timestamp"].dt.date <= end_date)
    ]

if filtered.empty:
    st.warning("No observations exist for this date range.")
    st.stop()

# Calculate metrics using the full selected asset history before
# applying the display date filter, to preserve return continuity.
full_selected = raw[
    raw["symbol"].isin(selected_symbols)
    & raw["asset_type"].isin(selected_types)
].copy()

full_daily = calculate_daily_returns(full_selected)
summary = calculate_summary(full_daily)

# Restrict the displayed time series to the selected date range.
daily = calculate_daily_returns(filtered)

latest = (
    filtered.sort_values("timestamp")
    .groupby("symbol", as_index=False)
    .tail(1)
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Assets Selected", filtered["symbol"].nunique())
col2.metric("Price Records", f"{len(filtered):,}")
col3.metric(
    "Latest Observation",
    filtered["timestamp"].max().strftime("%d %b %Y"),
)
col4.metric(
    "Asset Classes",
    filtered["asset_type"].nunique(),
)

st.divider()

st.header("Market Overview")

left, right = st.columns(2)

with left:
    st.subheader("Latest Available Prices")
    st.dataframe(
        latest[
            ["symbol", "asset_type", "timestamp", "close", "volume"]
        ].sort_values("symbol"),
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.subheader("Historical Price Trends")
    price_fig = px.line(
        filtered,
        x="timestamp",
        y="close",
        color="symbol",
        title="Closing Prices",
        labels={
            "timestamp": "Date",
            "close": "Closing Price",
            "symbol": "Asset",
        },
    )
    st.plotly_chart(price_fig, use_container_width=True)

st.divider()

st.header("Performance Analysis")

performance_fig = px.line(
    daily,
    x="timestamp",
    y="growth_of_1",
    color="symbol",
    title="Growth of 1 Unit of Each Asset",
    labels={
        "timestamp": "Date",
        "growth_of_1": "Growth Index",
        "symbol": "Asset",
    },
)
performance_fig.add_hline(y=1, line_dash="dash")
st.plotly_chart(performance_fig, use_container_width=True)

st.caption(
    "Growth indices are normalized to each asset's first observed "
    "price in the selected date range. They do not include dividends, "
    "fees, taxes, or currency conversion."
)

st.header("Risk Analysis")

risk_left, risk_right = st.columns(2)

with risk_left:
    volatility_fig = px.bar(
        summary,
        x="symbol",
        y="annualized_volatility_pct",
        color="asset_type",
        title="Annualized Historical Volatility",
        labels={
            "symbol": "Asset",
            "annualized_volatility_pct": "Volatility (%)",
            "asset_type": "Asset Class",
        },
    )
    st.plotly_chart(volatility_fig, use_container_width=True)

with risk_right:
    drawdown_fig = px.bar(
        summary,
        x="symbol",
        y="max_drawdown_pct",
        color="asset_type",
        title="Historical Maximum Drawdown",
        labels={
            "symbol": "Asset",
            "max_drawdown_pct": "Maximum Drawdown (%)",
            "asset_type": "Asset Class",
        },
    )
    st.plotly_chart(drawdown_fig, use_container_width=True)

st.header("Financial Metrics Comparison")

display_columns = [
    "symbol",
    "asset_type",
    "observations",
    "start_date",
    "end_date",
    "total_return_pct",
    "annualized_volatility_pct",
    "sharpe_ratio_rf_zero",
    "max_drawdown_pct",
]

display_summary = summary[
    summary["symbol"].isin(selected_symbols)
    & summary["asset_type"].isin(selected_types)
][display_columns].copy()

st.dataframe(
    display_summary.round(3),
    use_container_width=True,
    hide_index=True,
)

csv = display_summary.to_csv(index=False).encode("utf-8")

st.download_button(
    "Download Financial Summary CSV",
    data=csv,
    file_name="finpulse_financial_summary.csv",
    mime="text/csv",
)

st.caption(
    "Historical analysis for research and educational purposes only. "
    "The Sharpe ratio assumes a zero risk-free rate. Historical "
    "performance does not predict future returns."
)
