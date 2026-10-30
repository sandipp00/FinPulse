"""Source-linked news: official press releases, crypto news and SEC filings.

Every item carries its source, a link to the original and its publication time.
FinPulse keeps only the headline, a short plain-text snippet, the link, the
source and the time: never full article text. Items without a usable title,
link or publication time are dropped (and counted), not filled in.

Sources and their terms (checked 2026-10-30):
  * Federal Reserve press releases (RSS): public domain; cite the Board.
  * ECB press releases (RSS): reuse allowed if accurate and the ECB is cited.
  * BEA news releases (RSS): US government, public domain.
  * CoinDesk (RSS): content for personal, informational, non-commercial use.
  * SEC EDGAR (JSON): public; clients must identify themselves (SEC_USER_AGENT)
    and stay under 10 requests a second (FinPulse makes one per refresh).

Each source is fetched at most every CACHE_SECONDS and kept, labelled stale, for
up to STALE_MAX_SECONDS when it fails. Nothing is stored in the database.
"""
import asyncio
import hashlib
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from backend import config

log = logging.getLogger("finpulse.news")

CACHE_SECONDS = 15 * 60
STALE_MAX_SECONDS = 24 * 3600
REQUEST_TIMEOUT_SECONDS = 20
MAX_BYTES = 3_000_000
SNIPPET_CHARS = 280
EDGAR_ITEMS = 20
EDGAR_FORMS = ("8-K", "10-Q", "10-K")

_monotonic = time.monotonic
_wall = time.time


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    kind: str  # "rss" or "edgar"
    topics: tuple[str, ...]
    attribution: str
    homepage: str
    instruments: tuple[str, ...] = ()


SOURCES = (
    Source("fed", "Federal Reserve", "https://www.federalreserve.gov/feeds/press_monetary.xml", "rss",
           ("rates", "macro"), "Board of Governors of the Federal Reserve System",
           "https://www.federalreserve.gov/newsevents/pressreleases.htm"),
    Source("ecb", "European Central Bank", "https://www.ecb.europa.eu/rss/press.html", "rss",
           ("rates", "fx"), "Source: ECB", "https://www.ecb.europa.eu/press/html/index.en.html"),
    Source("bea", "U.S. Bureau of Economic Analysis", "https://apps.bea.gov/rss/rss.xml", "rss",
           ("macro",), "U.S. Bureau of Economic Analysis", "https://www.bea.gov/news/current-releases"),
    Source("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "rss",
           ("crypto",), "CoinDesk (personal, non-commercial use)", "https://www.coindesk.com/"),
    Source("sec", "SEC EDGAR", "https://data.sec.gov/submissions/CIK0000320193.json", "edgar",
           ("filings", "equities"), "U.S. Securities and Exchange Commission (EDGAR)",
           "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193", ("AAPL",)),
)

TOPICS = ("rates", "macro", "fx", "crypto", "filings", "equities")

# Instrument tags by keyword. Tickers match case-sensitively as whole words, so
# "SOL" is tagged but "solid" or "sol" in a sentence are not; names are case-insensitive.
INSTRUMENT_PATTERNS = {
    "BTC/USDT": [(r"\bBTC\b", 0), (r"\bbitcoin\b", re.I)],
    "ETH/USDT": [(r"\bETH\b", 0), (r"\bethereum\b", re.I), (r"\bether\b", re.I)],
    "SOL/USDT": [(r"\bSOL\b", 0), (r"\bsolana\b", re.I)],
    "BNB/USDT": [(r"\bBNB\b", 0), (r"\bbinance coin\b", re.I)],
    "XRP/USDT": [(r"\bXRP\b", 0), (r"\bripple\b", re.I)],
    "TRX/USDT": [(r"\bTRON\b", 0), (r"\bTRX\b", 0), (r"\bJustin Sun\b", 0)],
    "HYPE/USDT": [(r"\bhyperliquid\b", re.I), (r"\bHYPE\b", 0)],
    "ZEC/USDT": [(r"\bzcash\b", re.I), (r"\bZEC\b", 0)],
    "DOGE/USDT": [(r"\bdogecoin\b", re.I), (r"\bDOGE\b", 0)],
    "LINK/USDT": [(r"\bchainlink\b", re.I), (r"\bLINK\b", 0)],
    "ADA/USDT": [(r"\bcardano\b", re.I), (r"\bADA\b", 0)],
    "XLM/USDT": [(r"\bXLM\b", 0), (r"\bStellar (Lumens|network|Development)\b", 0)],
    "NEAR/USDT": [(r"\bNEAR\b", 0), (r"\bnear protocol\b", re.I)],
    "BCH/USDT": [(r"\bbitcoin cash\b", re.I), (r"\bBCH\b", 0)],
    "LTC/USDT": [(r"\blitecoin\b", re.I), (r"\bLTC\b", 0)],
    "UNI/USDT": [(r"\buniswap\b", re.I), (r"\bUNI\b", 0)],
    "AVAX/USDT": [(r"\bavalanche\b", re.I), (r"\bAVAX\b", 0)],
    "SUI/USDT": [(r"\bSui\b", 0), (r"\bSUI\b", 0)],
    "GRAM/USDT": [(r"\bGRAM\b", 0), (r"\btoncoin\b", re.I), (r"\bTON\b", 0)],
    "HBAR/USDT": [(r"\bhedera\b", re.I), (r"\bHBAR\b", 0)],
    "AAPL": [(r"\bAAPL\b", 0), (r"\bApple\b", 0), (r"\biPhone\b", 0)],
}
_COMPILED = {sym: [re.compile(p, f) for p, f in pats] for sym, pats in INSTRUMENT_PATTERNS.items()}


class NewsError(Exception):
    pass


class NotConfigured(Exception):
    pass


@dataclass
class SourceState:
    items: list[dict]
    dropped: int
    fetched_mono: float
    fetched_wall: float
    error: Optional[str] = None


_cache: dict[str, SourceState] = {}
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True, max_redirects=3)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


# ---- text helpers ---------------------------------------------------------------

def plain_text(raw: Optional[str], limit: Optional[int] = None) -> str:
    """Feed HTML or entity-escaped text -> plain text (feeds sometimes escape twice)."""
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"
    return text


def clean_url(raw: Optional[str]) -> Optional[str]:
    """Only absolute http(s) links survive (no javascript: or relative links); double slashes are collapsed."""
    url = (raw or "").strip()
    if not re.match(r"^https?://[^\s/]+", url, re.I):
        return None
    scheme, rest = url.split("://", 1)
    host, _, path = rest.partition("/")
    path = path.lstrip("/")
    # Collapse doubled slashes in the path only; a query string may legitimately contain "//".
    cut = min([i for i in (path.find("?"), path.find("#")) if i >= 0], default=len(path))
    path = re.sub(r"/{2,}", "/", path[:cut]) + path[cut:]
    return f"{scheme.lower()}://{host}/{path}"


def parse_time(raw: Optional[str]) -> Optional[datetime]:
    """RFC 822 (RSS) or ISO 8601 -> aware UTC datetime, or None."""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None  # a time without a zone cannot be placed honestly
    return parsed.astimezone(timezone.utc)


def tag_instruments(*texts: str) -> list[str]:
    text = " ".join(t for t in texts if t)
    return [sym for sym, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]


def _item(source: Source, title: str, url: str, published: datetime, summary: str, extra: tuple = ()) -> dict:
    instruments = sorted(set(source.instruments) | set(tag_instruments(title, summary)))
    return {
        "id": hashlib.sha1(url.encode()).hexdigest()[:16],
        "source": source.id,
        "source_name": source.name,
        "title": title,
        "url": url,
        "published_at": published.isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "topics": sorted(set(source.topics) | set(extra)),
        "instruments": instruments,
    }


# ---- parsers ---------------------------------------------------------------------

def parse_rss(source: Source, content: bytes) -> tuple[list[dict], int]:
    """RSS 2.0 -> (items, dropped). Raises NewsError if it is not an RSS document."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise NewsError(f"{source.name} sent a feed that is not valid XML ({exc})") from None
    if root.tag != "rss" or root.find("channel") is None:
        raise NewsError(f"{source.name} sent XML that is not an RSS feed")

    items, dropped = [], 0
    for node in root.findall("./channel/item"):
        title = plain_text(node.findtext("title"), 300)
        url = clean_url(node.findtext("link"))
        published = parse_time(node.findtext("pubDate"))
        if not title or not url or not published:
            dropped += 1
            continue
        summary = plain_text(node.findtext("description"), SNIPPET_CHARS)
        if summary == title:
            summary = ""
        items.append(_item(source, title, url, published, summary))
    return items, dropped


def parse_edgar(source: Source, body) -> tuple[list[dict], int]:
    """EDGAR submissions JSON -> the newest EDGAR_ITEMS filings of EDGAR_FORMS."""
    try:
        name = body["name"]
        cik = int(body["cik"])
        recent = body["filings"]["recent"]
        columns = [recent[k] for k in ("form", "accessionNumber", "acceptanceDateTime", "primaryDocument",
                                       "primaryDocDescription", "filingDate", "reportDate")]
    except (KeyError, TypeError, ValueError):
        raise NewsError("EDGAR sent submissions data in an unexpected shape") from None
    if len({len(c) for c in columns}) != 1:
        raise NewsError("EDGAR sent filing columns of different lengths")

    items, dropped = [], 0
    for form, accession, accepted, document, description, filed, report in zip(*columns):
        if form not in EDGAR_FORMS:
            continue
        # acceptanceDateTime is UTC ("...Z"): an earnings 8-K shows 20:30Z, i.e. 16:30 New York.
        published = parse_time(accepted)
        if not published or not accession or not document:
            dropped += 1
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
        label = f": {description}" if description and description != form else ""
        title = f"{name} filed {form}{label}"
        summary = f"Form {form} filed {filed}" + (f" for the period ending {report}" if report else "") + "."
        items.append(_item(source, title, url, published, summary))
        if len(items) >= EDGAR_ITEMS:
            break
    return items, dropped


# ---- fetching -----------------------------------------------------------------------

async def _fetch(source: Source) -> tuple[list[dict], int]:
    if source.kind == "edgar":
        if not config.SEC_USER_AGENT:
            raise NotConfigured("SEC_USER_AGENT is not set (EDGAR requires a name and contact email)")
        agent = config.SEC_USER_AGENT
    else:
        agent = config.FEED_USER_AGENT

    try:
        response = await get_client().get(source.url, headers={"User-Agent": agent})
    except httpx.TimeoutException:
        raise NewsError(f"{source.name} did not answer in time") from None
    except httpx.HTTPError as exc:
        raise NewsError(f"Could not reach {source.name} ({type(exc).__name__})") from None

    if response.status_code != 200:
        raise NewsError(f"{source.name} answered {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise NewsError(f"{source.name} sent more than {MAX_BYTES:,} bytes")

    if source.kind == "edgar":
        try:
            body = response.json()
        except ValueError:
            raise NewsError("EDGAR did not send JSON") from None
        return parse_edgar(source, body)
    return parse_rss(source, response.content)


async def source_state(source: Source) -> SourceState:
    cached = _cache.get(source.id)
    if cached and cached.error is None and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return cached
    try:
        items, dropped = await _fetch(source)
    except NotConfigured:
        raise
    except NewsError as exc:
        if cached and cached.items and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving kept %s items: %s", source.id, exc)
            return SourceState(cached.items, cached.dropped, cached.fetched_mono, cached.fetched_wall, str(exc))
        raise
    state = SourceState(items, dropped, _monotonic(), _wall())
    _cache[source.id] = state
    return state


async def collect() -> tuple[list[dict], list[dict]]:
    """(items newest first, per-source status) from every source, fetched concurrently."""
    results = await asyncio.gather(*(source_state(s) for s in SOURCES), return_exceptions=True)
    items, statuses, seen = [], [], set()
    for source, result in zip(SOURCES, results):
        status = {
            "id": source.id, "name": source.name, "topics": list(source.topics),
            "attribution": source.attribution, "homepage": source.homepage,
        }
        if isinstance(result, NotConfigured):
            status.update(status="not_configured", error=str(result), count=0)
        elif isinstance(result, NewsError):
            status.update(status="unavailable", error=str(result), count=0)
        elif isinstance(result, Exception):
            raise result
        else:
            status.update(
                status="stale" if result.error else "ok",
                error=result.error,
                count=len(result.items),
                dropped=result.dropped,
                fetched_at=datetime.fromtimestamp(result.fetched_wall, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            for item in result.items:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    items.append({**item, "stale": bool(result.error)})
        statuses.append(status)

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items, statuses
