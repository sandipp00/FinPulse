import { verifyEmail } from '../api/finpulse'

/**
 * Emailed links look like  https://site/#verify=TOKEN  or  https://site/#reset=TOKEN.
 * The token sits in the URL fragment on purpose: browsers never send it to any
 * server, so it cannot end up in access logs or Referer headers.
 */
export function parseAccountLink(hash) {
  const match = /^#(verify|reset)=([A-Za-z0-9_-]{10,200})$/.exec(hash ?? '')
  return match ? { kind: match[1], token: match[2] } : null
}

/** Read a link from the address bar (if there is one) and scrub it from the URL. */
export function takeLinkFromAddressBar() {
  if (typeof window === 'undefined') return null

  const link = parseAccountLink(window.location.hash)
  if (link) {
    // Remove the token from the address bar and history right away, so it is
    // not left behind for shoulder-surfers or a copied URL.
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
  return link
}

// Read once, when the page loads. Doing this at module level (not in a
// component) means React StrictMode's double rendering cannot lose the link.
export const initialAccountLink = takeLinkFromAddressBar()

// A link works once. StrictMode runs effects twice in development, which would
// spend the token on the first call and show "invalid link" for the second, so
// every caller shares one request per token.
const verifications = new Map()

export function confirmEmailOnce(token) {
  if (!verifications.has(token)) verifications.set(token, verifyEmail(token))
  return verifications.get(token)
}
