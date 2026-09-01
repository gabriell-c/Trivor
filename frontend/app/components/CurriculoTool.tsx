'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Key, Briefcase, Upload, Sparkles, CheckCircle2, AlertTriangle, TrendingUp, Cpu, RefreshCw, Zap, Award, Settings2, Globe, Sliders, Eye, EyeOff, Check, XCircle, Activity, Clock, BarChart3, UserCheck, FileSearch, ChevronRight, RotateCcw, Target, FileCode2, AlertCircle, Download, FileSpreadsheet, ChevronDown } from 'lucide-react'
import type { AnalysisResult, AnaliseSecao, ErroComum } from '../types/analysis'
import { API_BASE_URL } from '../lib/api'
import { CustomSelect } from './CustomSelect'
import { Dropzone } from './Dropzone'
import { getBestProvider } from '../hooks/useIaProviders'

const SECTION_LABELS: Record<string, string> = {
  contato: 'Contato',
  summary: 'Profile Summary',
  experiencia: 'Experiência',
  educacao: 'Educação',
  habilidades: 'Habilidades',
  projetos: 'Projetos',
  certificacoes: 'Certificações',
  idiomas: 'Idiomas'
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  descricao_vaga: 'Descrição da vaga genérica',
  texto_paragraph: 'Texto em parágrafos longos',
  falta_numeros: 'Falta de números/métricas',
  abreviacoes: 'Abreviações desconhecidas',
  motivo_saida: 'Motivo de saída do emprego',
  summary_generico: 'Profile summary genérico',
  espaco_branco: 'Espaço em branco excessivo',
  tech_so_skills: 'Tecnologias só em skills',
  foto: 'Foto no currículo',
  graficos: 'Gráficos/barras de habilidade',
  formatacao_inconsistente: 'Formatação inconsistente'
}

export default function CurriculoTool() {
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  // Step Control: 1 = Envio / Config, 2 = Diagnóstico
  const [activeStep, setActiveStep] = useState<1 | 2>(1)
  const [jobLevel, setJobLevel] = useState('Sem nível específico')
  const [jobTitle, setJobTitle] = useState('')
  const [showJobDesc, setShowJobDesc] = useState(false)
  const [area, setArea] = useState('')

  // State para o box de métricas da IA
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportFormat, setExportFormat] = useState<'json' | 'md' | 'docx' | 'pdf'>('pdf')

  const handleExport = async () => {
    if (!res) return
    setExporting(exportFormat)
    try {
      const formData = new FormData()
      formData.set('format', exportFormat)
      formData.set('filename', fileName || 'Curriculo.pdf')
      formData.set('job_target', `${jobTitle || 'Geral'} (${jobLevel})`)
      formData.set('data_json', JSON.stringify(res))

      const response = await fetch(`${API_BASE_URL}/api/export`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) throw new Error('Falha ao gerar arquivo de exportação.')

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Diagnostico_CV_${fileName?.replace('.pdf', '') || 'Analise'}.${exportFormat}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Erro ao baixar o arquivo.')
    } finally {
      setExporting(null)
    }
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

  const analyzeCV = async (file: File) => {
    setLoading(true)
    setError(null)
    setRes(null)
    const formData = new FormData()
    formData.append('cv_file', file)
    if (area) formData.set('area', area)
    if (jobTitle.trim()) formData.set('job_description', jobTitle.trim())
    if (jobLevel !== 'Sem nível específico') formData.set('target_role', jobLevel.toLowerCase())
    const provider = getBestProvider(['curriculo'])
    if (provider) {
      formData.set('api_key', provider.apiKey)
      formData.set('api_url', provider.apiUrl)
      formData.set('model_name', provider.modelName)
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/analyze`, {
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
    if (score >= 80) return { text: 'text-emerald-400', stroke: '#10b981', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
    if (score >= 60) return { text: 'text-amber-400', stroke: '#f59e0b', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
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
        <AlertCircle className="w-3.5 h-3.5" /> Crítico
      </span>
    )
  }

  const renderAnaliseSecoes = (data?: Record<string, AnaliseSecao>) => {
    if (!data) return null
    const entries = Object.entries(data)
    return entries.map(([key, value]) => {
      const label = SECTION_LABELS[key] || key
      return (
        <div key={key} className="rounded-2xl bg-slate-950/60 border border-slate-800/80 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-bold text-white">{label}</h3>
              {value.presente === false && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-500">Não presente</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono text-slate-500">{value.score}/10</span>
              {value.status && getStatusBadge(value.status)}
            </div>
          </div>

          {/* Badges para experiência */}
          {key === 'experiencia' && (value.has_xyz !== undefined || value.has_metrics !== undefined || value.bullet_points !== undefined) && (
            <div className="flex flex-wrap gap-2 mb-3">
              {value.has_xyz && (
                <span className="text-[10px] px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  ✓ Fórmula XYZ
                </span>
              )}
              {value.has_metrics === false && (
                <span className="text-[10px] px-2 py-1 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  ✗ Sem métricas
                </span>
              )}
              {value.bullet_points === false && (
                <span className="text-[10px] px-2 py-1 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  ✗ Parágrafos em vez de bullets
                </span>
              )}
              {value.bullet_points === true && (
                <span className="text-[10px] px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  ✓ Bullet points
                </span>
              )}
            </div>
          )}

          {value.problema && (
            <div className="mb-3">
              <p className="text-xs text-rose-400 font-medium mb-1">Problema detectado:</p>
              <p className="text-sm text-slate-400">{value.problema}</p>
            </div>
          )}
          {value.como_corrigir && (
            <div>
              <p className="text-xs text-emerald-400 font-medium mb-1">Como corrigir:</p>
              <p className="text-sm text-slate-400">{value.como_corrigir}</p>
            </div>
          )}
        </div>
      )
    })
  }

  const renderErrosComuns = (erros?: ErroComum[]) => {
    if (!erros || erros.length === 0) return null
    return (
      <div className="space-y-2">
        {erros.map((erro, i) => (
          <div key={i} className="rounded-xl bg-slate-950/60 border border-slate-800/80 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-amber-400">
                    {ERROR_TYPE_LABELS[erro.tipo] || erro.tipo}
                  </span>
                </div>
                <p className="text-sm text-slate-400">{erro.descricao}</p>
                {erro.exemplo && (
                  <div className="mt-2 p-2 rounded-lg bg-slate-900/80 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Exemplo no currículo:</p>
                    <p className="text-sm text-slate-300 font-mono">{erro.exemplo}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <FileSearch className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-white">Diagnóstico de Currículo</h1>
            <p className="text-sm text-slate-500">Análise completa com IA para otimização de ATS</p>
          </div>
        </div>
      </div>

      {/* Step Navigation */}
      <div className="flex gap-2 mb-8">
        <button
          onClick={() => setActiveStep(1)}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-all ${
            activeStep === 1
              ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-600/25'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <FileText className="w-3.5 h-3.5" /> 1. Envio
        </button>
        <button
          onClick={() => setActiveStep(2)}
          disabled={activeStep !== 2 || !res}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-all ${
            activeStep === 2
              ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-600/25'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <Activity className="w-3.5 h-3.5" /> 2. Diagnóstico
        </button>
      </div>

      {/* Step 1: Upload */}
      {activeStep === 1 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="space-y-6"
        >
          {/* File Upload */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Upload className="w-4 h-4 text-indigo-400" /> Upload do Currículo
            </h2>
            <Dropzone
              onFileSelect={setSelectedFile}
              accept=".pdf,.docx,.doc"
            />
            {selectedFile && (
              <p className="mt-3 text-xs text-emerald-400 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>

          {/* Config */}
          <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Target className="w-4 h-4 text-indigo-400" /> Configuração da Análise
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  Sua Área de Atuação <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  placeholder="Ex: Administrativo, Tecnologia, Vendas..."
                  className="w-full px-4 py-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-indigo-500/60"
                />
              </div>
              <div>
                <button
                  type="button"
                  onClick={() => setShowJobDesc(v => !v)}
                  className="flex items-center justify-between w-full text-xs font-medium text-slate-400 hover:text-slate-300 transition-colors"
                >
                  <span>Descrição da vaga (opcional)</span>
                  <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showJobDesc ? 'rotate-180' : ''}`} />
                </button>
                {showJobDesc && (
                  <textarea
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="Cole aqui a descrição da vaga alvo para análise de compatibilidade..."
                    className="w-full mt-2 h-24 px-4 py-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-indigo-500/60 resize-none"
                  />
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  Nível desejado
                </label>
                <CustomSelect
                  value={jobLevel}
                  onChange={setJobLevel}
                  options={[
                    { value: 'Sem nível específico', label: 'Sem nível específico' },
                    { value: 'Estágio', label: 'Estágio' },
                    { value: 'Júnior', label: 'Júnior' },
                    { value: 'Pleno', label: 'Pleno' },
                    { value: 'Sênior', label: 'Sênior' },
                    { value: 'Lead', label: 'Lead' },
                    { value: 'Manager', label: 'Manager' }
                  ]}
                />
              </div>
            </div>
          </div>

          {/* Analyze Button */}
          <button
            onClick={() => {
              if (!selectedFile) return
              if (!area) {
                setError('Selecione sua área de atuação para continuar.')
                return
              }
              analyzeCV(selectedFile)
            }}
            disabled={loading || !selectedFile || !area}
            className="w-full py-4 rounded-2xl text-sm font-bold bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-500 hover:to-purple-500 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/25"
          >
            {loading ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Analisando currículo...</>
            ) : (
              <><Sparkles className="w-4 h-4" /> Analisar Currículo</>
            )}
          </button>

          {error && (
            <div className="rounded-2xl bg-rose-500/10 border border-rose-500/30 p-4">
              <p className="text-sm text-rose-400">{error}</p>
            </div>
          )}
        </motion.div>
      )}
      <AnimatePresence mode="wait">
      {/* Step 2: Results */}
      {activeStep === 2 && res && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-6"
        >
          {/* Score card */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
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
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value as 'json' | 'md' | 'docx' | 'pdf')}
                  className="px-2 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-300 border border-slate-700/60 focus:outline-none focus:border-indigo-500/40"
                >
                  <option value="pdf">PDF</option>
                  <option value="docx">DOCX</option>
                  <option value="md">Markdown</option>
                  <option value="json">JSON</option>
                </select>
                <button
                  onClick={handleExport}
                  disabled={exporting !== null}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition disabled:opacity-50"
                >
                  {exporting !== null ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : (
                    <><Download className="w-3 h-3" /> Exportar</>
                  )}
                </button>
                <button
                  onClick={() => setActiveStep(1)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition"
                >
                  <RotateCcw className="w-3 h-3" />
                  Nova análise
                </button>
              </div>
            </div>

            {res.uso_tokens && (
              <details className="mt-4 rounded-2xl bg-slate-900/60 border border-slate-800">
                <summary className="flex items-center justify-between px-5 py-3 cursor-pointer text-xs font-bold text-slate-400 uppercase tracking-wider hover:text-slate-300 select-none">
                  <span className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-indigo-400" /> Uso de Tokens</span>
                  <ChevronDown className="w-4 h-4 transition-transform duration-200" />
                </summary>
                <div className="px-5 pb-4 pt-2 grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-[10px] text-slate-500 mb-1">Modelo</p>
                    <p className="text-xs font-black text-white font-mono truncate">{res.api_info?.model || '—'}</p>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-[10px] text-slate-500 mb-1">Input</p>
                    <p className="text-xs font-black text-indigo-300 font-mono">{formatTokens(res.uso_tokens?.prompt_tokens)}</p>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-[10px] text-slate-500 mb-1">Output</p>
                    <p className="text-xs font-black text-purple-300 font-mono">{formatTokens(res.uso_tokens?.completion_tokens)}</p>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-[10px] text-slate-500 mb-1">Total</p>
                    <p className="text-xs font-black text-white font-mono">{formatTokens(res.uso_tokens?.total_tokens)}</p>
                  </div>
                </div>
              </details>
            )}

            {res.resumo_executivo && (
              <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Resumo Executivo</p>
                <p className="text-sm text-slate-300 leading-relaxed">{res.resumo_executivo}</p>
              </div>
            )}

            {res.pontos_fortes && res.pontos_fortes.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Pontos Fortes</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {res.pontos_fortes.map((ponto, i) => (
                    <div key={i} className="flex items-start gap-2 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-emerald-200/80">{ponto}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {res.pontos_fracos && res.pontos_fracos.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Pontos de Atenção</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {res.pontos_fracos.map((ponto, i) => (
                    <div key={i} className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/5 border border-rose-500/20">
                      <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-rose-200/80">{ponto}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>

          {/* Foto e Ordem das Seções */}
          {(res.foto_detectada !== undefined || res.ordem_secoes) && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <FileCode2 className="w-4 h-4 text-indigo-400" /> Estrutura do Currículo
              </h2>
              <div className="space-y-4">
                {/* Foto */}
                {res.foto_detectada !== undefined && (
                  <div className="rounded-2xl bg-slate-950/60 border border-slate-800/80 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Eye className={`w-5 h-5 ${res.foto_detectada ? 'text-rose-400' : 'text-emerald-400'}`} />
                        <div>
                          <p className="text-sm font-bold text-white">
                            {res.foto_detectada ? 'Foto detectada' : 'Sem foto'}
                          </p>
                          <p className="text-xs text-slate-500">
                            {res.foto_recomendada === false
                              ? 'Foto não recomendada para vaga de tecnologia'
                              : res.foto_recomendada === true
                              ? 'Foto recomendada para esta vaga'
                              : 'Análise de foto'}
                          </p>
                        </div>
                      </div>
                      {res.foto_detectada && (
                        <span className="px-3 py-1 rounded-full text-xs font-bold bg-rose-500/15 border border-rose-500/30 text-rose-400">
                          Remover foto
                        </span>
                      )}
                    </div>
                    {res.foto_detectada && res.foto_recomendada === false && (
                      <p className="mt-3 text-sm text-slate-400">
                        Currículos com foto são descartados automaticamente por muitos ATS. Remova a foto para aumentar suas chances.
                      </p>
                    )}
                  </div>
                )}

                {/* Ordem das seções */}
                {res.ordem_secoes && (
                  <div className="rounded-2xl bg-slate-950/60 border border-slate-800/80 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <Activity className="w-5 h-5 text-indigo-400" />
                        <p className="text-sm font-bold text-white">Ordem das Seções</p>
                      </div>
                      {res.ordem_secoes.correta ? (
                        <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                          <CheckCircle2 className="w-3 h-3 inline mr-1" />Correta
                        </span>
                      ) : (
                        <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-500/15 border border-amber-500/30 text-amber-400">
                          <AlertCircle className="w-3 h-3 inline mr-1" />Requer ajuste
                        </span>
                      )}
                    </div>
                    {res.ordem_secoes.problema && (
                      <p className="text-sm text-slate-400 mb-2">{res.ordem_secoes.problema}</p>
                    )}
                    {res.ordem_secoes.como_corrigir && (
                      <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                        <p className="text-xs text-emerald-400 font-medium mb-1">Como corrigir:</p>
                        <p className="text-sm text-slate-400">{res.ordem_secoes.como_corrigir}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Palavras-chave */}
          {(res.palavras_chave_presentes?.length ?? 0) > 0 || (res.palavras_chave_faltantes?.length ?? 0) > 0 ? (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <Target className="w-4 h-4 text-indigo-400" /> Palavras-chave
              </h2>
              <div className="space-y-4">
                {res.palavras_chave_presentes && res.palavras_chave_presentes.length > 0 && (
                  <div>
                    <p className="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-2">
                      Presentes ({res.palavras_chave_presentes.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {res.palavras_chave_presentes.map((kw, i) => (
                        <span key={i} className="px-2.5 py-1 rounded-full text-xs bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                          {kw}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {res.palavras_chave_faltantes && res.palavras_chave_faltantes.length > 0 && (
                  <div>
                    <p className="text-xs font-bold text-rose-400 uppercase tracking-wider mb-2">
                      Faltantes ({res.palavras_chave_faltantes.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {res.palavras_chave_faltantes.map((kw, i) => (
                        <span key={i} className="px-2.5 py-1 rounded-full text-xs bg-rose-500/10 text-rose-300 border border-rose-500/20">
                          {kw}
                        </span>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-2">
                      Adicione estas palavras-chave naturalmente no currículo para melhorar a compatibilidade com o ATS.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {/* Erros comuns detectados */}
          {res.erros_comuns_detectados && res.erros_comuns_detectados.length > 0 && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <AlertTriangle className="w-4 h-4 text-amber-400" /> Erros Comuns Detectados
              </h2>
              {renderErrosComuns(res.erros_comuns_detectados)}
            </div>
          )}

          {/* ATS Analysis */}
          {res.analise_ats && typeof res.analise_ats === 'object' && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <Cpu className="w-4 h-4 text-indigo-400" /> Análise ATS
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60">
                  <p className="text-xs text-slate-500 mb-1">Score ATS</p>
                  <p className="text-2xl font-black text-white">{res.analise_ats.score_ats ?? '—'}</p>
                </div>
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60">
                  <p className="text-xs text-slate-500 mb-1">Veredito dos Robôs</p>
                  <p className="text-sm font-medium text-white">{res.analise_ats.veredito_robos ?? '—'}</p>
                </div>
              </div>
              {res.analise_ats.explicacao && (
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 mb-4">
                  <p className="text-sm text-slate-400">{res.analise_ats.explicacao}</p>
                </div>
              )}
              {res.analise_ats.palavras_chave_faltantes && res.analise_ats.palavras_chave_faltantes.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Palavras-chave faltantes</p>
                  <div className="flex flex-wrap gap-2">
                    {res.analise_ats.palavras_chave_faltantes.map((kw, i) => (
                      <span key={i} className="px-2.5 py-1 rounded-full text-xs bg-rose-500/10 text-rose-300 border border-rose-500/20">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {res.analise_ats.gargalos_formatacao && res.analise_ats.gargalos_formatacao.length > 0 && (
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Gargalos de formatação</p>
                  <div className="space-y-1">
                    {res.analise_ats.gargalos_formatacao.map((gargalo, i) => (
                      <p key={i} className="text-xs text-slate-400 flex items-center gap-2">
                        <AlertCircle className="w-3 h-3 text-amber-400" />
                        {gargalo}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Análise por Seção */}
          {res.analise_secoes && Object.keys(res.analise_secoes).length > 0 && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <Sliders className="w-4 h-4 text-indigo-400" /> Análise por Seção
              </h2>
              <div className="space-y-3">
                {renderAnaliseSecoes(res.analise_secoes)}
              </div>
            </div>
          )}

          {/* Sugestões */}
          {res.sugestoes && res.sugestoes.length > 0 && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <Sparkles className="w-4 h-4 text-indigo-400" /> Sugestões de Melhoria
              </h2>
              <div className="space-y-2">
                {res.sugestoes.map((sugestao, i) => (
                  <div key={i} className="flex items-start gap-3 p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-xs font-bold text-indigo-400">
                      {i + 1}
                    </span>
                    <p className="text-sm text-slate-300 leading-relaxed">{sugestao}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Back to upload */}
          <button
            onClick={() => setActiveStep(1)}
            className="w-full py-3 rounded-2xl text-sm font-medium text-slate-400 hover:text-white bg-slate-800/40 hover:bg-slate-800/60 border border-slate-700/60 transition"
          >
            <span className="flex items-center justify-center gap-2">
              <RotateCcw className="w-4 h-4" />
              Voltar para envio
            </span>
          </button>
        </motion.div>
      )}
      </AnimatePresence>
    </div>
  )
}
