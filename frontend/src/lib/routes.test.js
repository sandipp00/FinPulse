import { describe, expect, it } from 'vitest'
import { AUTH_ROUTES, ROUTES, routeFor } from './routes'

describe('routeFor', () => {
  it('maps every known path to its route, with or without a trailing slash', () => {
    for (const [name, path] of Object.entries(ROUTES)) {
      expect(routeFor(path)).toBe(name)
      if (path !== '/') expect(routeFor(`${path}/`)).toBe(name)
    }
  })

  it('treats everything else as the dashboard home', () => {
    for (const path of ['', undefined, null, '/overview', '/signin/extra', '/SIGNIN', '/api/health', '/risk/x']) {
      expect(routeFor(path)).toBe('home')
    }
  })

  it('knows which routes are standalone auth pages', () => {
    expect(AUTH_ROUTES).toEqual(['signin', 'signup'])
  })
})
