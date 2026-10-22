import { memo, useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const money = (value) => `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

const dayFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })
const timeFormat = new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit' })

function EquityCurve({ points, startingCash }) {
  // One point per minute from the server (plus one after every order). The
  // header shows the live equity; redrawing this chart on every tick is costly.
  const data = useMemo(
    () => points.map((point) => ({ ts: point.ts, equity: point.equity })),
    [points],
  )

  if (data.length < 2) {
    return (
      <div className="holdings-empty">
        The equity curve builds up as you trade, with one point per minute.
      </div>
    )
  }

  const values = data.map((point) => point.equity).concat(startingCash)
  const padding = Math.max((Math.max(...values) - Math.min(...values)) * 0.15, 50)
  const spanHours = (data.at(-1).ts - data[0].ts) / 3_600_000

  const formatTime = (ts) => {
    return (spanHours > 36 ? dayFormat : timeFormat).format(new Date(ts))
  }

  const up = data.at(-1).equity >= startingCash
  const color = up ? '#34D399' : '#F87171'

  return (
    <div className="equity-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1E293B" strokeDasharray="3 5" vertical={false} />
          <XAxis
            dataKey="ts"
            type="number"
            domain={['dataMin', 'dataMax']}
            scale="time"
            minTickGap={50}
            tick={{ fill: '#64748B', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatTime}
          />
          <YAxis
            width={64}
            domain={[Math.min(...values) - padding, Math.max(...values) + padding]}
            tick={{ fill: '#64748B', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={money}
          />
          <ReferenceLine y={startingCash} stroke="#475569" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
            labelStyle={{ color: '#94A3B8' }}
            labelFormatter={formatTime}
            formatter={(value) => [`$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`, 'Equity']}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={color}
            strokeWidth={2}
            fill="url(#equityGradient)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export default memo(EquityCurve)
