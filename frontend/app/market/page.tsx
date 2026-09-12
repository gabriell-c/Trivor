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
  Link as LinkIcon,
  ExternalLink,
  Globe,
} from 'lucide-react'
import { CustomInput } from '../components/CustomInput'
import { CustomSelect } from '../components/CustomSelect'
import { CustomButton } from '../components/CustomButton'
import { TagInput } from '../components/TagInput'
import { getBestProvider } from '../hooks/useIaProviders'
import { API_BASE_URL } from '../lib/api'
import type { MarketAnalysisResult, MarketReport, MarketJob } from '../types/analysis'

export default function MarketIntelligencePage() {
  const [jobTitle, setJobTitle] = useState('')
  const [targetStack, setTargetStack] = useState<string[]>([])
  const [negativeKeywords, setNegativeKeywords] = useState<string[]>([])
  const [seniority, setSeniority] = useState('Nenhum')
  const [timeWindow, setTimeWindow] = useState('30 dias')
  const [activeTab, setActiveTab] = useState<'config' | 'results' | 'jobs'>('config')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportFormat, setExportFormat] = useState<'pdf' | 'docx' | 'md'>('pdf')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MarketAnalysisResult | null>(null)
  const [expandedJob, setExpandedJob] = useState<number | null>(null)
  const [jobFilter, setJobFilter] = useState<'all' | 'relevant' | 'discarded'>('all')
  const [jobSourceFilter, setJobSourceFilter] = useState('all')
  const [jobSearchText, setJobSearchText] = useState('')
  const [jobPage, setJobPage] = useState(0)
  const [reqTechPage, setReqTechPage] = useState(0)
  const [niceTechPage, setNiceTechPage] = useState(0)
  const [softSkillPage, setSoftSkillPage] = useState(0)
  const [certPage, setCertPage] = useState(0)
  const [langPage, setLangPage] = useState(0)
  const STAT_PAGE_SIZE = 10
  const JOB_PAGE_SIZE = 15

  // Location: simples Nacional/Internacional
  const [isInternational, setIsInternational] = useState(false)

  const getLocationValue = (): string => {
    return isInternational ? 'Remoto Internacional' : 'Remoto Nacional'
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

    // Envia credenciais do provider configurado para a IA
    const marketProvider = getBestProvider(['market'])
    if (marketProvider) {
      formData.set('api_key', marketProvider.apiKey)
      formData.set('api_url', marketProvider.apiUrl)
      formData.set('model_name', marketProvider.modelName)
    }

    // Busca chaves JSearch do backend (onde são salvas na página de settings)
    let jsearchKeysStr = ''
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/keys`)
      if (res.ok) {
        const data = await res.json()
        jsearchKeysStr = (data.keys || [])
          .map((k: { api_key: string }) => k.api_key)
          .join(',')
      }
    } catch {}
    formData.set('jsearch_api_keys', jsearchKeysStr)

    try {
      const res = await fetch(`${API_BASE_URL}/api/market/analyze`, { method: 'POST', body: formData })
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

  const handleExport = async () => {
    if (!result) return
    setExporting(true)
    try {
      const formData = new FormData()
      formData.set('format', exportFormat)
      formData.set('job_title', result.report.summary.job_title)
      formData.set('seniority', result.report.summary.seniority)
      formData.set('location', result.report.summary.location)
      formData.set('model_name', result.model)
      formData.set('report_json', JSON.stringify(result.report))
      const res = await fetch(`${API_BASE_URL}/api/export/market`, { method: 'POST', body: formData })
      if (!res.ok) throw new Error('Falha ao exportar')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `analise_mercado_${result.report.summary.job_title.toLowerCase().replace(/\s+/g, '_')}.${exportFormat === 'pdf' ? 'pdf' : exportFormat === 'docx' ? 'docx' : 'md'}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.message || 'Erro ao exportar')
    } finally {
      setExporting(false)
    }
  }

  const R = result?.report

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
              <CustomSelect value={seniority} onChange={setSeniority} options={['Nenhum', 'Estagiário', 'Júnior', 'Pleno', 'Sênior', 'Especialista'].map(s => ({ value: s, label: s }))} placeholder="Nível..." />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Janela Temporal</label>
              <CustomSelect value={timeWindow} onChange={setTimeWindow} options={['7 dias', '15 dias', '30 dias', '60 dias', '90 dias'].map(w => ({ value: w, label: w }))} placeholder="Período..." />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Escopo Geográfico</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setIsInternational(false)}
                  className={`flex-1 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                    !isInternational
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-800/60 text-slate-400 hover:text-white border border-slate-700/60'
                  }`}>
                  🇧🇷 Nacional
                </button>
                <button
                  onClick={() => setIsInternational(true)}
                  className={`flex-1 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                    isInternational
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-800/60 text-slate-400 hover:text-white border border-slate-700/60'
                  }`}>
                  🌍 Internacional
                </button>
              </div>
              <p className="text-[10px] text-slate-600 mt-1">
                {isInternational ? 'Vagas em inglês, dólar/euro, exterior.' : 'Vagas em português, real, Brasil.'}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-2xl bg-purple-500/5 border border-purple-500/15">
            <Info className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-purple-300/80">
              A análise utilizará IA para classificar relevância das vagas e extrair dados estruturados. O resultado incluirá ranking de habilidades, anos de experiência, modalidades e score de confiança.
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              <XCircle className="w-4 h-4 flex-shrink-0" />
              <span className="flex-1">{error}</span>
              <button
                onClick={runAnalysis}
                disabled={loading}
                className="flex items-center gap-1 px-2 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 text-xs transition-colors disabled:opacity-50"
              >
                <RefreshCw className="w-3 h-3" /> Tentar novamente
              </button>
            </div>
          )}

          <CustomButton onClick={runAnalysis} loading={loading} disabled={loading || !jobTitle.trim()} className="w-full">
            <TrendingUp className="w-4 h-4" />
            {loading ? 'Analisando Mercado...' : 'Analisar Mercado'}
          </CustomButton>
        </div>
      )}

      {/* Skeleton loading while analysis runs */}
      {loading && (
        <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-4">
          <div className="h-4 bg-slate-700/50 rounded-full w-1/3 animate-pulse" />
          <div className="space-y-3">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="flex gap-4 items-center">
                <div className="h-10 bg-slate-700/50 rounded-xl w-16 animate-pulse" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 bg-slate-700/50 rounded-full w-3/4 animate-pulse" />
                  <div className="h-3 bg-slate-700/50 rounded-full w-1/2 animate-pulse" />
                </div>
              </div>
            ))}
          </div>
          <div className="h-4 bg-slate-700/50 rounded-full w-1/4 animate-pulse mt-6" />
          <div className="grid grid-cols-2 gap-3">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-16 bg-slate-700/50 rounded-xl animate-pulse" />
            ))}
          </div>
        </div>
      )}

      {/* Results Tab */}
      {activeTab === 'results' && R && R.statistics && (
        <div className="space-y-6">
          {/* Diagnóstico: se 0 vagas coletadas */}
          {((R.summary as any).jsearch_status === 'no_jobs_found' || (R.summary as any).jsearch_message) && (
            <div className="flex items-start gap-3 px-4 py-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <p className="font-semibold text-amber-200">Nenhuma vaga encontrada na busca</p>
                <p className="text-amber-300/80">{(R.summary as any).jsearch_message}</p>
                <p className="text-amber-400/70 mt-1">Dicas: verifique se as chaves da JSearch estão válidas e com créditos, amplie a janela temporal (ex: 90 dias) ou remova filtros de stack/senioridade.</p>
              </div>
            </div>
          )}

          {/* Download bar */}
          <div className="flex items-center justify-between rounded-2xl bg-slate-900/60 border border-slate-800 p-3">
            <div className="flex items-center gap-2">
              <Download className="w-4 h-4 text-purple-400" />
              <span className="text-xs text-slate-400">Exportar análise</span>
            </div>
            <div className="flex items-center gap-2">
              <CustomSelect
                value={exportFormat}
                onChange={v => setExportFormat(v as 'pdf' | 'docx' | 'md')}
                options={[
                  { value: 'pdf', label: 'PDF' },
                  { value: 'docx', label: 'DOCX' },
                  { value: 'md', label: 'Markdown' },
                ]}
                className="w-28"
              />
              <button
                onClick={handleExport}
                disabled={exporting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
              >
                {exporting ? (
                  <>
                    <RefreshCw className="w-3 h-3 animate-spin" />
                    Exportando...
                  </>
                ) : (
                  <>
                    <Download className="w-3 h-3" />
                    Baixar
                  </>
                )}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Vagas Analisadas</p>
              <p className="text-2xl font-black text-white mt-1">{R.summary.relevant_jobs_analyzed}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{R.summary.pre_filtered_count} passaram filtro → {R.summary.total_jobs_scanned} coletadas</p>
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
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Pré-filtradas</p>
              <p className="text-2xl font-black text-slate-500 mt-1">{R.summary.pre_filtered_count}</p>
              <p className="text-[10px] text-slate-600 mt-0.5">analisadas pela IA</p>
            </div>
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4">
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Descartadas</p>
              <p className="text-2xl font-black text-slate-500 mt-1">{R.summary.discarded_jobs}</p>
              <p className="text-[10px] text-slate-600 mt-0.5">pela IA</p>
            </div>

            {/* Rejection reasons removed from summary tab */}
          </div>

          {/* Required Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><ArrowUpRight className="w-4 h-4 text-emerald-400" />Habilidades Mais Exigidas (Obrigatórias)</h3>
            <div className="space-y-2">
              {R.statistics.required_technologies.slice(reqTechPage * STAT_PAGE_SIZE, (reqTechPage + 1) * STAT_PAGE_SIZE).map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{reqTechPage * STAT_PAGE_SIZE + i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate" title={tech.name}>{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500" style={{ width: `${Math.min(tech.percentage, 100)}%` }} />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
              {R.statistics.required_technologies.length === 0 && <p className="text-xs text-slate-500">Nenhuma habilidade obrigatória extraída.</p>}
            </div>
            {R.statistics.required_technologies.length > STAT_PAGE_SIZE && (
              <div className="flex items-center justify-center gap-2 pt-2 border-t border-slate-800">
                <button onClick={() => setReqTechPage(p => Math.max(0, p - 1))} disabled={reqTechPage === 0}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Anterior
                </button>
                <span className="text-xs text-slate-500">{reqTechPage + 1} / {Math.ceil(R.statistics.required_technologies.length / STAT_PAGE_SIZE)}</span>
                <button onClick={() => setReqTechPage(p => p + 1)} disabled={(reqTechPage + 1) * STAT_PAGE_SIZE >= R.statistics.required_technologies.length}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Próximo
                </button>
              </div>
            )}
          </div>

          {/* Desirable Technologies */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><ArrowDownRight className="w-4 h-4 text-amber-400" />Habilidades Diferenciais (Desejáveis)</h3>
            <div className="space-y-2">
              {R.statistics.desirable_technologies.slice(niceTechPage * STAT_PAGE_SIZE, (niceTechPage + 1) * STAT_PAGE_SIZE).map((tech, i) => (
                <div key={tech.name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-5 text-center">{niceTechPage * STAT_PAGE_SIZE + i + 1}</span>
                  <span className="text-xs font-semibold text-slate-200 w-32 truncate" title={tech.name}>{tech.name}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500" style={{ width: `${Math.min(tech.percentage, 100)}%` }} />
                  </div>
                  <span className="text-xs text-slate-400 w-16 text-right">{tech.percentage}%</span>
                  <span className="text-xs text-slate-600 w-12 text-right">{tech.count}</span>
                </div>
              ))}
              {R.statistics.desirable_technologies.length === 0 && <p className="text-xs text-slate-500">Nenhuma habilidade diferenciada extraída.</p>}
            </div>
            {R.statistics.desirable_technologies.length > STAT_PAGE_SIZE && (
              <div className="flex items-center justify-center gap-2 pt-2 border-t border-slate-800">
                <button onClick={() => setNiceTechPage(p => Math.max(0, p - 1))} disabled={niceTechPage === 0}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Anterior
                </button>
                <span className="text-xs text-slate-500">{niceTechPage + 1} / {Math.ceil(R.statistics.desirable_technologies.length / STAT_PAGE_SIZE)}</span>
                <button onClick={() => setNiceTechPage(p => p + 1)} disabled={(niceTechPage + 1) * STAT_PAGE_SIZE >= R.statistics.desirable_technologies.length}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Próximo
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2"><Briefcase className="w-4 h-4 text-blue-400" />Modalidades Mais Comuns</h3>
              <div className="space-y-2">
                {R.statistics.modalities.map(mod => (
                  <div key={mod.name} className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-slate-300 w-28 truncate" title={mod.name}>{mod.name}</span>
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
                {R.statistics.top_soft_skills.slice(softSkillPage * STAT_PAGE_SIZE, (softSkillPage + 1) * STAT_PAGE_SIZE).length > 0
                  ? R.statistics.top_soft_skills.slice(softSkillPage * STAT_PAGE_SIZE, (softSkillPage + 1) * STAT_PAGE_SIZE).map(s => (
                    <span key={s.name} className="px-3 py-1.5 rounded-xl text-xs font-medium bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">{s.name} <span className="text-cyan-500 ml-1">{s.count}x</span></span>
                  ))
                  : <p className="text-xs text-slate-500">Nenhuma soft skill extraída.</p>
                }
              </div>
              {R.statistics.top_soft_skills.length > STAT_PAGE_SIZE && (
                <div className="flex items-center justify-center gap-2 mt-3 pt-3 border-t border-slate-800">
                  <button onClick={() => setSoftSkillPage(p => Math.max(0, p - 1))} disabled={softSkillPage === 0}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    Anterior
                  </button>
                  <span className="text-xs text-slate-500">{softSkillPage + 1} / {Math.ceil(R.statistics.top_soft_skills.length / STAT_PAGE_SIZE)}</span>
                  <button onClick={() => setSoftSkillPage(p => p + 1)} disabled={(softSkillPage + 1) * STAT_PAGE_SIZE >= R.statistics.top_soft_skills.length}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    Próximo
                  </button>
                </div>
              )}
            </div>
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-4">Certificações Mais Citadas</h3>
              <div className="space-y-2">
                {R.statistics.top_certifications.slice(certPage * STAT_PAGE_SIZE, (certPage + 1) * STAT_PAGE_SIZE).length > 0
                  ? R.statistics.top_certifications.slice(certPage * STAT_PAGE_SIZE, (certPage + 1) * STAT_PAGE_SIZE).map(c => (
                    <div key={c.name} className="flex items-center justify-between p-2 rounded-xl bg-slate-950/60">
                      <span className="text-xs text-slate-300">{c.name}</span>
                      <span className="text-[10px] text-slate-500">{c.count}x</span>
                    </div>
                  ))
                  : <p className="text-xs text-slate-500">Nenhuma certificação extraída.</p>
                }
              </div>
              {R.statistics.top_certifications.length > STAT_PAGE_SIZE && (
                <div className="flex items-center justify-center gap-2 mt-3 pt-3 border-t border-slate-800">
                  <button onClick={() => setCertPage(p => Math.max(0, p - 1))} disabled={certPage === 0}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    Anterior
                  </button>
                  <span className="text-xs text-slate-500">{certPage + 1} / {Math.ceil(R.statistics.top_certifications.length / STAT_PAGE_SIZE)}</span>
                  <button onClick={() => setCertPage(p => p + 1)} disabled={(certPage + 1) * STAT_PAGE_SIZE >= R.statistics.top_certifications.length}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    Próximo
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Idiomas */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
            <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2"><Globe className="w-4 h-4 text-blue-400" />Idiomas Mais Requisitados</h3>
            <div className="space-y-2">
              {R.statistics.top_languages.slice(langPage * STAT_PAGE_SIZE, (langPage + 1) * STAT_PAGE_SIZE).length > 0
                ? R.statistics.top_languages.slice(langPage * STAT_PAGE_SIZE, (langPage + 1) * STAT_PAGE_SIZE).map(l => (
                  <div key={l.name} className="flex items-center justify-between p-2 rounded-xl bg-slate-950/60">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-300">{l.name}</span>
                      {l.top_level && l.top_level !== 'Não especificado' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/20">
                          {l.top_level}
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-slate-500">{l.count}x</span>
                  </div>
                ))
                : <p className="text-xs text-slate-500">Nenhum idioma extraído.</p>
              }
            </div>
            {R.statistics.top_languages.length > STAT_PAGE_SIZE && (
              <div className="flex items-center justify-center gap-2 mt-3 pt-3 border-t border-slate-800">
                <button onClick={() => setLangPage(p => Math.max(0, p - 1))} disabled={langPage === 0}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Anterior
                </button>
                <span className="text-xs text-slate-500">{langPage + 1} / {Math.ceil(R.statistics.top_languages.length / STAT_PAGE_SIZE)}</span>
                <button onClick={() => setLangPage(p => p + 1)} disabled={(langPage + 1) * STAT_PAGE_SIZE >= R.statistics.top_languages.length}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                  Próximo
                </button>
              </div>
            )}
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
          {/* Header with stats */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2"><Briefcase className="w-4 h-4 text-purple-400" />Vagas Analisadas</h3>
            <div className="flex items-center gap-2 text-xs">
              <span className="px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{R.summary.relevant_jobs_analyzed} relevantes</span>
              <span className="px-2 py-1 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">{R.summary.discarded_jobs} descartadas</span>
              <span className="px-2 py-1 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">{R.summary.pre_filtered_count} analisadas</span>
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-800/80 border border-slate-700/60">
              {(['all', 'relevant', 'discarded'] as const).map(f => (
                <button key={f} onClick={() => { setJobFilter(f); setJobPage(0); }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    jobFilter === f ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}>
                  {f === 'all' ? 'Todas' : f === 'relevant' ? 'Relevantes' : 'Descartadas'}
                </button>
              ))}
            </div>
            <CustomSelect
              value={jobSourceFilter}
              onChange={v => { setJobSourceFilter(v); setJobPage(0) }}
              options={[
                { value: 'all', label: 'Todas as fontes' },
                { value: 'LinkedIn', label: 'LinkedIn' },
                { value: 'Glassdoor', label: 'Glassdoor' },
                { value: 'Indeed', label: 'Indeed' },
                { value: 'Catho', label: 'Catho' },
                { value: 'Empregos.com', label: 'Empregos.com' },
              ]}
              className="w-44"
            />
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input type="text" placeholder="Buscar por título ou empresa..."
                className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                value={jobSearchText}
                onChange={e => { setJobSearchText(e.target.value); setJobPage(0); }}
              />
            </div>
          </div>

          {/* Job list */}
          {(() => {
            const allJobs = R.sample_jobs ?? R.vagas
            const sources = [...new Set(allJobs.map(j => j.source).filter(Boolean))]
            const filtered = allJobs.filter(j => {
              if (jobFilter === 'relevant' && !j.is_relevant) return false
              if (jobFilter === 'discarded' && j.is_relevant) return false
              if (jobSourceFilter !== 'all' && j.source !== jobSourceFilter) return false
              if (jobSearchText.trim()) {
                const q = jobSearchText.toLowerCase()
                if (!j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false
              }
              return true
            })
            const totalPages = Math.max(1, Math.ceil(filtered.length / JOB_PAGE_SIZE))
            const paginated = filtered.slice(jobPage * JOB_PAGE_SIZE, (jobPage + 1) * JOB_PAGE_SIZE)

            if (filtered.length === 0) {
              return <div className="text-center py-8 text-slate-500 text-sm">Nenhuma vaga corresponde aos filtros.</div>
            }

            return (
              <>
                <div className="space-y-2">
                  {paginated.map((job, i) => {
                    const globalIdx = allJobs.indexOf(job)
                    return (
                      <div key={globalIdx} className="rounded-2xl bg-slate-950/60 border border-slate-800 overflow-hidden">
                        <button
                          onClick={() => setExpandedJob(expandedJob === globalIdx ? null : globalIdx)}
                          className="w-full flex items-start justify-between p-4 text-left hover:bg-slate-800/30 transition"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <p className="text-sm font-bold text-white truncate">{job.title}</p>
                              {job.is_relevant
                                ? <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                                : <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                              }
                              {job.rejection_reason && (
                                <span className="px-2 py-0.5 rounded-md bg-rose-500/10 border border-rose-500/20 text-[10px] text-rose-400 flex-shrink-0" title={job.rejection_reason}>
                                  {job.rejection_reason}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 text-[11px] text-slate-500 flex-wrap">
                              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{job.company}</span>
                              <span className="flex items-center gap-1"><MapPinIcon className="w-3 h-3" />{job.location}</span>
                              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{job.modality}</span>
                              <span className="text-slate-600">· {job.source}</span>
                              {job.source_url && (
                                <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                                  onClick={e => e.stopPropagation()}
                                  className="flex items-center gap-1 text-purple-400 hover:text-purple-300 transition-colors">
                                  <ExternalLink className="w-3 h-3" />Ver vaga
                                </a>
                              )}
                            </div>
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {job.requirements.slice(0, 4).map(t => (
                                <span key={t} className="px-1.5 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400">{t}</span>
                              ))}
                              {job.nice_to_have.slice(0, 2).map(t => (
                                <span key={t} className="px-1.5 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-400">{t}</span>
                              ))}
                            </div>
                          </div>
                          <div className="ml-4 flex-shrink-0">
                            {expandedJob === globalIdx
                              ? <ChevronUp className="w-4 h-4 text-slate-400" />
                              : <ChevronDown className="w-4 h-4 text-slate-400" />
                            }
                          </div>
                        </button>

                        <AnimatePresence>
                          {expandedJob === globalIdx && (
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
                                    <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Habilidades Exigidas</p>
                                    <div className="flex flex-wrap gap-1.5">
                                      {job.requirements.length > 0 ? job.requirements.map(t => (
                                        <span key={t} className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400">{t}</span>
                                      )) : <span className="text-[10px] text-slate-600">—</span>}
                                    </div>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Diferenciais</p>
                                    <div className="flex flex-wrap gap-1.5">
                                      {job.nice_to_have.length > 0 ? job.nice_to_have.map(t => (
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
                                      {job.exp_years_min ? `${job.exp_years_min}` : '—'}
                                      {job.exp_years_max ? ` - ${job.exp_years_max}` : ''}
                                      {job.exp_years_min || job.exp_years_max ? ' anos' : ''}
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
                                {job.soft_skills?.length && (
                                  <div>
                                    <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Soft Skills</p>
                                    <div className="flex flex-wrap gap-1.5">
                                      {job.soft_skills.map(s => (
                                        <span key={s} className="px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-[10px] text-cyan-300">{s}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {job.certifications?.length && (
                                  <div>
                                    <p className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Certificações</p>
                                    <div className="flex flex-wrap gap-1.5">
                                      {job.certifications.map(c => (
                                        <span key={c} className="px-2 py-0.5 rounded-md bg-purple-500/10 border border-purple-500/20 text-[10px] text-purple-300">{c}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Go to job button */}
                                <div className="pt-2 border-t border-slate-800/60">
                                  {job.source_url ? (
                                    <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                                      onClick={e => e.stopPropagation()}
                                      className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl bg-purple-600/20 border border-purple-500/40 text-sm font-semibold text-purple-300 hover:bg-purple-600/30 transition-colors">
                                      <ExternalLink className="w-4 h-4" />Abrir vaga no {job.source}
                                    </a>
                                  ) : (
                                    <div className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/40 border border-slate-700/40 text-xs text-slate-500">
                                      <MapPinIcon className="w-3 h-3" />
                                      {job.location} · {job.modality}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )
                  })}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500">Mostrando {jobPage * JOB_PAGE_SIZE + 1}-{Math.min((jobPage + 1) * JOB_PAGE_SIZE, filtered.length)} de {filtered.length}</p>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setJobPage(p => Math.max(0, p - 1))} disabled={jobPage === 0}
                        className="px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs text-slate-400 hover:text-white disabled:opacity-40 transition-colors">
                        Anterior
                      </button>
                      <span className="text-xs text-slate-500">{jobPage + 1} / {totalPages}</span>
                      <button onClick={() => setJobPage(p => Math.min(totalPages - 1, p + 1))} disabled={jobPage >= totalPages - 1}
                        className="px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs text-slate-400 hover:text-white disabled:opacity-40 transition-colors">
                        Próxima
                      </button>
                    </div>
                  </div>
                )}
              </>
            )
          })()}
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
