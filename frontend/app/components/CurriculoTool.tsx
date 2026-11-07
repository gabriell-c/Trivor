'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Sparkles, CheckCircle2, AlertTriangle, Cpu,
  RefreshCw, Sliders, Eye, XCircle, Activity, BarChart3,
  FileSearch, RotateCcw, Target, FileCode2, AlertCircle,
  Download, ChevronDown, UserCheck,
} from 'lucide-react'
import type { AnalysisResult } from '../types/analysis'
import { API_BASE_URL } from '../lib/api'
import { friendlyError } from '../lib/errors'
import { scoreTone } from '../lib/score'
import { CustomSelect } from './CustomSelect'
import { useExport } from '../hooks/useExport'
import {
  EASE, Card, SectionHead, GhostBtn, ScoreBadge,
  addLlmProvider, formatTokens,
} from './curriculo/ui'
import {
  AnaliseSecoes, ErrosComuns, TokenMetric, KeywordGroup, ChecklistItems,
  SemanticFitSection, RecruiterSimSection, CoverLetterSection, CVDiffSection,
  StepOneForm,
} from './curriculo/sections'

/* ═══════════ Main page ═══════════ */
export default function CurriculoTool() {
  const [res, setRes] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  const [activeStep, setActiveStep] = useState<1 | 2>(1)
  const [jobLevel, setJobLevel] = useState('Sem nível específico')
  const [jobTitle, setJobTitle] = useState('')
  const [area, setArea] = useState('')

  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const [analysisId, setAnalysisId] = useState(0)
  const [fitAutoRun, setFitAutoRun] = useState(false)

  const { exporting, exportError, exportFormat, setExportFormat, handleExport } = useExport(
    res,
    fileName,
    jobTitle,
    jobLevel,
  )

  const analyzeCV = async (file: File) => {
    setLoading(true)
    setError(null)
    setRes(null)
    setFileName(file.name)
    setAnalysisId((id) => id + 1)
    setFitAutoRun(jobTitle.trim().length >= 40)
    const formData = new FormData()
    formData.append('cv_file', file)
    if (area) formData.set('area', area)
    if (jobTitle.trim()) formData.set('job_description', jobTitle.trim())
    if (jobLevel !== 'Sem nível específico') formData.set('target_role', jobLevel.toLowerCase())
    addLlmProvider(formData, ['curriculo'])

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/analyze`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: Falha no processamento.`)
      }

      const data: AnalysisResult = await response.json()
      setRes(data)
      setActiveStep(2)
    } catch (err) {
      setError(friendlyError(err, 'Falha na análise do currículo.'))
    } finally {
      setLoading(false)
    }
  }

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
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/15 border border-indigo-400/30 text-indigo-200 text-xs font-semibold mb-4"
        >
          <span className="relative flex h-2 w-2">
            <motion.span
              animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
              className="absolute inset-0 rounded-full bg-indigo-400"
            />
            <span className="relative w-2 h-2 rounded-full bg-indigo-400" />
          </span>
          Otimizador de Currículo
        </motion.span>

        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-indigo-500/15 border border-indigo-400/30 shadow-[0_0_30px_-6px_rgba(99,102,241,0.5)] flex items-center justify-center shrink-0">
            <FileSearch className="w-7 h-7 text-indigo-300" />
          </div>
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight">
              Diagnóstico de Currículo
            </h1>
            <p className="text-base text-slate-300 mt-1.5 max-w-xl leading-relaxed">
              Análise completa com IA para otimização de ATS, fit com a vaga e simulação de recrutador.
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
              layoutId="curriculo-step-indicator"
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="absolute inset-0 rounded-xl bg-indigo-600 shadow-lg shadow-indigo-500/30"
            />
          )}
          <span className="relative flex items-center gap-2">
            <FileText className="w-4 h-4" />
            1. Envio
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
              layoutId="curriculo-step-indicator"
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="absolute inset-0 rounded-xl bg-indigo-600 shadow-lg shadow-indigo-500/30"
            />
          )}
          <span className="relative flex items-center gap-2">
            <Activity className="w-4 h-4" />
            2. Diagnóstico
          </span>
        </button>
      </motion.div>

      {/* ──────── Step 1 ──────── */}
      <AnimatePresence mode="wait">
        {activeStep === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: EASE }}
            className="space-y-5"
          >
            <StepOneForm
              selectedFile={selectedFile}
              onFileSelect={setSelectedFile}
              area={area}
              onArea={setArea}
              jobTitle={jobTitle}
              onJobTitle={setJobTitle}
              jobLevel={jobLevel}
              onJobLevel={setJobLevel}
              loading={loading}
              error={error}
              onAnalyze={() => {
                if (!selectedFile) return
                if (!area) {
                  setError('Selecione sua área de atuação para continuar.')
                  return
                }
                analyzeCV(selectedFile)
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>

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
            {/* ── Score + export + resumo ── */}
            <Card className="p-6 md:p-8">
              <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
                <ScoreBadge
                  score={res.nota || 0}
                  label="Resume Score"
                  hint="Compatibilidade geral do seu currículo"
                />
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="w-32">
                    <CustomSelect
                      value={exportFormat}
                      onChange={(v) =>
                        setExportFormat(v as 'json' | 'md' | 'docx' | 'pdf')
                      }
                      options={[
                        { value: 'pdf', label: 'PDF' },
                        { value: 'docx', label: 'DOCX' },
                        { value: 'md', label: 'Markdown' },
                        { value: 'json', label: 'JSON' },
                      ]}
                    />
                  </div>
                  <GhostBtn
                    tone="indigo"
                    onClick={handleExport}
                    disabled={exporting !== null}
                  >
                    {exporting !== null ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <>
                        <Download className="w-3.5 h-3.5" />
                        Exportar
                      </>
                    )}
                  </GhostBtn>
                  <GhostBtn onClick={() => setActiveStep(1)}>
                    <RotateCcw className="w-3.5 h-3.5" />
                    Nova análise
                  </GhostBtn>
                </div>
              </div>

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
                <details className="mt-2 rounded-xl bg-slate-950 border border-slate-700 overflow-hidden group">
                  <summary className="flex items-center justify-between px-5 py-3 cursor-pointer text-sm font-semibold text-slate-300 hover:text-white transition-colors select-none">
                    <span className="flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-indigo-300" />
                      Uso de Tokens
                    </span>
                    <ChevronDown className="w-4 h-4 text-slate-400 group-open:rotate-180 transition-transform duration-200" />
                  </summary>
                  <div className="px-5 pb-4 pt-1 grid grid-cols-2 md:grid-cols-4 gap-2.5">
                    <TokenMetric label="Modelo" value={res.api_info?.model || '—'} mono tone="purple" />
                    <TokenMetric
                      label="Entrada"
                      value={formatTokens(res.uso_tokens?.prompt_tokens)}
                      mono
                      tone="indigo"
                    />
                    <TokenMetric
                      label="Saída"
                      value={formatTokens(res.uso_tokens?.completion_tokens)}
                      mono
                      tone="purple"
                    />
                    <TokenMetric
                      label="Total"
                      value={formatTokens(res.uso_tokens?.total_tokens)}
                      mono
                      highlight
                    />
                  </div>
                </details>
              )}

              {res.resumo_executivo && (
                <div className="mt-4 p-5 rounded-xl bg-slate-950 border border-slate-700">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    Resumo Executivo
                  </p>
                  <p className="text-base text-slate-200 leading-relaxed">{res.resumo_executivo}</p>
                </div>
              )}

              {res.pontos_fortes && res.pontos_fortes.length > 0 && (
                <div className="mt-5">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                    Pontos Fortes ({res.pontos_fortes.length})
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

              {res.pontos_fracos && res.pontos_fracos.length > 0 && (
                <div className="mt-5">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                    Pontos de Atenção ({res.pontos_fracos.length})
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {res.pontos_fracos.map((ponto, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          duration: 0.3,
                          delay: Math.min(i * 0.04, 0.3),
                          ease: EASE,
                        }}
                        className="flex items-start gap-2.5 p-3 rounded-xl bg-rose-500/10 border border-rose-400/20"
                      >
                        <AlertCircle className="w-4 h-4 text-rose-300 shrink-0 mt-0.5" />
                        <span className="text-sm text-rose-100 leading-relaxed">{ponto}</span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            {/* ── Estrutura do Currículo ── */}
            {(res.foto_detectada !== undefined || res.ordem_secoes) && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<FileCode2 className="w-5 h-5 text-purple-300" />}
                  tone="purple"
                  title="Estrutura do Currículo"
                  subtitle="Análise de formatação e organização"
                />
                <div className="space-y-3">
                  {res.foto_detectada !== undefined && (
                    <div className="rounded-xl bg-slate-950 border border-slate-700 p-4">
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-10 h-10 rounded-lg border flex items-center justify-center shrink-0 ${
                              res.foto_detectada
                                ? 'bg-rose-500/15 border-rose-400/30'
                                : 'bg-emerald-500/15 border-emerald-400/30'
                            }`}
                          >
                            <Eye
                              className={`w-5 h-5 ${
                                res.foto_detectada ? 'text-rose-300' : 'text-emerald-300'
                              }`}
                            />
                          </div>
                          <div>
                            <p className="text-sm font-bold text-white">
                              {res.foto_detectada ? 'Foto detectada' : 'Sem foto'}
                            </p>
                            <p className="text-xs text-slate-400 mt-0.5">
                              {res.foto_recomendada === false
                                ? 'Foto não recomendada para vaga de tecnologia'
                                : res.foto_recomendada === true
                                ? 'Foto recomendada para esta vaga'
                                : 'Análise de foto'}
                            </p>
                          </div>
                        </div>
                        {res.foto_detectada && (
                          <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-500/15 border border-rose-400/30 text-rose-200">
                            Remover foto
                          </span>
                        )}
                      </div>
                      {res.foto_detectada && res.foto_recomendada === false && (
                        <p className="mt-3 text-sm text-slate-300 leading-relaxed">
                          Currículos com foto são descartados automaticamente por muitos ATS.
                          Remova a foto para aumentar suas chances.
                        </p>
                      )}
                    </div>
                  )}

                  {res.ordem_secoes && (
                    <div className="rounded-xl bg-slate-950 border border-slate-700 p-4">
                      <div className="flex items-start justify-between gap-3 mb-2 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg border bg-blue-500/15 border-blue-400/30 flex items-center justify-center shrink-0">
                            <Activity className="w-5 h-5 text-blue-300" />
                          </div>
                          <p className="text-sm font-bold text-white">Ordem das Seções</p>
                        </div>
                        {res.ordem_secoes.correta ? (
                          <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/15 border border-emerald-400/30 text-emerald-200">
                            <CheckCircle2 className="w-3 h-3 inline mr-1" />
                            Correta
                          </span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/15 border border-amber-400/30 text-amber-200">
                            <AlertCircle className="w-3 h-3 inline mr-1" />
                            Requer ajuste
                          </span>
                        )}
                      </div>
                      {res.ordem_secoes.problema && (
                        <p className="text-sm text-slate-300 mb-2 leading-relaxed">
                          {res.ordem_secoes.problema}
                        </p>
                      )}
                      {res.ordem_secoes.como_corrigir && (
                        <div className="mt-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-400/30">
                          <p className="text-xs font-bold text-emerald-300 mb-1">Como corrigir:</p>
                          <p className="text-sm text-slate-200 leading-relaxed">
                            {res.ordem_secoes.como_corrigir}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* ── Fit com a Vaga (determinístico) ── */}
            {res.fit_com_vaga && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<UserCheck className="w-5 h-5 text-indigo-300" />}
                  tone="indigo"
                  title="Fit com a Vaga"
                  subtitle="Correspondência entre seu CV e a vaga"
                />
                {res.fit_com_vaga.calculado && res.fit_com_vaga.nota !== null ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-4">
                      <div className="flex flex-col items-center justify-center w-20 h-20 rounded-2xl bg-slate-950 border border-slate-700 shrink-0">
                        <span
                          className="text-2xl font-bold tabular-nums"
                          style={{ color: scoreTone(res.fit_com_vaga.nota).stroke }}
                        >
                          {Math.round(res.fit_com_vaga.nota)}
                        </span>
                        <span className="text-xs text-slate-500 font-medium uppercase mt-0.5">
                          de 100
                        </span>
                      </div>
                      <p className="text-sm text-slate-300 leading-relaxed">
                        {res.fit_com_vaga.resumo}
                      </p>
                    </div>

                    {(res.fit_com_vaga.requisitos_faltantes?.length ?? 0) > 0 && (
                      <KeywordGroup
                        label={`Faltantes (${res.fit_com_vaga.requisitos_faltantes!.length})`}
                        tone="rose"
                        words={res.fit_com_vaga.requisitos_faltantes!}
                      />
                    )}
                    {(res.fit_com_vaga.desejaveis_faltantes?.length ?? 0) > 0 && (
                      <KeywordGroup
                        label={`Diferenciais que faltam (${
                          res.fit_com_vaga.desejaveis_faltantes!.length
                        })`}
                        tone="amber"
                        words={res.fit_com_vaga.desejaveis_faltantes!}
                      />
                    )}
                    {(res.fit_com_vaga.requisitos_cobertos?.length ?? 0) > 0 && (
                      <KeywordGroup
                        label={`Cobertos (${res.fit_com_vaga.requisitos_cobertos!.length})`}
                        tone="emerald"
                        words={res.fit_com_vaga.requisitos_cobertos!}
                      />
                    )}
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-400/30">
                    <p className="text-sm font-semibold text-amber-200 mb-1">Fit não calculado</p>
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {res.fit_com_vaga.resumo}
                    </p>
                  </div>
                )}
              </Card>
            )}

            {/* ── Sub-sections (LLM) — só fazem sentido com descrição da vaga ── */}
            {jobTitle.trim().length >= 40 && (
              <>
                <SemanticFitSection
                  file={selectedFile}
                  jobTitle={jobTitle}
                  area={area}
                  analysisId={analysisId}
                  autoRun={fitAutoRun}
                />
                <RecruiterSimSection
                  file={selectedFile}
                  jobTitle={jobTitle}
                  jobLevel={jobLevel}
                  area={area}
                  analysisId={analysisId}
                />
                <CoverLetterSection
                  file={selectedFile}
                  jobTitle={jobTitle}
                  jobLevel={jobLevel}
                  analysisId={analysisId}
                />
              </>
            )}
            <CVDiffSection area={area} />

            {/* ── Palavras-chave ── */}
            {((res.palavras_chave_presentes?.length ?? 0) > 0 ||
              (res.palavras_chave_faltantes?.length ?? 0) > 0) && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<Target className="w-5 h-5 text-indigo-300" />}
                  tone="indigo"
                  title="Palavras-chave"
                  subtitle="Termos relevantes para o ATS"
                />
                <div className="space-y-4">
                  {res.palavras_chave_presentes && res.palavras_chave_presentes.length > 0 && (
                    <KeywordGroup
                      label={`Presentes (${res.palavras_chave_presentes.length})`}
                      tone="emerald"
                      words={res.palavras_chave_presentes}
                    />
                  )}
                  {res.palavras_chave_faltantes && res.palavras_chave_faltantes.length > 0 && (
                    <div>
                      <KeywordGroup
                        label={`Faltantes (${res.palavras_chave_faltantes.length})`}
                        tone="rose"
                        words={res.palavras_chave_faltantes}
                      />
                      <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                        Adicione estas palavras-chave naturalmente no currículo para melhorar a
                        compatibilidade com o ATS.
                      </p>
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* ── Erros Ortográficos ── */}
            {res.erros_ortograficos && res.erros_ortograficos.length > 0 && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<XCircle className="w-5 h-5 text-rose-300" />}
                  tone="rose"
                  title="Erros Ortográficos"
                  subtitle={`${res.erros_ortograficos.length} ${
                    res.erros_ortograficos.length === 1 ? 'erro encontrado' : 'erros encontrados'
                  }`}
                />
                <div className="space-y-2.5">
                  {res.erros_ortograficos.map((err, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.25), ease: EASE }}
                      className="rounded-xl bg-slate-950 border border-rose-400/20 p-4"
                    >
                      <div className="flex items-start gap-3">
                        <XCircle className="w-4 h-4 text-rose-300 shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <code className="text-sm font-bold text-rose-300 font-mono">
                              {err.palavra}
                            </code>
                            <span className="text-slate-500">→</span>
                            <code className="text-sm font-bold text-emerald-300 font-mono">
                              {err.correcao}
                            </code>
                            <span
                              className={`text-xs px-2 py-0.5 rounded-md font-semibold ${
                                err.gravidade === 'alta'
                                  ? 'bg-rose-500/20 text-rose-200'
                                  : err.gravidade === 'medio'
                                  ? 'bg-amber-500/20 text-amber-200'
                                  : 'bg-slate-700 text-slate-300'
                              }`}
                            >
                              {err.gravidade}
                            </span>
                          </div>
                          <p className="text-sm text-slate-400 leading-relaxed">{err.contexto}</p>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </Card>
            )}

            {/* ── Erros Comuns ── */}
            {res.erros_comuns_detectados && res.erros_comuns_detectados.length > 0 && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<AlertTriangle className="w-5 h-5 text-amber-300" />}
                  tone="amber"
                  title="Erros Comuns Detectados"
                  subtitle={`${res.erros_comuns_detectados.length} ${
                    res.erros_comuns_detectados.length === 1
                      ? 'padrão problemático'
                      : 'padrões problemáticos'
                  }`}
                />
                <ErrosComuns erros={res.erros_comuns_detectados} />
              </Card>
            )}

            {/* ── Checklist ── */}
            {res.checklist_validacao && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<CheckCircle2 className="w-5 h-5 text-emerald-300" />}
                  tone="emerald"
                  title="Checklist do Guia"
                  subtitle="Validação de boas práticas"
                />
                <ChecklistItems data={res.checklist_validacao} />
              </Card>
            )}

            {/* ── ATS ── */}
            {res.analise_ats && typeof res.analise_ats === 'object' && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<Cpu className="w-5 h-5 text-blue-300" />}
                  tone="blue"
                  title="Análise ATS"
                  subtitle="Como os sistemas de triagem leem seu CV"
                />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-700">
                    <p className="text-xs font-semibold text-slate-400 mb-1">Score ATS</p>
                    <p className="text-3xl font-bold text-white tabular-nums">
                      {res.analise_ats.score_ats ?? '—'}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-700">
                    <p className="text-xs font-semibold text-slate-400 mb-1">Veredito dos Robôs</p>
                    <p className="text-base font-medium text-white leading-relaxed">
                      {res.analise_ats.veredito_robos ?? '—'}
                    </p>
                  </div>
                </div>
                {res.analise_ats.explicacao && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-700 mb-4">
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {res.analise_ats.explicacao}
                    </p>
                  </div>
                )}
                {res.analise_ats.palavras_chave_faltantes &&
                  res.analise_ats.palavras_chave_faltantes.length > 0 && (
                    <div className="mb-4">
                      <KeywordGroup
                        label={`Palavras-chave faltantes (${res.analise_ats.palavras_chave_faltantes.length})`}
                        tone="rose"
                        words={res.analise_ats.palavras_chave_faltantes}
                      />
                    </div>
                  )}
                {res.analise_ats.gargalos_formatacao &&
                  res.analise_ats.gargalos_formatacao.length > 0 && (
                    <div>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                        Gargalos de formatação
                      </p>
                      <ul className="space-y-2">
                        {res.analise_ats.gargalos_formatacao.map((gargalo, i) => (
                          <li
                            key={i}
                            className="text-sm text-amber-200 flex items-start gap-2 leading-relaxed"
                          >
                            <AlertCircle className="w-4 h-4 text-amber-300 shrink-0 mt-0.5" />
                            {gargalo}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </Card>
            )}

            {/* ── Análise por Seção ── */}
            {res.analise_secoes && Object.keys(res.analise_secoes).length > 0 && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<Sliders className="w-5 h-5 text-purple-300" />}
                  tone="purple"
                  title="Análise por Seção"
                  subtitle={`${Object.keys(res.analise_secoes).length} seções avaliadas`}
                />
                <div className="space-y-2.5"><AnaliseSecoes data={res.analise_secoes} /></div>
              </Card>
            )}

            {/* ── Sugestões ── */}
            {res.sugestoes && res.sugestoes.length > 0 && (
              <Card className="p-6 md:p-8">
                <SectionHead
                  icon={<Sparkles className="w-5 h-5 text-indigo-300" />}
                  tone="indigo"
                  title="Sugestões de Melhoria"
                  subtitle={`${res.sugestoes.length} recomendações`}
                />
                <div className="space-y-2.5">
                  {res.sugestoes.map((sugestao, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.3), ease: EASE }}
                      className="flex items-start gap-3 p-4 rounded-xl bg-slate-950 border border-slate-700"
                    >
                      <span className="shrink-0 w-6 h-6 rounded-md bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-xs font-bold text-indigo-200">
                        {i + 1}
                      </span>
                      <p className="text-sm text-slate-200 leading-relaxed">{sugestao}</p>
                    </motion.div>
                  ))}
                </div>
              </Card>
            )}

            {/* ── Back ── */}
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
