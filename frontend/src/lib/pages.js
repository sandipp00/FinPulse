// Modules shown in the sidebar that have no data source yet. They are listed so the
// layout is visible, but they are not links and have no page: nothing to fabricate.
export const PLANNED_MODULES = [
  { key: 'commodities', nav: 'Commodities', note: 'Gold, silver and oil need a data source; planned for a later phase.' },
  { key: 'news', nav: 'News', note: 'Source-linked headlines are planned for a later phase.' },
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
  macro: {
    title: 'US macro',
    nav: 'Macro',
    blurb: 'Inflation, rates, Treasury yields, growth and jobs, from FRED.',
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
