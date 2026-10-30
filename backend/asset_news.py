"""The asset registry and per-asset news for the asset terminal page.

Each asset groups the instruments that price it (a live symbol, stored daily
history, an EIA series or an ECB pair) and says where its news comes from:

  * Yahoo Finance's headline feed for the asset (personal use), fetched at most
    every CACHE_SECONDS. Yahoo's per-symbol feeds include general market stories,
    so a headline is kept only if its title matches one of the asset's keywords;
  * the general news sources (backend/news.py) whose items are tagged with the
    asset, or for FX assets, central-bank releases on rates and FX.

NIFTY 50 and the rupee pairs have no news feed: the user chose not to pursue
Indian news. Nothing is summarised or rewritten; every item links to its original.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend import config, news

log = logging.getLogger("finpulse.asset_news")

router = APIRouter(tags=["asset"])

CACHE_SECONDS = 120
STALE_MAX_SECONDS = 6 * 3600
MAX_ITEMS = 40
YAHOO_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

_monotonic = time.monotonic
_wall = time.time


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    asset_class: str
    live: Optional[str] = None  # symbol on the price socket
    stored: Optional[str] = None  # symbol in market_prices
    eia: Optional[str] = None  # EIA spot series
    ecb: Optional[str] = None  # ECB reference pair on the FX page
    yahoo_news: tuple[str, ...] = ()  # Yahoo symbols whose headline feeds are used
    keywords: tuple[str, ...] = ()  # regexes a Yahoo headline must match
    news_tag: Optional[str] = None  # instrument tag in backend/news.py
    news_topics: tuple[str, ...] = ()  # general-news topics that count as this asset's
    note: str = ""

    @property
    def symbols(self) -> list[str]:
        return [s for s in (self.live, self.stored, self.eia, self.ecb) if s]


CRYPTO_NOTE = "Live from Binance spot; daily history stored from Binance."
FUTURES_NOTE = "Live price: a Binance perpetual futures contract in USDT, not an official spot or exchange price."
FX_NOTE = "Live quote from Yahoo Finance every 15 seconds; ECB reference rate once a day."
INDEX_NOTE = (
    "Live quote from Yahoo Finance every 15 seconds; Yahoo delays some exchanges by about 15 minutes (Hong Kong, "
    "mainland China, Singapore, Malaysia, the Sensex), shown as DELAYED. Charts from Yahoo."
)

ASSETS = [
    Asset("btc", "Bitcoin", "crypto", live="BTC/USDT", stored="BTC/USDT", yahoo_news=("BTC-USD",),
          keywords=(r"\bbitcoin\b", r"\bBTC\b"), news_tag="BTC/USDT", note=CRYPTO_NOTE),
    Asset("eth", "Ethereum", "crypto", live="ETH/USDT", stored="ETH/USDT", yahoo_news=("ETH-USD",),
          keywords=(r"\bethereum\b", r"\bether\b", r"\bETH\b"), news_tag="ETH/USDT", note=CRYPTO_NOTE),
    Asset("sol", "Solana", "crypto", live="SOL/USDT", yahoo_news=("SOL-USD",),
          keywords=(r"\bsolana\b", r"\bSOL\b"), news_tag="SOL/USDT", note="Live from Binance spot."),
    Asset("bnb", "BNB", "crypto", live="BNB/USDT", yahoo_news=("BNB-USD",),
          keywords=(r"\bBNB\b", r"\bbinance coin\b"), news_tag="BNB/USDT", note="Live from Binance spot."),
    Asset("xrp", "XRP", "crypto", live="XRP/USDT", yahoo_news=("XRP-USD",),
          keywords=(r"\bXRP\b", r"\bripple\b"), news_tag="XRP/USDT", note="Live from Binance spot."),
    Asset("aapl", "Apple Inc.", "stock", live="AAPL", stored="AAPL", yahoo_news=("AAPL",),
          keywords=(r"\bapple\b", r"\bAAPL\b", r"\biphone\b"), news_tag="AAPL",
          note="Live quote from Yahoo Finance every 15 seconds; daily history from Yahoo."),
    Asset("spx", "S&P 500", "index", live="^GSPC", stored="^GSPC", yahoo_news=("^GSPC",),
          keywords=(r"S&P", r"\bstocks?\b", r"\bwall street\b", r"\bdow\b", r"\bnasdaq\b", r"\bequit"),
          note="Live quote from Yahoo Finance every 15 seconds; daily history from Yahoo."),
    Asset("nifty", "NIFTY 50", "index", live="^NSEI", stored="^NSEI",
          note="Live quote from Yahoo Finance every 15 seconds; daily history from Yahoo. No news feed, by choice."),
    *[
        Asset(id_, name, "index", live=symbol, yahoo_news=(symbol,), keywords=keywords, note=INDEX_NOTE)
        for id_, name, symbol, keywords in (
            ("dji", "Dow Jones Industrial Average", "^DJI", (r"\bdow\b", r"\bblue[- ]chip")),
            ("ixic", "Nasdaq Composite", "^IXIC", (r"\bnasdaq\b", r"\btech stocks\b")),
            ("tsx", "S&P/TSX Composite", "^GSPTSE", (r"\bTSX\b", r"\bcanad", r"\btoronto\b")),
            ("bvsp", "Ibovespa", "^BVSP", (r"bovespa\b", r"\bbrazil")),
            ("ftse", "FTSE 100", "^FTSE", (r"\bFTSE\b", r"\bLondon stocks\b", r"\bU\.?K\.? stocks\b", r"\bBritish stocks\b")),
            ("dax", "DAX", "^GDAXI", (r"\bDAX\b", r"\bGerman", r"\bFrankfurt\b", r"\bEuropean (stocks|shares|equities|markets)\b")),
            ("cac", "CAC 40", "^FCHI", (r"\bCAC\b", r"\bFrench stocks\b", r"\bParis\b")),
            ("sx5e", "Euro Stoxx 50", "^STOXX50E", (r"\bstoxx\b", r"\bEuropean (stocks|shares|equities)\b")),
            ("n225", "Nikkei 225", "^N225", (r"\bnikkei\b", r"\bJapan", r"\btokyo\b", r"\btopix\b")),
            ("hsi", "Hang Seng", "^HSI", (r"\bhang seng\b", r"\bHong Kong\b")),
            ("sse", "Shanghai Composite", "000001.SS", (r"\bshanghai\b", r"\bChin(a|ese) (stocks|shares)\b")),
            ("kospi", "KOSPI", "^KS11", (r"\bkospi\b", r"\bKorea(n)? (stocks|shares)\b", r"\bseoul\b")),
            ("asx", "S&P/ASX 200", "^AXJO", (r"\bASX\b", r"\bAustralia", r"\bsydney\b")),
            ("rut", "Russell 2000", "^RUT", (r"\brussell\b", r"\bsmall[- ]caps?\b")),
            ("nya", "NYSE Composite", "^NYA", (r"\bNYSE\b", r"\bwall street\b", r"\bU\.?S\.? stocks\b")),
            ("vix", "Cboe Volatility Index (VIX)", "^VIX", (r"\bVIX\b", r"\bvolatility\b", r"\bfear (gauge|index)\b")),
            ("mxx", "S&P/BMV IPC", "^MXX", (r"\bmexic", r"\bIPC\b", r"\bpeso\b")),
            ("stoxx", "STOXX Europe 600", "^STOXX", (r"\bSTOXX\b", r"\bEuropean (stocks|shares|equities|markets)\b")),
            ("ibex", "IBEX 35", "^IBEX", (r"\bIBEX\b", r"\bspain\b", r"\bspanish\b", r"\bmadrid\b")),
            ("ftsemib", "FTSE MIB", "FTSEMIB.MI", (r"\bFTSE MIB\b", r"\bital", r"\bmilan\b")),
            ("aex", "AEX", "^AEX", (r"\bAEX\b", r"\bdutch\b", r"\bnetherlands\b", r"\bamsterdam\b")),
            ("smi", "SMI", "^SSMI", (r"\bSMI\b", r"\bswiss\b", r"\bswitzerland\b", r"\bzurich\b")),
            ("omx", "OMX Stockholm 30", "^OMX", (r"\bOMX\b", r"\bswed", r"\bstockholm\b", r"\bnordic\b")),
            ("szse", "Shenzhen Component", "399001.SZ", (r"\bshenzhen\b", r"\bChin(a|ese) (stocks|shares)\b")),
            ("twii", "Taiwan Weighted", "^TWII", (r"\btaiwan", r"\btaiex\b", r"\bTSMC\b")),
            ("sti", "Straits Times Index", "^STI", (r"\bstraits times\b", r"\bsingapore\b")),
            ("jkse", "Jakarta Composite", "^JKSE", (r"\bindonesia", r"\bjakarta\b")),
            ("klse", "FTSE Bursa Malaysia KLCI", "^KLSE", (r"\bmalaysia", r"\bbursa\b", r"\bKLCI\b")),
            ("nz50", "S&P/NZX 50", "^NZ50", (r"\bNZX\b", r"\bnew zealand\b")),
            ("ta125", "TA-125", "^TA125.TA", (r"\bTA-?125\b", r"\btel aviv\b", r"\bisrael")),
            ("tasi", "Tadawul All Share", "^TASI.SR", (r"\btadawul\b", r"\bsaudi\b")),
            ("jse40", "FTSE/JSE Top 40", "^J200.JO", (r"\bJSE\b", r"\bsouth africa", r"\bjohannesburg\b", r"\brand\b")),
        )
    ],
    Asset("sensex", "S&P BSE Sensex", "index", live="^BSESN",
          note=INDEX_NOTE + " No news feed, by choice."),
    Asset("niftybank", "Nifty Bank", "index", live="^NSEBANK",
          note=INDEX_NOTE + " No news feed, by choice."),
    Asset("gold", "Gold", "commodity", live="XAU/USDT", stored="GC=F", yahoo_news=("GC=F",),
          keywords=(r"\bgold\b", r"\bbullion\b", r"\bprecious metals?\b"),
          note=FUTURES_NOTE + " Daily history: COMEX futures from Yahoo."),
    Asset("silver", "Silver", "commodity", live="XAG/USDT", stored="SI=F", yahoo_news=("SI=F",),
          keywords=(r"\bsilver\b", r"\bprecious metals?\b"),
          note=FUTURES_NOTE + " Daily history: COMEX futures from Yahoo."),
    Asset("wti", "WTI crude oil", "commodity", live="CL/USDT", eia="RWTC", yahoo_news=("CL=F", "BZ=F"),
          keywords=(r"\boil\b", r"\bcrude\b", r"\bWTI\b", r"\bOPEC", r"\bbarrels?\b"),
          note=FUTURES_NOTE + " Reference: EIA weekly-released daily spot price."),
    Asset("brent", "Brent crude oil", "commodity", live="BZ/USDT", eia="RBRTE", yahoo_news=("BZ=F", "CL=F"),
          keywords=(r"\boil\b", r"\bcrude\b", r"\bbrent\b", r"\bOPEC", r"\bbarrels?\b"),
          note=FUTURES_NOTE + " Reference: EIA weekly-released daily spot price."),
    Asset("eurusd", "Euro / US dollar", "fx", live="EUR/USD", ecb="EUR/USD", yahoo_news=("EURUSD=X",),
          keywords=(r"\beuro\b", r"\bEUR", r"\bECB\b", r"\bdollar\b"), news_topics=("fx",), note=FX_NOTE),
    Asset("gbpusd", "British pound / US dollar", "fx", live="GBP/USD", ecb="GBP/USD", yahoo_news=("GBPUSD=X",),
          keywords=(r"\bpound\b", r"\bsterling\b", r"\bGBP", r"\bBank of England\b", r"\bdollar\b"),
          news_topics=("fx",), note=FX_NOTE),
    Asset("usdjpy", "US dollar / Japanese yen", "fx", live="USD/JPY", ecb="USD/JPY", yahoo_news=("JPY=X",),
          keywords=(r"\byen\b", r"\bJPY\b", r"\bBOJ\b", r"\bBank of Japan\b", r"\bdollar\b"),
          news_topics=("fx",), note=FX_NOTE),
    Asset("eurgbp", "Euro / British pound", "fx", live="EUR/GBP", ecb="EUR/GBP", yahoo_news=("EURGBP=X",),
          keywords=(r"\beuro\b", r"\bpound\b", r"\bsterling\b", r"\bECB\b"), news_topics=("fx",), note=FX_NOTE),
    Asset("eurjpy", "Euro / Japanese yen", "fx", live="EUR/JPY", ecb="EUR/JPY", yahoo_news=("EURJPY=X",),
          keywords=(r"\beuro\b", r"\byen\b", r"\bECB\b", r"\bBOJ\b"), news_topics=("fx",), note=FX_NOTE),
    Asset("usdinr", "US dollar / Indian rupee", "fx", live="USD/INR", ecb="USD/INR",
          note=FX_NOTE + " No news feed, by choice."),
    Asset("eurinr", "Euro / Indian rupee", "fx", live="EUR/INR", ecb="EUR/INR",
          note=FX_NOTE + " No news feed, by choice."),
]
BY_ID = {asset.id: asset for asset in ASSETS}
BY_SYMBOL = {symbol: asset for asset in ASSETS for symbol in asset.symbols}
_KEYWORDS = {asset.id: [re.compile(k, re.I) for k in asset.keywords] for asset in ASSETS}


def find(key: str) -> Optional[Asset]:
    """An asset by its id ("gold") or by any of its symbols ("GC=F", "XAU/USDT")."""
    return BY_ID.get(key.lower()) or BY_SYMBOL.get(key)


def relevant(asset: Asset, item: dict) -> bool:
    """The headline itself must name the asset: summaries mention too much in passing."""
    return any(pattern.search(item["title"]) for pattern in _KEYWORDS[asset.id])


@dataclass
class _Feed:
    items: list[dict]
    fetched_mono: float
    fetched_wall: float
    error: Optional[str] = None


_cache: dict[str, _Feed] = {}


def clear_cache() -> None:
    _cache.clear()


def _source(symbol: str) -> news.Source:
    return news.Source(
        id="yahoo", name="Yahoo Finance",
        url=YAHOO_FEED.format(symbol=quote(symbol, safe="")), kind="rss", topics=(),
        attribution="Yahoo Finance (personal use)",
        homepage=f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}",
    )


async def yahoo_feed(symbol: str) -> _Feed:
    """One Yahoo symbol's headlines (unfiltered), cached; a kept copy if Yahoo fails."""
    cached = _cache.get(symbol)
    if cached and cached.error is None and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return cached
    source = _source(symbol)
    try:
        response = await news.get_client().get(source.url, headers={"User-Agent": config.FEED_USER_AGENT})
        if response.status_code != 200:
            raise news.NewsError(f"Yahoo Finance answered {response.status_code}")
        if len(response.content) > news.MAX_BYTES:
            raise news.NewsError("Yahoo Finance sent too much data")
        items, _ = news.parse_rss(source, response.content)
    except (httpx.HTTPError, news.NewsError) as exc:
        message = str(exc) if isinstance(exc, news.NewsError) else f"Could not reach Yahoo Finance ({type(exc).__name__})"
        if cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving kept Yahoo headlines for %s: %s", symbol, message)
            return _Feed(cached.items, cached.fetched_mono, cached.fetched_wall, message)
        raise news.NewsError(message) from None
    feed = _Feed(items, _monotonic(), _wall())
    _cache[symbol] = feed
    return feed


def _when(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


async def asset_headlines(asset: Asset) -> dict:
    sources, items, seen = [], [], set()

    def add(item: dict, stale: bool) -> None:
        if item["url"] not in seen:
            seen.add(item["url"])
            items.append({**item, "stale": stale})

    if asset.yahoo_news:
        status = {"id": "yahoo", "name": "Yahoo Finance", "attribution": "Yahoo Finance (personal use)",
                  "homepage": _source(asset.yahoo_news[0]).homepage}
        results = await asyncio.gather(*(yahoo_feed(s) for s in asset.yahoo_news), return_exceptions=True)
        feeds = [r for r in results if isinstance(r, _Feed)]
        errors = [str(r) for r in results if isinstance(r, news.NewsError)]
        for result in results:
            if isinstance(result, Exception) and not isinstance(result, news.NewsError):
                raise result
        if not feeds:
            status.update(status="unavailable", error="; ".join(errors), count=0)
        else:
            before, dropped = len(items), 0
            for feed in feeds:
                for item in feed.items:
                    if relevant(asset, item):
                        add(item, bool(feed.error))  # the oil feeds overlap: add() drops repeats
                    else:
                        dropped += 1
            kept = len(items) - before
            error = "; ".join(errors + [f.error for f in feeds if f.error]) or None
            status.update(status="stale" if error else "ok", error=error, count=kept, filtered_out=dropped,
                          fetched_at=_when(min(f.fetched_wall for f in feeds)))
        sources.append(status)

    if asset.news_tag or asset.news_topics:
        general, statuses = await news.collect()
        for item in general:
            if asset.news_tag in item["instruments"] or set(asset.news_topics) & set(item["topics"]):
                add(item, item.get("stale", False))
        sources.extend(s for s in statuses if s["status"] != "not_configured")

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return {"items": items[:MAX_ITEMS], "total": len(items), "sources": sources}


def describe(asset: Asset) -> dict:
    return {
        "id": asset.id, "name": asset.name, "asset_class": asset.asset_class,
        "live": asset.live, "stored": asset.stored, "eia": asset.eia, "ecb": asset.ecb,
        "has_news": bool(asset.yahoo_news or asset.news_tag or asset.news_topics),
        "note": asset.note,
    }


@router.get("/api/asset-registry")
def registry():
    """Every asset the terminal page covers, with the instruments that price it."""
    return {"count": len(ASSETS), "assets": [describe(a) for a in ASSETS]}


@router.get("/api/asset-news")
async def asset_news(asset: str = Query(..., min_length=1, max_length=20)):
    """Recent headlines for one asset, newest first, each linking to the original."""
    found = find(asset)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset}")
    body = await asset_headlines(found) if (found.yahoo_news or found.news_tag or found.news_topics) else {
        "items": [], "total": 0, "sources": [],
    }
    return {
        "asset": describe(found),
        "count": len(body["items"]),
        **body,
        "refresh_seconds": CACHE_SECONDS,
        "policy": "Headlines and short snippets only, each linking to the original publication.",
    }
