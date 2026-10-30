// Modules shown in the sidebar that have no data source yet. They are listed so the
// layout is visible, but they are not links and have no page: nothing to fabricate.
export const PLANNED_MODULES = [
]

// Titles and one-line descriptions for the dashboard pages (used by the sidebar,
// the page header and the quick links on the overview).
export const PAGES = {
  home: {
    title: 'Market overview',
    nav: 'Overview',
    blurb: 'Where the markets stand right now, and where to dig deeper.',
  },
  equities: {
    title: 'Equities',
    nav: 'Equities',
    blurb: 'Stocks and indices with stored daily history.',
  },
  crypto: {
    title: 'Crypto',
    nav: 'Crypto',
    blurb: 'Live exchange prices and stored daily history for crypto assets.',
  },
  fx: {
    title: 'FX rates',
    nav: 'FX',
    blurb: 'ECB euro reference rates and cross rates derived from them. Daily, not live.',
  },
  commodities: {
    title: 'Commodities',
    nav: 'Commodities',
    blurb: 'Live and end-of-day gold and silver, and WTI and Brent crude oil spot prices from the U.S. Energy Information Administration.',
  },
  macro: {
    title: 'US macro',
    nav: 'Macro',
    blurb: 'Inflation, rates, Treasury yields, growth and jobs, from FRED.',
  },
  news: {
    title: 'News',
    nav: 'News',
    blurb: 'Headlines from the Fed, ECB, BEA, CoinDesk and SEC filings, each linked to the original.',
  },
  calendar: {
    title: 'Economic calendar',
    nav: 'Calendar',
    blurb: 'Upcoming US data releases and Fed and ECB policy meetings.',
  },
  markets: {
    title: 'Markets',
    nav: 'Markets',
    blurb: 'Live candlestick charts, price history and every tracked asset.',
  },
  explorer: {
    title: 'Instrument explorer',
    nav: 'Explorer',
    blurb: 'Pick any supported instrument and inspect its history, returns and volume.',
  },
  assistant: {
    title: 'Research assistant',
    nav: 'Assistant',
    blurb: 'Ask questions about the data. Answers cite every source; nothing is invented.',
  },
  portfolio: {
    title: 'Portfolio',
    nav: 'Portfolio',
    blurb: 'Practice trading with virtual money at live prices.',
  },
  analytics: {
    title: 'Analytics',
    nav: 'Analytics',
    blurb: 'Buy/sell signals, how they backtested, and how assets compare.',
  },
  research: {
    title: 'Research',
    nav: 'Research',
    blurb: 'A plain-language brief for each asset, written from your own data.',
  },
  risk: {
    title: 'Risk monitor',
    nav: 'Risk Monitor',
    blurb: 'How volatile each asset is, how far it has fallen, and how assets move together.',
  },
  settings: {
    title: 'Settings',
    nav: 'Settings',
    blurb: 'Your account and how this app is connected.',
  },
  help: {
    title: 'Help & support',
    nav: 'Help & support',
    blurb: 'What each page does, what the terms mean, and where the data comes from.',
  },
}
