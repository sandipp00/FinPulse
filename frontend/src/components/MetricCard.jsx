import { memo } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

function MetricCard({ label, value, change, positive, icon: Icon, note }) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-neutral-400">{label}</p>
        <span className="icon-tile"><Icon size={18} /></span>
      </div>
      <div className="mt-5 flex flex-wrap items-baseline gap-2">
        <h2 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">{value}</h2>
        {change && (
          <span className={`change-pill ${positive ? 'positive' : 'negative'}`}>
            {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {change}
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-neutral-500">{note}</p>
    </div>
  )
}

export default memo(MetricCard)
