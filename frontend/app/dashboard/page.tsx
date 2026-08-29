'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Clock,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Activity,
  Server,
} from 'lucide-react'
import type { LogEntry, LogStats } from '../types/analysis'

function StatCard({
  label,
  value,
  icon,
  color,
  subtext,
}: {
  label: string
  value: string | number
  icon: React.ReactNode
  color: string
  subtext?: string
}) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <span className="text-slate-400 text-sm">{label}</span>
        <span className={color}>{icon}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <div className="text-2xl font-bold text-white">{value}</div>
        {subtext && <span className="text-xs text-slate-500">{subtext}</span>}
      </div>
    </div>
  )
}

function RecentLogItem({
  endpoint,
  status_code,
  duration_ms,
  timestamp,
}: {
  endpoint: string
  status_code: number
  duration_ms: number
  timestamp: string
}) {
  const isOk = status_code < 400
  const time = new Date(timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-slate-700/30 last:border-0">
      <span
        className={`w-2 h-2 rounded-full flex-shrink-0 ${
          isOk ? 'bg-emerald-400' : 'bg-red-400'
        }`}
      />
      <span className="text-slate-300 text-sm font-mono flex-1 truncate">{endpoint}</span>
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          isOk
            ? 'bg-emerald-500/10 text-emerald-400'
            : 'bg-red-500/10 text-red-400'
        }`}
      >
        {status_code}
      </span>
      <span className="text-slate-500 text-xs">{duration_ms}ms</span>
      <span className="text-slate-600 text-xs">{time}</span>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<LogStats | null>(null)
  const [recentLogs, setRecentLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/logs?limit=1').then((r) => r.json()).catch(() => null),
      fetch('/api/logs?limit=5&sort=desc')
        .then((r) => r.json())
        .catch(() => null),
    ]).then(([statsData, logsData]) => {
      if (statsData?.stats) setStats(statsData.stats)
      if (logsData?.logs) setRecentLogs(logsData.logs)
      setLoading(false)
    })
  }, [])

  const successRate =
    stats && stats.total > 0
      ? Math.round((stats.successes / stats.total) * 100)
      : null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">Visão geral do sistema</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>Carregando estatísticas...</span>
        </div>
      ) : error ? (
        <div className="text-red-400 text-sm py-8 text-center bg-red-500/5 border border-red-500/20 rounded-xl">
          {error}
        </div>
      ) : stats ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total de Requisições"
              value={stats.total.toLocaleString('pt-BR')}
              icon={<Clock className="w-5 h-5" />}
              color="text-blue-400"
            />
            <StatCard
              label="Sucessos"
              value={stats.successes.toLocaleString('pt-BR')}
              icon={<CheckCircle className="w-5 h-5" />}
              color="text-green-400"
              subtext={`${successRate ?? 0}% taxa`}
            />
            <StatCard
              label="Erros"
              value={stats.errors.toLocaleString('pt-BR')}
              icon={<AlertCircle className="w-5 h-5" />}
              color="text-red-400"
            />
            <StatCard
              label="Tempo médio"
              value={`${Math.round(stats.avg_duration_ms)}ms`}
              icon={<Activity className="w-5 h-5" />}
              color="text-purple-400"
            />
          </div>

          {/* Health bar */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-emerald-400" />
                <span className="text-sm font-medium text-white">Health do Backend</span>
              </div>
              <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Online
              </span>
            </div>
            <div className="w-full bg-slate-700/50 rounded-full h-2">
              <div
                className="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all"
                style={{ width: `${successRate ?? 100}%` }}
              />
            </div>
            <div className="flex justify-between mt-1.5 text-xs text-slate-500">
              <span>Taxa de sucesso: {successRate ?? '—'}%</span>
              <span>{stats.total} requisições totais</span>
            </div>
          </div>

          {/* Recent activity */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-indigo-400" />
                Atividade recente
              </h2>
              <span className="text-xs text-slate-500">Últimas 5 requisições</span>
            </div>
            {recentLogs.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-6">
                Nenhuma requisição registrada ainda.
              </p>
            ) : (
              <div className="space-y-0">
                {recentLogs.map((log: LogEntry) => (
                  <RecentLogItem
                    key={log.id}
                    endpoint={log.endpoint}
                    status_code={log.status_code}
                    duration_ms={log.duration_ms}
                    timestamp={log.timestamp}
                  />
                ))}
              </div>
            )}
          </div>

          {/* About */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-3">Sobre o Trivor</h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Trivor é uma ferramenta de inteligência para currículos e perfis profissionais.
              Analisa compatibilidade com vagas, otimiza para ATS e gera insights baseados em
              dados do mercado.
            </p>
          </div>
        </>
      ) : (
        <div className="text-slate-500 text-center py-12 bg-slate-800/30 rounded-xl border border-slate-700/30">
          Nenhuma requisição registrada ainda.
        </div>
      )}
    </div>
  )
}
