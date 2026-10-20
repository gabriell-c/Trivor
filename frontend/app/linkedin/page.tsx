'use client'
import { useState, useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import {
  FileText, Sparkles, CheckCircle2, AlertCircle, RefreshCw, Activity,
  XCircle, RotateCcw, BarChart3, Download, Image as ImageIcon,
  Link as LinkIcon, Users, ShieldCheck, Clock, Hash, Cpu, Eye,
} from 'lucide-react'
import { getBestProvider } from '../hooks/useIaProviders'
import type { AnalysisResult, SecaoDiagnostico } from '../types/analysis'
import { API_BASE_URL } from '../lib/api'

const EASE = [0.16, 1, 0.3, 1] as const

/* ═══════════ Tons semânticos ═══════════ */
const TONE = {
  blue: {
    wrap: 'bg-blue-500/15 border-blue-400/30 text-blue-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(59,130,246,0.4)]',
  },
  cyan: {
    wrap: 'bg-cyan-500/15 border-cyan-400/30 text-cyan-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(6,182,212,0.4)]',
  },
  green: {
    wrap: 'bg-emerald-500/15 border-emerald-400/30 text-emerald-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(16,185,129,0.4)]',
  },
  amber: {
    wrap: 'bg-amber-500/15 border-amber-400/30 text-amber-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(245,158,11,0.4)]',
  },
  red: {
    wrap: 'bg-rose-500/15 border-rose-400/30 text-rose-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(244,63,94,0.4)]',
  },
  purple: {
    wrap: 'bg-purple-500/15 border-purple-400/30 text-purple-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(168,85,247,0.4)]',
  },
} as const

function scoreTone(score: number = 0) {
  if (score >= 80) return TONE.green
  if (score >= 60) return TONE.amber
  return TONE.red
}

/* ═══════════ Botão primário ═══════════ */
function PrimaryBtn({
  children,
  onClick,
  disabled,
  loading,
  className = '',
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  loading?: boolean
  className?: string
}) {
  return (
    <motion.button
      whileHover={disabled ? {} : { scale: 1.02, y: -1 }}
      whileTap={disabled ? {} : { scale: 0.98 }}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 h-12 px-5 rounded-xl text-base font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 ${className}`}
    >
      {loading ? (
        <>
          <RefreshCw className="w-4 h-4 animate-spin" />
          {children}
        </>
      ) : (
        children
      )}
    </motion.button>
  )
}

/* ═══════════ Section wrapper ═══════════ */
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden shadow-2xl shadow-black/30 ${className}`}>
      {children}
    </div>
  )
}

function SectionHead({
  icon,
  tone,
  title,
  subtitle,
  right,
}: {
  icon: React.ReactNode
  tone: (typeof TONE)[keyof typeof TONE]
  title: string
  subtitle?: string
  right?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div className="flex items-center gap-3 min-w-0">
        <div className={`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 ${tone.wrap}`}>
          {icon}
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-white leading-tight truncate">{title}</h2>
          {subtitle && <p className="text-sm text-slate-400 mt-0.5 truncate">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  )
}

/* ═══════════ Score badge ═══════════ */
function ScoreBadge({
  score,
  label,
  hint,
  size = 'lg',
}: {
  score: number
  label: string
  hint?: string
  size?: 'sm' | 'lg'
}) {
  const tone = scoreTone(score)
  const big = size === 'lg'
  return (
    <div className="flex items-center gap-3">
      <div
        className={`rounded-xl border flex items-center justify-center shrink-0 ${tone.wrap} ${tone.glow} ${
          big ? 'w-16 h-16' : 'w-12 h-12'
        }`}
      >
        <span className={`font-black tabular-nums ${big ? 'text-2xl' : 'text-lg'}`}>
          {score.toFixed(1)}
        </span>
      </div>
      <div className="min-w-0">
        <p className={`font-bold text-white ${big ? 'text-base' : 'text-sm'}`}>{label}</p>
        {hint && <p className="text-sm text-slate-400 mt-0.5">{hint}</p>}
      </div>
    </div>
  )
}

/* ═══════════ Status pill ═══════════ */
function StatusPill({ status }: { status?: string }) {
  if (status === 'ok') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/15 border border-emerald-400/30 text-emerald-200">
        <CheckCircle2 className="w-3.5 h-3.5" />
        Ok / Bom
      </span>
    )
  }
  if (status === 'atencao') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/15 border border-amber-400/30 text-amber-200">
        <AlertCircle className="w-3.5 h-3.5" />
        Requer Ajuste
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-500/15 border border-rose-400/30 text-rose-200">
      <AlertCircle className="w-3.5 h-3.5" />
      Crítico
    </span>
  )
}

/* ═══════════ Page ═══════════ */
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
  const [exportError, setExportError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handlePasteImage = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const blob = items[i].getAsFile()
        if (blob) {
          const url = URL.createObjectURL(blob)
          setImagePreview(url)
        }
        break
      }
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file)
      setImagePreview(url)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

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
      const response = await fetch(`${API_BASE_URL}/api/linkedin/analyze`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: Falha no processamento.`)
      }

      const data: AnalysisResult = await response.json()
      if (data.error) throw new Error(data.error)
      if (typeof data.nota === 'string') data.nota = parseFloat(data.nota)
      if (
        data.analise_ats &&
        typeof data.analise_ats === 'object' &&
        typeof data.analise_ats.score_ats === 'string'
      )
        data.analise_ats.score_ats = parseFloat(data.analise_ats.score_ats)
      setRes(data)
      setActiveStep(2)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Erro desconhecido ao conectar ao servidor backend.'
      )
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async (format: 'json' | 'md' | 'docx' | 'pdf') => {
    if (!res) return
    setExporting(format)
    setExportError(null)
    try {
      const formData = new FormData()
      formData.set('format', format)
      formData.set('filename', 'Perfil_LinkedIn.md')
      formData.set('job_target', 'Análise de Perfil LinkedIn')
      formData.set('data_json', JSON.stringify(res))

      const response = await fetch(`${API_BASE_URL}/api/export`, {
        method: 'POST',
        body: formData,
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
      setExportError(err instanceof Error ? err.message : 'Erro ao baixar o arquivo.')
    } finally {
      setExporting(null)
    }
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const charCount = text.length

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      {/* ──────── Header ──────── */}
      <motion.header
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
        className="mb-8"
      >
        <motion.span
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1, ease: EASE }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-400/30 text-blue-200 text-xs font-semibold mb-4"
        >
          <span className="relative flex h-2 w-2">
            <motion.span
              animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
              className="absolute inset-0 rounded-full bg-blue-400"
            />
            <span className="relative w-2 h-2 rounded-full bg-blue-400" />
          </span>
          LinkedIn Optimizer
        </motion.span>

        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-blue-500/15 border border-blue-400/30 shadow-[0_0_30px_-6px_rgba(59,130,246,0.5)] flex items-center justify-center shrink-0">
            <Users className="w-7 h-7 text-blue-300" />
          </div>
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight">
              Análise de LinkedIn
            </h1>
            <p className="text-base text-slate-300 mt-1.5 max-w-xl leading-relaxed">
              Diagnóstico completo do seu perfil profissional, com score, pontos fortes e plano de ação.
            </p>
          </div>
        </div>
      </motion.header>

      {/* ──────── Step tabs ──────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
        className="grid grid-cols-2 gap-2 p-1.5 rounded-2xl bg-slate-900 border border-slate-700 mb-8"
      >
        <button
          onClick={() => setActiveStep(1)}
          className={`relative flex items-center justify-center gap-2 h-11 rounded-xl text-sm font-semibold transition-colors ${
            activeStep === 1 ? 'text-white' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          {activeStep === 1 && (
            <motion.span
              layoutId="step-indicator"
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="absolute inset-0 rounded-xl bg-blue-600 shadow-lg shadow-blue-500/30"
            />
          )}
          <span className="relative flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Cole seu perfil
          </span>
        </button>
        <button
          onClick={() => setActiveStep(2)}
          disabled={!res}
          className={`relative flex items-center justify-center gap-2 h-11 rounded-xl text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
            activeStep === 2 ? 'text-white' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          {activeStep === 2 && (
            <motion.span
              layoutId="step-indicator"
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="absolute inset-0 rounded-xl bg-blue-600 shadow-lg shadow-blue-500/30"
            />
          )}
          <span className="relative flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Diagnóstico
          </span>
        </button>
      </motion.div>

      {/* ──────── Step 1 ──────── */}
      <AnimatePresence mode="wait">
        {activeStep === 1 && !loading && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: EASE }}
          >
            <Card className="p-6 md:p-8 space-y-6">
              {/* Instructions */}
              <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-500/10 border border-blue-400/20">
                <div className="w-8 h-8 rounded-lg bg-blue-500/20 border border-blue-400/30 flex items-center justify-center shrink-0">
                  <Sparkles className="w-4 h-4 text-blue-300" />
                </div>
                <div className="text-sm text-slate-200 leading-relaxed">
                  <strong className="text-white">Como usar:</strong> Abra seu perfil no LinkedIn →
                  <Kbd>Ctrl</Kbd>+<Kbd>A</Kbd> → <Kbd>Ctrl</Kbd>+<Kbd>C</Kbd> → cole aqui com{' '}
                  <Kbd>Ctrl</Kbd>+<Kbd>V</Kbd>. A IA filtra automaticamente o conteúdo útil.
                </div>
              </div>

              {/* Textarea */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-slate-200">
                    Conteúdo do Perfil LinkedIn
                  </label>
                  <span className="text-xs font-medium text-slate-400 tabular-nums">
                    {wordCount.toLocaleString('pt-BR')} palavras ·{' '}
                    {charCount.toLocaleString('pt-BR')} chars
                  </span>
                </div>
                <textarea
                  ref={textareaRef}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onPaste={handlePasteImage}
                  placeholder="Cole aqui o conteúdo copiado do seu perfil LinkedIn (Ctrl+A → Ctrl+C → Ctrl+V)..."
                  className="w-full h-72 bg-slate-950 border border-slate-700 rounded-xl py-3.5 px-4 text-base font-mono text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/25 resize-none leading-relaxed"
                />
              </div>

              {/* Image upload */}
              <div>
                <label className="text-sm font-medium text-slate-200 mb-2 block">
                  Foto de Perfil{' '}
                  <span className="text-slate-500 font-normal">(opcional)</span>
                </label>
                <div className="space-y-3">
                  <div
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    className={`flex flex-col items-center justify-center w-full h-28 border-2 border-dashed rounded-xl transition-all cursor-pointer ${
                      dragging
                        ? 'border-blue-400 bg-blue-500/10'
                        : 'border-slate-700 hover:border-blue-400/50 hover:bg-slate-800/40'
                    }`}
                  >
                    <motion.div
                      animate={dragging ? { scale: 1.1, y: -2 } : { scale: 1, y: 0 }}
                      transition={{ type: 'spring', damping: 20, stiffness: 400 }}
                      className={`w-10 h-10 rounded-lg flex items-center justify-center mb-2 ${
                        dragging
                          ? 'bg-blue-500/20 border border-blue-400/40'
                          : 'bg-slate-800 border border-slate-700'
                      }`}
                    >
                      <ImageIcon className={`w-5 h-5 ${dragging ? 'text-blue-300' : 'text-slate-400'}`} />
                    </motion.div>
                    <span className="text-sm font-medium text-slate-300">
                      {dragging ? 'Solte a imagem aqui' : 'Arraste a foto ou cole com Ctrl+V'}
                    </span>
                    <span className="text-xs text-slate-500 mt-0.5">PNG, JPG · até 5MB</span>
                  </div>

                  <div className="relative">
                    <LinkIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                    <input
                      type="url"
                      value={imageUrl}
                      onChange={(e) => setImageUrl(e.target.value)}
                      placeholder="Ou cole a URL da foto de perfil..."
                      className="w-full h-12 pl-10 pr-4 bg-slate-950 border border-slate-700 rounded-xl text-base text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/25"
                    />
                  </div>

                  <AnimatePresence>
                    {imagePreview && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-950 border border-slate-700">
                          <img
                            src={imagePreview}
                            alt="Preview"
                            className="w-12 h-12 rounded-lg object-cover border border-slate-700"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-emerald-300 flex items-center gap-1.5">
                              <CheckCircle2 className="w-4 h-4" />
                              Foto adicionada
                            </p>
                            <p className="text-xs text-slate-400 mt-0.5 truncate">
                              Pronta para envio
                            </p>
                          </div>
                          <motion.button
                            whileHover={{ scale: 1.1 }}
                            whileTap={{ scale: 0.9 }}
                            onClick={() => {
                              setImagePreview(null)
                              setImageUrl('')
                            }}
                            className="h-8 w-8 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-rose-500/15 flex items-center justify-center transition-colors"
                            aria-label="Remover foto"
                          >
                            <XCircle className="w-4 h-4" />
                          </motion.button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="flex items-start gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-400/30">
                      <XCircle className="w-5 h-5 text-rose-300 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-rose-200">Erro na análise</p>
                        <p className="text-sm text-rose-300/90 mt-0.5 leading-relaxed">{error}</p>
                      </div>
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={analyzeLinkedIn}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-400/30 text-rose-200 text-xs font-semibold transition-colors disabled:opacity-50 shrink-0"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Tentar novamente
                      </motion.button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Submit */}
              <PrimaryBtn
                onClick={analyzeLinkedIn}
                disabled={loading || !text.trim()}
                loading={loading}
                className="w-full"
              >
                {loading ? (
                  'Analisando perfil...'
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Analisar Perfil LinkedIn
                  </>
                )}
              </PrimaryBtn>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ──────── Loading skeleton ──────── */}
      {loading && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, ease: EASE }}
        >
          <Card className="p-6 md:p-8 space-y-5">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-xl bg-slate-800 relative overflow-hidden">
                <Shimmer />
              </div>
              <div className="flex-1 space-y-2">
                <div className="h-5 bg-slate-800 rounded-full w-1/3 relative overflow-hidden">
                  <Shimmer />
                </div>
                <div className="h-4 bg-slate-800 rounded-full w-1/4 relative overflow-hidden">
                  <Shimmer />
                </div>
              </div>
            </div>
            <div className="h-24 bg-slate-800/60 rounded-xl relative overflow-hidden">
              <Shimmer />
            </div>
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-3 items-start">
                <div className="h-10 w-10 bg-slate-800 rounded-lg relative overflow-hidden shrink-0">
                  <Shimmer />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="h-3.5 bg-slate-800 rounded-full w-2/3 relative overflow-hidden">
                    <Shimmer />
                  </div>
                  <div className="h-3.5 bg-slate-800 rounded-full w-full relative overflow-hidden">
                    <Shimmer />
                  </div>
                  <div className="h-3.5 bg-slate-800 rounded-full w-5/6 relative overflow-hidden">
                    <Shimmer />
                  </div>
                </div>
              </div>
            ))}
            <p className="text-sm font-medium text-slate-400 text-center pt-2 flex items-center justify-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Analisando seu perfil com IA...
            </p>
          </Card>
        </motion.div>
      )}

      {/* ──────── Step 2 ──────── */}
      <AnimatePresence mode="wait">
        {activeStep === 2 && res && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: EASE }}
            className="space-y-5"
          >
            {/* ──────── Score + resumo ──────── */}
            <Card>
              <div className="p-6 md:p-8 space-y-6">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <ScoreBadge
                    score={res.nota || 0}
                    label="LinkedIn Score"
                    hint="Qualidade geral do seu perfil"
                  />
                  <div className="flex items-center gap-2 flex-wrap">
                    <motion.button
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => setShowMetrics(!showMetrics)}
                      className={`inline-flex items-center gap-1.5 h-10 px-3 rounded-lg text-sm font-semibold border transition-colors ${
                        showMetrics
                          ? 'bg-purple-500/15 border-purple-400/30 text-purple-200'
                          : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      <Activity className="w-4 h-4" />
                      {showMetrics ? 'Ocultar' : 'Métricas IA'}
                    </motion.button>
                    <motion.button
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => setActiveStep(1)}
                      className="inline-flex items-center gap-1.5 h-10 px-3 rounded-lg text-sm font-semibold bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 transition-colors"
                    >
                      <RotateCcw className="w-4 h-4" />
                      Nova análise
                    </motion.button>
                  </div>
                </div>

                {/* Metrics (expandable) */}
                <AnimatePresence initial={false}>
                  {showMetrics && res.api_info && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: EASE }}
                      className="overflow-hidden"
                    >
                      <div className="p-4 rounded-xl bg-slate-950 border border-slate-700 grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <MiniStat
                          icon={<Cpu className="w-4 h-4 text-purple-300" />}
                          label="Modelo"
                          value={res.api_info.model ?? '—'}
                          mono
                        />
                        <MiniStat
                          icon={<Clock className="w-4 h-4 text-blue-300" />}
                          label="Tempo de resposta"
                          value={`${res.api_info.response_time_ms}ms`}
                          mono
                        />
                        <MiniStat
                          icon={<Hash className="w-4 h-4 text-cyan-300" />}
                          label="Request ID"
                          value={res.api_info.request_id?.slice(0, 12) + '…'}
                          mono
                        />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Resumo */}
                {res.resumo_executivo && (
                  <div className="p-5 rounded-xl bg-slate-950 border border-slate-700">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      Resumo Executivo
                    </p>
                    <p className="text-base text-slate-200 leading-relaxed">
                      {res.resumo_executivo}
                    </p>
                  </div>
                )}

                {/* Pontos fortes */}
                {res.pontos_fortes && res.pontos_fortes.length > 0 && (
                  <div>
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                      Pontos Fortes
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {res.pontos_fortes.map((ponto, i) => (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.3), ease: EASE }}
                          className="flex items-start gap-2.5 p-3 rounded-xl bg-emerald-500/10 border border-emerald-400/20"
                        >
                          <CheckCircle2 className="w-4 h-4 text-emerald-300 shrink-0 mt-0.5" />
                          <span className="text-sm text-emerald-100 leading-relaxed">{ponto}</span>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>

            {/* ──────── Diagnóstico ──────── */}
            {res.diagnostico_por_secao &&
              Object.keys(res.diagnostico_por_secao).length > 0 && (
                <Card>
                  <div className="p-6 md:p-8">
                    <SectionHead
                      icon={<Activity className="w-5 h-5 text-blue-300" />}
                      tone={TONE.blue}
                      title="Diagnóstico por Seção"
                      subtitle={`${Object.keys(res.diagnostico_por_secao).length} área${
                        Object.keys(res.diagnostico_por_secao).length > 1 ? 's' : ''
                      } analisada${Object.keys(res.diagnostico_por_secao).length > 1 ? 's' : ''}`}
                    />
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {Object.entries(res.diagnostico_por_secao).map(([key, value], idx) => (
                        <DiagnosticCard key={key} name={key} data={value} delay={idx * 0.04} />
                      ))}
                    </div>
                  </div>
                </Card>
              )}

            {/* ──────── ATS / Visibilidade ──────── */}
            {res.analise_ats && typeof res.analise_ats === 'object' && (
              <Card>
                <div className="p-6 md:p-8">
                  <SectionHead
                    icon={<ShieldCheck className="w-5 h-5 text-purple-300" />}
                    tone={TONE.purple}
                    title="Análise de Visibilidade"
                    subtitle="Quão encontrável é seu perfil para recrutadores e ATS"
                  />

                  {res.analise_ats.score_ats !== undefined && (
                    <div className="p-5 rounded-xl bg-slate-950 border border-slate-700 mb-4">
                      <ScoreBadge
                        score={res.analise_ats.score_ats}
                        label="Score de Visibilidade"
                        hint="Quão encontrável é seu perfil"
                        size="sm"
                      />
                      {res.analise_ats.veredito_robos && (
                        <p className="text-sm text-slate-300 mt-3 leading-relaxed pl-[60px]">
                          {res.analise_ats.veredito_robos}
                        </p>
                      )}
                    </div>
                  )}

                  {res.analise_ats.palavras_chave_faltantes &&
                    res.analise_ats.palavras_chave_faltantes.length > 0 && (
                      <div className="mb-4">
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                          Palavras-chave recomendadas
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {res.analise_ats.palavras_chave_faltantes.map((pk: string, i: number) => (
                            <motion.span
                              key={i}
                              initial={{ opacity: 0, scale: 0.9 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={{
                                duration: 0.25,
                                delay: Math.min(i * 0.03, 0.3),
                                ease: EASE,
                              }}
                              className="inline-flex items-center h-7 px-2.5 rounded-md text-xs font-semibold bg-blue-500/15 border border-blue-400/30 text-blue-200"
                            >
                              {pk}
                            </motion.span>
                          ))}
                        </div>
                      </div>
                    )}

                  {res.analise_ats.gargalos_formatacao &&
                    res.analise_ats.gargalos_formatacao.length > 0 && (
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                          Gargalos de formatação
                        </p>
                        <ul className="space-y-2">
                          {res.analise_ats.gargalos_formatacao.map((g: string, i: number) => (
                            <li
                              key={i}
                              className="flex items-start gap-2.5 text-sm text-amber-200 leading-relaxed"
                            >
                              <AlertCircle className="w-4 h-4 text-amber-300 shrink-0 mt-0.5" />
                              {g}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              </Card>
            )}

            {/* ──────── Tokens + export ──────── */}
            {(res.uso_tokens || res.api_info) && (
              <Card>
                <div className="p-6 md:p-8">
                  <SectionHead
                    icon={<BarChart3 className="w-5 h-5 text-cyan-300" />}
                    tone={TONE.cyan}
                    title="Uso de Tokens & Exportação"
                    subtitle="Consumo da IA nesta análise"
                    right={
                      <div className="flex gap-1.5 flex-wrap">
                        {(['json', 'md', 'docx', 'pdf'] as const).map((fmt) => (
                          <motion.button
                            key={fmt}
                            whileHover={{ scale: 1.04, y: -1 }}
                            whileTap={{ scale: 0.96 }}
                            onClick={() => handleExport(fmt)}
                            disabled={exporting !== null}
                            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-xs font-semibold bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {exporting === fmt ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Download className="w-3.5 h-3.5" />
                            )}
                            {fmt.toUpperCase()}
                          </motion.button>
                        ))}
                      </div>
                    }
                  />

                  {exportError && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-4 flex items-center gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-400/30 text-sm font-medium text-rose-200"
                    >
                      <XCircle className="w-4 h-4 shrink-0" />
                      {exportError}
                    </motion.div>
                  )}

                  {res.uso_tokens && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <TokenCard
                        label="Prompt"
                        value={res.uso_tokens.prompt_tokens ?? 0}
                        icon={<Hash className="w-4 h-4 text-blue-300" />}
                        tone={TONE.blue}
                      />
                      <TokenCard
                        label="Completion"
                        value={res.uso_tokens.completion_tokens ?? 0}
                        icon={<Hash className="w-4 h-4 text-cyan-300" />}
                        tone={TONE.cyan}
                      />
                      <TokenCard
                        label="Total"
                        value={res.uso_tokens.total_tokens ?? 0}
                        icon={<Hash className="w-4 h-4 text-purple-300" />}
                        tone={TONE.purple}
                        highlight
                      />
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* Voltar */}
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => setActiveStep(1)}
              className="w-full h-12 inline-flex items-center justify-center gap-2 rounded-xl text-sm font-semibold text-slate-300 hover:text-white bg-slate-800/60 hover:bg-slate-800 border border-slate-700 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              Voltar para envio
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ═══════════ Sub-components ═══════════ */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[22px] h-5 px-1.5 rounded border border-slate-600 bg-slate-800 text-slate-200 text-xs font-semibold font-mono shadow-[0_1px_0_rgba(0,0,0,0.4)]">
      {children}
    </kbd>
  )
}

function Shimmer() {
  return (
    <motion.div
      className="absolute inset-0 bg-gradient-to-r from-transparent via-slate-700/50 to-transparent"
      initial={{ x: '-100%' }}
      animate={{ x: '100%' }}
      transition={{ repeat: Infinity, duration: 1.4, ease: 'linear' }}
    />
  )
}

function MiniStat({
  icon,
  label,
  value,
  mono,
}: {
  icon: React.ReactNode
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <div className="w-8 h-8 rounded-md bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-400">{label}</p>
        <p className={`text-sm font-semibold text-white truncate ${mono ? 'font-mono' : ''}`}>
          {value}
        </p>
      </div>
    </div>
  )
}

function DiagnosticCard({
  name,
  data,
  delay = 0,
}: {
  name: string
  data: SecaoDiagnostico
  delay?: number
}) {
  const hasProblem = !!data?.problema
  const hasFix = !!data?.como_corrigir

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: EASE }}
      className="rounded-xl bg-slate-950 border border-slate-700 p-4"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <h3 className="text-sm font-bold text-white capitalize leading-tight">
          {name.replace(/_/g, ' ')}
        </h3>
        {data?.status && <StatusPill status={data.status} />}
      </div>

      {hasProblem && (
        <div className="mb-2.5">
          <p className="text-xs font-bold text-rose-300 mb-1 flex items-center gap-1.5">
            <AlertCircle className="w-3 h-3" />
            Problema detectado
          </p>
          <p className="text-sm text-slate-300 leading-relaxed">{data.problema}</p>
        </div>
      )}

      {hasFix && (
        <div>
          <p className="text-xs font-bold text-emerald-300 mb-1 flex items-center gap-1.5">
            <CheckCircle2 className="w-3 h-3" />
            Como corrigir
          </p>
          <p className="text-sm text-slate-300 leading-relaxed">{data.como_corrigir}</p>
        </div>
      )}
    </motion.div>
  )
}

function TokenCard({
  label,
  value,
  icon,
  tone,
  highlight,
}: {
  label: string
  value: number
  icon: React.ReactNode
  tone: (typeof TONE)[keyof typeof TONE]
  highlight?: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: EASE }}
      className={`p-4 rounded-xl border ${
        highlight ? 'bg-slate-800 border-slate-600' : 'bg-slate-950 border-slate-700'
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-7 h-7 rounded-md border flex items-center justify-center ${tone.wrap}`}>
          {icon}
        </div>
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <p className="text-2xl font-bold font-mono text-white tabular-nums">
        {value.toLocaleString('pt-BR')}
      </p>
    </motion.div>
  )
}