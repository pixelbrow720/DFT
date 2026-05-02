// Response types mirror DFT-Lite API spec (Blueprint v1.2 §B).

export interface ApiEnvelope<T> {
  ok: boolean
  ts: string
  version?: string
  data: T
}

export interface LevelsData {
  parent: string
  date: string
  spot_at_close: number
  call_wall: number | null
  put_wall: number | null
  zero_gamma: number | null
  total_gex_dollar: number
  vol_trigger?: number | null
  hi_band?: number | null
  lo_band?: number | null
  cumulative_gex_dollar?: number | null
  computed_from?: {
    n_strikes?: number
    n_expiries?: number
    method?: string
  }
}

export type RegimeKind =
  | 'LONG_GAMMA'
  | 'SHORT_GAMMA'
  | 'NEUTRAL'
  | 'TRANSITION'

export interface RegimeData {
  parent: string
  date?: string
  ts?: string
  spot: number
  zero_gamma: number | null
  regime: RegimeKind | string
  confidence: number
  distance_pct: number | null
  duration_minutes?: number
  history_30m?: { ts: string; regime: string }[]
}

export interface HiroData {
  parent: string
  bucket: string
  ts: string[]
  signed_premium: number[]
  cumulative: number[]
  n_trades: number[]
}

export interface GexHeatmapData {
  parent: string
  date: string
  strikes: number[]
  ts_minutes: string[]
  gex_dollar: number[][]
  color_quantiles: {
    p05: number
    p10: number
    p25: number
    p50: number
    p75: number
    p90: number
    p95: number
  }
}

export interface EventsNextData {
  next_fomc: string | null
  next_cpi: string | null
  next_nfp: string | null
  next_opex: string | null
  is_quad_witching: boolean
  days_to_next_event: number | null
}

export interface SpotData {
  asset: string
  spot: number
  as_of: string
  source: string
  stale_seconds: number
}
