'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BarChart3,
  Search,
  MapPin,
  Briefcase,
  Clock,
  TrendingUp,
  Info,
  Filter,
  Download,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  Zap,
  Activity,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'

interface AnalysisResult {
  success: boolean
  report: MarketReport
  elapsed_seconds: number
  model: string
}

interface MarketReport {
  summary: {
    job_title: string
    target_stack: string[]
    seniority: string
    location: string
    time_window: string
    total_jobs_scanned: number
    relevant_jobs_analyzed: number
    discarded_jobs: number
    confidence_score: string
    confidence_reason: string
    generated_at: string
  }
  statistics: {
    required_technologies: { name: string; count: number; percentage: number }[]
    desirable_technologies: { name: string; count: number; percentage: number }[]
    exp_years_median: number
    exp_years_distribution: { [key: string]: number }
    modalities: { name: string; count: number; percentage: number }[]
    top_soft_skills: { name: string; count: number }[]
    top_certifications: { name: string; count: number }[]
  }
  sample_jobs: { title: string; company: string; is_relevant: boolean; req_techs: string[]; desirable_techs: string[] }[]
}

interface State {
  jobTitle: string
  targetStack: string
  seniority: string
  location: string
  timeWindow: string
  apiKey: string
  apiUrl: string
  modelName: string
  activeTab: 'config' | 'results' | 'jobs'
  loading: boolean
  error: string | null
  result: AnalysisResult | null
}

export default function MarketIntelligencePage() {
  const [state, setState] = useState<State>({
    jobTitle: '',
    targetStack: '',
    seniority: 'Pleno',
    location: 'Remoto Nacional',
    timeWindow: '90 dias',
    apiKey: '',
    apiUrl: '',
    modelName: 'gpt-4o',
    activeTab: 'config',
    loading: false,
    error: null,
    result: null,
  })

  const update = (partial: Partial<State>) => setState(s => ({ ...s, ...partial }))

  const runAnalysis = async () => {
    if (!state.jobTitle.trim() || !state.apiKey.trim()) {
      update({ error: 'Preencha o título da vaga e a chave de API.' })
      return
    }
    update({ loading: true, error: null, result: null })

    const formData = new FormData()
    formData.set('api_key', state.apiKey.trim())
    if (state.apiUrl.trim()) formData.set('api_url', state.apiUrl.trim())
    if (state.modelName.trim()) formData.set('model_name', state.modelName.trim())
    formData.set('job_title', state.jobTitle.trim())
    formData.set('target_stack', state.targetStack.trim())
    formData.set('seniority', state.seniority)
    formData.set('location', state.location)
    formData.set('time_window', state.timeWindow)

    try {
      const res = await fetch('http://127.0.0.1:8000/api/market/analyze', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Erro na análise')
      update({ result: data, activeTab: 'results' })
    } catch (err: any) {
      update({ error: err.message || 'Erro desconhecido' })
    } finally {
      update({ loading: false })
    }
  }

  const R = state.result?.report

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      className="w-full max-w-5xl z-10 space-y-6"
    >
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-semibold tracking-wider">
          <BarChart3 className="w-3.5 h-3.5 text-purple-400" />
          Intelligence
        </div>
        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">
          Inteligência de Mercado
        </h1>
        <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">
          Analise vagas reais do mercado, identifique tendências e gaps de skill para seu perfil.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center justify-center gap-2">
        {[
          { id: 'config' as const, label: 'Configurar', icon: <Filter className="w-3.5 h-3.5" /> },
          { id: 'results' as const, label: 'Resultados', icon: <TrendingUp className="w-3.5 h-3.5" /> },
          { id: 'jobs' as const, label: 'Vagas Analisadas', icon: <Briefcase className="w-3.5 h-3.5" /> },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => update({ activeTab: tab.id })}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all ${
              state.activeTab === tab.id
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30 border border-purple-500'
                : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
            }`}
          >
            {tab.icon} {tab.label}
            {tab.id === 'results' && R && (
              <span className="ml-1 px-1.5 py-0.5 rounded-full bg-purple-500/30 text-[10px]">
                {R.summary.relevant_jobs_analyzed}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Config Tab */}
      {state.activeTab === 'config' && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-6">
          <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Parâmetros da Análise</h2>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Área / Cargo-Alvo</label>
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="text"
                placeholder="Ex: Desenvolvedor Backend Python"
                value={state.jobTitle}
                onChange={e => update({ jobTitle: e.target.value })}
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500/60 focus:ring-1 focus:ring-purple-500/30"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Stack / Skills Principais</label>
            <input
              type="text"
              placeholder="Ex: Python, FastAPI, PostgreSQL (separado por vírgula)"
              value={state.targetStack}
              onChange={e => update({ targetStack: e.target.value })}
              className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500/60 focus:ring-1 focus:ring-purple-500/30"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Senioridade</label>
              <select
                value={state.seniority}
                onChange={e => update({ seniority: e.target.value })}
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white focus:outline-none focus:border-purple-500/60"
              >
                {['Estagiário', 'Júnior', 'Pleno', 'Sênior', 'Especialista'].map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Escopo Geográfico</label>
              <select
                value={state.location}
                onChange={e => update({ location: e.target.value })}
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white focus:outline-none focus:border-purple-500/60"
              >
                {['Remoto Nacional', 'Remoto Internacional', 'São Paulo, SP', 'Rio de Janeiro, RJ', 'Brasil'].map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Janela Temporal</label>
              <select
                value={state.timeWindow}
                onChange={e => update({ timeWindow: e.target.value })}
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white focus:outline-none focus:border-purple-500/60"
              >
                {['30 dias', '60 dias', '90 dias'].map(w => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
            </div>
          </div>

          {/* IA Config */}
          <div className="pt-2 border-t border-slate-800/60">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Configuração da IA</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Chave de API</label>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={state.apiKey}
                  onChange={e => update({ apiKey: e.target.value })}
                  className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-2.5 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500/60"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">Modelo</label>
                  <input
                    type="text"
                    placeholder="gpt-4o"
                    value={state.modelName}
                    onChange={e => update({ modelName: e.target.value })}
                    className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-2.5 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500/60"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">Base URL</label>
                  <input
                    type="text"
                    placeholder="Opcional"
                    value={state.apiUrl}
                    onChange={e => update({ apiUrl: e.target.value })}
                    className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-2.5 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500/60"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Info */}
          <div className="flex items-start gap-3 p-4 rounded-2xl bg-purple-500/5 border border-purple-500/15">
            <Info className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-purple-300/80">
              A análise utilizará IA para classificar relevância das vagas e extrair dados estruturados.
              O resultado incluirá ranking de tecnologias, anos de experiência, modalidades e score de confiança.
            </div>
          </div>

          {/* Error */}
          {state.error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              <XCircle className="w-4 h-4 flex-shrink-0" />
              {state.error}
            </div>
          )}

          {/* Run */}
          <button
            onClick={runAnalysis}
            disabled={state.loading || !state.jobTitle.trim() || !state.apiKey.trim()}
            className="w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold text-sm hover:from-purple-500 hover:to-indigo-500 transition-all shadow-lg shadow-purple-600/25 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {state.loading ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Analisando Mercado...</>
            ) : (
              <><TrendingUp className="w-4 h-4" /> Analisar Mercado</>
            )}
          </button>
        </div>
      )}

      {/* Results Tab */}
      {state.activeTab === 'results' && R && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Vagas Analisadas</p>
              <p className="text-2xl font-black text-white mt-1">{R.summary.relevant_jobs_analyzed}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{R.summary.total_jobs_scanned} coletadas</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Confiança</p>
              <p className={`text-2xl font-black mt-1 ${
                R.summary.confidence_score === 'Alta' ? 'text-emerald-400' :
                R.summary.confidence_score === 'Média' ? 'text-amber-400' : 'text-rose-400'
              }`}>{R.summary.confidence_score}</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Exp. Média (Anos)</p>
              <p className="text-2xl font-black text-purple-300 mt-1">{R.statistics.exp_years_median}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">Mediana</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Tempo de Análise</p>
              <p className="text-2xl font-black text-indigo-300 mt-1">
                {state.result?.elapsed_seconds?.toFixed(1)}s
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">{state.result?.model}</p>
            </div>
          </div>

          {/* Required Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <ArrowUpRight className="w-4 h-4 text-emerald-400" />
              Tecnologias Mais Exigidas (Obrigatórias)
            </h3>
            <div className="space-y-2">
              {R.statistics.required_technologies.map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate">{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(tech.percentage, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
              {R.statistics.required_technologies.length === 0 && (
                <p className="text-xs text-slate-500">Nenhuma tecnologia obrigatória extraída.</p>
              )}
            </div>
          </div>

          {/* Desirable Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <ArrowDownRight className="w-4 h-4 text-amber-400" />
              Tecnologias Diferenciais (Desejáveis)
            </h3>
            <div className="space-y-2">
              {R.statistics.desirable_technologies.map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate">{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(tech.percentage, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Modalities & Experience Distribution */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-blue-400" />
                Modalidades de Trabalho
              </h3>
              <div className="space-y-3">
                {R.statistics.modalities.map(mod => (
                  <div key={mod.name} className="flex items-center gap-3">
                    <span className="text-xs text-slate-400 w-24 truncate">{mod.name}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${mod.percentage}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-500 w-12 text-right">{mod.percentage}%</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-orange-400" />
                Distribuição de Experiência
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(R.statistics.exp_years_distribution).map(([label, count]) => (
                  <div key={label} className="p-3 rounded-2xl bg-slate-950/60 border border-slate-800 text-center">
                    <p className="text-lg font-black text-orange-300">{count}</p>
                    <p className="text-[10px] text-slate-500">{label}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-center">
                <p className="text-[10px] text-purple-400 uppercase font-semibold">Mediana</p>
                <p className="text-xl font-black text-white">{R.statistics.exp_years_median} anos</p>
              </div>
            </div>
          </div>

          {/* Soft Skills & Certifications */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4">Soft Skills Mais Cobradas</h3>
              <div className="flex flex-wrap gap-2">
                {R.statistics.top_soft_skills.length > 0 ? R.statistics.top_soft_skills.map(s => (
                  <span key={s.name} className="px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-xs text-slate-300">
                    {s.name}
                  </span>
                )) : (
                  <p className="text-xs text-slate-500">Nenhuma soft skill extraída.</p>
                )}
              </div>
            </div>
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4">Certificações Mais Citadas</h3>
              <div className="space-y-2">
                {R.statistics.top_certifications.length > 0 ? R.statistics.top_certifications.map(c => (
                  <div key={c.name} className="flex items-center justify-between p-2 rounded-xl bg-slate-950/60">
                    <span className="text-xs text-slate-300">{c.name}</span>
                    <span className="text-[10px] text-slate-500">{c.count}x</span>
                  </div>
                )) : (
                  <p className="text-xs text-slate-500">Nenhuma certificação extraída.</p>
                )}
              </div>
            </div>
          </div>

          {/* Confidence reason */}
          <div className="flex items-start gap-3 p-4 rounded-2xl bg-slate-800/40 border border-slate-700/60">
            <Activity className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-slate-300">Score de Confiança: {R.summary.confidence_score}</p>
              <p className="text-xs text-slate-500 mt-1">{R.summary.confidence_reason}</p>
            </div>
          </div>
        </div>
      )}

      {/* Jobs Tab */}
      {state.activeTab === 'jobs' && R && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-purple-400" />
            Vagas Analisadas ({R.sample_jobs.length} de {R.summary.relevant_jobs_analyzed})
          </h3>
          <div className="space-y-3">
            {R.sample_jobs.map((job, i) => (
              <div key={i} className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <p className="text-sm font-bold text-white">{job.title}</p>
                    <p className="text-xs text-slate-500">{job.company}</p>
                  </div>
                  {job.is_relevant ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {job.req_techs.slice(0, 5).map(t => (
                    <span key={t} className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400">{t}</span>
                  ))}
                  {job.desirable_techs.slice(0, 3).map(t => (
                    <span key={t} className="px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-400">{t}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No result yet */}
      {state.activeTab === 'results' && !state.result && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-10 text-center space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto">
            <BarChart3 className="w-8 h-8 text-slate-600" />
          </div>
          <div>
            <p className="text-slate-300 font-semibold text-sm">Nenhuma análise de mercado gerada ainda</p>
            <p className="text-slate-500 text-xs mt-1">Configure os parâmetros e clique em "Analisar Mercado".</p>
          </div>
        </div>
      )}
    </motion.div>
  )
}
