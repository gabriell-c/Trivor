'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText,
  Key,
  Briefcase,
  Upload,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  Cpu,
  RefreshCw,
  Zap,
  Award,
  Settings2,
  Globe,
  Sliders,
  Eye,
  EyeOff,
  Check,
  XCircle,
  Activity,
  Clock,
  BarChart3,
  UserCheck,
  FileSearch,
  ChevronRight,
  RotateCcw,
  Target,
  FileCode2,
  AlertCircle,
  Download,
  FileSpreadsheet,
  ChevronDown
} from 'lucide-react'
import { CustomSelect } from './CustomSelect'
import { CustomInput } from './CustomInput'
import { CustomButton } from './CustomButton'

interface SecaoDiagnostico {
  status: 'ok' | 'atencao' | 'critico'
  problema: string
  como_corrigir: string
}

interface AnalysisResult {
  nota?: number
  resumo_executivo?: string
  pontos_fortes?: string[]
  diagnostico_por_secao?: {
    dados_pessoais?: SecaoDiagnostico
    resumo_profissional?: SecaoDiagnostico
    experiencia_profissional?: SecaoDiagnostico
    educacao_e_cursos?: SecaoDiagnostico
    habilidades_e_keywords?: SecaoDiagnostico
  }
  analise_ats?: {
    score_ats?: number
    palavras_chave_faltantes?: string[]
    gargalos_formatacao?: string[]
    veredito_robos?: string
  } | string
  uso_tokens?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  api_info?: {
    model: string
    request_id: string
    response_time_ms: number
  }
  error?: string
}

interface SavedAIConfig {
  provider: 'openai' | 'custom'
  apiKey: string
  apiUrl: string
  modelName: string
  message: string
  expiry: number
}

const STORAGE_KEY = 'cv_engine_ai_config_v1'
const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000

export default function CurriculoTool() {
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  // Step Control: 1 = Envio / Config, 2 = Diagnóstico
  const [activeStep, setActiveStep] = useState<1 | 2>(1)

  // Configurações de IA — usar provedores globais
  const [providers, setProviders] = useState<import('../hooks/useIaProviders').IAProvider[]>(() => {
    try { const s = localStorage.getItem('trivor_ia_providers_v2'); return s ? JSON.parse(s) : [] } catch { return [] }
  })
  const [selectedProviderId, setSelectedProviderId] = useState<string>('')
  const [currentApiKey, setCurrentApiKey] = useState('')
  const [currentApiUrl, setCurrentApiUrl] = useState('')
  const [currentModelName, setCurrentModelName] = useState('gpt-4o')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSelectOpen, setIsSelectOpen] = useState(false)
  const [jobLevel, setJobLevel] = useState('Sem nível específico')
  const [jobTitle, setJobTitle] = useState('')

  // State para o box de métricas da IA
  const [showMetrics, setShowMetrics] = useState(false)
  const [showFullApiKey, setShowFullApiKey] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<{ type: 'success' | 'error'; message: string; savedUntil?: string } | null>(null)

  // Carregar provedores globais e config inicial
  useEffect(() => {
    try {
      const savedStr = localStorage.getItem(STORAGE_KEY)
      if (savedStr) {
        const saved: SavedAIConfig = JSON.parse(savedStr)
        const now = Date.now()
        if (saved.expiry && saved.expiry > now) {
          setCurrentApiKey(saved.apiKey || '')
          setCurrentApiUrl(saved.apiUrl || '')
          setCurrentModelName(saved.modelName || 'gpt-4o')
          const formattedExpiry = new Date(saved.expiry).toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          })
          setConnectionStatus({
            type: 'success',
            message: saved.message || 'Conexão salva e verificada!',
            savedUntil: formattedExpiry
          })
        } else {
          localStorage.removeItem(STORAGE_KEY)
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }

    // Load global providers
    try {
      const saved = localStorage.getItem('trivor_ia_providers_v2')
      if (saved) {
        const parsed = JSON.parse(saved)
        setProviders(parsed)
        // Auto-select a provider for curriculo
        const curriculoProvider = parsed.find((p: any) => p.usedFor === 'all' || p.usedFor === 'curriculo')
        if (curriculoProvider) {
          setSelectedProviderId(curriculoProvider.id)
          setCurrentApiKey(curriculoProvider.apiKey)
          setCurrentApiUrl(curriculoProvider.apiUrl || '')
          setCurrentModelName(curriculoProvider.modelName || 'gpt-4o')
        }
      }
    } catch {}
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFileName(e.target.files[0].name)
    }
  }

  const [exporting, setExporting] = useState<string | null>(null)

  const handleExport = async (format: 'json' | 'md' | 'docx' | 'pdf') => {
    if (!res) return
    setExporting(format)
    try {
      const formData = new FormData()
      formData.set('format', format)
      formData.set('filename', fileName || 'Curriculo.pdf')
      formData.set('job_target', `${jobTitle || 'Geral'} (${jobLevel})`)
      formData.set('model_name', currentModelName)
      formData.set('data_json', JSON.stringify(res))

      const response = await fetch('http://127.0.0.1:8000/api/export', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error('Falha ao gerar arquivo de exportação.')
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Diagnostico_CV_${fileName?.replace('.pdf', '') || 'Analise'}.${format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Erro ao baixar o arquivo.')
    } finally {
      setExporting(null)
    }
  }

  const getMaskedApiKey = (key: string) => {
    if (!key) return ''
    if (key.length <= 10) return key
    return `${key.slice(0, 5)}...${key.slice(-5)}`
  }

  // Função de formatação amigável de tokens (ex: 10455 -> 10.455 / 10.4k)
  const formatTokens = (num?: number) => {
    if (num === undefined || num === null) return '0'
    if (num >= 1000) {
      const formattedNum = num.toLocaleString('pt-BR')
      const kValue = (num / 1000).toFixed(1).replace('.', ',')
      return `${formattedNum} (${kValue}k)`
    }
    return num.toString()
  }

  const handleProviderPreset = (preset: 'openai' | 'openrouter' | 'ollama' | 'custom') => {
    setConnectionStatus(null)
    if (preset === 'openai') {
      setCurrentApiUrl('')
      setCurrentModelName('gpt-4o')
    } else if (preset === 'openrouter') {
      setCurrentApiUrl('https://openrouter.ai/api/v1')
      setCurrentModelName('openai/gpt-4o')
    } else if (preset === 'ollama') {
      setCurrentApiUrl('http://localhost:11434/v1')
      setCurrentModelName('llama3')
    } else {
      setCurrentApiUrl('')
    }
    setSelectedProviderId('')
  }

  const handleTestConnection = async () => {
    if (!currentApiKey.trim()) {
      setConnectionStatus({ type: 'error', message: 'Preencha a chave de API antes de testar a conexão.' })
      return
    }

    setTestingConnection(true)
    setConnectionStatus(null)

    const headers: Record<string, string> = {
      'api_key': currentApiKey.trim()
    }
    if (currentApiUrl.trim()) headers['api_url'] = currentApiUrl.trim()
    if (currentModelName.trim()) headers['model_name'] = currentModelName.trim()

    try {
      const response = await fetch('http://127.0.0.1:8000/api/test-connection', {
        method: 'POST',
        headers
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data?.detail || 'Erro ao conectar à API.')
      }

      const expiry = Date.now() + ONE_WEEK_MS
      const formattedExpiry = new Date(expiry).toLocaleDateString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
      })

      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        provider: 'openai',
        apiKey: currentApiKey.trim(),
        apiUrl: currentApiUrl.trim(),
        modelName: currentModelName.trim(),
        message: data.message || 'Conexão estabelecida com sucesso!',
        expiry
      }))

      setConnectionStatus({ type: 'success', message: data.message || 'Conexão estabelecida com sucesso!', savedUntil: formattedExpiry })
    } catch (err) {
      setConnectionStatus({ type: 'error', message: err instanceof Error ? err.message : 'Erro ao conectar.' })
    } finally {
      setTestingConnection(false)
    }
  }

  const analyzeCV = async (file: File) => {
    setLoading(true)
    setError(null)
    setRes(null)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('api_key', currentApiKey)
    if (currentApiUrl.trim()) formData.set('api_url', currentApiUrl.trim())
    if (currentModelName.trim()) formData.set('model_name', currentModelName.trim())
    if (selectedProviderId) formData.set('provider_id', selectedProviderId)
    if (jobTitle.trim()) formData.set('job', jobTitle.trim())
    if (jobLevel !== 'Sem nível específico') formData.set('job_level', jobLevel)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: Falha no processamento.`)
      }

      const data: AnalysisResult = await response.json()
      setRes(data)
      setActiveStep(2) // Avança para a aba de resultados
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido ao conectar ao servidor backend.')
    } finally {
      setLoading(false)
    }
  }

  const getScoreColor = (score: number = 0) => {
    if (score >= 8) return { text: 'text-emerald-400', stroke: '#10b981', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
    if (score >= 6) return { text: 'text-amber-400', stroke: '#f59e0b', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
    return { text: 'text-rose-400', stroke: '#f43f5e', bg: 'bg-rose-500/10', border: 'border-rose-500/30' }
  }

  const getStatusBadge = (status?: 'ok' | 'atencao' | 'critico') => {
    if (status === 'ok') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
          <CheckCircle2 className="w-3.5 h-3.5" /> Ok / Bom
        </span>
      )
    }
    if (status === 'atencao') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/15 border border-amber-500/30 text-amber-400">
          <AlertCircle className="w-3.5 h-3.5" /> Requer Ajuste
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-500/15 border border-rose-500/30 text-rose-400">
        <XCircle className="w-3.5 h-3.5" /> Crítico
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold tracking-wider">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          Trivor
        </div>
        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">
          Análise de Currículo
        </h1>
        <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">
          Envie seu currículo e receba um diagnóstico ATS completo com recomendações de melhoria.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => setActiveStep(1)}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs font-bold transition ${
            activeStep === 1
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-500'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <Upload className="w-3.5 h-3.5" /> 1. Enviar Currículo
        </button>
        <ChevronRight className="w-4 h-4 text-slate-600" />
        <button
          onClick={() => setActiveStep(2)}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs font-bold transition ${
            activeStep === 2
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-500'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <FileSearch className="w-3.5 h-3.5" /> 2. Diagnóstico
        </button>
      </div>

      {/* Step 1: Upload & Config */}
      {activeStep === 1 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-6"
        >
          {/* IA Config */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-indigo-400" /> Configuração da IA
              </h2>
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-xs text-slate-500 hover:text-slate-300 transition"
              >
                {showAdvanced ? 'Ocultar' : 'Avançado'}
              </button>
            </div>

            {/* Provider selector */}
            <div className="mb-4">
              <label className="block text-xs font-semibold text-slate-400 mb-2">IA para Currículo</label>
              <select
                value={selectedProviderId}
                onChange={(e) => {
                  setSelectedProviderId(e.target.value)
                  const prov = providers.find((p: any) => p.id === e.target.value)
                  if (prov) {
                    setCurrentApiKey(prov.apiKey || '')
                    setCurrentApiUrl(prov.apiUrl || '')
                    setCurrentModelName(prov.modelName || 'gpt-4o')
                  }
                }}
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30"
              >
                <option value="">Selecione uma IA...</option>
                {providers.filter((p: any) => p.usedFor === 'all' || p.usedFor === 'curriculo').map((p: any) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.modelName})</option>
                ))}
              </select>
              {!selectedProviderId && (
                <p className="text-[10px] text-slate-600 mt-1">Cadastre suas IAs na aba "Config. IAs" da sidebar</p>
              )}
            </div>

            {/* Manual override */}
            {showAdvanced && (
              <div className="space-y-3 pt-4 border-t border-slate-800/60">
                <div className="flex gap-2">
                  {(['openai', 'openrouter', 'ollama', 'custom'] as const).map(preset => (
                    <button key={preset} onClick={() => handleProviderPreset(preset)}
                      className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition">
                      {preset.charAt(0).toUpperCase() + preset.slice(1)}
                    </button>
                  ))}
                </div>
                <CustomInput type="text" value={currentApiKey} onChange={setCurrentApiKey} placeholder="API Key" showPasswordToggle />
                <CustomInput type="text" value={currentApiUrl} onChange={setCurrentApiUrl} placeholder="API URL (opcional)" />
                <CustomInput type="text" value={currentModelName} onChange={setCurrentModelName} placeholder="Model Name (ex: gpt-4o)" />
                <CustomButton variant="ghost" onClick={handleTestConnection} loading={testingConnection} className="text-xs">
                  {testingConnection ? 'Testando...' : 'Testar Conexão'}
                </CustomButton>
                {connectionStatus && (
                  <p className={`text-xs ${connectionStatus.type === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {connectionStatus.message}{connectionStatus.savedUntil ? ` (válido até ${connectionStatus.savedUntil})` : ''}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Job info */}
          <div>
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
              <Briefcase className="w-4 h-4 text-indigo-400" /> Vaga Alvo
            </h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-2">Título da Vaga</label>
                <input
                  type="text"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  placeholder="Ex: Desenvolvedor Backend Python"
                  className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-2">Nível</label>
                <select
                  value={jobLevel}
                  onChange={(e) => setJobLevel(e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30"
                >
                  <option>Sem nível específico</option>
                  <option>Estagiário</option>
                  <option>Júnior</option>
                  <option>Pleno</option>
                  <option>Sênior</option>
                  <option>Especialista</option>
                </select>
              </div>
            </div>
          </div>

          {/* Upload */}
          <div>
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
              <Upload className="w-4 h-4 text-indigo-400" /> Currículo
            </h2>
            <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-slate-700/60 rounded-2xl cursor-pointer hover:border-indigo-500/40 hover:bg-slate-800/30 transition">
              <input type="file" accept=".pdf,.docx,.doc" className="hidden" onChange={handleFileChange} />
              {fileName ? (
                <div className="flex items-center gap-3 text-emerald-400">
                  <CheckCircle2 className="w-5 h-5" />
                  <span className="text-sm font-medium">{fileName}</span>
                </div>
              ) : (
                <div className="flex flex-col items-center text-slate-500">
                  <Upload className="w-6 h-6 mb-2" />
                  <span className="text-sm">Clique para enviar PDF ou DOCX</span>
                </div>
              )}
            </label>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              <XCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Analyze button */}
          <button
            onClick={() => {
              const input = document.querySelector('input[type="file"]') as HTMLInputElement
              if (input?.files?.[0]) analyzeCV(input.files[0])
            }}
            disabled={loading || !fileName}
            className="w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-sm hover:from-indigo-500 hover:to-purple-500 transition-all shadow-lg shadow-indigo-600/25 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" /> Analisando...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" /> Analisar Currículo
              </>
            )}
          </button>
        </motion.div>
      )}

      {/* Step 2: Results */}
      {activeStep === 2 && res && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="space-y-6"
        >
          {/* Score card */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                  <span className="text-xl font-black text-white">{res.nota?.toFixed(1)}</span>
                </div>
                <div>
                  <p className="text-sm font-bold text-white">Resume Score</p>
                  <p className="text-xs text-slate-500">Compatibilidade geral</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setActiveStep(1); setRes(null); setFileName(null) }}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800/60 text-slate-400 text-xs font-semibold border border-slate-700/60 hover:text-white hover:border-slate-600 transition"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Novo
                </button>
              </div>
            </div>

            {res.resumo_executivo && (
              <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800">
                <p className="text-sm text-slate-300 leading-relaxed">{res.resumo_executivo}</p>
              </div>
            )}

            {res.pontos_fortes && res.pontos_fortes.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Pontos Fortes</p>
                <div className="flex flex-wrap gap-2">
                  {res.pontos_fortes.map((p, i) => (
                    <span key={i} className="px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Diagnostic by section */}
          {res.diagnostico_por_secao && Object.keys(res.diagnostico_por_secao).length > 0 && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-4">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Cpu className="w-4 h-4 text-indigo-400" /> Diagnóstico por Seção
              </h2>
              {Object.entries(res.diagnostico_por_secao).map(([key, sec]) => (
                sec && (
                  <div key={key} className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-slate-300 capitalize">
                        {key.replace(/_/g, ' ')}
                      </span>
                      {getStatusBadge(sec.status)}
                    </div>
                    {sec.problema && (
                      <p className="text-xs text-rose-400 mb-1">⚠ {sec.problema}</p>
                    )}
                    {sec.como_corrigir && (
                      <p className="text-xs text-emerald-400">✓ {sec.como_corrigir}</p>
                    )}
                  </div>
                )
              ))}
            </div>
          )}

          {/* ATS Analysis */}
          {res.analise_ats && typeof res.analise_ats === 'object' && (
            <div className="p-6 md:p-8 rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 space-y-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 text-indigo-400 font-bold text-sm">
                  <div className="p-2 rounded-xl bg-indigo-500/10">
                    <Cpu className="w-4 h-4" />
                  </div>
                  Compatibilidade com Robôs ATS (Triagem Automática)
                </div>
                {res.analise_ats.score_ats !== undefined && (
                  <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-bold">
                    ATS Score: {res.analise_ats.score_ats}/10
                  </span>
                )}
              </div>

              <div className="space-y-4 text-xs">
                {res.analise_ats.veredito_robos && (
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-slate-300">
                    <strong className="block font-semibold text-white mb-1">🤖 Veredito dos Filtros Automáticos:</strong>
                    {res.analise_ats.veredito_robos}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {res.analise_ats.palavras_chave_faltantes && res.analise_ats.palavras_chave_faltantes.length > 0 && (
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-rose-500/20">
                      <strong className="block font-semibold text-rose-400 mb-2">Palavras-chave faltantes</strong>
                      <div className="flex flex-wrap gap-1.5">
                        {res.analise_ats.palavras_chave_faltantes.map((kw, i) => (
                          <span key={i} className="px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {res.analise_ats.gargalos_formatacao && res.analise_ats.gargalos_formatacao.length > 0 && (
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-amber-500/20">
                      <strong className="block font-semibold text-amber-400 mb-2">Gargalos de formatação</strong>
                      <div className="space-y-1">
                        {res.analise_ats.gargalos_formatacao.map((g, i) => (
                          <p key={i} className="text-slate-400">• {g}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Metrics box */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 overflow-hidden">
            <button
              onClick={() => setShowMetrics(!showMetrics)}
              className="w-full flex items-center justify-between p-5 text-left hover:bg-slate-800/30 transition"
            >
              <div className="flex items-center gap-2.5 text-indigo-400 font-bold text-sm">
                <div className="p-2 rounded-xl bg-indigo-500/10">
                  <Activity className="w-4 h-4" />
                </div>
                Consumo de Tokens da IA
              </div>
              <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${showMetrics ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
              {showMetrics && res.uso_tokens && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="px-5 pb-5 border-t border-slate-800/60 pt-4"
                >
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80 text-center">
                      <span className="block text-[10px] text-slate-400 font-medium uppercase">Entrada (Prompt)</span>
                      <span className="text-sm font-black text-indigo-300 font-mono">{formatTokens(res.uso_tokens.prompt_tokens)}</span>
                    </div>
                    <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80 text-center">
                      <span className="block text-[10px] text-slate-400 font-medium uppercase">Resposta (Output)</span>
                      <span className="text-sm font-black text-purple-300 font-mono">{formatTokens(res.uso_tokens.completion_tokens)}</span>
                    </div>
                    <div className="p-3 rounded-2xl bg-indigo-600/15 border border-indigo-500/30 text-center">
                      <span className="block text-[10px] text-indigo-400 font-bold uppercase">Total Geral</span>
                      <span className="text-sm font-black text-white font-mono">{formatTokens(res.uso_tokens.total_tokens)}</span>
                    </div>
                  </div>
                  {res.api_info && (
                    <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                        <span className="block text-[10px] text-slate-400 font-medium uppercase">Modelo</span>
                        <span className="text-xs font-bold text-slate-200 font-mono truncate block" title={res.api_info.model}>{res.api_info.model}</span>
                      </div>
                      <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                        <span className="block text-[10px] text-slate-400 font-medium uppercase">Tempo de Resposta</span>
                        <span className="text-xs font-bold text-emerald-400 font-mono flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          {(res.api_info.response_time_ms / 1000).toFixed(1)}s
                        </span>
                      </div>
                      <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                        <span className="block text-[10px] text-slate-400 font-medium uppercase">Request ID</span>
                        <span className="text-xs font-mono text-slate-500 truncate block" title={res.api_info.request_id}>{res.api_info.request_id.slice(0, 8)}...</span>
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Export buttons */}
          <div className="flex flex-wrap gap-3 justify-center">
            {[
              { id: 'pdf' as const, label: 'PDF', icon: <Download className="w-3.5 h-3.5" /> },
              { id: 'docx' as const, label: 'DOCX', icon: <FileSpreadsheet className="w-3.5 h-3.5" /> },
              { id: 'md' as const, label: 'Markdown', icon: <FileCode2 className="w-3.5 h-3.5" /> },
              { id: 'json' as const, label: 'JSON', icon: <FileText className="w-3.5 h-3.5" /> },
            ].map(({ id, label, icon }) => (
              <button
                key={id}
                onClick={() => handleExport(id)}
                disabled={exporting === id}
                className="flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-slate-800/60 text-slate-300 text-xs font-semibold border border-slate-700/60 hover:border-indigo-500/40 hover:text-indigo-300 transition disabled:opacity-50"
              >
                {exporting === id ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : icon}
                {label}
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
