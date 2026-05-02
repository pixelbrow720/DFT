import { ReactNode } from 'react'

interface PanelShellProps {
  title: string
  subtitle?: string
  loading?: boolean
  error?: unknown
  children: ReactNode
  className?: string
  right?: ReactNode
}

export function PanelShell({
  title,
  subtitle,
  loading,
  error,
  children,
  className = '',
  right,
}: PanelShellProps) {
  return (
    <section
      className={`rounded-xl border border-slate-700/60 bg-slate-900/60 p-4 shadow-lg backdrop-blur ${className}`}
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs text-slate-500">{subtitle}</p>
          )}
        </div>
        {right}
      </header>

      {loading ? (
        <div className="flex h-24 items-center justify-center text-xs text-slate-500">
          Loading…
        </div>
      ) : error ? (
        <ErrorBox error={error} />
      ) : (
        children
      )}
    </section>
  )
}

function ErrorBox({ error }: { error: unknown }) {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : 'Unknown error'
  return (
    <div className="rounded-md border border-red-700/60 bg-red-950/40 p-3 text-xs text-red-300">
      <div className="font-semibold">Failed to load</div>
      <div className="mt-1 opacity-80">{message}</div>
    </div>
  )
}
