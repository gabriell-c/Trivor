'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Upload, Sparkles, CheckCircle2, AlertCircle, RefreshCw, Activity, XCircle, RotateCcw, BarChart3, Download } from 'lucide-react'
import type { AnalysisResult, SecaoDiagnostico } from './types/analysis'
import { API_BASE_URL } from './lib/api'

export default function Home() {
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [activeStep, setActiveStep] = useState<1 | 2>(1)
  const [jobLevel, setJobLevel] = useState('Sem nível específico')
  const [jobTitle, setJobTitle] = useState('')
  const [showMetrics, setShowMetrics] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFileName(e.target.files[0].name)
    }
  }

  const handleExport = async (format: 'json' | 'md' | 'docx' | 'pdf') => {
    if (!res) return
    setExporting(format)
    try {
      const formData = new FormData()
      formData.set('format', format)
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
      a.download = `Diagnostico_CV_${fileName?.replace('.pdf', '') || 'Analise'}.${format}`
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

  const analyzeCV = async (file: File) => {
    setLoading(true)
    setError(null)
    setRes(null)
    const formData = new FormData()
    formData.append('file', file)
    if (jobTitle.trim()) formData.set('job', jobTitle.trim())
    if (jobLevel !== 'Sem nível específico') formData.set('job_level', jobLevel)

    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: Falha no processamento.`)
      }

      const data: AnalysisResult = await response.json()
      setRes(data)
      setActiveStep(2)
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
        <AlertCircle className="w-3.5 h-3.5" /> Crítico
      </span>
    )
  }

  const renderDiagnostico = (data?: Record<string, SecaoDiagnostico>) => {
    if (!data) return null
    const entries = Object.entries(data)
    return entries.map(([key, value]) => (
      <div key={key} className="rounded-2xl bg-slate-950/60 border border-slate-800/80 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-white capitalize">
            {key.replace(/_/g, ' ')}
          </h3>
          {value?.status && getStatusBadge(value.status)}
        </div>
        {value?.problema && (
          <div className="mb-3">
            <p className="text-xs text-rose-400 font-medium mb-1">Problema detectado:</p>
            <p className="text-xs text-slate-400">{value.problema}</p>
          </div>
        )}
        {value?.como_corrigir && (
          <div>
            <p className="text-xs text-emerald-400 font-medium mb-1">Como corrigir:</p>
            <p className="text-xs text-slate-400">{value.como_corrigir}</p>
          </div>
        )}
      </div>
    ))
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <FileText className="w-6 h-6 text-white" />
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
          <FileText className="w-3.5 h-3.5" /> 2. Diagnóstico
        </button>
      </div>

      {/* Step 1: Upload */}
      {activeStep === 1 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-6"
        >
          <div>
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
              <FileText className="w-4 h-4 text-indigo-400" /> Vaga Alvo
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

          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              <XCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <button
            onClick={() => {
              const input = document.querySelector('input[type="file"]') as HTMLInputElement
              if (input?.files?.[0]) {
                analyzeCV(input.files[0])
              } else {
                setError('Por favor, selecione um currículo para analisar.')
              }
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
                  onClick={() => setShowMetrics(!showMetrics)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition"
                >
                  <Activity className="w-3 h-3" />
                  {showMetrics ? 'Ocultar métricas' : 'Métricas IA'}
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

            {showMetrics && res.api_info && (
              <div className="mb-4 p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Métricas da IA</span>
                  <button onClick={() => setShowMetrics(false)} className="text-xs text-slate-500 hover:text-slate-300">
                    <XCircle className="w-3 h-3" />
                  </button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <p className="text-[10px] text-slate-500 mb-0.5">Modelo</p>
                    <p className="text-xs font-mono text-indigo-300 truncate">{res.api_info.model}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 mb-0.5">Tokens (prompt)</p>
                    <p className="text-xs font-mono text-slate-300">{res.uso_tokens?.prompt_tokens?.toLocaleString('pt-BR')}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 mb-0.5">Tokens (completação)</p>
                    <p className="text-xs font-mono text-slate-300">{res.uso_tokens?.completion_tokens?.toLocaleString('pt-BR')}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 mb-0.5">Tempo resposta</p>
                    <p className="text-xs font-mono text-slate-300">{res.api_info.response_time_ms}ms</p>
                  </div>
                </div>
                <p className="text-[10px] text-slate-600 mt-2 truncate">ID: {res.api_info.request_id}</p>
              </div>
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
          </div>

          {/* ATS Analysis */}
          {res.analise_ats && typeof res.analise_ats === 'object' && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <BarChart3 className="w-4 h-4 text-indigo-400" /> Análise ATS
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

          {/* Diagnostic by section */}
          {res.diagnostico_por_secao && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-indigo-400" /> Diagnóstico por Seção
              </h2>
              <div className="space-y-3">
                {renderDiagnostico(res.diagnostico_por_secao)}
              </div>
            </div>
          )}

          {/* Tokens and export */}
          {res.uso_tokens && (
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-indigo-400" /> Uso de Tokens
                </h2>
                <div className="flex gap-2">
                  {(['json', 'md', 'docx', 'pdf'] as const).map((fmt) => (
                    <button
                      key={fmt}
                      onClick={() => handleExport(fmt)}
                      disabled={exporting !== null}
                      className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition disabled:opacity-50"
                    >
                      {exporting === fmt ? (
                        <span className="flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin" /></span>
                      ) : (
                        <><Download className="w-3 h-3 mr-1" />{fmt.toUpperCase()}</>
                      )}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                  <p className="text-xs text-slate-500 mb-1">Prompt</p>
                  <span className="text-sm font-black text-indigo-300 font-mono">{res.uso_tokens.prompt_tokens.toLocaleString('pt-BR')}</span>
                </div>
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                  <p className="text-xs text-slate-500 mb-1">Completion</p>
                  <span className="text-sm font-black text-purple-300 font-mono">{res.uso_tokens.completion_tokens?.toLocaleString('pt-BR')}</span>
                </div>
                <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                  <p className="text-xs text-slate-500 mb-1">Total</p>
                  <span className="text-sm font-black text-white font-mono">{res.uso_tokens.total_tokens.toLocaleString('pt-BR')}</span>
                </div>
              </div>
            </div>
          )}

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
    </div>
  )
}
