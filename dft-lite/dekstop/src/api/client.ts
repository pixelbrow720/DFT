import axios, { AxiosInstance } from 'axios'
import type {
  ApiEnvelope,
  EventsNextData,
  GexHeatmapData,
  HiroData,
  LevelsData,
  RegimeData,
  SpotData,
} from './types'

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  'http://localhost:8080'

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15_000,
})

async function unwrap<T>(p: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const res = await p
  if (!res.data?.ok) {
    throw new Error('API returned ok=false')
  }
  return res.data.data
}

export const dftApi = {
  health: () => api.get('/api/v1/health').then((r) => r.data),

  levels: (parent: string, date?: string) =>
    unwrap<LevelsData>(
      api.get(`/api/v1/levels/${parent}`, { params: date ? { date } : undefined }),
    ),

  regime: (parent: string, date?: string) =>
    unwrap<RegimeData>(
      api.get(`/api/v1/regime/${parent}`, { params: date ? { date } : undefined }),
    ),

  hiro: (parent: string, date?: string) =>
    unwrap<HiroData>(
      api.get(`/api/v1/hiro/${parent}`, { params: date ? { date } : undefined }),
    ),

  gexHeatmap: (parent: string, date?: string) =>
    unwrap<GexHeatmapData>(
      api.get(`/api/v1/gex/heatmap/${parent}`, {
        params: date ? { date } : undefined,
      }),
    ),

  eventsNext: () => unwrap<EventsNextData>(api.get('/api/v1/events/next')),

  spot: (asset: string) =>
    unwrap<SpotData>(api.get(`/api/v1/spot/${asset}`)),
}
