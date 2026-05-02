import { useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as d3 from 'd3'
import { dftApi } from '../api/client'
import type { GexHeatmapData } from '../api/types'
import { fmtCompactDollar } from '../lib/format'
import { PanelShell } from './PanelShell'

interface Props {
  parent: string
  date?: string
}

const MARGIN = { top: 12, right: 16, bottom: 32, left: 64 }

export function GexHeatmapPanel({ parent, date }: Props) {
  const q = useQuery<GexHeatmapData>({
    queryKey: ['gexHeatmap', parent, date ?? 'latest'],
    queryFn: () => dftApi.gexHeatmap(parent, date),
    refetchInterval: 60_000,
  })

  const d = q.data

  const colorScale = useMemo(() => {
    if (!d) return null
    const qd = d.color_quantiles
    // Diverging quantile-based scale: red (negative) → white (0) → green (positive).
    const stops = [qd.p05, qd.p10, qd.p25, qd.p50, qd.p75, qd.p90, qd.p95]
    const colors = ['#7f1d1d', '#b91c1c', '#fca5a5', '#0f172a', '#86efac', '#16a34a', '#14532d']
    return d3.scaleLinear<string>().domain(stops).range(colors).clamp(true)
  }, [d])

  return (
    <PanelShell
      title="GEX Heatmap"
      subtitle={d ? `${d.parent} • ${d.date}` : parent}
      loading={q.isLoading}
      error={q.error}
      right={d ? <Legend quantiles={d.color_quantiles} /> : null}
    >
      {d && colorScale ? (
        <Heatmap data={d} colorScale={colorScale} />
      ) : !q.isLoading && !q.error ? (
        <div className="flex h-32 items-center justify-center text-xs text-slate-500">
          No heatmap data available.
        </div>
      ) : null}
    </PanelShell>
  )
}

function Heatmap({
  data,
  colorScale,
}: {
  data: GexHeatmapData
  colorScale: d3.ScaleLinear<string, string>
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const tooltipRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const wrapper = wrapperRef.current
    const svg = svgRef.current
    const tooltip = tooltipRef.current
    if (!wrapper || !svg || !tooltip) return

    const draw = () => {
      const rect = wrapper.getBoundingClientRect()
      const width = Math.max(320, rect.width)
      const height = 320

      const innerW = Math.max(10, width - MARGIN.left - MARGIN.right)
      const innerH = Math.max(10, height - MARGIN.top - MARGIN.bottom)

      const nT = data.ts_minutes.length
      const nS = data.strikes.length

      const sel = d3.select(svg)
      sel.selectAll('*').remove()
      sel.attr('width', width).attr('height', height)

      const g = sel
        .append('g')
        .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)

      const xScale = d3
        .scaleBand<number>()
        .domain(d3.range(nT))
        .range([0, innerW])
        .padding(0)

      const yScale = d3
        .scaleBand<number>()
        .domain(d3.range(nS).reverse()) // higher strike on top
        .range([0, innerH])
        .padding(0)

      const cellW = Math.max(1, xScale.bandwidth())
      const cellH = Math.max(1, yScale.bandwidth())

      // Gridlines for orientation.
      const xTicksCount = Math.min(8, nT)
      const xTickIdxs = d3.range(0, nT, Math.max(1, Math.floor(nT / xTicksCount)))
      const yTicksCount = Math.min(8, nS)
      const yTickIdxs = d3.range(0, nS, Math.max(1, Math.floor(nS / yTicksCount)))

      // Cells.
      for (let si = 0; si < nS; si++) {
        const row = data.gex_dollar[si] ?? []
        const yPos = yScale(si) ?? 0
        for (let ti = 0; ti < nT; ti++) {
          const v = Number(row[ti] ?? 0)
          if (!Number.isFinite(v)) continue
          g.append('rect')
            .attr('x', xScale(ti) ?? 0)
            .attr('y', yPos)
            .attr('width', cellW)
            .attr('height', cellH)
            .attr('fill', colorScale(v))
            .attr('shape-rendering', 'crispEdges')
            .on('mousemove', (ev: MouseEvent) => {
              const wrapperRect = wrapper.getBoundingClientRect()
              tooltip.style.opacity = '1'
              tooltip.style.left = `${ev.clientX - wrapperRect.left + 12}px`
              tooltip.style.top = `${ev.clientY - wrapperRect.top + 12}px`
              tooltip.innerHTML = `
                <div class="font-mono text-[11px] leading-tight">
                  <div>K <span class="text-slate-200">${data.strikes[si]}</span></div>
                  <div>T <span class="text-slate-200">${data.ts_minutes[ti]}</span></div>
                  <div>GEX <span class="${v >= 0 ? 'text-emerald-300' : 'text-rose-300'}">${fmtCompactDollar(v)}</span></div>
                </div>
              `
            })
            .on('mouseleave', () => {
              tooltip.style.opacity = '0'
            })
        }
      }

      // X axis ticks (time).
      const xAxisGroup = sel
        .append('g')
        .attr('transform', `translate(${MARGIN.left},${MARGIN.top + innerH})`)
      xAxisGroup
        .selectAll('text')
        .data(xTickIdxs)
        .enter()
        .append('text')
        .attr('x', (i) => (xScale(i) ?? 0) + cellW / 2)
        .attr('y', 16)
        .attr('text-anchor', 'middle')
        .attr('fill', '#94a3b8')
        .attr('font-size', 10)
        .text((i) => data.ts_minutes[i])

      // Y axis ticks (strike).
      const yAxisGroup = sel
        .append('g')
        .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)
      yAxisGroup
        .selectAll('text')
        .data(yTickIdxs)
        .enter()
        .append('text')
        .attr('x', -8)
        .attr('y', (i) => (yScale(i) ?? 0) + cellH / 2 + 3)
        .attr('text-anchor', 'end')
        .attr('fill', '#94a3b8')
        .attr('font-size', 10)
        .text((i) => String(data.strikes[i]))
    }

    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(wrapper)
    return () => ro.disconnect()
  }, [data, colorScale])

  return (
    <div ref={wrapperRef} className="relative w-full">
      <svg ref={svgRef} className="block w-full" />
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute rounded border border-slate-700 bg-slate-900/95 px-2 py-1 text-[11px] text-slate-200 shadow-lg"
        style={{ opacity: 0, transition: 'opacity 100ms' }}
      />
    </div>
  )
}

function Legend({ quantiles }: { quantiles: GexHeatmapData['color_quantiles'] }) {
  const items = [
    { k: 'p05', v: quantiles.p05, color: '#7f1d1d' },
    { k: 'p25', v: quantiles.p25, color: '#fca5a5' },
    { k: 'p50', v: quantiles.p50, color: '#475569' },
    { k: 'p75', v: quantiles.p75, color: '#86efac' },
    { k: 'p95', v: quantiles.p95, color: '#14532d' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
      {items.map((it) => (
        <span key={it.k} className="inline-flex items-center gap-1">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: it.color }}
          />
          <span>
            {it.k.toUpperCase()} {fmtCompactDollar(it.v)}
          </span>
        </span>
      ))}
    </div>
  )
}
