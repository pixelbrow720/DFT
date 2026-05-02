import { useQuery } from '@tanstack/react-query'
import { dftApi } from '../api/client'
import { fmtDate, fmtTime } from '../lib/format'
import { PanelShell } from './PanelShell'

export function EventsPanel() {
  const q = useQuery({
    queryKey: ['eventsNext'],
    queryFn: () => dftApi.eventsNext(),
    refetchInterval: 60_000,
  })

  const d = q.data
  const items: { label: string; value: string; sub?: string }[] = [
    {
      label: 'FOMC',
      value: fmtDate(d?.next_fomc),
      sub: d?.next_fomc ? fmtTime(d.next_fomc) : undefined,
    },
    {
      label: 'CPI',
      value: fmtDate(d?.next_cpi),
      sub: d?.next_cpi ? fmtTime(d.next_cpi) : undefined,
    },
    {
      label: 'NFP',
      value: fmtDate(d?.next_nfp),
      sub: d?.next_nfp ? fmtTime(d.next_nfp) : undefined,
    },
    {
      label: 'OPEX',
      value: fmtDate(d?.next_opex),
      sub: d?.is_quad_witching ? 'Quad Witching' : undefined,
    },
  ]

  return (
    <PanelShell
      title="Next Macro Events"
      subtitle={
        d?.days_to_next_event != null
          ? `Next event in ${d.days_to_next_event}d`
          : undefined
      }
      loading={q.isLoading}
      error={q.error}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map((it) => (
          <div
            key={it.label}
            className="rounded-lg bg-slate-800/40 px-3 py-2"
          >
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              {it.label}
            </div>
            <div className="mt-0.5 font-mono text-sm text-slate-200">
              {it.value}
            </div>
            {it.sub && (
              <div className="text-[10px] text-amber-400/80">{it.sub}</div>
            )}
          </div>
        ))}
      </div>
    </PanelShell>
  )
}
