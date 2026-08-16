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

export default function Home() {
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  // Step Control: 1 = Envio / Config, 2 = Diagnóstico
  const [activeStep, setActiveStep] = useState<1 | 2>(1)

  // Configurações de IA
  const [provider, setProvider] = useState<'openai' | 'custom'>('openai')
  const [apiKey, setApiKey] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [modelName, setModelName] = useState('gpt-4o')
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Form Vaga & Nível
  const [jobTitle, setJobTitle] = useState('')
  const [jobLevel, setJobLevel] = useState('Sem nível específico')
  const [isSelectOpen, setIsSelectOpen] = useState(false)

  // State para o box de métricas da IA
  const [showMetrics, setShowMetrics] = useState(false)
  const [showFullApiKey, setShowFullApiKey] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<{ type: 'success' | 'error'; message: string; savedUntil?: string } | null>(null)

  // Carregar configurações salvas
  useEffect(() => {
    try {
      const savedStr = localStorage.getItem(STORAGE_KEY)
      if (savedStr) {
        const saved: SavedAIConfig = JSON.parse(savedStr)
        const now = Date.now()
        if (saved.expiry && saved.expiry > now) {
          setProvider(saved.provider || 'openai')
          setApiKey(saved.apiKey || '')
          setApiUrl(saved.apiUrl || '')
          setModelName(saved.modelName || 'gpt-4o')
          
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
      formData.set('model_name', modelName)
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
      setProvider('openai')
      setApiUrl('')
      setModelName('gpt-4o')
    } else if (preset === 'openrouter') {
      setProvider('custom')
      setApiUrl('https://openrouter.ai/api/v1')
      setModelName('openai/gpt-4o')
    } else if (preset === 'ollama') {
      setProvider('custom')
      setApiUrl('http://localhost:11434/v1')
      setModelName('llama3')
    } else {
      setProvider('custom')
    }
  }

  const handleTestConnection = async () => {
    if (!apiKey.trim()) {
      setConnectionStatus({ type: 'error', message: 'Preencha a chave de API antes de testar a conexão.' })
      return
    }

    setTestingConnection(true)
    setConnectionStatus(null)

    const headers: Record<string, string> = {
      'api_key': apiKey.trim()
    }
    if (apiUrl.trim()) headers['api_url'] = apiUrl.trim()
    if (modelName.trim()) headers['model_name'] = modelName.trim()

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
      const configToSave: SavedAIConfig = {
        provider,
        apiKey: apiKey.trim(),
        apiUrl: apiUrl.trim(),
        modelName: modelName.trim(),
        message: data.message || `Conexão salva com modelo '${modelName}'!`,
        expiry
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(configToSave))

      const formattedExpiry = new Date(expiry).toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })

      setConnectionStatus({
        type: 'success',
        message: data.message || `Conexão bem-sucedida com o modelo '${modelName}'!`,
        savedUntil: formattedExpiry
      })
    } catch (err) {
      setConnectionStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Falha na conexão.'
      })
    } finally {
      setTestingConnection(false)
    }
  }

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setRes(null)
    const formData = new FormData(e.currentTarget)
    formData.set('job', jobTitle)
    formData.set('job_level', jobLevel)

    formData.set('api_key', apiKey.trim())
    if (apiUrl.trim()) formData.set('api_url', apiUrl.trim())
    if (modelName.trim()) formData.set('model_name', modelName.trim())

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
    <main className="relative min-h-screen flex flex-col items-center p-4 md:p-8 overflow-x-hidden bg-[#070a12]">
      {/* Background Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-tr from-indigo-600/20 via-purple-600/20 to-pink-600/10 rounded-full animate-pulse-glow pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-4xl z-10 space-y-6"
      >
        {/* Header Superior */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold tracking-wider">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Trivor
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white">
            Trivor
          </h1>
          <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">
            Análise inteligente e precisa de currículos para destacar seu perfil e superar os filtros ATS do mercado.
          </p>
        </div>

        {/* Tabbar de Passos (Step 1 & Step 2) */}
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setActiveStep(1)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs font-bold transition ${
              activeStep === 1
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-500'
                : 'bg-slate-900/60 text-slate-400 border border-slate-800 hover:text-slate-200'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-[10px]">1</span>
            Configuração & Envio
          </button>

          <ChevronRight className="w-4 h-4 text-slate-600" />

          <button
            onClick={() => res && setActiveStep(2)}
            disabled={!res}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs font-bold transition ${
              activeStep === 2
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-500'
                : res
                ? 'bg-slate-900/60 text-slate-300 border border-slate-800 hover:text-white cursor-pointer'
                : 'bg-slate-900/20 text-slate-600 border border-slate-900 cursor-not-allowed'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-[10px]">2</span>
            Relatório de Análise
          </button>
        </div>

        {/* PASSO 1: CONFIGURAÇÃO & ENVIO */}
        {activeStep === 1 && (
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="bg-slate-900/60 backdrop-blur-xl p-6 md:p-8 rounded-3xl border border-slate-800 shadow-2xl shadow-indigo-950/20 space-y-6"
          >
            <form onSubmit={submit} className="space-y-6">
              
              {/* Bloco de Configuração da IA (Com colapso inicial se já testado) */}
              <div className="p-5 rounded-2xl bg-slate-950/40 border border-slate-800/80 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5 text-sm font-semibold text-indigo-400">
                    <Cpu className="w-4 h-4" />
                    Provedor & Motor de IA
                    {connectionStatus?.type === 'success' && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" /> API Conectada
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 transition"
                  >
                    <Sliders className="w-3.5 h-3.5" />
                    {showAdvanced ? 'Minimizar' : 'Configurações / Alterar'}
                  </button>
                </div>

                {/* Mostra resumo simples se minimizado e conectado */}
                {!showAdvanced && connectionStatus?.type === 'success' ? (
                  <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800/60 flex items-center justify-between text-xs text-slate-300">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white uppercase">{provider}</span>
                      <span className="text-slate-500">•</span>
                      <span className="font-mono text-indigo-300">{modelName}</span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Chave: {getMaskedApiKey(apiKey)}
                    </span>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Presets */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {[
                        { id: 'openai', label: 'OpenAI Oficial', desc: 'GPT-4o (Padrão)' },
                        { id: 'openrouter', label: 'OpenRouter', desc: 'Multi-modelos Cloud' },
                        { id: 'ollama', label: 'Ollama / Local', desc: 'Llama3 (Localhost)' },
                        { id: 'custom', label: 'Personalizado', desc: 'URL/Modelo Próprio' }
                      ].map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => handleProviderPreset(p.id as any)}
                          className={`p-3 rounded-xl border text-left transition flex flex-col justify-between ${
                            (p.id === 'openai' && provider === 'openai') || (p.id !== 'openai' && provider === 'custom' && ((p.id === 'openrouter' && apiUrl.includes('openrouter')) || (p.id === 'ollama' && apiUrl.includes('11434')) || (p.id === 'custom' && !apiUrl.includes('openrouter') && !apiUrl.includes('11434'))))
                              ? 'bg-indigo-600/15 border-indigo-500/60 text-white'
                              : 'bg-slate-900/40 border-slate-800/60 text-slate-400 hover:border-slate-700'
                          }`}
                        >
                          <span className="text-xs font-bold">{p.label}</span>
                          <span className="text-[10px] opacity-70 mt-1">{p.desc}</span>
                        </button>
                      ))}
                    </div>

                    {/* Inputs API Key + Modelo */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                            <Key className="w-3.5 h-3.5 text-indigo-400" />
                            Chave de API (API Key)
                          </label>
                          {apiKey && !showFullApiKey && (
                            <span className="text-[10px] font-mono text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                              {getMaskedApiKey(apiKey)}
                            </span>
                          )}
                        </div>

                        <div className="relative flex items-center">
                          <input
                            type={showFullApiKey ? "text" : "password"}
                            value={apiKey}
                            onChange={(e) => {
                              setApiKey(e.target.value)
                              setConnectionStatus(null)
                            }}
                            placeholder={provider === 'openai' ? 'sk-proj-...' : 'Cole sua chave de API'}
                            required
                            className="w-full pl-4 pr-10 py-2.5 rounded-xl bg-slate-900 text-slate-100 placeholder-slate-500 border border-slate-800 focus:border-indigo-500 outline-none text-xs transition font-mono"
                          />

                          <button
                            type="button"
                            onClick={() => setShowFullApiKey(!showFullApiKey)}
                            title={showFullApiKey ? "Ocultar chave" : "Exibir chave completa"}
                            className="absolute right-2.5 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                          >
                            {showFullApiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                          <Settings2 className="w-3.5 h-3.5 text-indigo-400" />
                          Nome do Modelo
                        </label>
                        <input
                          type="text"
                          value={modelName}
                          onChange={(e) => {
                            setModelName(e.target.value)
                            setConnectionStatus(null)
                          }}
                          placeholder="ex: gpt-4o, claude-3-5-sonnet, llama3"
                          required
                          className="w-full px-4 py-2.5 rounded-xl bg-slate-900 text-slate-100 placeholder-slate-500 border border-slate-800 focus:border-indigo-500 outline-none text-xs transition"
                        />
                      </div>
                    </div>

                    {/* Base URL */}
                    {(showAdvanced || provider === 'custom') && (
                      <div className="space-y-1.5 pt-1">
                        <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                          <Globe className="w-3.5 h-3.5 text-indigo-400" />
                          Base URL (Opcional - Compatível OpenAI)
                        </label>
                        <input
                          type="text"
                          value={apiUrl}
                          onChange={(e) => {
                            setApiUrl(e.target.value)
                            setConnectionStatus(null)
                          }}
                          placeholder="https://api.openai.com/v1 ou http://localhost:11434/v1"
                          className="w-full px-4 py-2.5 rounded-xl bg-slate-900 text-slate-100 placeholder-slate-500 border border-slate-800 focus:border-indigo-500 outline-none text-xs transition"
                        />
                      </div>
                    )}

                    {/* Botão Testar & Salvar */}
                    <div className="pt-2 border-t border-slate-800/60 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
                      <button
                        type="button"
                        onClick={handleTestConnection}
                        disabled={testingConnection || !apiKey.trim()}
                        className="px-4 py-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600 hover:text-white transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-xs font-semibold"
                      >
                        {testingConnection ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            Testando Conexão...
                          </>
                        ) : (
                          <>
                            <Activity className="w-3.5 h-3.5" />
                            Testar & Salvar Conexão
                          </>
                        )}
                      </button>

                      {connectionStatus && (
                        <div className={`px-3 py-1.5 rounded-xl border text-xs flex items-center gap-2 ${
                          connectionStatus.type === 'success'
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                            : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                        }`}>
                          {connectionStatus.type === 'success' ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                          ) : (
                            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                          )}
                          <span>{connectionStatus.message}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Vaga & Nível de Experiência Organizados */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="md:col-span-2 space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Briefcase className="w-3.5 h-3.5 text-indigo-400" />
                    Vaga / Cargo Desejado
                  </label>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="Ex: Desenvolvedor Full Stack, Designer UI/UX"
                    className="w-full px-4 py-3 rounded-xl bg-slate-950/60 text-slate-100 placeholder-slate-500 border border-slate-800 focus:border-indigo-500 outline-none text-sm transition"
                  />
                </div>

                <div className="space-y-1.5 relative">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-indigo-400" />
                    Nível da Vaga
                  </label>
                  
                  {/* Select Customizado UI/UX em vez do combo nativo feio */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setIsSelectOpen(!isSelectOpen)}
                      className="w-full px-4 py-3 rounded-xl bg-slate-950/60 text-slate-100 border border-slate-800 focus:border-indigo-500 flex items-center justify-between text-xs font-medium transition hover:border-slate-700"
                    >
                      <span className="truncate">{jobLevel}</span>
                      <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isSelectOpen ? 'rotate-180' : ''}`} />
                    </button>

                    <AnimatePresence>
                      {isSelectOpen && (
                        <motion.div
                          initial={{ opacity: 0, y: -5 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -5 }}
                          className="absolute left-0 right-0 top-full mt-1 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 overflow-hidden py-1"
                        >
                          {[
                            'Sem nível específico',
                            'Estágio / Trainee',
                            'Júnior / Iniciante',
                            'Pleno / Intermediário',
                            'Sênior / Avançado',
                            'Especialista / Lead'
                          ].map((option) => (
                            <button
                              key={option}
                              type="button"
                              onClick={() => {
                                setJobLevel(option)
                                setIsSelectOpen(false)
                              }}
                              className={`w-full text-left px-4 py-2.5 text-xs transition flex items-center justify-between ${
                                jobLevel === option
                                  ? 'bg-indigo-600/20 text-indigo-300 font-bold border-l-2 border-indigo-500'
                                  : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                              }`}
                            >
                              {option}
                              {jobLevel === option && <Check className="w-3.5 h-3.5 text-indigo-400" />}
                            </button>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </div>

              {/* Upload de Arquivo PDF */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-indigo-400" />
                  Arquivo de Currículo (.pdf)
                </label>
                <div className="relative border-2 border-dashed border-slate-800 hover:border-indigo-500/50 rounded-2xl p-6 text-center bg-slate-950/30 hover:bg-slate-950/50 transition cursor-pointer group">
                  <input
                    type="file"
                    name="file"
                    accept=".pdf"
                    onChange={handleFileChange}
                    required
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                  />
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 group-hover:scale-110 transition">
                      <Upload className="w-6 h-6" />
                    </div>
                    {fileName ? (
                      <span className="text-sm font-medium text-emerald-400 flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4" /> {fileName}
                      </span>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-slate-300">
                          Clique ou arraste seu currículo em PDF aqui
                        </p>
                        <p className="text-xs text-slate-500">Suporta apenas formato PDF (Máx 10MB)</p>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Botão de Envio */}
              <button
                type="submit"
                disabled={loading}
                className={`w-full py-4 px-6 rounded-xl font-bold text-sm tracking-wide transition flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 ${
                  loading
                    ? 'bg-indigo-900/50 text-indigo-300 cursor-wait'
                    : 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white'
                }`}
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-5 h-5 animate-spin" />
                    Analisando com {modelName}...
                  </>
                ) : (
                  <>
                    <Zap className="w-5 h-5" />
                    GERAR DIAGNÓSTICO E2E
                  </>
                )}
              </button>
            </form>
          </motion.div>
        )}

        {/* PASSO 2: EXIBIÇÃO ORGANIZADA DO RELATÓRIO */}
        {activeStep === 2 && res && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-6"
          >
            {/* Header de Ações + Botões de Exportação + Botão de Nova Análise */}
            <div className="flex flex-col md:flex-row items-center justify-between p-4 rounded-2xl bg-slate-900/60 border border-slate-800 gap-4">
              <div className="flex items-center gap-3 text-xs text-slate-300">
                <span className="font-semibold text-white flex items-center gap-1.5">
                  <FileCode2 className="w-4 h-4 text-indigo-400" /> {fileName || 'Curriculo.pdf'}
                </span>
                <span className="text-slate-600">•</span>
                <span className="text-slate-400">Vaga: {jobTitle || 'Geral'} ({jobLevel})</span>
                <span className="text-slate-600">•</span>
                <span className="font-mono text-indigo-300">{modelName}</span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {/* Botões de Exportação em Formatos Vários */}
                <div className="flex items-center gap-1.5 bg-slate-950/60 p-1.5 rounded-xl border border-slate-800">
                  <span className="text-[10px] font-bold text-slate-400 px-2 flex items-center gap-1 uppercase tracking-wider">
                    <Download className="w-3 h-3 text-indigo-400" /> Baixar:
                  </span>
                  {[
                    { id: 'pdf', label: 'PDF', color: 'hover:bg-rose-500/20 text-rose-300 border-rose-500/30' },
                    { id: 'docx', label: 'DOCX', color: 'hover:bg-blue-500/20 text-blue-300 border-blue-500/30' },
                    { id: 'md', label: 'MD', color: 'hover:bg-purple-500/20 text-purple-300 border-purple-500/30' },
                    { id: 'json', label: 'JSON', color: 'hover:bg-amber-500/20 text-amber-300 border-amber-500/30' }
                  ].map((btn) => (
                    <button
                      key={btn.id}
                      onClick={() => handleExport(btn.id as any)}
                      disabled={!!exporting}
                      className={`px-2.5 py-1 rounded-lg border text-[11px] font-bold font-mono transition flex items-center gap-1 bg-slate-900 ${btn.color} disabled:opacity-50`}
                    >
                      {exporting === btn.id ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        btn.label
                      )}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => setActiveStep(1)}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold flex items-center gap-1.5 transition"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Nova Análise
                </button>
              </div>
            </div>

            {/* Score & Resumo Executivo */}
            {(() => {
              const scoreTheme = getScoreColor(res.nota)
              return (
                <div className={`p-6 md:p-8 rounded-3xl bg-slate-900/80 backdrop-blur-xl border ${scoreTheme.border} grid grid-cols-1 md:grid-cols-3 gap-6 items-center`}>
                  <div className="flex flex-col items-center justify-center md:border-r border-slate-800 pr-0 md:pr-6">
                    <span className="text-xs uppercase tracking-widest text-slate-400 font-bold mb-2">Resume Score</span>
                    <div className="relative flex items-center justify-center">
                      <svg className="w-32 h-32 transform -rotate-90">
                        <circle cx="64" cy="64" r="54" stroke="#1e293b" strokeWidth="10" fill="transparent" />
                        <circle
                          cx="64"
                          cy="64"
                          r="54"
                          stroke={scoreTheme.stroke}
                          strokeWidth="10"
                          fill="transparent"
                          strokeDasharray="339.29"
                          strokeDashoffset={339.29 - (res.nota || 0) * 33.929}
                          strokeLinecap="round"
                          className="transition-all duration-1000 ease-out"
                        />
                      </svg>
                      <div className="absolute flex flex-col items-center">
                        <span className={`text-3xl font-black ${scoreTheme.text}`}>
                          {res.nota?.toFixed(1) || '0.0'}
                        </span>
                        <span className="text-[10px] text-slate-500 font-semibold">DE 10</span>
                      </div>
                    </div>
                  </div>

                  <div className="md:col-span-2 space-y-3">
                    <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
                      <Award className="w-4 h-4" />
                      Parecer Executivo
                    </div>
                    <h3 className="text-xl font-bold text-white">
                      {res.resumo_executivo || 'Diagnóstico concluído com sucesso.'}
                    </h3>
                  </div>
                </div>
              )
            })()}

            {/* Diagnóstico Organizado Bloco a Bloco */}
            {res.diagnostico_por_secao && (
              <div className="space-y-4">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <FileSearch className="w-5 h-5 text-indigo-400" />
                  Diagnóstico Estruturado por Seção do Currículo
                </h3>

                <div className="grid grid-cols-1 gap-4">
                  {[
                    { key: 'dados_pessoais', title: '👤 Dados Pessoais & Contatos', item: res.diagnostico_por_secao.dados_pessoais },
                    { key: 'resumo_profissional', title: '📝 Resumo / Perfil Profissional', item: res.diagnostico_por_secao.resumo_profissional },
                    { key: 'experiencia_profissional', title: '💼 Experiência Profissional & Métricas', item: res.diagnostico_por_secao.experiencia_profissional },
                    { key: 'educacao_e_cursos', title: '🎓 Formação Acadêmica & Cursos', item: res.diagnostico_por_secao.educacao_e_cursos },
                    { key: 'habilidades_e_keywords', title: '🛠️ Habilidades & Palavras-Chave', item: res.diagnostico_por_secao.habilidades_e_keywords }
                  ].map((secao) => (
                    secao.item && (
                      <div key={secao.key} className="p-5 rounded-2xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="font-bold text-slate-100 text-sm">{secao.title}</h4>
                          {getStatusBadge(secao.item.status)}
                        </div>

                        {secao.item.problema && (
                          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-200 text-xs">
                            <strong className="block font-semibold mb-1 text-rose-300">⚠️ Problema Detectado:</strong>
                            {secao.item.problema}
                          </div>
                        )}

                        {secao.item.como_corrigir && (
                          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-200 text-xs">
                            <strong className="block font-semibold mb-1 text-emerald-300">💡 Como Ajustar Exatamente:</strong>
                            {secao.item.como_corrigir}
                          </div>
                        )}
                      </div>
                    )
                  ))}
                </div>
              </div>
            )}

            {/* Relatório de Compatibilidade ATS */}
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
                    {/* Keywords Faltantes */}
                    {res.analise_ats.palavras_chave_faltantes && res.analise_ats.palavras_chave_faltantes.length > 0 && (
                      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-200">
                        <strong className="block font-semibold text-amber-300 mb-2">🔑 Palavras-Chave Faltantes no CV:</strong>
                        <div className="flex flex-wrap gap-1.5">
                          {res.analise_ats.palavras_chave_faltantes.map((kw, i) => (
                            <span key={i} className="px-2 py-1 rounded bg-amber-500/20 border border-amber-500/30 text-[11px] font-mono text-amber-100">
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Gargalos de Formatação */}
                    {res.analise_ats.gargalos_formatacao && res.analise_ats.gargalos_formatacao.length > 0 && (
                      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-200">
                        <strong className="block font-semibold text-rose-300 mb-2">🚨 Gargalos de Parsing / Formatação:</strong>
                        <ul className="list-disc list-inside space-y-1">
                          {res.analise_ats.gargalos_formatacao.map((g, i) => (
                            <li key={i}>{g}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Pontos Fortes */}
            {res.pontos_fortes && res.pontos_fortes.length > 0 && (
              <div className="p-6 rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-emerald-500/20 space-y-3">
                <div className="flex items-center gap-2.5 text-emerald-400 font-bold text-sm">
                  <div className="p-2 rounded-xl bg-emerald-500/10">
                    <TrendingUp className="w-4 h-4" />
                  </div>
                  Pontos Fortes Rastreados
                </div>
                <ul className="space-y-2">
                  {res.pontos_fortes.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-2.5 text-slate-300 text-xs">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Métricas de Uso de Tokens e Performance da IA */}
            {res.uso_tokens && (
              <div className="rounded-3xl bg-slate-950/50 backdrop-blur-xl border border-indigo-500/20 overflow-hidden transition-all duration-300">
                {/* Header Clicável (Minimizado por padrão) */}
                <button
                  onClick={() => setShowMetrics(!showMetrics)}
                  className="w-full p-5 flex items-center justify-between gap-4 text-left hover:bg-slate-900/40 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-2xl bg-indigo-500/10 text-indigo-400">
                      <BarChart3 className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        Consumo de Tokens e Performance da IA
                        <span className="text-[10px] normal-case bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/30">
                          {formatTokens(res.uso_tokens.total_tokens)} tokens
                        </span>
                      </h4>
                      <p className="text-[11px] text-slate-400">Clique para ver métricas detalhadas da requisição</p>
                    </div>
                  </div>
                  <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400">
                    <ChevronDown className={`w-4 h-4 transition-transform duration-300 ${showMetrics ? 'rotate-180' : ''}`} />
                  </div>
                </button>

                {/* Conteúdo Expansível */}
                <AnimatePresence>
                  {showMetrics && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.3 }}
                      className="border-t border-slate-800/60 p-5 space-y-4 bg-slate-950/40"
                    >
                      {/* Métricas de Tokens */}
                      <div>
                        <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2">Consumo de Tokens</span>
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
                      </div>

                      {/* Métricas Técnicas da API */}
                      {res.api_info && (
                        <div>
                          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2">Dados da API</span>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                              <span className="block text-[10px] text-slate-400 font-medium uppercase">Modelo Utilizado</span>
                              <span className="text-xs font-bold text-slate-200 font-mono truncate block" title={res.api_info.model}>{res.api_info.model}</span>
                            </div>

                            <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                              <span className="block text-[10px] text-slate-400 font-medium uppercase">Tempo de Resposta</span>
                              <span className="text-xs font-bold text-emerald-400 font-mono flex items-center gap-1">
                                <Zap className="w-3 h-3" /> {(res.api_info.response_time_ms / 1000).toFixed(2)}s ({res.api_info.response_time_ms} ms)
                              </span>
                            </div>

                            <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800/80">
                              <span className="block text-[10px] text-slate-400 font-medium uppercase">ID da Requisição</span>
                              <span className="text-xs font-bold text-slate-300 font-mono truncate block" title={res.api_info.request_id}>{res.api_info.request_id || 'N/A'}</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </motion.div>
        )}
      </motion.div>
    </main>
  )
}
