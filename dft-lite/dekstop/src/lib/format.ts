export function fmtNumber(
  v: number | null | undefined,
  digits = 2,
): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtCompactDollar(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  const fmt = (n: number, suffix: string) =>
    `${sign}$${n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2)}${suffix}`
  if (abs >= 1e12) return fmt(abs / 1e12, 'T')
  if (abs >= 1e9) return fmt(abs / 1e9, 'B')
  if (abs >= 1e6) return fmt(abs / 1e6, 'M')
  if (abs >= 1e3) return fmt(abs / 1e3, 'K')
  return `${sign}$${abs.toFixed(0)}`
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}
