// Every screen of the app and its URL. The dashboard pages share one shell (sidebar,
// top bar, live ticker); sign-in and sign-up are standalone pages.
export const ROUTES = {
  home: '/',
  equities: '/equities',
  indices: '/indices',
  hours: '/hours',
  crypto: '/crypto',
  fx: '/fx',
  commodities: '/commodities',
  macro: '/macro',
  news: '/news',
  calendar: '/calendar',
  markets: '/markets',
  explorer: '/explorer',
  asset: '/asset',
  assistant: '/assistant',
  portfolio: '/portfolio',
  analytics: '/analytics',
  research: '/research',
  risk: '/risk',
  positioning: '/positioning',
  settings: '/settings',
  help: '/help',
  signin: '/signin',
  signup: '/signup',
}

const BY_PATH = Object.fromEntries(Object.entries(ROUTES).map(([name, path]) => [path, name]))

/** The route name for a URL path. Anything unrecognised is the home page. */
export function routeFor(pathname) {
  const path = (pathname ?? '/').replace(/\/+$/, '') || '/'
  return BY_PATH[path] ?? 'home'
}

export const AUTH_ROUTES = ['signin', 'signup']
