'use client'
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Filter,
  RefreshCw,
  Trash2,
  Eye,
  X,
  Cpu,
  ArrowDownUp,
  ShieldAlert,
  ShieldCheck,
  Code,
  Server,
  FileText,
  Copy,
  Check,
  Search,
} from 'lucide-react'
import type { LogEntry, LogStats } from '../types/analysis'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useDebounce } from '../hooks/useDebounce'
import { CustomCheckbox } from '../components/CustomCheckbox'
import { API_BASE_URL } from '../lib/api'

const EASE = [0.16, 1, 0.3, 1] as const

/* ═══════════ Cores semânticas (sólidas + glow) ═══════════ */
const TONE = {
  blue: {
    wrap: 'bg-blue-500/15 border-blue-400/30 text-blue-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(59,130,246,0.4)]',
  },
  green: {
    wrap: 'bg-emerald-500/15 border-emerald-400/30 text-emerald-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(16,185,129,0.4)]',
  },
  red: {
    wrap: 'bg-rose-500/15 border-rose-400/30 text-rose-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(244,63,94,0.4)]',
  },
  purple: {
    wrap: 'bg-purple-500/15 border-purple-400/30 text-purple-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(168,85,247,0.4)]',
  },
  amber: {
    wrap: 'bg-amber-500/15 border-amber-400/30 text-amber-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(245,158,11,0.4)]',
  },
  slate: {
    wrap: 'bg-slate-800 border-slate-700 text-slate-300',
    glow: '',
  },
} as const

/* ═══════════ Input custom (sem estilo nativo) ═══════════ */
function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div className="relative flex-1">
      <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full h-12 pl-10 pr-4 rounded-xl bg-slate-900 border border-slate-700 text-base font-medium text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-purple-400 focus:ring-4 focus:ring-purple-500/25"
      />
    </div>
  )
}

/* ═══════════ Copy button (com feedback) ═══════════ */
function CopyBtn({ text, label = 'Copiar' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    })
  }
  return (
    <motion.button
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={copy}
      className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 transition-colors"
    >
      <AnimatePresence mode="wait" initial={false}>
        {copied ? (
          <motion.span
            key="check"
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.5, opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="inline-flex items-center gap-1.5 text-emerald-300"
          >
            <Check className="w-3.5 h-3.5" />
            Copiado
          </motion.span>
        ) : (
          <motion.span
            key="copy"
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.5, opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="inline-flex items-center gap-1.5"
          >
            <Copy className="w-3.5 h-3.5" />
            {label}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  )
}

/* ═══════════ Page ═══════════ */
export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('')
  const [errorOnly, setErrorOnly] = useState(false)
  const [offset, setOffset] = useState(0)
  const [showClearDialog, setShowClearDialog] = useState(false)
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null)
  const LIMIT = 100

  const debouncedFilter = useDebounce(filter, 300)

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        limit: String(LIMIT),
        offset: String(offset),
      })
      if (debouncedFilter) params.set('endpoint', debouncedFilter)
      if (errorOnly) params.set('error_only', 'true')

      const res = await fetch(`${API_BASE_URL}/api/logs?${params}`)
      const data = await res.json()
      setLogs(data.logs || [])
      setStats(data.stats || null)
    } catch {
      setLogs([])
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [debouncedFilter, errorOnly, offset])

  // fetchLogs faz setLoading(true) síncrono (feedback de carregamento antes do await) —
  // é refetch imperativo quando os filtros mudam, não sincronização de estado
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchLogs()
  }, [fetchLogs])

  const handleClear = async () => {
    await fetch(`${API_BASE_URL}/api/logs`, { method: 'DELETE' })
    setLogs([])
    setStats(null)
    setShowClearDialog(false)
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-10 space-y-8">
      {/* ──────── Header ──────── */}
      <motion.header
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
      >
        <motion.span
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1, ease: EASE }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/15 border border-purple-400/30 text-purple-200 text-xs font-semibold mb-4"
        >
          <span className="relative flex h-2 w-2">
            <motion.span
              animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
              className="absolute inset-0 rounded-full bg-purple-400"
            />
            <span className="relative w-2 h-2 rounded-full bg-purple-400" />
          </span>
          Observabilidade
        </motion.span>

        <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight">
          Logs de Requisições
        </h1>
        <p className="text-base text-slate-300 mt-2.5 max-w-xl leading-relaxed">
          Histórico completo de todas as requisições ao backend, com detalhes de extração, tokens e resposta da IA.
        </p>
      </motion.header>

      {/* ──────── Stats ──────── */}
      {stats && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
          className="grid grid-cols-2 md:grid-cols-4 gap-3"
        >
          <StatCard
            label="Total"
            value={stats.total}
            icon={<Clock className="w-6 h-6 text-blue-300" />}
            tone={TONE.blue}
            delay={0.05}
          />
          <StatCard
            label="Sucessos"
            value={stats.successes}
            icon={<CheckCircle className="w-6 h-6 text-emerald-300" />}
            tone={TONE.green}
            delay={0.1}
          />
          <StatCard
            label="Erros"
            value={stats.errors}
            icon={<AlertCircle className="w-6 h-6 text-rose-300" />}
            tone={TONE.red}
            delay={0.15}
          />
          <StatCard
            label="Média (ms)"
            value={Math.round(stats.avg_duration_ms)}
            icon={<RefreshCw className="w-6 h-6 text-purple-300" />}
            tone={TONE.purple}
            delay={0.2}
          />
        </motion.div>
      )}

      {/* ──────── Filtros ──────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15, ease: EASE }}
        className="flex flex-col sm:flex-row gap-3 items-stretch"
      >
        <SearchInput
          value={filter}
          onChange={(v) => {
            setFilter(v)
            setOffset(0)
          }}
          placeholder="Filtrar por endpoint..."
        />
        <div className="flex items-center gap-3">
          <CustomCheckbox
            checked={errorOnly}
            onChange={(v) => {
              setErrorOnly(v)
              setOffset(0)
            }}
            label="Somente erros"
          />
          <motion.button
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={fetchLogs}
            disabled={loading}
            className="inline-flex items-center gap-2 h-12 px-4 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => setShowClearDialog(true)}
            className="inline-flex items-center gap-2 h-12 px-4 text-sm font-semibold text-rose-200 bg-rose-500/15 hover:bg-rose-500/25 border border-rose-400/30 rounded-xl transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Limpar
          </motion.button>
        </div>
      </motion.div>

      <ConfirmDialog
        isOpen={showClearDialog}
        title="Limpar Logs"
        message="Tem certeza que deseja remover todos os logs? Esta ação não pode ser desfeita."
        confirmLabel="Limpar"
        cancelLabel="Cancelar"
        variant="danger"
        onConfirm={handleClear}
        onCancel={() => setShowClearDialog(false)}
      />

      {/* ──────── Tabela ──────── */}
      {logs.length === 0 && !loading ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: EASE }}
          className="rounded-2xl border border-slate-700 bg-slate-900 px-6 py-16 text-center"
        >
          <motion.div
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="w-16 h-16 rounded-2xl bg-purple-500/15 border border-purple-400/30 shadow-[0_0_30px_-6px_rgba(168,85,247,0.5)] flex items-center justify-center mx-auto mb-5"
          >
            <Clock className="w-7 h-7 text-purple-300" />
          </motion.div>
          <h3 className="text-lg font-bold text-white">Nenhuma requisição registrada</h3>
          <p className="text-base text-slate-300 mt-2 max-w-sm mx-auto leading-relaxed">
            As requisições feitas ao backend aparecerão aqui automaticamente.
          </p>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: EASE }}
          className="rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden shadow-2xl shadow-black/40"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead>
                <tr className="bg-slate-800/80 text-slate-300 text-left border-b border-slate-700">
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Timestamp</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Método</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Endpoint</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Duração</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-center">Detalhes</th>
                  <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider">Erro</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/70">
                {logs.map((log, idx) => {
                  const isOk = log.status_code < 400
                  const methodTone =
                    log.method === 'POST'
                      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
                      : log.method === 'GET'
                      ? 'bg-blue-500/15 text-blue-300 border-blue-400/30'
                      : 'bg-slate-700/60 text-slate-200 border-slate-600'
                  return (
                    <motion.tr
                      key={log.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: Math.min(idx * 0.02, 0.2), ease: EASE }}
                      className="hover:bg-slate-800/50 transition-colors"
                    >
                      <td className="px-4 py-3.5 text-slate-300 font-mono text-xs whitespace-nowrap tabular-nums">
                        {formatDate(log.timestamp)}
                      </td>
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center h-6 px-2 rounded-md text-xs font-bold font-mono border ${methodTone}`}
                        >
                          {log.method}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <code className="font-mono text-sm text-slate-100">{log.endpoint}</code>
                      </td>
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1.5 h-6 px-2 rounded-md text-xs font-bold font-mono border ${
                            isOk
                              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
                              : 'bg-rose-500/15 text-rose-300 border-rose-400/30'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${isOk ? 'bg-emerald-400' : 'bg-rose-400'}`}
                          />
                          {log.status_code}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-slate-200 font-mono text-sm tabular-nums">
                        {log.duration_ms}ms
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <motion.button
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          onClick={() => setSelectedLog(log)}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
                          title="Ver detalhes"
                        >
                          <Eye className="w-4 h-4" />
                        </motion.button>
                      </td>
                      <td className="px-4 py-3.5 max-w-[220px]">
                        {log.error ? (
                          <span className="text-sm text-rose-300 truncate block" title={log.error}>
                            {log.error}
                          </span>
                        ) : (
                          <span className="text-sm text-slate-500">—</span>
                        )}
                      </td>
                    </motion.tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      <AnimatePresence>
        {selectedLog && <LogDetailModal log={selectedLog} onClose={() => setSelectedLog(null)} />}
      </AnimatePresence>
    </div>
  )
}

/* ═══════════ StatCard ═══════════ */
function StatCard({
  label,
  value,
  icon,
  tone,
  delay = 0,
}: {
  label: string
  value: number | string
  icon: React.ReactNode
  tone: (typeof TONE)[keyof typeof TONE]
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: EASE }}
      whileHover={{ y: -3 }}
      className="group flex items-center gap-4 rounded-xl border border-slate-700 bg-slate-900 p-4 hover:border-slate-600 transition-colors"
    >
      <div
        className={`w-12 h-12 rounded-xl border flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110 ${tone.wrap} ${tone.glow}`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-white leading-tight tabular-nums">{value}</div>
        <div className="text-sm font-medium text-slate-300 mt-0.5">{label}</div>
      </div>
    </motion.div>
  )
}

// Resposta serializada da análise de CV (JSON salvo em log.response_summary)
interface ParsedResponse {
  nota?: number
  score_ats?: number
  resumo_executivo?: string
  pontos_fortes?: string[]
  pontos_fracos?: string[]
  uso_tokens?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  api_info?: { model: string; request_id: string; response_time_ms: number }
}
// Corpo serializado da requisição (JSON salvo em log.request_body)
interface ParsedRequest {
  model?: string
  area?: string
  target_role?: string
  filename?: string
  file_size_bytes?: number
  job_description_present?: boolean
  job_description_len?: number
  extractor_error?: string
}

/* ═══════════ Modal de detalhes ═══════════ */
function LogDetailModal({ log, onClose }: { log: LogEntry; onClose: () => void }) {
  const [showRawText, setShowRawText] = useState(false)
  const reduce = useReducedMotion()
  const isFallback = Boolean(log.fallback_used)
  const isDocling = log.extractor === 'docling' || log.extractor === 'docling_parse'
  const isPypdfium = log.extractor === 'pypdfium2'

  let parsedResponse: ParsedResponse | null = null
  let tokensInfo: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null =
    null
  let apiInfo: { model: string; request_id: string; response_time_ms: number } | null = null
  if (log.response_summary) {
    try {
      parsedResponse = JSON.parse(log.response_summary) as ParsedResponse
      tokensInfo = parsedResponse.uso_tokens || null
      apiInfo = parsedResponse.api_info || null
    } catch {
      /* not JSON */
    }
  }

  let parsedRequest: ParsedRequest | null = null
  if (log.request_body) {
    try {
      parsedRequest = JSON.parse(log.request_body) as ParsedRequest
    } catch {
      /* not JSON */
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={reduce ? {} : { scale: 0.94, opacity: 0, y: 12 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={reduce ? {} : { scale: 0.94, opacity: 0, y: 12 }}
        transition={{ type: 'spring', damping: 28, stiffness: 320 }}
        className="relative bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl shadow-black/70"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-slate-700 bg-slate-800/60">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <span
              className={`inline-flex items-center h-7 px-2.5 rounded-md text-xs font-bold font-mono border shrink-0 ${
                log.method === 'POST'
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
                  : log.method === 'GET'
                  ? 'bg-blue-500/15 text-blue-300 border-blue-400/30'
                  : 'bg-slate-700/60 text-slate-200 border-slate-600'
              }`}
            >
              {log.method}
            </span>
            <code className="font-mono text-base font-medium text-white truncate">
              {log.endpoint}
            </code>
            <span
              className={`inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-xs font-bold font-mono border shrink-0 ${
                log.status_code < 400
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
                  : 'bg-rose-500/15 text-rose-300 border-rose-400/30'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  log.status_code < 400 ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              {log.status_code}
            </span>
          </div>
          <motion.button
            whileHover={{ scale: 1.1, rotate: 90 }}
            whileTap={{ scale: 0.9 }}
            onClick={onClose}
            className="p-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-700 transition-colors shrink-0"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </motion.button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Timeline meta */}
          <div className="flex items-center gap-3 flex-wrap text-sm">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-200">
              <Clock className="w-4 h-4 text-slate-400" />
              <span className="font-medium">{formatDate(log.timestamp)}</span>
            </span>
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-200">
              <RefreshCw className="w-4 h-4 text-slate-400" />
              <span className="font-mono font-medium">{formatDuration(log.duration_ms)}</span>
            </span>
            {apiInfo?.request_id && (
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono min-w-0">
                <Server className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span className="truncate max-w-[260px]">{apiInfo.request_id}</span>
              </span>
            )}
          </div>

          {/* Request info */}
          {parsedRequest && (
            <section>
              <SectionHeader icon={<Code className="w-4 h-4" />} label="Requisição" />
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
                {parsedRequest.model && <Field label="Modelo" value={parsedRequest.model} mono />}
                {parsedRequest.area && <Field label="Área de Atuação" value={parsedRequest.area} />}
                {parsedRequest.target_role && (
                  <Field label="Cargo Alvo" value={parsedRequest.target_role} />
                )}
                {parsedRequest.filename && <Field label="Arquivo" value={parsedRequest.filename} mono />}
                {parsedRequest.file_size_bytes && (
                  <Field
                    label="Tamanho do Arquivo"
                    value={formatBytes(parsedRequest.file_size_bytes)}
                    mono
                  />
                )}
                {parsedRequest.job_description_present !== undefined && (
                  <Field
                    label="Job Description"
                    value={
                      parsedRequest.job_description_present
                        ? `${parsedRequest.job_description_len} chars`
                        : 'Não informada'
                    }
                    valueClass={
                      parsedRequest.job_description_present ? 'text-emerald-300' : 'text-slate-400'
                    }
                  />
                )}
                {parsedRequest.extractor_error && (
                  <div className="col-span-full pt-2 border-t border-slate-700">
                    <div className="text-xs font-semibold text-slate-400 mb-1.5">Erro do Docling</div>
                    <p className="text-sm text-amber-300 font-mono break-all bg-amber-500/10 border border-amber-400/20 rounded-lg p-2.5">
                      {parsedRequest.extractor_error}
                    </p>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Tech stack */}
          <section>
            <SectionHeader icon={<Cpu className="w-4 h-4" />} label="Tecnologia" />
            <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 space-y-3.5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-slate-300">Modelo IA</span>
                <span className="font-mono text-sm font-semibold text-white bg-slate-900 px-3 py-1 rounded-lg border border-slate-700">
                  {log.model || apiInfo?.model || '—'}
                </span>
              </div>

              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-slate-300">Extractor</span>
                <div className="flex items-center gap-2">
                  {isDocling && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-400/30">
                      <CheckCircle className="w-3.5 h-3.5" />
                      Docling
                    </span>
                  )}
                  {isPypdfium && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-400/30">
                      <AlertCircle className="w-3.5 h-3.5" />
                      pypdfium2
                    </span>
                  )}
                  {!log.extractor && <span className="text-slate-400 text-sm">—</span>}
                </div>
              </div>

              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-slate-300">Fallback</span>
                {isFallback ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-400/30">
                    <ArrowDownUp className="w-3.5 h-3.5" />
                    Ativado → {log.fallback_level || 'pypdfium2'}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-700/60 text-slate-200 border border-slate-600">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    Disponível
                  </span>
                )}
              </div>

              {log.api_key_preview && (
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-slate-300">API Key</span>
                  <span className="font-mono text-xs font-medium text-slate-300 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-700">
                    {log.api_key_preview}
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* Tokens */}
          {tokensInfo &&
            (tokensInfo.prompt_tokens > 0 || tokensInfo.completion_tokens > 0) && (
              <section>
                <SectionHeader icon={<Cpu className="w-4 h-4" />} label="Uso de Tokens" />
                <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
                  <div className="grid grid-cols-3 gap-3">
                    <TokenStat
                      label="Input (prompt)"
                      value={tokensInfo.prompt_tokens}
                      color="text-blue-300"
                    />
                    <TokenStat
                      label="Output (completion)"
                      value={tokensInfo.completion_tokens}
                      color="text-purple-300"
                    />
                    <TokenStat
                      label="Total"
                      value={tokensInfo.total_tokens}
                      color="text-white"
                      highlight
                    />
                  </div>
                </div>
              </section>
            )}

          {/* Error */}
          {log.error && (
            <section>
              <SectionHeader
                icon={<ShieldAlert className="w-4 h-4 text-rose-300" />}
                label="Erro"
              />
              <div className="bg-rose-500/10 border border-rose-400/30 rounded-xl p-4">
                <p className="text-sm text-rose-200 font-mono whitespace-pre-wrap break-words leading-relaxed">
                  {log.error}
                </p>
              </div>
            </section>
          )}

          {/* Parsed response */}
          {parsedResponse && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-3">
                <SectionHeader icon={<Server className="w-4 h-4" />} label="Resposta da IA" noMargin />
                <CopyBtn text={log.response_summary!} label="Copiar JSON" />
              </div>
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden">
                {parsedResponse.nota !== undefined && (
                  <div className="px-5 py-4 border-b border-slate-700 flex items-center gap-6 flex-wrap">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm text-slate-400">Nota</span>
                      <span
                        className={`text-2xl font-bold tabular-nums ${
                          parsedResponse.nota >= 70
                            ? 'text-emerald-300'
                            : parsedResponse.nota >= 50
                            ? 'text-amber-300'
                            : 'text-rose-300'
                        }`}
                      >
                        {parsedResponse.nota}
                        <span className="text-base text-slate-500 font-normal">/100</span>
                      </span>
                    </div>
                    {parsedResponse.score_ats !== undefined && (
                      <div className="flex items-baseline gap-2">
                        <span className="text-sm text-slate-400">ATS</span>
                        <span className="text-lg font-bold font-mono text-blue-300">
                          {parsedResponse.score_ats}%
                        </span>
                      </div>
                    )}
                  </div>
                )}

                <div className="p-5 space-y-4 max-h-72 overflow-y-auto">
                  {parsedResponse.resumo_executivo && (
                    <div>
                      <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                        Resumo Executivo
                      </div>
                      <p className="text-sm text-slate-200 leading-relaxed">
                        {parsedResponse.resumo_executivo}
                      </p>
                    </div>
                  )}
                  {(parsedResponse.pontos_fortes?.length ?? 0) > 0 && (
                    <div>
                      <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                        Pontos Fortes
                      </div>
                      <ul className="space-y-1.5">
                        {parsedResponse.pontos_fortes?.slice(0, 5).map((p: string, i: number) => (
                          <li
                            key={i}
                            className="text-sm text-emerald-200 flex items-start gap-2 leading-relaxed"
                          >
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(parsedResponse.pontos_fracos?.length ?? 0) > 0 && (
                    <div>
                      <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                        Pontos de Atenção
                      </div>
                      <ul className="space-y-1.5">
                        {parsedResponse.pontos_fracos?.slice(0, 5).map((p: string, i: number) => (
                          <li
                            key={i}
                            className="text-sm text-amber-200 flex items-start gap-2 leading-relaxed"
                          >
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                <div className="border-t border-slate-700">
                  <details className="group">
                    <summary className="px-5 py-3 text-sm font-medium text-slate-400 hover:text-slate-200 cursor-pointer select-none transition-colors">
                      Ver JSON completo da resposta
                    </summary>
                    <pre className="px-5 pb-4 text-xs font-mono text-slate-300 whitespace-pre-wrap break-words max-h-72 overflow-y-auto leading-relaxed">
                      {log.response_summary}
                    </pre>
                  </details>
                </div>
              </div>
            </section>
          )}

          {/* Raw fallback */}
          {!parsedRequest && log.request_body && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-3">
                <SectionHeader icon={<Code className="w-4 h-4" />} label="Request Body" noMargin />
                <CopyBtn text={log.request_body} />
              </div>
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
                <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap break-words max-h-56 overflow-y-auto leading-relaxed">
                  {log.request_body}
                </pre>
              </div>
            </section>
          )}

          {!parsedResponse && log.response_summary && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-3">
                <SectionHeader icon={<Server className="w-4 h-4" />} label="Response Summary" noMargin />
                <CopyBtn text={log.response_summary} />
              </div>
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
                <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap break-words max-h-56 overflow-y-auto leading-relaxed">
                  {log.response_summary}
                </pre>
              </div>
            </section>
          )}

          {/* Texto extraído & prompt */}
          {(log.extracted_text || log.llm_prompt) && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-3">
                <SectionHeader
                  icon={<FileText className="w-4 h-4" />}
                  label="Texto Extraído & Prompt LLM"
                  noMargin
                />
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => setShowRawText((v) => !v)}
                  className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-semibold transition-colors border ${
                    showRawText
                      ? 'bg-blue-500/15 text-blue-200 border-blue-400/30 hover:bg-blue-500/25'
                      : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  <Eye className="w-3.5 h-3.5" />
                  {showRawText ? 'Ocultar' : 'Ver texto extraído'}
                </motion.button>
              </div>

              <AnimatePresence initial={false}>
                {showRawText && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: EASE }}
                    className="space-y-4 overflow-hidden"
                  >
                    {log.extracted_text && (
                      <div className="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden">
                        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-slate-700 bg-slate-800">
                          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                            Texto Extraído · {log.extracted_text.length.toLocaleString('pt-BR')} chars
                          </span>
                          <CopyBtn text={log.extracted_text} />
                        </div>
                        <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap break-words p-4 max-h-72 overflow-y-auto leading-relaxed">
                          {log.extracted_text}
                        </pre>
                      </div>
                    )}
                    {log.llm_prompt && (
                      <div className="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden">
                        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-slate-700 bg-slate-800">
                          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                            Prompt Enviado ao LLM · {log.llm_prompt.length.toLocaleString('pt-BR')}{' '}
                            chars
                          </span>
                          <CopyBtn text={log.llm_prompt} />
                        </div>
                        <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap break-words p-4 max-h-96 overflow-y-auto leading-relaxed">
                          {log.llm_prompt}
                        </pre>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-700 px-6 py-4 flex justify-end bg-slate-800/40">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={onClose}
            className="h-11 px-5 text-sm font-semibold text-slate-100 bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-xl transition-colors"
          >
            Fechar
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  )
}

/* ═══════════ SectionHeader ═══════════ */
function SectionHeader({
  icon,
  label,
  noMargin,
}: {
  icon: React.ReactNode
  label: string
  noMargin?: boolean
}) {
  return (
    <h3
      className={`text-sm font-bold text-slate-200 flex items-center gap-2 ${noMargin ? '' : 'mb-3'}`}
    >
      <span className="text-slate-400">{icon}</span>
      {label}
    </h3>
  )
}

/* ═══════════ Field ═══════════ */
function Field({
  label,
  value,
  valueClass = 'text-white',
  mono,
}: {
  label: string
  value: string
  valueClass?: string
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 min-w-0">
      <span className="text-sm font-medium text-slate-400 shrink-0">{label}</span>
      <span
        className={`text-sm font-semibold truncate ${valueClass} ${mono ? 'font-mono' : ''}`}
        title={value}
      >
        {value}
      </span>
    </div>
  )
}

/* ═══════════ TokenStat ═══════════ */
function TokenStat({
  label,
  value,
  color,
  highlight,
}: {
  label: string
  value: number
  color: string
  highlight?: boolean
}) {
  return (
    <div
      className={`text-center p-3 rounded-xl ${
        highlight ? 'bg-slate-900 border border-slate-700' : ''
      }`}
    >
      <div className={`text-2xl font-bold font-mono tabular-nums ${color}`}>
        {value.toLocaleString('pt-BR')}
      </div>
      <div className="text-sm font-medium text-slate-400 mt-1">{label}</div>
    </div>
  )
}

/* ═══════════ Date format ═══════════ */
function formatDate(iso: string) {
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}