import { useQuery } from '@tanstack/react-query'
import { dftApi } from '../api/client'
import { fmtCompactDollar, fmtNumber } from '../lib/format'
import { PanelShell } from './PanelShell'

interface Props {
  parent: string
  date?: string
}

export function DailyLevelsPanel({ parent, date }: Props) {
  const q = useQuery({
    queryKey: ['levels', parent, date ?? 'latest'],
    queryFn: () => dftApi.levels(parent, date),
    refetchInterval: 30_000,
  })

  const d = q.data
  const spot = d?.spot_at_close ?? null
  const cw = d?.call_wall ?? null
  const pw = d?.put_wall ?? null
  const zg = d?.zero_gamma ?? null

  return (
    <PanelShell
      title="Daily Levels"
      subtitle={d ? `${d.parent} • ${d.date}` : parent}
      loading={q.isLoading}
      error={q.error}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Spot" value={fmtNumber(spot)} accent="text-slate-100" />
        <Stat
          label="Call Wall"
          value={fmtNumber(cw)}
          accent="text-emerald-400"
          delta={spot != null && cw != null ? cw - spot : null}
        />
        <Stat
          label="Put Wall"
          value={fmtNumber(pw)}
          accent="text-rose-400"
          delta={spot != null && pw != null ? pw - spot : null}
        />
        <Stat
          label="Zero Gamma"
          value={fmtNumber(zg)}
          accent="text-amber-400"
          delta={spot != null && zg != null ? zg - spot : null}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        <span>
          Total GEX:{' '}
          <span className="font-mono text-slate-200">
            {fmtCompactDollar(d?.total_gex_dollar ?? null)}
          </span>
        </span>
        {d?.computed_from?.n_strikes !== undefined && (
          <span>
            Strikes: <span className="text-slate-300">{d.computed_from.n_strikes}</span>
          </span>
        )}
        {d?.computed_from?.n_expiries !== undefined && (
          <span>
            Expiries: <span className="text-slate-300">{d.computed_from.n_expiries}</span>
          </span>
        )}
      </div>
    </PanelShell>
  )
}

function Stat({
  label,
  value,
  accent,
  delta,
}: {
  label: string
  value: string
  accent: string
  delta?: number | null
}) {
  return (
    <div className="rounded-lg bg-slate-800/50 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-lg font-semibold ${accent}`}>
        {value}
      </div>
      {delta != null && Number.isFinite(delta) && (
        <div
          className={`text-[11px] font-mono ${
            delta >= 0 ? 'text-emerald-400/80' : 'text-rose-400/80'
          }`}
        >
          {delta >= 0 ? '+' : ''}
          {delta.toFixed(2)}
        </div>
      )}
    </div>
  )
}
