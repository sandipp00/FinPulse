import { formatPrice } from '../lib/format'

/**
 * A price that flashes green/red whenever it ticks. Changing `key` remounts
 * the span, which restarts the CSS animation once per real price move.
 */
export default function LivePrice({ tick, className = '' }) {
  return (
    <span
      key={tick.seq}
      className={`live-price flash-${tick.direction} ${className}`}
    >
      {formatPrice(tick.price, tick.symbol)}
    </span>
  )
}
