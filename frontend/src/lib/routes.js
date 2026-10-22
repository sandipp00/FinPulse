// The app has three screens. Everything that is not a sign-in or sign-up URL is the
// dashboard, so a mistyped address still lands somewhere useful (the server also falls
// back to index.html for unknown paths).
export const ROUTES = {
  home: '/',
  signin: '/signin',
  signup: '/signup',
}

export function routeFor(pathname) {
  const path = (pathname ?? '/').replace(/\/+$/, '') || '/'
  if (path === ROUTES.signin) return 'signin'
  if (path === ROUTES.signup) return 'signup'
  return 'home'
}
