import { DATA_STATUS_BADGE, DATA_STATUS_LABEL } from '../lib/dataStatus'

/** A small LIVE / STALE / HIST / N/A tag, so freshness is spelled out rather than shown by colour alone. */
export default function DataTag({ status, detail }) {
  const label = detail ? `${DATA_STATUS_LABEL[status]} (${detail})` : DATA_STATUS_LABEL[status]
  return (
    <span className={`data-tag data-tag-${status}`} title={label}>
      {DATA_STATUS_BADGE[status]}
      {detail && <span className="data-tag-detail">{detail}</span>}
    </span>
  )
}
