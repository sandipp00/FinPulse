import AppLink from '../components/AppLink'
import { PAGES } from '../lib/pages'
import { ROUTES } from '../lib/routes'

const TOUR = ['home', 'equities', 'crypto', 'fx', 'commodities', 'macro', 'news', 'calendar', 'asset', 'markets', 'explorer', 'portfolio', 'analytics', 'research', 'assistant', 'risk', 'settings']

const GLOSSARY = [
  ['Candlestick', 'One bar of a price chart. It shows the open, high, low and close for a period, and is green when the price closed higher than it opened.'],
  ['SMA / EMA', 'Simple and exponential moving averages: the average closing price over the last N candles. The EMA gives recent candles more weight.'],
  ['RSI', 'Relative Strength Index, from 0 to 100. Below 30 is often called oversold and above 70 overbought. It measures how one-sided recent moves were.'],
  ['MACD', 'The gap between a fast and a slow moving average. When its histogram is positive, momentum is building upward.'],
  ['Bollinger Bands', 'A band two standard deviations either side of the 20-candle average. A close outside it means price is stretched.'],
  ['Volatility', 'How much the price swings, shown per year. Higher means a rougher ride, in both directions.'],
  ['Drawdown', 'How far the price has fallen from its highest close. The worst fall is the deepest one in the data.'],
  ['Value at risk (1-in-20 day)', 'On 1 day in 20 the loss was this big or bigger. It describes the past, not a limit on what could happen.'],
  ['Correlation', 'How closely two assets move together day to day: 1 is in lockstep, 0 unrelated, -1 opposite. Low correlation helps diversify.'],
  ['Sharpe ratio', 'Return per unit of volatility. Higher means more return for the swings endured.'],
  ['Backtest', 'Replaying a set of rules over past prices to see what they would have done. It shows the past on one stretch of history, not the future.'],
  ['Paper trading', 'Practising with virtual money at live prices. Nothing you do there is a real order.'],
]

export default function HelpPage() {
  return (
    <div className="help">
      <section className="panel help-card">
        <h2>What each page does</h2>
        <ul className="help-tour">
          {TOUR.map((route) => (
            <li key={route}>
              <AppLink href={ROUTES[route]} className="link-inline">{PAGES[route].title}</AppLink>
              <span>{PAGES[route].blurb}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel help-card">
        <h2>Where the numbers come from</h2>
        <ul>
          <li><b>Live prices and candles:</b> Binance&apos;s public market data, with no account or key. If your network blocks Binance, the app tries a second endpoint.</li>
          <li><b>Stocks and indices:</b> daily history downloaded from Yahoo Finance and stored in the local database. It is not a live quote.</li>
          <li><b>FX rates:</b> every pair is live: Yahoo Finance quotes refreshed every 15 seconds, with intraday charts (1 minute to 1 day). Yahoo quotes are indicative and for personal use. Each card also shows the European Central Bank&apos;s daily reference rate (through the free Frankfurter API, published around 16:00 CET on working days); USD/INR, GBP/USD and USD/JPY ECB rates are cross rates that FinPulse calculates from two ECB euro rates.</li>
          <li><b>Oil prices:</b> WTI (Cushing, OK) and Brent (Europe) crude oil spot prices from the U.S. Energy Information Administration, fetched with the server&apos;s own key. EIA releases these daily prices once a week, so the newest can be several days old. Source: U.S. Energy Information Administration.</li>
          <li><b>Live gold, silver and oil:</b> Binance perpetual futures contracts (XAUUSDT, XAGUSDT, CLUSDT for WTI, BZUSDT for Brent), priced in USDT and tracking the real markets, streamed like the crypto prices. They are not official spot or exchange prices, and they trade around the clock: when the futures markets are closed (about Friday 17:00 to Sunday 18:00 New York time, and daily 17:00 to 18:00), the Commodities page says that the price reflects Binance trading only.</li>
          <li><b>Live stocks, indices and FX:</b> AAPL, the S&amp;P 500, the NIFTY 50 and the FX pairs are quoted from Yahoo Finance every 15 seconds. <b>LIVE</b> means the market is open and the price is current; <b>DELAYED</b> means Yahoo&apos;s newest price is a few minutes old; <b>CLOSED</b> means the market is shut and the price is the last of the session. Nothing can move a price while its market is closed.</li>
          <li><b>Gold and silver, end of day:</b> COMEX front-month futures settlement prices from Yahoo Finance, in US dollars per troy ounce, refreshed by the same update script as the stocks and indices. They are futures, not spot prices, and never live. Silver&apos;s series stays on the expiring contract until it expires, so some days trade very thinly and the price can jump slightly when it rolls to the next contract.</li>
          <li><b>US macro:</b> series from FRED (Federal Reserve Bank of St. Louis), fetched with the server&apos;s own key and refreshed at most hourly. This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. See the <a className="link-inline" href="https://fred.stlouisfed.org/docs/api/terms_of_use.html" target="_blank" rel="noreferrer">FRED® API Terms of Use</a>.</li>
          <li><b>News:</b> headlines and short snippets from the Federal Reserve, the ECB (source: ECB), the BEA, CoinDesk (personal, non-commercial use) and SEC EDGAR filings, each linking to the original. FinPulse never stores full articles. SEC filings appear only when <code>SEC_USER_AGENT</code> is set, as EDGAR requires.</li>
          <li><b>Calendar:</b> release dates from FRED, release times from the BEA, and Fed and ECB meeting dates from their own calendars. There are no consensus forecasts: free sources do not publish them.</li>
          <li><b>Signals:</b> six rules (trend, moving-average cross, RSI, MACD, Bollinger Bands and volume) each vote on every closed candle. Their weighted average is the score; +20 or more is a Buy, -20 or less a Sell.</li>
          <li><b>Research briefs:</b> sentences generated by fixed rules from the same numbers. They are not AI, and they include no news.</li>
          <li><b>Paper trading:</b> fills at the live price with a flat fee and no slippage, so real trades would fill a little worse.</li>
        </ul>
      </section>

      <section className="panel help-card help-wide">
        <h2>Glossary</h2>
        <dl className="glossary">
          {GLOSSARY.map(([term, meaning]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{meaning}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="panel help-card help-wide">
        <h2>Need a hand?</h2>
        <p>
          Found a bug or have an idea? Open an issue on{' '}
          <a className="link-inline" href="https://github.com/sandipp00/FinPulse/issues" target="_blank" rel="noopener noreferrer">GitHub</a>.
          Forgot your password? Use <em>Forgot your password?</em> on the sign-in page, or ask whoever runs this server.
        </p>
        <p className="help-disclaimer">
          FinPulse is for education and research. Nothing here is investment advice, and past performance does not predict future results.
        </p>
      </section>
    </div>
  )
}
