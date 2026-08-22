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
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronUp,
  Building2,
  MapPin as MapPinIcon,
} from 'lucide-react'
import { CustomInput } from '../components/CustomInput'
import { CustomSelect } from '../components/CustomSelect'
import { CustomButton } from '../components/CustomButton'
import { TagInput } from '../components/TagInput'

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
  sample_jobs: MarketJob[]
}

interface MarketJob {
  title: string
  company: string
  location: string
  modality: string
  source: string
  is_relevant: boolean
  req_techs: string[]
  desirable_techs: string[]
  role_level: string | null
  exp_years_min: number | null
  exp_years_max: number | null
  soft_skills: string[]
  certifications: string[]
  salary_min: number | null
  salary_max: number | null
  currency: string | null
  raw_description: string
}

const BRAZILIAN_STATES = [
  { value: 'AC', label: 'Acre' }, { value: 'AL', label: 'Alagoas' }, { value: 'AP', label: 'Amapá' },
  { value: 'AM', label: 'Amazonas' }, { value: 'BA', label: 'Bahia' }, { value: 'CE', label: 'Ceará' },
  { value: 'DF', label: 'Distrito Federal' }, { value: 'ES', label: 'Espírito Santo' }, { value: 'GO', label: 'Goiás' },
  { value: 'MA', label: 'Maranhão' }, { value: 'MT', label: 'Mato Grosso' }, { value: 'MS', label: 'Mato Grosso do Sul' },
  { value: 'MG', label: 'Minas Gerais' }, { value: 'PA', label: 'Pará' }, { value: 'PB', label: 'Paraíba' },
  { value: 'PR', label: 'Paraná' }, { value: 'PE', label: 'Pernambuco' }, { value: 'PI', label: 'Piauí' },
  { value: 'RJ', label: 'Rio de Janeiro' }, { value: 'RN', label: 'Rio Grande do Norte' },
  { value: 'RS', label: 'Rio Grande do Sul' }, { value: 'RO', label: 'Rondônia' }, { value: 'RR', label: 'Roraima' },
  { value: 'SC', label: 'Santa Catarina' }, { value: 'SP', label: 'São Paulo' }, { value: 'SE', label: 'Sergipe' },
  { value: 'TO', label: 'Tocantins' },
]

const MAIN_COUNTRIES = [
  'Estados Unidos', 'Canadá', 'Reino Unido', 'Alemanha', 'França', 'Irlanda', 'Espanha', 'Portugal',
  'Holanda', 'Bélgica', 'Suíça', 'Austrália', 'Japão', 'Coreia do Sul', 'Singapura',
  'Israel', 'Noruega', 'Suécia', 'Dinamarca', 'Finlândia', 'Nova Zelândia',
  'Argentina', 'Chile', 'Colômbia', 'México', 'Brasil', 'Emirados Árabes',
]

type LocationMode = 'remoto' | 'estado' | 'pais' | 'outro'

export default function MarketIntelligencePage() {
  const [jobTitle, setJobTitle] = useState('')
  const [targetStack, setTargetStack] = useState<string[]>([])
  const [negativeKeywords, setNegativeKeywords] = useState<string[]>([])
  const [seniority, setSeniority] = useState('Pleno')
  const [timeWindow, setTimeWindow] = useState('90 dias')
  const [activeTab, setActiveTab] = useState<'config' | 'results' | 'jobs'>('config')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [expandedJob, setExpandedJob] = useState<number | null>(null)

  // Location state
  const [locationMode, setLocationMode] = useState<LocationMode>('remoto')
  const [locationValue, setLocationValue] = useState('Remoto Nacional')
  const [customCountry, setCustomCountry] = useState('')
  const [customState, setCustomState] = useState('')

  const getLocationValue = (): string => {
    switch (locationMode) {
      case 'remoto': return locationValue
      case 'estado': return customState
      case 'pais': return customCountry || 'Brasil'
      case 'outro': return customCountry || 'Brasil'
      default: return 'Remoto Nacional'
    }
  }

  const runAnalysis = async () => {
    if (!jobTitle.trim()) { setError('Preencha o título da vaga.')
      return
    }
    const loc = getLocationValue()
    if (!loc.trim()) { setError('Selecione o escopo geográfico.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.set('job_title', jobTitle.trim())
    formData.set('target_stack', targetStack.join(', '))
    formData.set('negative_keywords', negativeKeywords.join(', '))
    formData.set('seniority', seniority)
    formData.set('location', loc)
    formData.set('time_window', timeWindow)

    try {
      const res = await fetch('http://127.0.0.1:8000/api/market/analyze', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Erro na análise')
      setResult(data)
      setActiveTab('results')
    } catch (err: any) {
      setError(err.message || 'Erro desconhecido')
    } finally {
      setLoading(false)
    }
  }

  const R = result?.report

  // Location options based on mode
  const locationOptions = (() => {
    switch (locationMode) {
      case 'remoto': return [
        { value: 'Remoto Nacional', label: 'Remoto Nacional' },
        { value: 'Remoto Internacional', label: 'Remoto Internacional' },
      ]
      case 'estado': return BRAZILIAN_STATES.map(s => ({ value: s.label, label: s.label }))
      case 'pais': return MAIN_COUNTRIES.map(c => ({ value: c, label: c }))
      case 'outro': return [{ value: 'Outro', label: 'Outro (digitar)' }]
      default: return []
    }
  })()

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="w-full max-w-4xl mx-auto z-10 space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-semibold tracking-wider">
          <BarChart3 className="w-3.5 h-3.5 text-purple-400" />
          Intelligence
        </div>
        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">Inteligência de Mercado</h1>
        <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">Analise vagas reais do mercado, identifique tendências e gaps de skill para seu perfil.</p>
      </div>

      {/* Tabs */}
      <div className="flex items-center justify-center gap-2">
        {([
          { id: 'config' as const, label: 'Configurar', icon: <Filter className="w-3.5 h-3.5" /> },
          { id: 'results' as const, label: 'Resultados', icon: <TrendingUp className="w-3.5 h-3.5" /> },
          { id: 'jobs' as const, label: 'Vagas Analisadas', icon: <Briefcase className="w-3.5 h-3.5" /> },
        ].map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all ${
              activeTab === tab.id ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30 border border-purple-500' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
            }`}>
            {tab.icon} {tab.label}
            {tab.id === 'results' && R && <span className="ml-1 px-1.5 py-0.5 rounded-full bg-purple-500/30 text-[10px]">{R.summary.relevant_jobs_analyzed}</span>}
          </button>
        )))}
      </div>

      {/* Config Tab */}
      {activeTab === 'config' && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-6">
          <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Parâmetros da Análise</h2>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Área / Cargo-Alvo</label>
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <CustomInput type="text" placeholder="Ex: Desenvolvedor Backend Python" value={jobTitle} onChange={setJobTitle} className="w-full pl-11" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Stack / Skills Principais</label>
            <TagInput value={targetStack} onChange={setTargetStack} placeholder="Ex: Python, FastAPI, PostgreSQL (Enter ou vírgula)" className="w-full" />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Palavras-chave Negativas (excluir vagas)</label>
            <TagInput value={negativeKeywords} onChange={setNegativeKeywords} placeholder="Ex: java, intern, estágio (Enter ou vírgula)" className="w-full" />
            <p className="text-[10px] text-slate-600 mt-1">Vagas que contiverem essas palavras serão excluídas da análise.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Senioridade</label>
              <CustomSelect value={seniority} onChange={setSeniority} options={['Estagiário', 'Júnior', 'Pleno', 'Sênior', 'Especialista'].map(s => ({ value: s, label: s }))} placeholder="Nível..." />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Janela Temporal</label>
              <CustomSelect value={timeWindow} onChange={setTimeWindow} options={['30 dias', '60 dias', '90 dias'].map(w => ({ value: w, label: w }))} placeholder="Período..." />
            </div>
          </div>

          {/* Location */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">Escopo Geográfico</label>
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {(['remoto', 'estado', 'pais', 'outro'] as const).map(mode => (
                  <button key={mode} onClick={() => setLocationMode(mode)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                      locationMode === mode ? 'bg-purple-600 text-white' : 'bg-slate-800/60 text-slate-400 hover:text-white border border-slate-700/60'
                    }`}>
                    {mode === 'remoto' ? '🌐 Remoto' : mode === 'estado' ? '📍 Estado (BR)' : mode === 'pais' ? '🗺️ País' : '✏️ Outro'}
                  </button>
                ))}
              </div>
              {locationMode === 'remoto' && (
                <CustomSelect value={locationValue} onChange={setLocationValue}
                  options={locationOptions.map(o => ({ value: o.value, label: o.label }))} placeholder="Selecione..." className="w-full" />
              )}
              {locationMode === 'estado' && (
                <CustomSelect value={customState} onChange={setCustomState}
                  options={BRAZILIAN_STATES.map(s => ({ value: s.label, label: s.label }))} placeholder="Selecione o estado..." className="w-full" />
              )}
              {locationMode === 'pais' && (
                <CustomSelect value={customCountry} onChange={setCustomCountry}
                  options={[...MAIN_COUNTRIES.map(c => ({ value: c, label: c })), { value: 'Outro', label: 'Outro (digitar abaixo)' }]} placeholder="Selecione o país..." className="w-full" />
              )}
              {(locationMode === 'outro' || (locationMode === 'pais' && customCountry === 'Outro')) && (
                <div className="mt-2">
                  <CustomInput type="text" placeholder="Nome do país..." value={locationMode === 'outro' || customCountry === 'Outro' ? customCountry : ''} onChange={v => setCustomCountry(v)} className="w-full" />
                </div>
              )}
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-2xl bg-purple-500/5 border border-purple-500/15">
            <Info className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-purple-300/80">
              A análise utilizará IA para classificar relevância das vagas e extrair dados estruturados. O resultado incluirá ranking de tecnologias, anos de experiência, modalidades e score de confiança.
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              <XCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <CustomButton onClick={runAnalysis} loading={loading} disabled={loading || !jobTitle.trim()} className="w-full">
            <TrendingUp className="w-4 h-4" />
            {loading ? 'Analisando Mercado...' : 'Analisar Mercado'}
          </CustomButton>
        </div>
      )}

      {/* Results Tab */}
      {activeTab === 'results' && R && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Vagas Analisadas</p>
              <p className="text-2xl font-black text-white mt-1">{R.summary.relevant_jobs_analyzed}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{R.summary.total_jobs_scanned} coletadas</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Confiança</p>
              <p className={`text-2xl font-black mt-1 ${R.summary.confidence_score === 'Alta' ? 'text-emerald-400' : R.summary.confidence_score === 'Média' ? 'text-amber-400' : 'text-rose-400'}`}>{R.summary.confidence_score}</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Exp. Média (Anos)</p>
              <p className="text-2xl font-black text-purple-300 mt-1">{R.statistics.exp_years_median}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">Mediana</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Descartadas</p>
              <p className="text-2xl font-black text-slate-500 mt-1">{R.summary.discarded_jobs}</p>
              <p className="text-[10px] text-slate-600 mt-0.5">por filtro</p>
            </div>
          </div>

          {/* Required Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><ArrowUpRight className="w-4 h-4 text-emerald-400" />Tecnologias Mais Exigidas (Obrigatórias)</h3>
            <div className="space-y-2">
              {R.statistics.required_technologies.map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate">{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500" style={{ width: `${Math.min(tech.percentage, 100)}%` }} />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
              {R.statistics.required_technologies.length === 0 && <p className="text-xs text-slate-500">Nenhuma tecnologia obrigatória extraída.</p>}
            </div>
          </div>

          {/* Desirable Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><ArrowDownRight className="w-4 h-4 text-amber-400" />Tecnologias Diferenciais (Desejáveis)</h3>
            <div className="space-y-2">
              {R.statistics.desirable_technologies.map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate">{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500" style={{ width: `${Math.min(tech.percentage, 100)}%` }} />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
              {R.statistics.desirable_technologies.length === 0 && <p className="text-xs text-slate-500">Nenhuma tecnologia diferenciada extraída.</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2"><Briefcase className="w-4 h-4 text-blue-400" />Modalidades Mais Comuns</h3>
              <div className="space-y-2">
                {R.statistics.modalities.map(mod => (
                  <div key={mod.name} className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-slate-300 w-28 truncate">{mod.name}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-blue-500 to-blue-400 rounded-full transition-all duration-500" style={{ width: `${mod.percentage}%` }} />
                    </div>
                    <span className="text-xs text-slate-500 w-12 text-right">{mod.percentage}%</span>
                  </div>
                ))}
                {R.statistics.modalities.length === 0 && <p className="text-xs text-slate-500">Nenhuma modalidade extraída.</p>}
              </div>
            </div>
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-orange-400" />Distribuição de Experiência</h3>
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
                  <span key={s.name} className="px-3 py-1.5 rounded-xl text-xs font-medium bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">{s.name} <span className="text-cyan-500 ml-1">{s.count}x</span></span>
                )) : <p className="text-xs text-slate-500">Nenhuma soft skill extraída.</p>}
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
                )) : <p className="text-xs text-slate-500">Nenhuma certificação extraída.</p>}
              </div>
            </div>
          </div>

          {/* Confidence */}
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
      {activeTab === 'jobs' && R && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><Briefcase className="w-4 h-4 text-purple-400" />Vagas Analisadas ({R.sample_jobs.length} de {R.summary.relevant_jobs_analyzed})</h3>
          <div className="space-y-3">
            {R.sample_jobs.map((job, i) => (
              <div key={i} className="rounded-2xl bg-slate-950/60 border border-slate-800 overflow-hidden">
                <button
                  onClick={() => setExpandedJob(expandedJob === i ? null : i)}
                  className="w-full flex items-start justify-between p-4 text-left hover:bg-slate-800/30 transition"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <p className="text-sm font-bold text-white truncate">{job.title}</p>
                      {job.is_relevant
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                        : <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                      }
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-500">
                      <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{job.company}</span>
                      <span className="flex items-center gap-1"><MapPinIcon className="w-3 h-3" />{job.location}</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{job.modality}</span>
                      <span className="text-slate-600">· {job.source}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {job.req_techs.slice(0, 4).map(t => (
                        <span key={t} className="px-1.5 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400">{t}</span>
                      ))}
                      {job.desirable_techs.slice(0, 2).map(t => (
                        <span key={t} className="px-1.5 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-400">{t}</span>
                      ))}
                    </div>
                  </div>
                  <div className="ml-4 flex-shrink-0">
                    {expandedJob === i
                      ? <ChevronUp className="w-4 h-4 text-slate-400" />
                      : <ChevronDown className="w-4 h-4 text-slate-400" />
                    }
                  </div>
                </button>

                <AnimatePresence>
                  {expandedJob === i && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="border-t border-slate-800/60"
                    >
                      <div className="p-4 space-y-4">
                        {/* Description */}
                        <div>
                          <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Descrição Completa</p>
                          <p className="text-xs text-slate-400 leading-relaxed">{job.raw_description}</p>
                        </div>

                        {/* Techs */}
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Tecnologias Obrigatórias</p>
                            <div className="flex flex-wrap gap-1.5">
                              {job.req_techs.length > 0 ? job.req_techs.map(t => (
                                <span key={t} className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400">{t}</span>
                              )) : <span className="text-[10px] text-slate-600">—</span>}
                            </div>
                          </div>
                          <div>
                            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Tecnologias Desejáveis</p>
                            <div className="flex flex-wrap gap-1.5">
                              {job.desirable_techs.length > 0 ? job.desirable_techs.map(t => (
                                <span key={t} className="px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-400">{t}</span>
                              )) : <span className="text-[10px] text-slate-600">—</span>}
                            </div>
                          </div>
                        </div>

                        {/* Details grid */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div className="p-2 rounded-xl bg-slate-900/60">
                            <p className="text-[10px] text-slate-500">Nível</p>
                            <p className="text-xs text-white font-semibold">{job.role_level || '—'}</p>
                          </div>
                          <div className="p-2 rounded-xl bg-slate-900/60">
                            <p className="text-[10px] text-slate-500">Experiência</p>
                            <p className="text-xs text-white font-semibold">
                              {job.exp_years_min ? `${job.exp_years_min}+` : '—'}
                              {job.exp_years_max ? ` - ${job.exp_years_max}` : ''}
                              {!job.exp_years_min && !job.exp_years_max ? ' anos' : ' anos'}
                            </p>
                          </div>
                          <div className="p-2 rounded-xl bg-slate-900/60">
                            <p className="text-[10px] text-slate-500">Salário</p>
                            <p className="text-xs text-white font-semibold">
                              {job.salary_min ? `${job.currency === 'USD' ? 'US$' : 'R$'} ${job.salary_min}` : '—'}
                              {job.salary_max ? ` - ${job.currency === 'USD' ? 'US$' : 'R$'} ${job.salary_max}` : ''}
                            </p>
                          </div>
                          <div className="p-2 rounded-xl bg-slate-900/60">
                            <p className="text-[10px] text-slate-500">Modalidade</p>
                            <p className="text-xs text-white font-semibold">{job.modality || '—'}</p>
                          </div>
                        </div>

                        {/* Soft Skills */}
                        {job.soft_skills.length > 0 && (
                          <div>
                            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Soft Skills</p>
                            <div className="flex flex-wrap gap-1.5">
                              {job.soft_skills.map(s => (
                                <span key={s} className="px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-[10px] text-cyan-300">{s}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Certifications */}
                        {job.certifications.length > 0 && (
                          <div>
                            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Certificações</p>
                            <div className="flex flex-wrap gap-1.5">
                              {job.certifications.map(c => (
                                <span key={c} className="px-2 py-0.5 rounded-md bg-purple-500/10 border border-purple-500/20 text-[10px] text-purple-300">{c}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {activeTab === 'results' && !result && (
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
      {activeTab === 'jobs' && !result && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-10 text-center space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto">
            <Briefcase className="w-8 h-8 text-slate-600" />
          </div>
          <div>
            <p className="text-slate-300 font-semibold text-sm">Nenhuma análise de mercado gerada ainda</p>
            <p className="text-slate-500 text-xs mt-1">Execute uma análise primeiro para ver as vagas.</p>
          </div>
        </div>
      )}
    </motion.div>
  )
}
