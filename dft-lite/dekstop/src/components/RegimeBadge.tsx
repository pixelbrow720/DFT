import { useQuery } from '@tanstack/react-query'
import { dftApi } from '../api/client'
import { fmtNumber, fmtPct } from '../lib/format'
import { PanelShell } from './PanelShell'

interface Props {
  parent: string
  date?: string
}

const REGIME_STYLES: Record<string, { bg: string; ring: string; text: string; label: string }> = {
  LONG_GAMMA:  { bg: 'bg-emerald-600/20', ring: 'ring-emerald-500/50', text: 'text-emerald-300', label: 'Long Gamma' },
  SHORT_GAMMA: { bg: 'bg-rose-600/20',    ring: 'ring-rose-500/50',    text: 'text-rose-300',    label: 'Short Gamma' },
  NEUTRAL:     { bg: 'bg-slate-600/20',   ring: 'ring-slate-500/50',   text: 'text-slate-200',   label: 'Neutral' },
  TRANSITION:  { bg: 'bg-amber-600/20',   ring: 'ring-amber-500/50',   text: 'text-amber-300',   label: 'Transition' },
}

export function RegimeBadge({ parent, date }: Props) {
  const q = useQuery({
    queryKey: ['regime', parent, date ?? 'latest'],
    queryFn: () => dftApi.regime(parent, date),
    refetchInterval: 30_000,
  })

  const d = q.data
  const regimeKey = (d?.regime ?? 'NEUTRAL').toUpperCase()
  const style = REGIME_STYLES[regimeKey] ?? REGIME_STYLES.NEUTRAL

  return (
    <PanelShell
      title="Regime"
      subtitle={d ? `${d.parent} • ${d.date ?? d.ts ?? 'now'}` : parent}
      loading={q.isLoading}
      error={q.error}
    >
      <div className="flex flex-col gap-3">
        <div
          className={`inline-flex w-fit items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold ring-1 ${style.bg} ${style.ring} ${style.text}`}
        >
          <span className={`inline-block h-2 w-2 rounded-full ${style.text.replace('text-', 'bg-')}`} />
          {style.label}
        </div>

        <div className="grid grid-cols-3 gap-3 text-xs">
          <Mini label="Spot"        value={fmtNumber(d?.spot ?? null)} />
          <Mini label="Zero Gamma"  value={fmtNumber(d?.zero_gamma ?? null)} />
          <Mini label="Confidence"  value={d?.confidence != null ? fmtPct(d.confidence, 1) : '—'} />
        </div>

        {d?.distance_pct != null && (
          <p className="text-[11px] text-slate-400">
            Distance to ZG:{' '}
            <span className={`font-mono ${d.distance_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
              {(d.distance_pct * 100).toFixed(3)}%
            </span>
          </p>
        )}
      </div>
    </PanelShell>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-800/40 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-sm text-slate-200">{value}</div>
    </div>
  )
}
