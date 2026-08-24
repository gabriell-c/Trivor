'use client'
import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, CheckCircle, Clock, Filter, RefreshCw, Trash2 } from 'lucide-react'

interface LogEntry {
  id: string
  timestamp: string
  endpoint: string
  method: string
  status: number
  duration_ms: number
  error?: string
  ip?: string
}

interface LogStats {
  total: number
  errors: number
  successes: number
  avg_duration_ms: number
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('')
  const [errorOnly, setErrorOnly] = useState(false)
  const [offset, setOffset] = useState(0)
  const LIMIT = 100

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        limit: String(LIMIT),
        offset: String(offset),
      })
      if (filter) params.set('endpoint', filter)
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
  }, [filter, errorOnly, offset])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  const handleClear = async () => {
    if (!confirm('Limpar todos os logs?')) return
    await fetch('/api/logs', { method: 'DELETE' })
    setLogs([])
    setStats(null)
  }

  return (
    <div className="space-y-6">
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
        <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={errorOnly}
            onChange={(e) => { setErrorOnly(e.target.checked); setOffset(0) }}
            className="rounded border-slate-600 bg-slate-800"
          />
          Somente erros
        </label>
        <button onClick={fetchLogs} disabled={loading} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
        <button onClick={handleClear} className="flex items-center gap-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-sm rounded-lg transition-colors">
          <Trash2 className="w-4 h-4" />
          Limpar
        </button>
      </div>

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
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                    {new Date(log.timestamp).toLocaleString('pt-BR')}
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
                  <td className="px-4 py-3 font-mono text-slate-300">{log.endpoint}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      log.status < 400 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {log.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">{log.duration_ms}ms</td>
                  <td className="px-4 py-3 text-red-400 max-w-xs truncate">
                    {log.error || '—'}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
