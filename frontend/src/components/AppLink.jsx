import { navigate } from '../hooks/useRoute'

/**
 * A real link (so "open in new tab", middle-click and copy-address all work) that
 * switches pages without a full reload on an ordinary click.
 */
export default function AppLink({ href, onClick, children, ...rest }) {
  const handleClick = (event) => {
    onClick?.(event)
    const modified = event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
    if (event.defaultPrevented || event.button !== 0 || modified) return
    event.preventDefault()
    navigate(href)
  }

  return (
    <a href={href} onClick={handleClick} {...rest}>
      {children}
    </a>
  )
}
