import { useMemo, memo } from 'react'
import { Command, ShieldCheck } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

const TYPE_COLORS = { Crypto: '#34D399', Stock: '#818CF8', Index: '#FBBF24' }

function AssetMix({ assets }) {
  const allocation = useMemo(() => {
    const counts = assets.reduce((result, asset) => {
      result[asset.type] = (result[asset.type] || 0) + 1
      return result
    }, {})

    return Object.entries(counts).map(([name, value]) => ({
      name: name === 'Index' ? 'Indices' : `${name}${value > 1 ? 's' : ''}`,
      value,
      color: TYPE_COLORS[name] ?? '#94A3B8',
    }))
  }, [assets])

  const total = allocation.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="panel allocation-panel">
      <div className="panel-heading">
        <div>
          <h2>Tracked asset mix</h2>
          <p>Count of assets by market type, not portfolio allocation</p>
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
                contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
                formatter={(value, name) => [`${value} asset${value === 1 ? '' : 's'}`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">No assets loaded</div>
        )}
        <div className="allocation-center">
          <span>Tracked</span>
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
        <span>This visual summarizes database coverage; it does not represent invested capital.</span>
      </div>
    </div>
  )
}

export default memo(AssetMix)
