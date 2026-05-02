import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dftApi } from './api/client'
import { DailyLevelsPanel } from './components/DailyLevelsPanel'
import { RegimeBadge } from './components/RegimeBadge'
import { HiroMeterPanel } from './components/HiroMeterPanel'
import { GexHeatmapPanel } from './components/GexHeatmapPanel'
import { EventsPanel } from './components/EventsPanel'

const PARENTS = ['SPX', 'SPXW'] as const
type Parent = (typeof PARENTS)[number]

function App() {
  const [parent, setParent] = useState<Parent>('SPX')

  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => dftApi.health(),
    refetchInterval: 30_000,
  })

  const ok = health.data?.ok === true
  const replay = health.data?.data?.status === 'replay_mode'

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="font-semibold tracking-wide text-slate-100">
              DFT-Lite
            </div>
            <span className="text-xs text-slate-500">Desktop · v1.2</span>
          </div>
          <div className="flex items-center gap-3">
            <ParentToggle parent={parent} onChange={setParent} />
            <HealthDot ok={ok} replay={replay} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <DailyLevelsPanel parent={parent} />
          <RegimeBadge parent={parent} />
          <EventsPanel />
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <HiroMeterPanel parent={parent} />
          <GexHeatmapPanel parent={parent} />
        </div>
      </main>
    </div>
  )
}

function ParentToggle({
  parent,
  onChange,
}: {
  parent: Parent
  onChange: (p: Parent) => void
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-slate-700/80 text-xs">
      {PARENTS.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onChange(p)}
          className={`px-3 py-1 font-medium transition ${
            parent === p
              ? 'bg-slate-200 text-slate-900'
              : 'bg-slate-900 text-slate-300 hover:bg-slate-800'
          }`}
        >
          {p}
        </button>
      ))}
    </div>
  )
}

function HealthDot({ ok, replay }: { ok: boolean; replay: boolean }) {
  const cls = ok
    ? replay
      ? 'bg-amber-400'
      : 'bg-emerald-400'
    : 'bg-rose-500'
  const label = ok ? (replay ? 'Replay' : 'Live') : 'Down'
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-800/60 px-2.5 py-1 text-[11px] text-slate-300">
      <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />
      {label}
    </span>
  )
}

export default App
