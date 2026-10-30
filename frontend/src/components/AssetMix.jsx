import { useMemo, memo } from 'react'
import { Command, ShieldCheck } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

const CLASSES = [
  ['stock', 'Stocks', '#4FC3F7'], ['index', 'Indices', '#FBBF24'], ['crypto', 'Crypto', '#2FD16B'],
  ['fx', 'FX pairs', '#A78BFA'], ['commodity', 'Commodities', '#F97316'],
]

/** How many instruments FinPulse follows in each class (`counts` from lib/overview coverage). */
function AssetMix({ counts }) {
  const allocation = useMemo(
    () => CLASSES.filter(([key]) => counts[key]).map(([key, name, color]) => ({ name, value: counts[key], color })),
    [counts],
  )

  const total = allocation.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="panel allocation-panel">
      <div className="panel-heading">
        <div>
          <h2>What FinPulse follows</h2>
          <p>Assets by market, each with a live price, charts and an asset page</p>
        </div>
        <button className="subtle-icon" aria-label="Asset mix information"><Command size={17} /></button>
      </div>
      <div className="allocation-chart">
        {total > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={allocation}
                dataKey="value"
                nameKey="name"
                innerRadius={66}
                outerRadius={91}
                paddingAngle={5}
                stroke="none"
              >
                {allocation.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#000000', border: '1px solid #263347', borderRadius: 12, color: '#F2F2F2' }}
                formatter={(value, name) => [`${value} asset${value === 1 ? '' : 's'}`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-neutral-400">No assets loaded</div>
        )}
        <div className="allocation-center">
          <span>Assets</span>
          <strong>{total}</strong>
        </div>
      </div>
      <div className="allocation-legend">
        {allocation.map((item) => (
          <div key={item.name} className="allocation-row">
            <span className="allocation-label"><i style={{ background: item.color }} />{item.name}</span>
            <strong>{item.value} ({total ? Math.round(item.value / total * 100) : 0}%)</strong>
          </div>
        ))}
      </div>
      <div className="allocation-note">
        <ShieldCheck size={15} />
        <span>A count of followed assets, not a portfolio allocation.</span>
      </div>
    </div>
  )
}

export default memo(AssetMix)
