'use client'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Server,
  AlertTriangle,
  Search,
  ChevronDown,
  Copy,
  Check,
  ArrowUpDown,
  Timer,
  BarChart3,
  ListChecks,
} from 'lucide-react'
import type { LogEntry, LogStats } from '../types/analysis'
import { API_BASE_URL } from '../lib/api'

const EASE = [0.16, 1, 0.3, 1] as const
const PAGE_SIZE = 100

/* ---------------- hooks ---------------- */
function useCountUp(target: number, duration = 700) {
  const [display, setDisplay] = useState(0)
  const ref = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    const to = Number.isFinite(target) ? Math.max(0, target) : 0
    const from = ref.current
    if (from === to) return
    let start: number | null = null
    let raf = 0
    const step = (t: number) => {
      if (start === null) start = t
      const p = Math.min((t - start) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = from + (to - from) * eased
      ref.current = v
      if (mounted.current) setDisplay(v)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return Math.round(display)
}

/* ---------------- primitives ---------------- */
function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl bg-slate-900 border border-slate-800 ${className}`}
    >
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-transparent via-slate-800 to-transparent"
        initial={{ x: '-100%' }}
        animate={{ x: '100%' }}
        transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
      />
    </div>
  )
}

function Sparkline({ data, width = 88, height = 26 }: { data: number[]; width?: number; height?: number }) {
  if (!data || data.length < 2) return <div className="h-[26px]" />
  const max = Math.max(...data, 1)
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - (v / max) * (height - 2) - 1
      return `${x},${y}`
    })
    .join(' ')
  return (
    <svg width={width} height={height} className="overflow-visible text-slate-500">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StatCard({
  label,
  value,
  format,
  icon,
  tone = 'neutral',
  subtext,
  spark,
  index,
}: {
  label: string
  value: number
  format?: (n: number) => string
  icon: React.ReactNode
  tone?: 'neutral' | 'positive' | 'negative'
  subtext?: string
  spark?: number[]
  index: number
}) {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0
  const animated = useCountUp(safe)
  const display = format ? format(animated) : animated.toLocaleString('pt-BR')

  const iconColor =
    tone === 'positive' ? 'text-emerald-400' : tone === 'negative' ? 'text-red-400' : 'text-slate-400'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: EASE }}
      className="bg-slate-900 border border-slate-800 rounded-xl p-5 transition-colors hover:border-slate-700"
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-sm font-medium text-slate-300">{label}</span>
        <span className={iconColor}>{icon}</span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-3xl font-semibold text-white tracking-tight tabular-nums leading-none">
            {display}
          </div>
          {subtext && <div className="text-sm text-slate-400 mt-2">{subtext}</div>}
        </div>
        {spark && <Sparkline data={spark} />}
      </div>
    </motion.div>
  )
}

/* ---------------- volume chart ---------------- */
function VolumeChart({ logs, nowMs }: { logs: LogEntry[]; nowMs: number }) {
  const buckets = useMemo(() => {
    const arr: { label: string; total: number; errors: number }[] = []
    if (!nowMs) return arr
    for (let i = 23; i >= 0; i--) {
      const end = nowMs - i * 3600_000
      const start = end - 3600_000
      const slice = logs.filter((l) => {
        const t = new Date(l.timestamp).getTime()
        return t >= start && t < end
      })
      arr.push({
        label: new Date(end).getHours().toString().padStart(2, '0'),
        total: slice.length,
        errors: slice.filter((l) => l.status_code >= 400).length,
      })
    }
    return arr
  }, [logs, nowMs])

  const max = Math.max(...buckets.map((b) => b.total), 1)
  const hasData = buckets.some((b) => b.total > 0)

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl">
      <div className="px-5 py-4 border-b border-slate-800">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Volume de requisições</h2>
            <p className="text-sm text-slate-400 mt-0.5">Últimas 24 horas</p>
          </div>
          <span className="text-sm text-slate-400 tabular-nums">
            {buckets.reduce((s, b) => s + b.total, 0).toLocaleString('pt-BR')} no período
          </span>
        </div>
      </div>
      <div className="px-5 py-5">
        {!hasData ? (
          <div className="flex items-center justify-center h-[140px] text-sm text-slate-400">
            Sem atividade nas últimas 24 horas
          </div>
        ) : (
          <div className="flex items-end gap-[3px] h-[140px]">
            {buckets.map((b, i) => {
              const h = (b.total / max) * 100
              const errRatio = b.total > 0 ? b.errors / b.total : 0
              return (
                <div
                  key={i}
                  className="relative flex-1 flex flex-col justify-end h-full group"
                >
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${Math.max(h, 2)}%` }}
                    transition={{ duration: 0.5, delay: 0.2 + i * 0.015, ease: EASE }}
                    className={`w-full rounded-sm ${
                      b.total === 0
                        ? 'bg-slate-800'
                        : errRatio > 0.3
                        ? 'bg-red-500/70 group-hover:bg-red-400'
                        : 'bg-slate-600 group-hover:bg-slate-400'
                    } transition-colors`}
                  />
                  {b.total > 0 && (
                    <div className="absolute -top-1 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 whitespace-nowrap pointer-events-none z-10">
                      {b.label}h · {b.total} req
                      {b.errors > 0 && ` · ${b.errors} erro${b.errors > 1 ? 's' : ''}`}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
        <div className="flex justify-between mt-2 text-xs text-slate-500 tabular-nums">
          <span>-24h</span>
          <span>-18h</span>
          <span>-12h</span>
          <span>-6h</span>
          <span>agora</span>
        </div>
      </div>
    </div>
  )
}

/* ---------------- status distribution ---------------- */
function StatusDistribution({ logs }: { logs: LogEntry[] }) {
  const groups = useMemo(() => {
    const g = {
      '2xx': { count: 0, color: 'bg-emerald-500', text: 'text-emerald-400' },
      '3xx': { count: 0, color: 'bg-blue-500', text: 'text-blue-400' },
      '4xx': { count: 0, color: 'bg-amber-500', text: 'text-amber-400' },
      '5xx': { count: 0, color: 'bg-red-500', text: 'text-red-400' },
    }
    logs.forEach((l) => {
      const k = `${Math.floor(l.status_code / 100)}xx` as keyof typeof g
      if (g[k]) g[k].count++
    })
    return g
  }, [logs])

  const total = logs.length || 1
  const order: (keyof typeof groups)[] = ['2xx', '3xx', '4xx', '5xx']

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl">
      <div className="px-5 py-4 border-b border-slate-800">
        <h2 className="text-base font-semibold text-white">Distribuição de status</h2>
        <p className="text-sm text-slate-400 mt-0.5">
          {logs.length.toLocaleString('pt-BR')} requisições analisadas
        </p>
      </div>
      <div className="px-5 py-5 space-y-4">
        {order.map((k, i) => {
          const { count, color, text } = groups[k]
          const pct = Math.round((count / total) * 100)
          return (
            <div key={k}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium text-slate-200">{k}</span>
                <div className="flex items-center gap-2 text-sm tabular-nums">
                  <span className="text-slate-400">{count.toLocaleString('pt-BR')}</span>
                  <span className={`font-medium ${text}`}>{pct}%</span>
                </div>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.7, delay: 0.25 + i * 0.08, ease: EASE }}
                  className={`h-full rounded-full ${color}`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---------------- latency percentiles ---------------- */
function LatencyPercentiles({ logs }: { logs: LogEntry[] }) {
  const { p50, p90, p95, p99, max } = useMemo(() => {
    const sorted = logs.map((l) => l.duration_ms ?? 0).sort((a, b) => a - b)
    const pick = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ?? 0
    return {
      p50: pick(0.5),
      p90: pick(0.9),
      p95: pick(0.95),
      p99: pick(0.99),
      max: Math.max(...sorted, 1),
    }
  }, [logs])

  const rows = [
    { label: 'P50', value: p50 },
    { label: 'P90', value: p90 },
    { label: 'P95', value: p95 },
    { label: 'P99', value: p99 },
  ]

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl">
      <div className="px-5 py-4 border-b border-slate-800">
        <h2 className="text-base font-semibold text-white">Latência</h2>
        <p className="text-sm text-slate-400 mt-0.5">Percentis de tempo de resposta</p>
      </div>
      <div className="px-5 py-5 space-y-4">
        {rows.map((r, i) => {
          const pct = Math.min(100, Math.round((r.value / max) * 100))
          const tone =
            r.value >= 1000 ? 'bg-red-500' : r.value >= 200 ? 'bg-amber-500' : 'bg-emerald-500'
          return (
            <div key={r.label}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium text-slate-200">{r.label}</span>
                <span className="text-sm font-medium text-slate-200 tabular-nums">
                  {Math.round(r.value)}ms
                </span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.7, delay: 0.25 + i * 0.08, ease: EASE }}
                  className={`h-full rounded-full ${tone}`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---------------- top endpoints ---------------- */
function TopEndpoints({ logs }: { logs: LogEntry[] }) {
  const items = useMemo(() => {
    const map = new Map<string, { count: number; totalMs: number; errors: number }>()
    logs.forEach((l) => {
      const cur = map.get(l.endpoint) ?? { count: 0, totalMs: 0, errors: 0 }
      cur.count++
      cur.totalMs += l.duration_ms ?? 0
      if (l.status_code >= 400) cur.errors++
      map.set(l.endpoint, cur)
    })
    return Array.from(map.entries())
      .map(([endpoint, v]) => ({
        endpoint,
        count: v.count,
        avg: Math.round(v.totalMs / v.count),
        errors: v.errors,
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
  }, [logs])

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl">
      <div className="px-5 py-4 border-b border-slate-800">
        <h2 className="text-base font-semibold text-white">Endpoints mais acessados</h2>
        <p className="text-sm text-slate-400 mt-0.5">Top 5 por volume</p>
      </div>
      <div className="px-5 py-2">
        {items.length === 0 ? (
          <div className="flex items-center justify-center h-[160px] text-sm text-slate-400">
            Sem dados suficientes
          </div>
        ) : (
          items.map((it, i) => (
            <motion.div
              key={it.endpoint}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.25 + i * 0.05, ease: EASE }}
              className="flex items-center gap-3 py-3 border-b border-slate-800 last:border-0"
            >
              <span className="w-6 text-sm text-slate-500 tabular-nums">{i + 1}</span>
              <span className="flex-1 text-sm font-mono text-slate-200 truncate">
                {it.endpoint}
              </span>
              <span className="text-sm text-slate-300 tabular-nums w-14 text-right">
                {it.count}
              </span>
              <span
                className={`text-sm tabular-nums w-16 text-right ${
                  it.errors > 0 ? 'text-red-400' : 'text-slate-400'
                }`}
              >
                {it.avg}ms
              </span>
            </motion.div>
          ))
        )}
      </div>
    </div>
  )
}

/* ---------------- logs table ---------------- */
type SortKey = 'recent' | 'oldest' | 'slowest' | 'fastest'

function LogsTable({
  logs,
  search,
  onSearch,
}: {
  logs: LogEntry[]
  search: string
  onSearch: (v: string) => void
}) {
  const [sort, setSort] = useState<SortKey>('recent')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let arr = logs
    if (search.trim()) {
      const q = search.toLowerCase()
      arr = arr.filter((l) => l.endpoint.toLowerCase().includes(q))
    }
    const sorted = [...arr]
    switch (sort) {
      case 'oldest':
        sorted.sort((a, b) => +new Date(a.timestamp) - +new Date(b.timestamp))
        break
      case 'slowest':
        sorted.sort((a, b) => (b.duration_ms ?? 0) - (a.duration_ms ?? 0))
        break
      case 'fastest':
        sorted.sort((a, b) => (a.duration_ms ?? 0) - (b.duration_ms ?? 0))
        break
      default:
        sorted.sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))
    }
    return sorted
  }, [logs, search, sort])

  const copy = (endpoint: string, id: string) => {
    navigator.clipboard?.writeText(endpoint).then(() => {
      setCopied(id)
      setTimeout(() => setCopied((c) => (c === id ? null : c)), 1600)
    })
  }

  const sortOptions: { key: SortKey; label: string }[] = [
    { key: 'recent', label: 'Mais recentes' },
    { key: 'oldest', label: 'Mais antigos' },
    { key: 'slowest', label: 'Mais lentos' },
    { key: 'fastest', label: 'Mais rápidos' },
  ]

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl">
      <div className="px-5 py-4 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Registro de requisições</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            {filtered.length.toLocaleString('pt-BR')} registros
            {search && ` · filtrando por "${search}"`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="Buscar endpoint..."
              className="pl-9 pr-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-slate-700 w-full sm:w-56"
            />
          </div>
          <div className="relative">
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="appearance-none pl-9 pr-8 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-slate-700 cursor-pointer"
            >
              {sortOptions.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
            <ArrowUpDown className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <ChevronDown className="w-4 h-4 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>
      </div>

      <div className="px-5">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <ListChecks className="w-6 h-6 text-slate-500 mb-3" />
            <p className="text-base text-slate-300 font-medium">
              {search ? 'Nenhum resultado encontrado' : 'Nenhuma requisição registrada'}
            </p>
            <p className="text-sm text-slate-400 mt-1">
              {search
                ? 'Tente outro termo de busca.'
                : 'A atividade aparecerá aqui em tempo real.'}
            </p>
          </div>
        ) : (
          <div>
            {/* header */}
            <div className="hidden sm:flex items-center gap-4 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wide border-b border-slate-800">
              <span className="w-2" />
              <span className="flex-1">Endpoint</span>
              <span className="w-16 text-right">Status</span>
              <span className="w-20 text-right">Latência</span>
              <span className="w-24 text-right">Horário</span>
              <span className="w-5" />
            </div>
            {filtered.map((log, i) => {
              const id = String(log.id ?? `${log.timestamp}-${i}`)
              const isOk = log.status_code < 400
              const isOpen = expanded === id
              const dur = log.duration_ms ?? 0
              const durClass =
                dur >= 1000
                  ? 'text-red-400'
                  : dur >= 200
                  ? 'text-amber-400'
                  : 'text-slate-300'
              const time = new Date(log.timestamp).toLocaleTimeString('pt-BR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })
              return (
                <div key={id} className="border-b border-slate-800 last:border-0">
                  <motion.button
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.4) }}
                    onClick={() => setExpanded(isOpen ? null : id)}
                    className="w-full flex items-center gap-4 py-3 text-left hover:bg-slate-800/40 rounded-lg px-2 -mx-2 transition-colors"
                  >
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        isOk ? 'bg-emerald-400' : 'bg-red-400'
                      }`}
                    />
                    <span className="flex-1 text-sm font-mono text-slate-200 truncate">
                      {log.endpoint}
                    </span>
                    <span
                      className={`text-sm font-medium tabular-nums px-2 py-0.5 rounded ${
                        isOk ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'
                      }`}
                    >
                      {log.status_code}
                    </span>
                    <span className={`text-sm tabular-nums w-20 text-right ${durClass}`}>
                      {dur}ms
                    </span>
                    <span className="hidden sm:inline-block text-sm tabular-nums w-24 text-right text-slate-400">
                      {time}
                    </span>
                    <ChevronDown
                      className={`w-4 h-4 text-slate-500 transition-transform ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </motion.button>
                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: EASE }}
                        className="overflow-hidden"
                      >
                        <div className="pb-4 pl-6 pr-2 space-y-2">
                          <div className="flex items-start gap-2">
                            <span className="text-sm text-slate-500 w-24 flex-shrink-0">
                              Endpoint
                            </span>
                            <code className="text-sm font-mono text-slate-200 break-all flex-1">
                              {log.endpoint}
                            </code>
                            <button
                              onClick={() => copy(log.endpoint, id)}
                              className="text-slate-400 hover:text-slate-200 p-1 rounded transition-colors"
                              aria-label="Copiar endpoint"
                            >
                              {copied === id ? (
                                <Check className="w-4 h-4 text-emerald-400" />
                              ) : (
                                <Copy className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                          <div className="flex items-start gap-2">
                            <span className="text-sm text-slate-500 w-24 flex-shrink-0">
                              Timestamp
                            </span>
                            <span className="text-sm font-mono text-slate-200 tabular-nums">
                              {new Date(log.timestamp).toLocaleString('pt-BR')}
                            </span>
                          </div>
                          <div className="flex items-start gap-2">
                            <span className="text-sm text-slate-500 w-24 flex-shrink-0">
                              Status
                            </span>
                            <span
                              className={`text-sm font-medium ${
                                isOk ? 'text-emerald-400' : 'text-red-400'
                              }`}
                            >
                              {log.status_code} {isOk ? '(sucesso)' : '(erro)'}
                            </span>
                          </div>
                          <div className="flex items-start gap-2">
                            <span className="text-sm text-slate-500 w-24 flex-shrink-0">
                              Latência
                            </span>
                            <span className={`text-sm font-medium ${durClass}`}>
                              {dur}ms
                            </span>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------- page ---------------- */
export default function DashboardPage() {
  const [stats, setStats] = useState<LogStats | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [search, setSearch] = useState('')

  const fetchData = useCallback(async (isInitial = false) => {
    if (isInitial) setInitialLoading(true)
    else setRefreshing(true)
    setError(null)

    try {
      const [statsRes, logsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/logs?limit=1`),
        fetch(`${API_BASE_URL}/api/logs?limit=${PAGE_SIZE}&sort=desc`),
      ])
      if (!statsRes.ok || !logsRes.ok) throw new Error('Bad response')

      const [statsData, logsData] = await Promise.all([statsRes.json(), logsRes.json()])
      if (statsData?.stats) setStats(statsData.stats)
      if (Array.isArray(logsData?.logs)) setLogs(logsData.logs)
      setLastUpdated(new Date())
    } catch {
      setError('Não foi possível carregar os dados. Verifique a conexão com o backend.')
    } finally {
      setInitialLoading(false)
      setRefreshing(false)
    }
  }, [])

  // feedback de carregamento: fetchData faz setInitialLoading/setRefreshing e
  // setError síncronos (antes do await) — é refetch imperativo, não sincronização de estado
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData(true)
  }, [fetchData])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(() => fetchData(false), 30_000)
    return () => clearInterval(id)
  }, [autoRefresh, fetchData])

  const total = stats?.total ?? 0
  const errors = stats?.errors ?? 0
  const successes = Math.max(0, total - errors)
  const avgMs = Math.round(stats?.avg_duration_ms ?? 0)
  const successRate =
    total > 0 ? Math.max(0, Math.min(100, Math.round((successes / total) * 100))) : null

  // sparkline source: últimos 24 buckets de volume derivado dos logs
  const nowMs = lastUpdated?.getTime() ?? 0
  const spark = useMemo(() => {
    const buckets = new Array(24).fill(0)
    if (!nowMs) return buckets
    logs.forEach((l) => {
      const t = new Date(l.timestamp).getTime()
      const diffH = Math.floor((nowMs - t) / 3600_000)
      if (diffH >= 0 && diffH < 24) buckets[23 - diffH]++
    })
    return buckets
  }, [logs, nowMs])

  const showFullError = !initialLoading && !stats && !!error
  const showInlineError = !initialLoading && !!stats && !!error

  return (
    <div className="space-y-6">
      {/* progress bar topo (durante refresh) */}
      <AnimatePresence>
        {refreshing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed top-0 left-0 right-0 h-0.5 bg-slate-800 z-50 overflow-hidden"
          >
            <motion.div
              className="h-full w-1/3 bg-emerald-500"
              initial={{ x: '-100%' }}
              animate={{ x: '300%' }}
              transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white tracking-tight">Dashboard</h1>
          <p className="text-base text-slate-400 mt-1">
            Visão geral do sistema
            {lastUpdated && (
              <span className="text-slate-500">
                {' · '}Atualizado às{' '}
                {lastUpdated.toLocaleTimeString('pt-BR', {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh((v) => !v)}
            className={`flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border transition-colors ${
              autoRefresh
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30 hover:bg-emerald-500/15'
                : 'text-slate-300 bg-slate-900 border-slate-800 hover:bg-slate-800'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                autoRefresh ? 'bg-emerald-400' : 'bg-slate-500'
              }`}
            />
            {autoRefresh ? 'Auto 30s' : 'Auto'}
          </button>
          <button
            onClick={() => fetchData(false)}
            disabled={initialLoading || refreshing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-200 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Atualizando' : 'Atualizar'}
          </button>
        </div>
      </div>

      {showInlineError && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="flex items-center justify-between gap-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <p className="text-sm text-red-300 truncate">{error}</p>
          </div>
          <button
            onClick={() => fetchData(false)}
            className="text-sm font-medium text-red-300 hover:text-red-200 whitespace-nowrap"
          >
            Tentar novamente
          </button>
        </motion.div>
      )}

      {initialLoading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[130px]" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Skeleton className="h-[260px]" />
            <Skeleton className="h-[260px]" />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Skeleton className="h-[260px]" />
            <Skeleton className="h-[260px]" />
          </div>
          <Skeleton className="h-[400px]" />
        </div>
      ) : showFullError ? (
        <div className="flex flex-col items-center justify-center py-20 text-center bg-slate-900 border border-slate-800 rounded-xl">
          <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
            <AlertTriangle className="w-6 h-6 text-red-400" />
          </div>
          <h3 className="text-lg font-semibold text-white mb-1">Erro ao carregar</h3>
          <p className="text-base text-slate-400 max-w-md mb-6">{error}</p>
          <button
            onClick={() => fetchData(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Tentar novamente
          </button>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Total de requisições"
              value={total}
              icon={<Activity className="w-5 h-5" />}
              subtext="todas as requisições"
              spark={spark}
              index={0}
            />
            <StatCard
              label="Sucessos"
              value={successes}
              icon={<CheckCircle2 className="w-5 h-5" />}
              tone="positive"
              subtext={successRate !== null ? `${successRate}% de taxa` : '—'}
              index={1}
            />
            <StatCard
              label="Erros"
              value={errors}
              icon={<XCircle className="w-5 h-5" />}
              tone={errors > 0 ? 'negative' : 'neutral'}
              subtext={
                total > 0 ? `${Math.round((errors / total) * 100)}% do total` : '—'
              }
              index={2}
            />
            <StatCard
              label="Tempo médio"
              value={avgMs}
              format={(n) => `${n}ms`}
              icon={<Clock className="w-5 h-5" />}
              subtext="por requisição"
              index={3}
            />
          </div>

          {/* Volume + Status */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2, ease: EASE }}
            className="grid grid-cols-1 lg:grid-cols-2 gap-4"
          >
            <VolumeChart logs={logs} nowMs={lastUpdated?.getTime() ?? 0} />
            <StatusDistribution logs={logs} />
          </motion.div>

          {/* Latency + Top endpoints */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.28, ease: EASE }}
            className="grid grid-cols-1 lg:grid-cols-2 gap-4"
          >
            <LatencyPercentiles logs={logs} />
            <TopEndpoints logs={logs} />
          </motion.div>

          {/* Logs table */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.36, ease: EASE }}
          >
            <LogsTable logs={logs} search={search} onSearch={setSearch} />
          </motion.div>

          {/* About */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-2">
              <Server className="w-4 h-4 text-slate-400" />
              <h2 className="text-base font-semibold text-white">Sobre o Trivor</h2>
            </div>
            <p className="text-base text-slate-400 leading-relaxed max-w-3xl">
              Trivor é uma ferramenta de inteligência para currículos e perfis
              profissionais. Analisa compatibilidade com vagas, otimiza para ATS e gera
              insights baseados em dados do mercado.
            </p>
          </div>
        </>
      )}
    </div>
  )
}