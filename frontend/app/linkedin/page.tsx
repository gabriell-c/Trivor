'use client'
import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Upload, Sparkles, CheckCircle2, AlertCircle, RefreshCw, Activity, XCircle, RotateCcw, BarChart3, Download, Image as ImageIcon, Link as LinkIcon, Users } from 'lucide-react'
import { getBestProvider } from '../hooks/useIaProviders'
import type { AnalysisResult } from '../types/analysis'

export default function LinkedinPage() {
  const [text, setText] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [activeStep, setActiveStep] = useState<1 | 2>(1)
  const [showMetrics, setShowMetrics] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)

  const handlePasteImage = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const blob = items[i].getAsFile()
        if (blob) {
          const url = URL.createObjectURL(blob)
          setImagePreview(url)
          // We can't send local blob directly via form, so we store for later if needed
          // For now, just show preview; user can also paste URL
        }
        break
      }
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file)
      setImagePreview(url)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const analyzeLinkedIn = async () => {
    if (!text.trim()) {
      setError('Cole o conteúdo da página do LinkedIn no campo abaixo.')
      return
    }
    setLoading(true)
    setError(null)
    setRes(null)

    const formData = new FormData()
    formData.set('text', text.trim())
    if (imageUrl.trim()) formData.set('image_url', imageUrl.trim())

    const provider = getBestProvider(['curriculo'])
    if (provider) {
      formData.set('api_key', provider.apiKey)
      formData.set('api_url', provider.apiUrl)
      formData.set('model_name', provider.modelName)
    }

    try {
      const response = await fetch('http://127.0.0.1:8000/api/linkedin/analyze', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: Falha no processamento.`)
      }

      const data: AnalysisResult = await response.json()
      if (data.error) throw new Error(data.error)
      if (typeof data.nota === 'string') data.nota = parseFloat(data.nota)
      if (data.analise_ats && typeof data.analise_ats === 'object' && typeof data.analise_ats.score_ats === 'string')
        data.analise_ats.score_ats = parseFloat(data.analise_ats.score_ats)
      setRes(data)
      setActiveStep(2)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido ao conectar ao servidor backend.')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async (format: 'json' | 'md' | 'docx' | 'pdf') => {
    if (!res) return
    setExporting(format)
    try {
      const formData = new FormData()
      formData.set('format', format)
      formData.set('filename', 'Perfil_LinkedIn.md')
      formData.set('job_target', 'Análise de Perfil LinkedIn')
      formData.set('data_json', JSON.stringify(res))

      const response = await fetch('http://127.0.0.1:8000/api/export', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) throw new Error('Falha ao gerar arquivo de exportação.')

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Diagnostico_LinkedIn.${format}`
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

  const renderDiagnostico = (data?: { [key: string]: any }) => {
    if (!data) return null
    const entries = Object.entries(data)
    return entries.map(([key, value]: any) => (
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

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const hasImage = !!imagePreview || !!imageUrl.trim()

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
            <Users className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-white">Análise de LinkedIn</h1>
            <p className="text-sm text-slate-500">Diagnóstico completo do seu perfil profissional</p>
          </div>
        </div>
      </div>

      {/* Step Navigation */}
      <div className="flex gap-2 mb-8">
        <button
          onClick={() => setActiveStep(1)}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-all ${
            activeStep === 1
              ? 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <FileText className="w-3.5 h-3.5" /> 1. Cole seu perfil
        </button>
        <button
          onClick={() => setActiveStep(2)}
          disabled={activeStep !== 2 || !res}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-all ${
            activeStep === 2
              ? 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
          }`}
        >
          <Activity className="w-3.5 h-3.5" /> 2. Diagnóstico
        </button>
      </div>

      {/* Step 1: Input */}
      <AnimatePresence mode="wait">
        {activeStep === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8 space-y-6"
          >
            {/* Instructions */}
            <div className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/20">
              <p className="text-xs text-blue-300 leading-relaxed">
                <strong>Como usar:</strong> Abra seu perfil no LinkedIn → Pressione <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-blue-200 font-mono text-[10px]">Ctrl+A</kbd> → <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-blue-200 font-mono text-[10px]">Ctrl+C</kbd> → Cole aqui com <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-blue-200 font-mono text-[10px]">Ctrl+V</kbd>. A IA irá filtrar automaticamente o conteúdo útil.
              </p>
            </div>

            {/* Textarea */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold text-slate-400">Conteúdo do Perfil LinkedIn</label>
                <span className="text-[10px] text-slate-600">{wordCount} palavras</span>
              </div>
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onPaste={handlePasteImage}
                placeholder="Cole aqui o conteúdo copiado do seu perfil LinkedIn (Ctrl+A → Ctrl+V)..."
                className="w-full h-64 bg-slate-950/80 border border-slate-700/80 rounded-2xl py-3 px-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30 resize-none font-mono"
              />
            </div>

            {/* Image upload section */}
            <div>
              <label className="text-xs font-semibold text-slate-400 mb-2 block">Foto de Perfil (opcional)</label>
              <div className="space-y-3">
                {/* Drop zone */}
                <div
                  ref={dropRef}
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  className="flex flex-col items-center justify-center w-full h-24 border-2 border-dashed border-slate-700/60 rounded-2xl cursor-pointer hover:border-blue-500/40 hover:bg-slate-800/30 transition"
                >
                  <ImageIcon className="w-5 h-5 text-slate-500 mb-1" />
                  <span className="text-xs text-slate-500">Arraste a foto ou cole com Ctrl+V</span>
                </div>

                {/* URL input */}
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="url"
                      value={imageUrl}
                      onChange={(e) => setImageUrl(e.target.value)}
                      placeholder="Ou cole a URL da foto de perfil..."
                      className="w-full bg-slate-950/80 border border-slate-700/80 rounded-2xl py-2.5 pl-9 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30"
                    />
                  </div>
                </div>

                {/* Preview */}
                {imagePreview && (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
                    <img src={imagePreview} alt="Preview" className="w-10 h-10 rounded-full object-cover" />
                    <span className="text-xs text-emerald-400 font-medium">Foto adicionada</span>
                    <button onClick={() => { setImagePreview(null); setImageUrl('') }} className="ml-auto text-slate-500 hover:text-rose-400 transition">
                      <XCircle className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                <XCircle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            <button
              onClick={analyzeLinkedIn}
              disabled={loading || !text.trim()}
              className="w-full py-4 rounded-2xl font-bold text-white bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 shadow-lg shadow-blue-600/25 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
            >
              {loading ? (
                <><RefreshCw className="w-4 h-4 animate-spin" /> Analisando perfil...</>
              ) : (
                <><Sparkles className="w-4 h-4" /> Analisar Perfil LinkedIn</>
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Step 2: Results */}
      <AnimatePresence mode="wait">
        {activeStep === 2 && res && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
          >
            {/* Score header */}
            <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${getScoreColor(res.nota || 0).bg} border ${getScoreColor(res.nota || 0).border}`}>
                    <span className={`text-xl font-black ${getScoreColor(res.nota || 0).text}`}>{res.nota?.toFixed(1)}</span>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white">LinkedIn Score</p>
                    <p className="text-xs text-slate-500">Qualidade do perfil</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowMetrics(!showMetrics)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-blue-500/40 transition"
                  >
                    <Activity className="w-3 h-3" />
                    {showMetrics ? 'Ocultar métricas' : 'Métricas IA'}
                  </button>
                  <button
                    onClick={() => setActiveStep(1)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-blue-500/40 transition"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Nova análise
                  </button>
                </div>
              </div>

              {showMetrics && res.api_info && (
                <div className="mb-4 p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex gap-4">
                      <div>
                        <p className="text-[10px] text-slate-500 mb-0.5">Modelo</p>
                        <p className="text-xs font-mono text-slate-300">{res.api_info.model}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-slate-500 mb-0.5">Tempo resposta</p>
                        <p className="text-xs font-mono text-slate-300">{res.api_info.response_time_ms}ms</p>
                      </div>
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

            {/* Diagnostic by section */}
            {res.diagnostico_por_secao && (
              <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
                <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                  <Activity className="w-4 h-4 text-blue-400" /> Diagnóstico por Seção
                </h2>
                <div className="space-y-3">
                  {renderDiagnostico(res.diagnostico_por_secao)}
                </div>
              </div>
            )}

            {/* ATS Analysis */}
            {res.analise_ats && typeof res.analise_ats === 'object' && (
              <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
                <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
                  <BarChart3 className="w-4 h-4 text-blue-400" /> Análise de Visibilidade
                </h2>
                {res.analise_ats.score_ats !== undefined && (
                  <div className="mb-4 p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60">
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${getScoreColor(res.analise_ats.score_ats).bg} border ${getScoreColor(res.analise_ats.score_ats).border}`}>
                        <span className={`text-sm font-black ${getScoreColor(res.analise_ats.score_ats).text}`}>{res.analise_ats.score_ats}</span>
                      </div>
                      <div>
                        <p className="text-xs font-bold text-white">Score de Visibilidade</p>
                        <p className="text-[10px] text-slate-500">Quão encontrável é seu perfil</p>
                      </div>
                    </div>
                    {res.analise_ats.veredito_robos && (
                      <p className="text-xs text-slate-400 mt-2">{res.analise_ats.veredito_robos}</p>
                    )}
                  </div>
                )}
                {res.analise_ats.palavras_chave_faltantes && res.analise_ats.palavras_chave_faltantes.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-bold text-slate-400 mb-2">Palavras-chave recomendadas:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {res.analise_ats.palavras_chave_faltantes.map((pk: string, i: number) => (
                        <span key={i} className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-blue-500/10 border border-blue-500/20 text-blue-300">
                          {pk}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {res.analise_ats.gargalos_formatacao && res.analise_ats.gargalos_formatacao.length > 0 && (
                  <div>
                    <p className="text-xs font-bold text-slate-400 mb-2">Gargalos de formatação:</p>
                    <ul className="text-xs text-slate-400 list-disc list-inside space-y-1">
                      {res.analise_ats.gargalos_formatacao.map((g: string, i: number) => (
                        <li key={i}>{g}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Tokens and export */}
            {res.uso_tokens && (
              <div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 md:p-8">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-blue-400" /> Uso de Tokens
                  </h2>
                  <div className="flex gap-2">
                    {(['json', 'md', 'docx', 'pdf'] as const).map((fmt) => (
                      <button
                        key={fmt}
                        onClick={() => handleExport(fmt)}
                        disabled={exporting !== null}
                        className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-blue-500/40 transition disabled:opacity-50"
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
                    <p className="text-xs text-slate-500 mb-1">Modelo</p>
                    <span className="text-xs font-black text-indigo-300 font-mono truncate block">{res.api_info?.model || '—'}</span>
                  </div>
                  <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-xs text-slate-500 mb-1">Prompt</p>
                    <span className="text-sm font-black text-blue-300 font-mono">{res.uso_tokens.prompt_tokens.toLocaleString('pt-BR')}</span>
                  </div>
                  <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-xs text-slate-500 mb-1">Completion</p>
                    <span className="text-sm font-black text-cyan-300 font-mono">{res.uso_tokens.completion_tokens?.toLocaleString('pt-BR')}</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-4 mt-4">
                  <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/60 text-center">
                    <p className="text-xs text-slate-500 mb-1">Total de Tokens</p>
                    <span className="text-sm font-black text-white font-mono">{res.uso_tokens.total_tokens.toLocaleString('pt-BR')}</span>
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={() => setActiveStep(1)}
              className="w-full py-3 rounded-2xl text-sm font-medium text-slate-400 hover:text-white bg-slate-800/40 hover:bg-slate-800/60 border border-slate-700/60 transition"
            >
              <RotateCcw className="w-3.5 h-3.5 inline mr-1" /> Voltar para envio
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
