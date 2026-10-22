import { memo } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatPercent, getAssetDetails } from '../lib/format'

const TOOLTIP_STYLE = { background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }

function MetricBars({ title, note, data, field, suffix = '%' }) {
  return (
    <div className="compare-chart">
      <h3>{title}</h3>
      <p>{note}</p>
      <div className="compare-chart-body">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="#1E293B" strokeDasharray="3 5" vertical={false} />
            <XAxis dataKey="short" tick={{ fill: '#64748B', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748B', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}${suffix}`} width={52} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ fill: '#1E293B66' }}
              formatter={(value) => [`${Number(value).toFixed(1)}${suffix}`, title]}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.symbol ?? ''}
            />
            <Bar dataKey={field} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((row) => <Cell key={row.symbol} fill={row.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

const tone = (value) => (value > 0 ? 'tone-up' : value < 0 ? 'tone-down' : '')

/** Side-by-side history of the assets stored in the database. */
function AssetComparison({ assets }) {
  if (assets.length === 0) {
    return (
      <section className="panel compare-panel">
        <div className="panel-heading"><div><h2>Historical comparison</h2></div></div>
        <p className="holdings-empty">No stored history yet. Load it with the seed job (see the deployment guide).</p>
      </section>
    )
  }

  const data = assets.map((asset) => ({
    ...asset,
    short: asset.symbol.replace('/USDT', '').replace('^', ''),
    color: getAssetDetails(asset.symbol).color,
  }))

  return (
    <section className="panel compare-panel">
      <div className="panel-heading">
        <div>
          <h2>Historical comparison</h2>
          <p>How each stored asset performed and how rough the ride was. Past results do not predict future ones.</p>
        </div>
      </div>

      <div className="compare-charts">
        <MetricBars
          title="Annualized volatility"
          note="Taller bars swing more."
          data={data}
          field="annualized_volatility_pct"
        />
        <MetricBars
          title="Worst fall from a peak"
          note="Deeper bars lost more at the low point."
          data={data}
          field="max_drawdown_pct"
        />
      </div>

      <div className="table-scroll">
        <table className="market-table compare-table">
          <thead>
            <tr>
              <th>ASSET</th>
              <th>PERIOD</th>
              <th>TOTAL RETURN</th>
              <th>VOLATILITY</th>
              <th>SHARPE</th>
              <th>WORST FALL</th>
            </tr>
          </thead>
          <tbody>
            {data.map((asset) => (
              <tr key={asset.symbol}>
                <td>
                  <div className="asset-cell">
                    <span className="asset-icon" style={{ color: asset.color, borderColor: `${asset.color}44`, background: `${asset.color}12` }}>
                      {asset.short[0]}
                    </span>
                    <span><strong>{asset.symbol}</strong><small>{getAssetDetails(asset.symbol).name}</small></span>
                  </div>
                </td>
                <td className="price-cell">
                  {asset.first_date?.slice(0, 10)} → {asset.last_date?.slice(0, 10)}
                  <small className="cell-sub">{asset.observations} daily closes</small>
                </td>
                <td className={`price-cell ${tone(asset.total_return_pct)}`}>{formatPercent(asset.total_return_pct, 1)}</td>
                <td className="price-cell">{asset.annualized_volatility_pct?.toFixed(1)}%</td>
                <td className="price-cell">{asset.sharpe_ratio?.toFixed(2) ?? '—'}</td>
                <td className="price-cell tone-down">{formatPercent(asset.max_drawdown_pct, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default memo(AssetComparison)
