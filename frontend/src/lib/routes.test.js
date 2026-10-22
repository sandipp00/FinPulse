import { describe, expect, it } from 'vitest'
import { routeFor } from './routes'

describe('routeFor', () => {
  it('recognises the sign-in and sign-up pages, with or without a trailing slash', () => {
    expect(routeFor('/signin')).toBe('signin')
    expect(routeFor('/signin/')).toBe('signin')
    expect(routeFor('/signup')).toBe('signup')
    expect(routeFor('/signup//')).toBe('signup')
  })

  it('treats everything else as the dashboard', () => {
    for (const path of ['/', '', undefined, null, '/overview', '/signin/extra', '/SIGNIN', '/api/health']) {
      expect(routeFor(path)).toBe('home')
    }
  })
})
