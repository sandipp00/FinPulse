import { LIVE_STATUS_BADGE, LIVE_STATUS_LABEL } from '../lib/liveStatus'

export default function LiveBadge({ status }) {
  return (
    <span className={`live-badge live-badge-${status}`} title={LIVE_STATUS_LABEL[status]}>
      <i />
      {LIVE_STATUS_BADGE[status]}
    </span>
  )
}
