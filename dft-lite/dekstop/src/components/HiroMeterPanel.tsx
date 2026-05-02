import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { dftApi } from '../api/client'
import { fmtCompactDollar } from '../lib/format'
import { PanelShell } from './PanelShell'

interface Props {
  parent: string
  date?: string
}

interface Row {
  ts: string
  label: string
  signed_premium: number
  cumulative: number
  n_trades: number
}

export function HiroMeterPanel({ parent, date }: Props) {
  const q = useQuery({
    queryKey: ['hiro', parent, date ?? 'latest'],
    queryFn: () => dftApi.hiro(parent, date),
    refetchInterval: 30_000,
  })

  const d = q.data

  const rows: Row[] = useMemo(() => {
    if (!d) return []
    const len = Math.min(
      d.ts.length,
      d.signed_premium.length,
      d.cumulative.length,
      d.n_trades.length,
    )
    const out: Row[] = []
    for (let i = 0; i < len; i++) {
      const tsRaw = d.ts[i]
      const date = new Date(tsRaw)
      const label = Number.isNaN(date.getTime())
        ? tsRaw
        : date.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })
      out.push({
        ts: tsRaw,
        label,
        signed_premium: Number(d.signed_premium[i]) || 0,
        cumulative: Number(d.cumulative[i]) || 0,
        n_trades: Number(d.n_trades[i]) || 0,
      })
    }
    return out
  }, [d])

  const summary = useMemo(() => {
    if (rows.length === 0) {
      return { last: 0, max: 0, min: 0, totalTrades: 0 }
    }
    let max = -Infinity
    let min = Infinity
    let totalTrades = 0
    for (const r of rows) {
      if (r.cumulative > max) max = r.cumulative
      if (r.cumulative < min) min = r.cumulative
      totalTrades += r.n_trades
    }
    return {
      last: rows[rows.length - 1].cumulative,
      max,
      min,
      totalTrades,
    }
  }, [rows])

  return (
    <PanelShell
      title="HIRO Meter"
      subtitle={d ? `${d.parent} • ${d.bucket} bucket` : parent}
      loading={q.isLoading}
      error={q.error}
      right={
        <div className="text-right text-xs text-slate-400">
          <div>
            Cumulative:{' '}
            <span
              className={`font-mono ${
                summary.last >= 0 ? 'text-emerald-300' : 'text-rose-300'
              }`}
            >
              {fmtCompactDollar(summary.last)}
            </span>
          </div>
          <div className="text-[10px] text-slate-500">
            High {fmtCompactDollar(summary.max)} • Low {fmtCompactDollar(summary.min)}
          </div>
        </div>
      }
    >
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 12, bottom: 4 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e293b" />
            <XAxis
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              minTickGap={32}
              stroke="#334155"
            />
            <YAxis
              yAxisId="left"
              tickFormatter={(v) => fmtCompactDollar(Number(v))}
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              stroke="#334155"
              width={64}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={(v) => fmtCompactDollar(Number(v))}
              tick={{ fill: '#64748b', fontSize: 10 }}
              stroke="#334155"
              width={64}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                borderRadius: 6,
                fontSize: 12,
              }}
              labelStyle={{ color: '#cbd5e1' }}
              formatter={(value, name) => {
                const num = Number(value ?? 0)
                const label = String(name ?? '')
                if (label === 'Trades') {
                  return [num.toLocaleString(), 'Trades']
                }
                return [fmtCompactDollar(num), label]
              }}
            />
            <ReferenceLine yAxisId="left" y={0} stroke="#475569" strokeDasharray="3 3" />
            <Bar
              yAxisId="right"
              dataKey="signed_premium"
              name="Signed Premium"
              barSize={2}
              fill="#475569"
              isAnimationActive={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cumulative"
              name="Cumulative"
              stroke="#22d3ee"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 text-[11px] text-slate-500">
        Total trades: {summary.totalTrades.toLocaleString()}
      </div>
    </PanelShell>
  )
}
