'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Clock, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react'
import type { LogStats } from '../types/analysis'

function StatCard({ label, value, icon, color }: { label: string; value: string | number; icon: React.ReactNode; color: string }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-slate-400 text-sm">{label}</span>
        <span className={color}>{icon}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/logs?limit=1')
      .then(r => r.json())
      .then(data => {
        setStats(data.stats)
        setLoading(false)
      })
      .catch(() => {
        setLoading(false)
      })
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 mt-1">Visão geral do sistema</p>
      </div>

      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>Carregando estatísticas...</span>
        </div>
      ) : stats ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total de Requisições"
            value={stats.total}
            icon={<Clock className="w-5 h-5" />}
            color="text-blue-400"
          />
          <StatCard
            label="Sucessos"
            value={stats.successes}
            icon={<CheckCircle className="w-5 h-5" />}
            color="text-green-400"
          />
          <StatCard
            label="Erros"
            value={stats.errors}
            icon={<AlertCircle className="w-5 h-5" />}
            color="text-red-400"
          />
          <StatCard
            label="Média (ms)"
            value={Math.round(stats.avg_duration_ms)}
            icon={<RefreshCw className="w-5 h-5" />}
            color="text-purple-400"
          />
        </div>
      ) : (
        <div className="text-slate-500 text-center py-12 bg-slate-800/30 rounded-xl border border-slate-700/30">
          Nenhuma requisição registrada ainda.
        </div>
      )}

      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-3">Sobre o Trivor</h2>
        <p className="text-slate-400 text-sm leading-relaxed">
          Trivor é uma ferramenta de inteligência para currículos e perfis profissionais.
          Analisa compatibilidade com vagas, otimiza para ATS e gera insights baseados em dados do mercado.
        </p>
      </div>
    </div>
  )
}
