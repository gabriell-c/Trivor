'use client'
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
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
} from 'lucide-react'
import type { LogEntry, LogStats } from '../types/analysis'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { useDebounce } from '../hooks/useDebounce'
import { CustomCheckbox } from '../components/CustomCheckbox'
import { API_BASE_URL } from '../lib/api'

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

      const res = await fetch(`/api/logs?${params}`)
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

  useEffect(() => { fetchLogs() }, [fetchLogs])

  const handleClear = async () => {
    await fetch(`${API_BASE_URL}/api/logs`, { method: 'DELETE' })
    setLogs([])
    setStats(null)
    setShowClearDialog(false)
  }

  const truncateBody = (body: string | null, max = 200) => {
    if (!body) return null
    return body.length > max ? body.slice(0, max) + '...' : body
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Logs de Requisições</h1>
        <p className="text-slate-400 mt-1">Histórico de todas as requisições ao backend</p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total" value={stats.total} icon={<Clock className="w-5 h-5" />} color="text-blue-400" />
          <StatCard label="Sucessos" value={stats.successes} icon={<CheckCircle className="w-5 h-5" />} color="text-green-400" />
          <StatCard label="Erros" value={stats.errors} icon={<AlertCircle className="w-5 h-5" />} color="text-red-400" />
          <StatCard label="Média (ms)" value={Math.round(stats.avg_duration_ms)} icon={<RefreshCw className="w-5 h-5" />} color="text-purple-400" />
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Filtrar por endpoint..."
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setOffset(0) }}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
        <CustomCheckbox
          checked={errorOnly}
          onChange={(v) => { setErrorOnly(v); setOffset(0) }}
          label="Somente erros"
        />
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
        <button
          onClick={() => setShowClearDialog(true)}
          className="flex items-center gap-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-sm rounded-lg transition-colors"
        >
          <Trash2 className="w-4 h-4" />
          Limpar
        </button>
      </div>

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

      {logs.length === 0 && !loading ? (
        <div className="text-center py-16 text-slate-500">
          <Clock className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>Nenhuma requisição registrada ainda.</p>
        </div>
      ) : (
        <div className="border border-slate-700 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-800/50 text-slate-400 text-left">
                <th className="px-4 py-3 font-medium">Timestamp</th>
                <th className="px-4 py-3 font-medium">Método</th>
                <th className="px-4 py-3 font-medium">Endpoint</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Duração</th>
                <th className="px-4 py-3 font-medium">Erro</th>
                <th className="px-4 py-3 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {logs.map((log) => (
                <motion.tr
                  key={log.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="hover:bg-slate-800/30"
                >
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap text-xs">
                    {formatDate(log.timestamp)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-mono ${
                      log.method === 'POST' ? 'bg-green-500/20 text-green-400' :
                      log.method === 'GET' ? 'bg-blue-500/20 text-blue-400' :
                      'bg-slate-500/20 text-slate-400'
                    }`}>
                      {log.method}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-300 text-xs">{log.endpoint}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      log.status_code < 400 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {log.status_code}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{log.duration_ms}ms</td>
                  <td className="px-4 py-3 text-red-400 max-w-xs truncate text-xs">
                    {log.error || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setSelectedLog(log)}
                      className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                      title="Ver detalhes"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AnimatePresence>
        {selectedLog && (
          <LogDetailModal
            log={selectedLog}
            onClose={() => setSelectedLog(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function StatCard({ label, value, icon, color }: { label: string; value: number | string; icon: React.ReactNode; color: string }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg bg-slate-700/50 flex items-center justify-center ${color}`}>
        {icon}
      </div>
      <div>
        <div className="text-lg font-bold text-white">{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  )
}

function LogDetailModal({ log, onClose }: { log: LogEntry; onClose: () => void }) {
  const isFallback = Boolean(log.fallback_used)
  const isDocling = log.extractor === 'docling' || log.extractor === 'docling_parse'
  const isPypdfium = log.extractor === 'pypdfium2'

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  // Parse response summary if it looks like JSON
  let parsedResponse: any = null
  let tokensInfo: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null = null
  let apiInfo: { model: string; request_id: string; response_time_ms: number } | null = null
  if (log.response_summary) {
    try {
      parsedResponse = JSON.parse(log.response_summary)
      tokensInfo = parsedResponse.uso_tokens || null
      apiInfo = parsedResponse.api_info || null
    } catch {
      // not JSON, leave as plain text
    }
  }

  // Parse request body if it looks like JSON
  let parsedRequest: any = null
  if (log.request_body) {
    try {
      parsedRequest = JSON.parse(log.request_body)
    } catch {
      // not JSON
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
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        className="relative bg-slate-900 border border-slate-700 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/60">
          <div className="flex items-center gap-3">
            <div className={`px-2.5 py-1 rounded text-xs font-mono font-bold ${
              log.method === 'POST' ? 'bg-green-500/20 text-green-400' :
              log.method === 'GET' ? 'bg-blue-500/20 text-blue-400' :
              'bg-slate-500/20 text-slate-400'
            }`}>
              {log.method}
            </div>
            <span className="font-mono text-sm text-slate-200">{log.endpoint}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${
              log.status_code < 400 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            }`}>
              {log.status_code}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Top row: timeline + status badges */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <Clock className="w-4 h-4" />
              <span>{formatDate(log.timestamp)}</span>
            </div>
            <div className="h-4 w-px bg-slate-700" />
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <RefreshCw className="w-4 h-4" />
              <span className="font-mono">{formatDuration(log.duration_ms)}</span>
            </div>
            {apiInfo?.request_id && (
              <>
                <div className="h-4 w-px bg-slate-700" />
                <div className="flex items-center gap-1.5 text-slate-500 text-xs font-mono">
                  <Server className="w-3 h-3" />
                  <span className="truncate max-w-[200px]">{apiInfo.request_id}</span>
                </div>
              </>
            )}
          </div>

          {/* === REQUEST INFO === */}
          {parsedRequest && (
            <section>
              <SectionHeader icon={<Code className="w-3.5 h-3.5" />} label="Requisição" />
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 grid grid-cols-2 gap-x-6 gap-y-2.5">
                {parsedRequest.model && (
                  <Field label="Modelo" value={parsedRequest.model} />
                )}
                {parsedRequest.area && (
                  <Field label="Área de Atuação" value={parsedRequest.area} />
                )}
                {parsedRequest.target_role && (
                  <Field label="Cargo Alvo" value={parsedRequest.target_role} />
                )}
                {parsedRequest.filename && (
                  <Field label="Arquivo" value={parsedRequest.filename} />
                )}
                {parsedRequest.file_size_bytes && (
                  <Field label="Tamanho do Arquivo" value={formatBytes(parsedRequest.file_size_bytes)} />
                )}
                {parsedRequest.job_description_present !== undefined && (
                  <Field
                    label="Job Description"
                    value={parsedRequest.job_description_present ? `${parsedRequest.job_description_len} chars` : 'Não informada'}
                    valueClass={parsedRequest.job_description_present ? 'text-emerald-400' : 'text-slate-500'}
                  />
                )}
                {parsedRequest.extractor_error && (
                  <div className="col-span-2">
                    <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Erro do Docling</div>
                    <p className="text-xs text-amber-400 font-mono break-all">{parsedRequest.extractor_error}</p>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* === TECH STACK === */}
          <section>
            <SectionHeader icon={<Cpu className="w-3.5 h-3.5" />} label="Tecnologia" />
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 space-y-3">
              {/* Modelo IA */}
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">Modelo IA</span>
                <span className="font-mono text-sm text-white bg-slate-700/60 px-2.5 py-0.5 rounded border border-slate-600">
                  {log.model || apiInfo?.model || '—'}
                </span>
              </div>

              {/* Extractor badge */}
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">Extractor</span>
                <div className="flex items-center gap-2">
                  {isDocling && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      <CheckCircle className="w-3 h-3" />
                      Docling
                    </span>
                  )}
                  {isPypdfium && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                      <AlertCircle className="w-3 h-3" />
                      pypdfium2
                    </span>
                  )}
                  {!log.extractor && <span className="text-slate-500 text-sm">—</span>}
                </div>
              </div>

              {/* Fallback */}
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">Fallback</span>
                {isFallback ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                    <ArrowDownUp className="w-3 h-3" />
                    Ativado → {log.fallback_level || 'pypdfium2'}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-500/15 text-slate-400 border border-slate-500/30">
                    <ShieldCheck className="w-3 h-3" />
                    Disponível
                  </span>
                )}
              </div>

              {/* API Key */}
              {log.api_key_preview && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 text-sm">API Key</span>
                  <span className="font-mono text-xs text-slate-500 bg-slate-700/30 px-2 py-0.5 rounded">{log.api_key_preview}</span>
                </div>
              )}
            </div>
          </section>

          {/* === TOKENS === */}
          {tokensInfo && (tokensInfo.prompt_tokens > 0 || tokensInfo.completion_tokens > 0) && (
            <section>
              <SectionHeader icon={<Cpu className="w-3.5 h-3.5" />} label="Uso de Tokens" />
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                <div className="grid grid-cols-3 gap-4">
                  <TokenStat label="Input (prompt)" value={tokensInfo.prompt_tokens} color="text-blue-400" />
                  <TokenStat label="Output (completion)" value={tokensInfo.completion_tokens} color="text-purple-400" />
                  <TokenStat label="Total" value={tokensInfo.total_tokens} color="text-white" highlight />
                </div>
              </div>
            </section>
          )}

          {/* === ERROR === */}
          {log.error && (
            <section>
              <SectionHeader icon={<ShieldAlert className="w-3.5 h-3.5 text-red-400" />} label="Erro" />
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                <p className="text-red-300 text-sm font-mono whitespace-pre-wrap break-words">{log.error}</p>
              </div>
            </section>
          )}

          {/* === Parsed Response (structured) === */}
          {parsedResponse && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <SectionHeader icon={<Server className="w-3.5 h-3.5" />} label="Resposta da IA" />
                <button
                  onClick={() => copyToClipboard(log.response_summary!)}
                  className="text-xs text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1"
                >
                  Copiar JSON
                </button>
              </div>
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg overflow-hidden">
                {/* Score badge */}
                {parsedResponse.nota !== undefined && (
                  <div className="px-4 py-3 border-b border-slate-700 flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 text-xs">Nota</span>
                      <span className={`text-xl font-bold ${
                        parsedResponse.nota >= 70 ? 'text-emerald-400' :
                        parsedResponse.nota >= 50 ? 'text-amber-400' : 'text-red-400'
                      }`}>
                        {parsedResponse.nota}/100
                      </span>
                    </div>
                    {parsedResponse.score_ats !== undefined && (
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400 text-xs">ATS</span>
                        <span className="text-sm font-mono text-blue-400">{parsedResponse.score_ats}%</span>
                      </div>
                    )}
                  </div>
                )}
                {/* Key sections summary */}
                <div className="p-4 space-y-3 max-h-64 overflow-y-auto">
                  {parsedResponse.resumo_executivo && (
                    <div>
                      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Resumo Executivo</div>
                      <p className="text-sm text-slate-300 leading-relaxed">{parsedResponse.resumo_executivo}</p>
                    </div>
                  )}
                  {parsedResponse.pontos_fortes && parsedResponse.pontos_fortes.length > 0 && (
                    <div>
                      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Pontos Fortes</div>
                      <ul className="space-y-1">
                        {parsedResponse.pontos_fortes.slice(0, 5).map((p: string, i: number) => (
                          <li key={i} className="text-sm text-emerald-300 flex items-start gap-2">
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {parsedResponse.pontos_fracos && parsedResponse.pontos_fracos.length > 0 && (
                    <div>
                      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Pontos de Atenção</div>
                      <ul className="space-y-1">
                        {parsedResponse.pontos_fracos.slice(0, 5).map((p: string, i: number) => (
                          <li key={i} className="text-sm text-amber-300 flex items-start gap-2">
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {/* "Ver JSON completo" toggle - just show raw JSON below */}
                <div className="border-t border-slate-700">
                  <details className="group">
                    <summary className="px-4 py-2 text-xs text-slate-500 hover:text-slate-300 cursor-pointer select-none transition-colors">
                      Ver JSON completo da resposta
                    </summary>
                    <pre className="px-4 pb-3 text-xs font-mono text-slate-400 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                      {log.response_summary}
                    </pre>
                  </details>
                </div>
              </div>
            </section>
          )}

          {/* Fallback: raw request/response if not parsed */}
          {!parsedRequest && log.request_body && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <SectionHeader icon={<Code className="w-3.5 h-3.5" />} label="Request Body" />
                <button onClick={() => copyToClipboard(log.request_body!)} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">Copiar</button>
              </div>
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">{log.request_body}</pre>
              </div>
            </section>
          )}

          {!parsedResponse && log.response_summary && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <SectionHeader icon={<Server className="w-3.5 h-3.5" />} label="Response Summary" />
                <button onClick={() => copyToClipboard(log.response_summary!)} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">Copiar</button>
              </div>
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">{log.response_summary}</pre>
              </div>
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-700 px-6 py-3 flex justify-end bg-slate-800/30">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-lg transition-colors"
          >
            Fechar
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

function SectionHeader({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
      {icon}
      {label}
    </h3>
  )
}

function Field({ label, value, valueClass = 'text-white' }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500 text-xs uppercase tracking-wide">{label}</span>
      <span className={`text-sm font-medium ${valueClass}`}>{value}</span>
    </div>
  )
}

function TokenStat({ label, value, color, highlight }: { label: string; value: number; color: string; highlight?: boolean }) {
  return (
    <div className="text-center">
      <div className={`text-lg font-bold font-mono ${color}`}>{value.toLocaleString('pt-BR')}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  )
}

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


