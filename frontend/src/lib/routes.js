// Every screen of the app and its URL. The dashboard pages share one shell (sidebar,
// top bar, live ticker); sign-in and sign-up are standalone pages.
export const ROUTES = {
  home: '/',
  equities: '/equities',
  crypto: '/crypto',
  markets: '/markets',
  explorer: '/explorer',
  portfolio: '/portfolio',
  analytics: '/analytics',
  research: '/research',
  risk: '/risk',
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
