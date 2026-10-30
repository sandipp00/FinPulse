"""The followed US stocks: one table (backend/stocks.py) drives quotes, charts, news and sectors."""
import os
import re

import pytest

from backend import asset_news, config, instruments, market_service
from backend.stocks import SECTORS, STOCK_SYMBOLS, US_STOCKS


@pytest.mark.skipif("YAHOO_LIVE_SYMBOLS" in os.environ, reason="the poller list is overridden in the environment")
def test_every_stock_is_polled_from_yahoo():
    assert set(STOCK_SYMBOLS) <= set(config.YAHOO_LIVE_SYMBOLS)


def test_the_table_is_well_formed():
    assert len(STOCK_SYMBOLS) == len(set(STOCK_SYMBOLS)) == 30
    for symbol, name, sector, keywords in US_STOCKS:
        assert sector in SECTORS, symbol
        assert name and keywords, symbol
        for pattern in keywords:
            re.compile(pattern)


def test_each_stock_is_an_asset_with_its_sector_news_and_currency():
    for symbol, name, sector, _ in US_STOCKS:
        asset = asset_news.find(symbol)
        assert asset is not None and asset.asset_class == "stock" and asset.live == symbol
        assert asset.sector == sector and asset.yahoo_news == (symbol,)
        assert asset_news.describe(asset)["sector"] == sector
        assert market_service.currency_of(symbol) == "USD"
    assert asset_news.find("brkb").live == "BRK-B"
    assert asset_news.find("AAPL").stored == "AAPL"  # the one stock with stored history
    assert asset_news.find("NVDA").stored is None


def test_headlines_must_name_the_company():
    nvda = asset_news.find("NVDA")
    assert asset_news.relevant(nvda, {"title": "Nvidia unveils new chips"})
    assert not asset_news.relevant(nvda, {"title": "Stocks rise as yields fall"})
    visa = asset_news.find("V")  # the ticker alone is not a keyword
    assert not asset_news.relevant(visa, {"title": "Sector V rotation continues"})


def test_stocks_chart_from_yahoo_at_every_interval(monkeypatch):
    monkeypatch.setattr(config, "YAHOO_LIVE_SYMBOLS", ["NVDA", "EUR/USD", "^N225"])
    assert instruments.yahoo_chart_symbols() == ["NVDA", "EUR/USD", "^N225"]
