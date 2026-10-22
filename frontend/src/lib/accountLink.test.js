import { describe, expect, it } from 'vitest'
import { parseAccountLink } from './accountLink'

const TOKEN = 'Abc123_-xyzAbc123_-xyzAbc123_-xyz0123456'

describe('parseAccountLink', () => {
  it('reads verify and reset links from the URL fragment', () => {
    expect(parseAccountLink(`#verify=${TOKEN}`)).toEqual({ kind: 'verify', token: TOKEN })
    expect(parseAccountLink(`#reset=${TOKEN}`)).toEqual({ kind: 'reset', token: TOKEN })
  })

  it('ignores anything else, including look-alikes and oversized tokens', () => {
    for (const hash of [
      '', '#', '#verify=', '#verify=short', '#other=' + TOKEN, '#verify=' + TOKEN + '&x=1',
      '#verify=' + 'a'.repeat(201), 'verify=' + TOKEN, '#verify=' + TOKEN + '<script>',
      null, undefined,
    ]) {
      expect(parseAccountLink(hash)).toBeNull()
    }
  })
})
