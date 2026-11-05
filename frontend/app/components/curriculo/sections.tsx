/**
 * Subcomponentes de secao da ferramenta de analise de curriculo.
 * Extraidos de CurriculoTool.tsx (split do god file) — logica preservada.
 */
'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Upload, Sparkles, CheckCircle2, AlertTriangle,
  AlertCircle, RefreshCw, Gavel, Play, GitCompare, XCircle,
  Check, Copy, Download, ChevronDown, UserCheck, Target, RotateCcw,
} from 'lucide-react'
import type {
  AnaliseSecao, ErroComum, FitSemantico, RecrutadorSim, CoverLetter,
  CVDiffResult, DiffCV, DiffCVItem, DiffCVDeterministico, ChecklistValidacao,
} from '../../types/analysis'
import { API_BASE_URL } from '../../lib/api'
import { friendlyError, isAbortError } from '../../lib/errors'
import { CustomSelect } from '../CustomSelect'
import { Dropzone } from '../Dropzone'
import { getBestProvider } from '../../hooks/useIaProviders'
import {
  EASE, Card, SectionHead, Input, PrimaryBtn, GhostBtn, StatusPill,
  addLlmProvider, SECTION_LABELS, ERROR_TYPE_LABELS,
} from './ui'

/* ═══════════ Análise por Seção ═══════════ */
export function AnaliseSecoes({ data }: { data: Record<string, AnaliseSecao> }) {
  return Object.entries(data).map(([key, value], idx) => {
    const label = SECTION_LABELS[key] || key
    return (
      <motion.div
        key={key}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: Math.min(idx * 0.04, 0.3), ease: EASE }}
        className="rounded-xl bg-slate-950 border border-slate-700 p-4"
      >
        <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-bold text-white">{label}</h3>
            {value.presente === false && (
              <span className="text-xs px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-400">
                Não presente
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-mono font-semibold text-slate-300 tabular-nums">
              {value.score}/100
            </span>
            {value.status && <StatusPill status={value.status} />}
          </div>
        </div>

        {key === 'experiencia' &&
          (value.has_xyz !== undefined ||
            value.has_metrics !== undefined ||
            value.bullet_points !== undefined) && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {value.has_xyz && (
                <span className="text-xs px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-200 border border-emerald-400/30">
                  ✓ Fórmula XYZ
                </span>
              )}
              {value.has_metrics === false && (
                <span className="text-xs px-2 py-1 rounded-md bg-rose-500/15 text-rose-200 border border-rose-400/30">
                  ✗ Sem métricas
                </span>
              )}
              {value.bullet_points === false && (
                <span className="text-xs px-2 py-1 rounded-md bg-rose-500/15 text-rose-200 border border-rose-400/30">
                  ✗ Parágrafos em vez de bullets
                </span>
              )}
              {value.bullet_points === true && (
                <span className="text-xs px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-200 border border-emerald-400/30">
                  ✓ Bullet points
                </span>
              )}
            </div>
          )}

        {value.problema && (
          <div className="mb-2.5">
            <p className="text-xs font-bold text-rose-300 mb-1 flex items-center gap-1.5">
              <AlertCircle className="w-3 h-3" />
              Problema detectado
            </p>
            <p className="text-sm text-slate-300 leading-relaxed">{value.problema}</p>
          </div>
        )}
        {value.como_corrigir && (
          <div>
            <p className="text-xs font-bold text-emerald-300 mb-1 flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3" />
              Como corrigir
            </p>
            <p className="text-sm text-slate-300 leading-relaxed">{value.como_corrigir}</p>
          </div>
        )}
      </motion.div>
    )
  })
}

/* ═══════════ Erros Comuns ═══════════ */
export function ErrosComuns({ erros }: { erros: ErroComum[] }) {
  if (erros.length === 0) return null
  return (
    <div className="space-y-2.5">
      {erros.map((erro, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.25), ease: EASE }}
          className="rounded-xl bg-slate-950 border border-slate-700 p-4"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-amber-200 mb-1">
                {ERROR_TYPE_LABELS[erro.tipo] || erro.tipo}
              </p>
              <p className="text-sm text-slate-300 leading-relaxed">{erro.descricao}</p>
              {erro.exemplo && (
                <div className="mt-2 p-3 rounded-lg bg-slate-900 border border-slate-800">
                  <p className="text-xs font-semibold text-slate-400 mb-1">Exemplo no currículo:</p>
                  <p className="text-sm text-slate-200 font-mono break-words">{erro.exemplo}</p>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  )
}

/* ═══════════ Small helpers ═══════════ */
export function TokenMetric({
  label,
  value,
  mono,
  tone = 'slate',
  highlight,
}: {
  label: string
  value: string
  mono?: boolean
  tone?: 'indigo' | 'purple' | 'slate'
  highlight?: boolean
}) {
  const textCls =
    tone === 'indigo'
      ? 'text-indigo-200'
      : tone === 'purple'
      ? 'text-purple-200'
      : 'text-white'
  return (
    <div
      className={`p-3 rounded-lg border text-center ${
        highlight ? 'bg-slate-900 border-slate-600' : 'bg-slate-900 border-slate-800'
      }`}
    >
      <p className="text-xs font-semibold text-slate-400 mb-1">{label}</p>
      <p
        className={`text-sm font-bold truncate ${textCls} ${mono ? 'font-mono' : ''}`}
        title={value}
      >
        {value}
      </p>
    </div>
  )
}

export function KeywordGroup({
  label,
  tone,
  words,
}: {
  label: string
  tone: 'rose' | 'amber' | 'emerald' | 'blue'
  words: string[]
}) {
  const cls =
    tone === 'rose'
      ? 'bg-rose-500/15 text-rose-200 border-rose-400/30'
      : tone === 'amber'
      ? 'bg-amber-500/15 text-amber-200 border-amber-400/30'
      : tone === 'emerald'
      ? 'bg-emerald-500/15 text-emerald-200 border-emerald-400/30'
      : 'bg-blue-500/15 text-blue-200 border-blue-400/30'
  const labelCls =
    tone === 'rose'
      ? 'text-rose-300'
      : tone === 'amber'
      ? 'text-amber-300'
      : tone === 'emerald'
      ? 'text-emerald-300'
      : 'text-blue-300'
  return (
    <div>
      <p className={`text-xs font-bold uppercase tracking-wider mb-2 ${labelCls}`}>{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {words.map((w, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.3), ease: EASE }}
            className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${cls}`}
          >
            {w}
          </motion.span>
        ))}
      </div>
    </div>
  )
}

export function ChecklistItems({ data }: { data: ChecklistValidacao }) {
  const items: React.ReactNode[] = []

  if (data.nome_arquivo) {
    const ok = data.nome_arquivo.valido
    items.push(
      <ChecklistRow
        key="nome"
        ok={ok}
        title="Nome do Arquivo"
        description={ok ? 'Nome adequado encontrado' : data.nome_arquivo.problema || 'Verificar nome'}
      />
    )
  }

  if (data.numero_paginas !== undefined) {
    const ok = data.numero_paginas_valido === true
    items.push(
      <ChecklistRow
        key="paginas"
        ok={ok}
        warn={!ok}
        title="Número de Páginas"
        description={`${data.numero_paginas} página${
          data.numero_paginas > 1 ? 's' : ''
        }${data.numero_paginas_problema ? ` — ${data.numero_paginas_problema}` : ''}`}
      />
    )
  }

  if (data.pdf_selecionavel) {
    const ok = data.pdf_selecionavel.selecionavel
    items.push(
      <ChecklistRow
        key="pdf"
        ok={ok}
        title="PDF Selecionável"
        description={
          ok
            ? 'Texto pode ser selecionado (Ctrl+F funciona)'
            : data.pdf_selecionavel.problema || 'PDF parece ser imagem escaneada'
        }
      />
    )
  }

  if (data.dados_sensiveis && data.dados_sensiveis.length > 0) {
    items.push(
      <ChecklistRow
        key="dados"
        ok={false}
        title="Dados Sensíveis Detectados"
        description={
          <ul className="text-xs text-slate-400 mt-1 space-y-0.5">
            {data.dados_sensiveis.map((d, i) => (
              <li key={i}>• {d.descricao}</li>
            ))}
          </ul>
        }
      />
    )
  }

  if (data.abreviacoes && data.abreviacoes.length > 0) {
    items.push(
      <ChecklistRow
        key="abrev"
        ok={false}
        warn
        title="Abreviações Encontradas"
        description={
          <ul className="text-xs text-slate-400 mt-1 space-y-0.5">
            {data.abreviacoes.map((a, i) => (
              <li key={i}>
                • {a.descricao}
                {a.sugestao && <span className="text-emerald-400"> → {a.sugestao}</span>}
              </li>
            ))}
          </ul>
        }
      />
    )
  }

  if (data.ordem_cronologica) {
    const ok = data.ordem_cronologica.cronologica
    items.push(
      <ChecklistRow
        key="crono"
        ok={ok}
        warn={!ok}
        title="Ordem Cronológica"
        description={
          ok
            ? 'Experiências em ordem reversa (mais recente primeiro)'
            : data.ordem_cronologica.problema || 'Verificar ordem'
        }
      />
    )
  }

  if (data.profile_summary?.genérico) {
    items.push(
      <ChecklistRow
        key="profile"
        ok={false}
        warn
        title="Profile Summary Genérico"
        description={
          <>
            {data.profile_summary.problema}
            {data.profile_summary.sugestao && (
              <span className="text-emerald-400"> — {data.profile_summary.sugestao}</span>
            )}
          </>
        }
      />
    )
  }

  if (data.projetos_com_link && !data.projetos_com_link.com_links) {
    items.push(
      <ChecklistRow
        key="projetos"
        ok={false}
        warn
        title="Projetos sem Link"
        description={data.projetos_com_link.problema || 'Adicionar link para projetos'}
      />
    )
  }

  if (data.motivo_saida && data.motivo_saida.length > 0) {
    items.push(
      <ChecklistRow
        key="saida"
        ok={false}
        title="Motivo de Saída Detectado"
        description={
          <ul className="text-xs text-slate-400 mt-1 space-y-0.5">
            {data.motivo_saida.map((m, i) => (
              <li key={i}>• {m.descricao}</li>
            ))}
          </ul>
        }
      />
    )
  }

  if (data.multiplos_curriculos?.problema) {
    items.push(
      <ChecklistRow
        key="multi"
        ok={false}
        warn
        title="Múltiplos Currículos"
        description={data.multiplos_curriculos.problema}
      />
    )
  }

  if (data.cover_letter?.problema) {
    items.push(
      <ChecklistRow
        key="cover"
        ok={false}
        warn
        title="Possível Cover Letter"
        description={data.cover_letter.problema}
      />
    )
  }

  return <div className="space-y-2.5">{items}</div>
}

function ChecklistRow({
  ok,
  warn,
  title,
  description,
}: {
  ok: boolean
  warn?: boolean
  title: string
  description: React.ReactNode
}) {
  const cls = ok
    ? 'bg-emerald-500/10 border-emerald-400/20'
    : warn
    ? 'bg-amber-500/10 border-amber-400/20'
    : 'bg-rose-500/10 border-rose-400/20'
  const Icon = ok ? CheckCircle2 : warn ? AlertTriangle : XCircle
  const iconColor = ok ? 'text-emerald-300' : warn ? 'text-amber-300' : 'text-rose-300'
  return (
    <div className={`flex items-start gap-3 p-3.5 rounded-xl border ${cls}`}>
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${iconColor}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-100">{title}</p>
        <div className="text-sm text-slate-300 mt-0.5 leading-relaxed">{description}</div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   SUB-COMPONENTS — lógica 100% preservada, styling atualizado
   ═══════════════════════════════════════════════════════════════ */

/* ───────────── SemanticFitSection ───────────── */
export function SemanticFitSection({
  file,
  jobTitle,
  area,
  analysisId,
  autoRun,
}: {
  file: File | null
  jobTitle: string
  area: string
  analysisId: number
  autoRun: boolean
}) {
  const [fit, setFit] = useState<FitSemantico | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const canRun = !!file && jobTitle.trim().length >= 40
  const canRetry = !!file

  const run = useCallback(async () => {
    if (!file) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setFit(null)
    setError(null)
    setLoading(true)
    const formData = new FormData()
    formData.append('cv_file', file)
    formData.set('job_description', jobTitle.trim())
    if (area) formData.set('area', area)
    addLlmProvider(formData, ['curriculo'])

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/semantic-fit`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `Erro HTTP ${response.status}: falha no fit semântico.`)
      }
      const data = await response.json()
      setFit(data.analise ?? null)
    } catch (err) {
      if (isAbortError(err)) return
      if (abortRef.current === controller) {
        setError(friendlyError(err, 'Falha na análise semântica da vaga.'))
      }
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }, [file, jobTitle, area])

  // Auto-execução quando a análise muda. O reset de fit/error/copiedIdx já
  // acontece no render (prevId, acima); `run` é imperativo (loading + fetch).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (autoRun) void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId])

  useEffect(() => () => {
    abortRef.current?.abort()
  }, [])

  const copySuggestion = async (sugerido: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(sugerido)
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx((cur) => (cur === idx ? null : cur)), 2000)
    } catch {
      setError('Não foi possível copiar para a área de transferência.')
    }
  }

  const requisitos = Array.isArray(fit?.requisitos) ? fit!.requisitos : []
  const comEvidencia = requisitos.filter((r) => r.presente && !!r.evidencia)
  const sugestoes = Array.isArray(fit?.sugestoes_de_reescrita) ? fit!.sugestoes_de_reescrita : []

  return (
    <Card className="p-6 md:p-8">
      <SectionHead
        icon={<UserCheck className="w-5 h-5 text-indigo-300" />}
        tone="indigo"
        title="Análise Semântica da Vaga"
        subtitle="Compara as evidências do seu CV com os requisitos da vaga"
      />

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-300" />
          Comparando seu CV com a vaga (IA)...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-400/30 p-4">
          <p className="text-sm text-rose-200 leading-relaxed">{error}</p>
          {canRetry && (
            <GhostBtn tone="rose" onClick={() => run()} className="mt-2">
              <RefreshCw className="w-3.5 h-3.5" />
              Tentar novamente
            </GhostBtn>
          )}
        </div>
      )}

      {!loading && !error && !fit && (
        <p className="text-sm text-amber-200 leading-relaxed">
          {canRun
            ? 'Esta análise roda sozinha ao clicar em "Analisar Currículo" com a descrição da vaga preenchida.'
            : 'Selecione um arquivo de currículo para liberar a análise.'}
        </p>
      )}

      {!loading && !error && fit && (
        <div className="space-y-5">
          {fit.gap_resumido && (
            <p className="text-sm text-slate-300 leading-relaxed">{fit.gap_resumido}</p>
          )}

          {requisitos.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Requisitos da Vaga ({requisitos.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {requisitos.map((req, i) => {
                  const ok = req.presente && !!req.evidencia
                  const chip = ok
                    ? 'bg-emerald-500/15 text-emerald-200 border-emerald-400/30'
                    : req.tipo === 'diferencial'
                    ? 'bg-amber-500/15 text-amber-200 border-amber-400/30'
                    : 'bg-rose-500/15 text-rose-200 border-rose-400/30'
                  return (
                    <span
                      key={i}
                      title={req.evidencia ? `No CV: "${req.evidencia}"` : undefined}
                      className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${chip}`}
                    >
                      {req.termo}
                      {req.tipo === 'diferencial' && (
                        <span className="opacity-70"> · diferencial</span>
                      )}
                    </span>
                  )
                })}
              </div>
              {comEvidencia.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  {comEvidencia.map((req, i) => (
                    <p key={i} className="text-xs text-slate-400 leading-relaxed">
                      <span className="text-emerald-300 font-semibold">{req.termo}:</span>{' '}
                      {req.alias_encontrado && req.alias_encontrado !== req.termo ? (
                        <>encontrado como “{req.alias_encontrado}” — </>
                      ) : null}
                      “{req.evidencia}”
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {sugestoes.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Sugestões de Reescrita ({sugestoes.length})
              </p>
              <div className="space-y-2.5">
                {sugestoes.map((sug, i) => (
                  <div
                    key={i}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-700"
                  >
                    <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-1">
                      {sug.secao}
                    </p>
                    {sug.texto_atual && (
                      <p className="text-xs text-slate-400 mb-1.5">
                        Hoje: <span className="line-through">“{sug.texto_atual}”</span>
                      </p>
                    )}
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-slate-200 leading-relaxed flex-1">
                        {sug.sugerido}
                      </p>
                      <GhostBtn
                        tone="indigo"
                        onClick={() => copySuggestion(sug.sugerido, i)}
                        className="shrink-0"
                      >
                        {copiedIdx === i ? (
                          <>
                            <Check className="w-3.5 h-3.5" />
                            Copiado
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" />
                            Copiar
                          </>
                        )}
                      </GhostBtn>
                    </div>
                    {sug.motivo && (
                      <p className="text-xs text-slate-400 mt-2 leading-relaxed">{sug.motivo}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

/* ───────────── RecruiterSimSection ───────────── */
const VEREDITO_BADGES: Record<
  RecrutadorSim['veredito'],
  { label: string; cls: string; Icon: typeof CheckCircle2 }
> = {
  aprovado: {
    label: 'Aprovado',
    cls: 'bg-emerald-500/15 border-emerald-400/30 text-emerald-200',
    Icon: CheckCircle2,
  },
  duvida: {
    label: 'Dúvida',
    cls: 'bg-amber-500/15 border-amber-400/30 text-amber-200',
    Icon: AlertCircle,
  },
  reprovado: {
    label: 'Reprovado',
    cls: 'bg-rose-500/15 border-rose-400/30 text-rose-200',
    Icon: XCircle,
  },
}

export function RecruiterSimSection({
  file,
  jobTitle,
  jobLevel,
  area,
  analysisId,
}: {
  file: File | null
  jobTitle: string
  jobLevel: string
  area: string
  analysisId: number
}) {
  const [sim, setSim] = useState<RecrutadorSim | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Quando a análise de origem muda, a simulação fica obsoleta — reset no render
  const [prevId, setPrevId] = useState(analysisId)
  if (prevId !== analysisId) {
    setPrevId(analysisId)
    setSim(null)
    setError(null)
  }

  const canRun = !!file && jobTitle.trim().length >= 40

  const run = useCallback(async () => {
    if (!file) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setSim(null)
    setError(null)
    setLoading(true)
    const formData = new FormData()
    formData.append('cv_file', file)
    formData.set('job_description', jobTitle.trim())
    if (jobLevel !== 'Sem nível específico') formData.set('target_role', jobLevel.toLowerCase())
    if (area) formData.set('area', area)
    addLlmProvider(formData, ['curriculo'])

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/recruiter-sim`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(
          errData?.detail || `Erro HTTP ${response.status}: falha na simulação do recrutador.`
        )
      }
      const data = await response.json()
      setSim(data.analise ?? null)
    } catch (err) {
      if (isAbortError(err)) return
      if (abortRef.current === controller) {
        setError(friendlyError(err, 'Falha na simulação do recrutador.'))
      }
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }, [file, jobTitle, jobLevel, area])

  useEffect(() => () => {
    abortRef.current?.abort()
  }, [])

  const badge = sim ? VEREDITO_BADGES[sim.veredito] ?? VEREDITO_BADGES.duvida : null
  const porQue = Array.isArray(sim?.por_que) ? sim!.por_que : []
  const sinais = Array.isArray(sim?.sinais_vermelhos) ? sim!.sinais_vermelhos : []
  const perguntas = Array.isArray(sim?.perguntas_de_entrevista) ? sim!.perguntas_de_entrevista : []

  return (
    <Card className="p-6 md:p-8">
      <SectionHead
        icon={<Gavel className="w-5 h-5 text-indigo-300" />}
        tone="indigo"
        title="Simulação de Recrutador"
        subtitle="A IA lê seu CV como um recrutador da vaga e devolve o veredito mais honesto antes de você aplicar."
      />

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-300" />
          Simulando a leitura do recrutador (IA)...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-400/30 p-4">
          <p className="text-sm text-rose-200 leading-relaxed">{error}</p>
          {canRun && (
            <GhostBtn tone="rose" onClick={() => run()} className="mt-2">
              <RefreshCw className="w-3.5 h-3.5" />
              Tentar novamente
            </GhostBtn>
          )}
        </div>
      )}

      {!loading && !error && !sim && (
        <div>
          <GhostBtn tone="indigo" onClick={() => run()} disabled={!canRun}>
            <Play className="w-3.5 h-3.5" />
            Rodar simulação
          </GhostBtn>
          {!canRun && (
            <p className="text-sm text-amber-200 mt-3 leading-relaxed">
              Selecione um arquivo de currículo para liberar a simulação.
            </p>
          )}
        </div>
      )}

      {!loading && !error && sim && badge && (
        <div className="space-y-5">
          <div className="flex items-center gap-4 flex-wrap">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-bold border ${badge.cls}`}
            >
              <badge.Icon className="w-4 h-4" />
              {badge.label}
            </span>
            <div className="flex flex-col">
              <span className="text-2xl font-bold text-white leading-tight tabular-nums">
                {sim.confianca}
                <span className="text-sm font-medium text-slate-400"> /10</span>
              </span>
              <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                confiança no veredito
              </span>
            </div>
          </div>

          {porQue.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Por quê
              </p>
              <ul className="space-y-2">
                {porQue.map((item, i) => (
                  <li key={i} className="text-sm text-slate-300 flex gap-2 leading-relaxed">
                    <span className="text-indigo-300 shrink-0 font-bold">•</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <p className="text-xs font-bold text-rose-300 uppercase tracking-wider mb-2">
              Sinais vermelhos
            </p>
            {sinais.length > 0 ? (
              <ul className="space-y-2">
                {sinais.map((item, i) => (
                  <li key={i} className="text-sm text-slate-300 flex gap-2 leading-relaxed">
                    <AlertTriangle className="w-4 h-4 text-rose-300 shrink-0 mt-0.5" />
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-emerald-300 leading-relaxed">
                Nenhum sinal vermelho identificado para esta vaga.
              </p>
            )}
          </div>

          {perguntas.length > 0 && (
            <div>
              <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-2">
                Perguntas da entrevista
              </p>
              <ol className="space-y-2">
                {perguntas.map((item, i) => (
                  <li key={i} className="text-sm text-slate-300 leading-relaxed">
                    <span className="font-bold text-indigo-300 mr-2 tabular-nums">{i + 1}.</span>
                    {item}
                  </li>
                ))}
              </ol>
            </div>
          )}

          <GhostBtn onClick={() => run()}>
            <RotateCcw className="w-3.5 h-3.5" />
            Rodar novamente
          </GhostBtn>
        </div>
      )}
    </Card>
  )
}

/* ───────────── CoverLetterSection ───────────── */
export function CoverLetterSection({
  file,
  jobTitle,
  jobLevel,
  area,
  analysisId,
}: {
  file: File | null
  jobTitle: string
  jobLevel: string
  area: string
  analysisId: number
}) {
  const [carta, setCarta] = useState<CoverLetter | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [format, setFormat] = useState<'completa' | 'curta'>('completa')
  const abortRef = useRef<AbortController | null>(null)

  // Quando a análise de origem muda, a carta fica obsoleta — reset no render
  const [prevId, setPrevId] = useState(analysisId)
  if (prevId !== analysisId) {
    setPrevId(analysisId)
    setCarta(null)
    setError(null)
    setCopied(false)
    setFormat('completa')
  }

  const canGenerate = !!file && jobTitle.trim().length >= 40

  const generate = useCallback(
    async (formato: 'completa' | 'curta') => {
      if (!file) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setCarta(null)
      setError(null)
      setCopied(false)
      setLoading(true)
      setFormat(formato)
      const formData = new FormData()
      formData.append('cv_file', file)
      formData.set('job_description', jobTitle.trim())
      formData.set('formato', formato)
      if (jobLevel !== 'Sem nível específico') formData.set('target_role', jobLevel.toLowerCase())
      addLlmProvider(formData, ['curriculo'])

      try {
        const response = await fetch(`${API_BASE_URL}/api/cv/cover-letter`, {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        })
        if (!response.ok) {
          const errData = await response.json().catch(() => null)
          throw new Error(
            errData?.detail || `Erro HTTP ${response.status}: falha na geração da cover letter.`
          )
        }
        const data = await response.json()
        setCarta(data.carta ?? null)
      } catch (err) {
        if (isAbortError(err)) return
        if (abortRef.current === controller) {
          setError(friendlyError(err, 'Falha na geração da cover letter.'))
        }
      } finally {
        if (abortRef.current === controller) setLoading(false)
      }
    },
    [file, jobTitle, jobLevel]
  )

  useEffect(() => () => {
    abortRef.current?.abort()
  }, [])

  const copyLetter = useCallback(async () => {
    if (!carta) return
    try {
      await navigator.clipboard.writeText(carta.texto)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Não foi possível copiar para a área de transferência.')
    }
  }, [carta])

  const downloadLetter = useCallback(() => {
    if (!carta) return
    const nivel =
      jobLevel !== 'Sem nível específico'
        ? jobLevel.toLowerCase().replace(/\s+/g, '-')
        : 'vaga'
    const blob = new Blob([carta.texto], { type: 'text/plain;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Cover_Letter_${nivel}.txt`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, [carta, jobLevel])

  const fatos = Array.isArray(carta?.fatos_usados) ? carta!.fatos_usados : []

  return (
    <Card className="p-6 md:p-8">
      <SectionHead
        icon={<FileText className="w-5 h-5 text-indigo-300" />}
        tone="indigo"
        title="Cover Letter"
        subtitle="A IA escreve a carta de apresentação a partir do seu CV e da descrição da vaga — só com fatos do seu currículo."
      />

      <div className="flex flex-wrap items-center gap-2 mb-2">
        <GhostBtn
          tone="indigo"
          onClick={() => generate('completa')}
          disabled={!canGenerate || loading}
        >
          <FileText className="w-3.5 h-3.5" />
          Gerar (completa)
        </GhostBtn>
        <GhostBtn
          tone="indigo"
          onClick={() => generate('curta')}
          disabled={!canGenerate || loading}
        >
          <FileText className="w-3.5 h-3.5" />
          Gerar (curta)
        </GhostBtn>
      </div>

      {!canGenerate && !carta && !loading && (
        <p className="text-sm text-amber-200 mt-3 leading-relaxed">
          Selecione um arquivo de currículo para liberar a geração.
        </p>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-300 mt-4">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-300" />
          Escrevendo a cover letter (IA)...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-400/30 p-4 mt-4">
          <p className="text-sm text-rose-200 leading-relaxed">{error}</p>
          {canGenerate && (
            <GhostBtn tone="rose" onClick={() => generate(format)} className="mt-2">
              <RefreshCw className="w-3.5 h-3.5" />
              Tentar novamente
            </GhostBtn>
          )}
        </div>
      )}

      {!loading && !error && carta && (
        <div className="space-y-4 mt-4">
          <div className="rounded-xl bg-slate-950 border border-slate-700 p-4">
            <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-2">
              {carta.formato === 'curta'
                ? 'Carta gerada · formato curto (2 parágrafos)'
                : 'Carta gerada · formato completo (5 parágrafos)'}
            </p>
            <textarea
              readOnly
              value={carta.texto}
              rows={Math.max(10, carta.texto.split('\n').length + 1)}
              className="w-full resize-y rounded-lg bg-transparent text-sm text-slate-200 leading-relaxed whitespace-pre-wrap outline-none focus:outline-none"
            />
          </div>

          {fatos.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Fatos do CV usados na carta ({fatos.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {fatos.map((fato, i) => (
                  <span
                    key={i}
                    title={fato}
                    className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 border border-slate-700 text-slate-300 max-w-full truncate"
                  >
                    {fato.length > 60 ? `${fato.slice(0, 57)}…` : fato}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <GhostBtn tone="indigo" onClick={copyLetter}>
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  Copiado
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copiar
                </>
              )}
            </GhostBtn>
            <GhostBtn onClick={downloadLetter}>
              <Download className="w-3.5 h-3.5" />
              Baixar .txt
            </GhostBtn>
          </div>
        </div>
      )}
    </Card>
  )
}

/* ───────────── CVDiffSection ───────────── */
function SinaisObjetivos({ det }: { det: DiffCVDeterministico }) {
  const metricaDelta = det.metricas_numericas.novo - det.metricas_numericas.anterior
  const bulletsDelta = det.bullets_experiencia.novo - det.bullets_experiencia.anterior
  const deltaCls = (d: number) =>
    d > 0 ? 'text-emerald-300' : d < 0 ? 'text-rose-300' : 'text-slate-400'

  return (
    <div className="rounded-xl bg-slate-950 border border-slate-700 p-4">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
        Sinais objetivos
      </p>
      <div className="flex flex-wrap gap-2">
        <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-800 border border-slate-700 text-slate-200">
          Métricas numéricas: {det.metricas_numericas.anterior} →{' '}
          <span className={`font-bold ${deltaCls(metricaDelta)}`}>
            {det.metricas_numericas.novo}
          </span>
        </span>
        <span className="px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-800 border border-slate-700 text-slate-200">
          Bullets na experiência: {det.bullets_experiencia.anterior} →{' '}
          <span className={`font-bold ${deltaCls(bulletsDelta)}`}>{det.bullets_experiencia.novo}</span>
        </span>
      </div>
      {(det.termos_adicionados.length > 0 || det.termos_removidos.length > 0) && (
        <div className="mt-3 space-y-2">
          {det.termos_adicionados.length > 0 && (
            <div>
              <p className="text-xs font-bold text-emerald-300 uppercase tracking-wider mb-1.5">
                Termos-chave adicionados
              </p>
              <div className="flex flex-wrap gap-1.5">
                {det.termos_adicionados.map((t, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/15 text-emerald-200 border border-emerald-400/30"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
          {det.termos_removidos.length > 0 && (
            <div>
              <p className="text-xs font-bold text-rose-300 uppercase tracking-wider mb-1.5">
                Termos-chave removidos
              </p>
              <div className="flex flex-wrap gap-1.5">
                {det.termos_removidos.map((t, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 rounded-md text-xs font-semibold bg-rose-500/15 text-rose-200 border border-rose-400/30"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function renderDiffItems(items: DiffCVItem[], tone: 'melhora' | 'piorou') {
  const Icon = tone === 'melhora' ? CheckCircle2 : AlertTriangle
  const iconCls = tone === 'melhora' ? 'text-emerald-300' : 'text-rose-300'
  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-400 leading-relaxed">
        {tone === 'melhora'
          ? 'Nenhuma melhoria detectada entre as versões.'
          : 'Nenhum problema detectado entre as versões.'}
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2">
          <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${iconCls}`} />
          <div className="min-w-0">
            <p className="text-sm text-slate-200 leading-relaxed">{item.item}</p>
            {item.evidencia_nova && (
              <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                No CV novo: “{item.evidencia_nova}”
              </p>
            )}
            {item.evidencia_antiga && (
              <p className="text-xs text-slate-400 leading-relaxed">
                Na versão antiga: “{item.evidencia_antiga}”
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function CVDiffSection({ area }: { area: string }) {
  const [arquivoAnterior, setArquivoAnterior] = useState<File | null>(null)
  const [arquivoNovo, setArquivoNovo] = useState<File | null>(null)
  const [diff, setDiff] = useState<CVDiffResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const diffAbortRef = useRef<AbortController | null>(null)

  useEffect(() => () => {
    diffAbortRef.current?.abort()
  }, [])

  const narrativa: DiffCV | null = diff ? diff.narrativa : null
  const canRun = !!arquivoAnterior && !!arquivoNovo && !loading

  const runDiff = async () => {
    if (!arquivoAnterior || !arquivoNovo) return
    diffAbortRef.current?.abort()
    const controller = new AbortController()
    diffAbortRef.current = controller
    setLoading(true)
    setError(null)
    setDiff(null)
    const formData = new FormData()
    formData.append('cv_file_anterior', arquivoAnterior)
    formData.append('cv_file_novo', arquivoNovo)
    if (area.trim()) formData.set('area', area.trim())
    const provider = getBestProvider(['curriculo'])
    if (provider) {
      formData.set('api_key', provider.apiKey)
      formData.set('api_url', provider.apiUrl)
      formData.set('model_name', provider.modelName)
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/diff`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(
          errData?.detail || `Erro HTTP ${response.status}: falha na comparação de versões.`
        )
      }
      const data: CVDiffResult = await response.json()
      setDiff(data)
    } catch (err) {
      if (isAbortError(err)) return
      if (diffAbortRef.current === controller) {
        setError(friendlyError(err, 'Falha ao comparar as versões do currículo.'))
      }
    } finally {
      if (diffAbortRef.current === controller) setLoading(false)
    }
  }

  return (
    <Card className="p-6 md:p-8">
      <SectionHead
        icon={<GitCompare className="w-5 h-5 text-indigo-300" />}
        tone="indigo"
        title="Comparar Versões"
        subtitle="Envie duas versões do seu CV e veja o que melhorou, o que piorou e qual a próxima melhoria."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <p className="text-sm font-medium text-slate-200 mb-2">Versão anterior</p>
          <Dropzone accept=".pdf,.docx,.doc,.txt" onFileSelect={(f) => setArquivoAnterior(f || null)} />
        </div>
        <div>
          <p className="text-sm font-medium text-slate-200 mb-2">Versão nova</p>
          <Dropzone accept=".pdf,.docx,.doc,.txt" onFileSelect={(f) => setArquivoNovo(f || null)} />
        </div>
      </div>

      <GhostBtn tone="indigo" onClick={runDiff} disabled={!canRun} className="mt-4">
        <Play className="w-3.5 h-3.5" />
        Comparar versões
      </GhostBtn>
      {!arquivoAnterior && !arquivoNovo && !loading && (
        <p className="text-xs text-slate-400 mt-2">PDF, DOCX, DOC ou TXT — até 10MB por arquivo.</p>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-300 mt-4">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-300" />
          Comparando as duas versões (IA)...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-400/30 p-4 mt-4">
          <p className="text-sm text-rose-200 leading-relaxed">{error}</p>
          {arquivoAnterior && arquivoNovo && (
            <GhostBtn tone="rose" onClick={runDiff} className="mt-2">
              <RefreshCw className="w-3.5 h-3.5" />
              Tentar novamente
            </GhostBtn>
          )}
        </div>
      )}

      {!loading && !error && diff && narrativa && (
        <div className="space-y-5 mt-4">
          {narrativa.resumo && (
            <p className="text-sm text-slate-200 leading-relaxed">{narrativa.resumo}</p>
          )}

          <SinaisObjetivos det={diff.deterministico} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-xl bg-emerald-500/10 border border-emerald-400/20 p-4">
              <p className="text-xs font-bold text-emerald-300 uppercase tracking-wider mb-3">
                Melhorou ({narrativa.melhorias.length})
              </p>
              {renderDiffItems(narrativa.melhorias, 'melhora')}
            </div>
            <div className="rounded-xl bg-rose-500/10 border border-rose-400/20 p-4">
              <p className="text-xs font-bold text-rose-300 uppercase tracking-wider mb-3">
                Piorou ({narrativa.piorou.length})
              </p>
              {renderDiffItems(narrativa.piorou, 'piorou')}
            </div>
          </div>

          {narrativa.recomendacao_proxima && (
            <div className="rounded-xl bg-indigo-500/10 border border-indigo-400/20 p-4">
              <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-1">
                Próxima melhoria
              </p>
              <p className="text-sm text-slate-200 leading-relaxed">
                {narrativa.recomendacao_proxima}
              </p>
            </div>
          )}

          <GhostBtn onClick={runDiff}>
            <RotateCcw className="w-3.5 h-3.5" />
            Rodar novamente
          </GhostBtn>
        </div>
      )}
    </Card>
  )
}

/* ═══════════ Step 1 — upload + configuração ═══════════
   Form do passo de envio: só estado local é a expansão do
   textarea (showJobDesc); os dados sobem via props para o main,
   que precisa de jobTitle/jobLevel para o gating do Step 2. */
export function StepOneForm({
  selectedFile,
  onFileSelect,
  area,
  onArea,
  jobTitle,
  onJobTitle,
  jobLevel,
  onJobLevel,
  loading,
  error,
  onAnalyze,
}: {
  selectedFile: File | null
  onFileSelect: (file: File) => void
  area: string
  onArea: (value: string) => void
  jobTitle: string
  onJobTitle: (value: string) => void
  jobLevel: string
  onJobLevel: (value: string) => void
  loading: boolean
  error: string | null
  onAnalyze: () => void
}) {
  const [showJobDesc, setShowJobDesc] = useState(false)

  return (
    <>
      {/* Upload */}
      <Card className="p-6 md:p-8">
        <SectionHead
          icon={<Upload className="w-5 h-5 text-indigo-300" />}
          tone="indigo"
          title="Upload do Currículo"
          subtitle="PDF, DOCX ou DOC — até 10MB"
        />
        <Dropzone onFileSelect={onFileSelect} accept=".pdf,.docx,.doc" />
        <AnimatePresence>
          {selectedFile && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mt-3 flex items-center gap-2.5 p-3 rounded-xl bg-emerald-500/10 border border-emerald-400/30">
                <CheckCircle2 className="w-5 h-5 text-emerald-300 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-emerald-100 truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-emerald-200/80 mt-0.5">
                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · pronto para análise
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>

      {/* Config */}
      <Card className="p-6 md:p-8">
        <SectionHead
          icon={<Target className="w-5 h-5 text-indigo-300" />}
          tone="indigo"
          title="Configuração da Análise"
          subtitle="Personalize o diagnóstico para o seu objetivo"
        />
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-200 mb-2">
              Sua Área de Atuação <span className="text-rose-400">*</span>
            </label>
            <Input
              value={area}
              onChange={(e) => onArea(e.target.value)}
              placeholder="Ex: Administrativo, Tecnologia, Vendas..."
            />
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowJobDesc((v) => !v)}
              className="flex items-center justify-between w-full text-sm font-medium text-slate-200 hover:text-white transition-colors"
            >
              <span className="flex items-center gap-1.5">
                Descrição da vaga
                <span className="text-slate-500 font-normal">(opcional)</span>
              </span>
              <ChevronDown
                className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${
                  showJobDesc ? 'rotate-180' : ''
                }`}
              />
            </button>
            <AnimatePresence initial={false}>
              {showJobDesc && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: EASE }}
                  className="overflow-hidden"
                >
                  <textarea
                    value={jobTitle}
                    onChange={(e) => onJobTitle(e.target.value)}
                    placeholder="Cole a descrição completa da vaga (com a seção de requisitos) — com isso calculamos o Fit do seu CV com a vaga."
                    className="w-full mt-2 h-32 px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-base text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-indigo-400 focus:ring-4 focus:ring-indigo-500/25 resize-none leading-relaxed"
                  />
                  <p className="text-xs text-slate-400 mt-1.5">
                    {jobTitle.trim().length >= 40
                      ? `✓ Descrição completa (${jobTitle.trim().length} chars) — Fit será calculado`
                      : `Cole ao menos 40 caracteres (${jobTitle.trim().length}/40)`}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-200 mb-2">
              Nível desejado
            </label>
            <CustomSelect
              value={jobLevel}
              onChange={onJobLevel}
              options={[
                { value: 'Sem nível específico', label: 'Sem nível específico' },
                { value: 'Estágio', label: 'Estágio' },
                { value: 'Júnior', label: 'Júnior' },
                { value: 'Pleno', label: 'Pleno' },
                { value: 'Sênior', label: 'Sênior' },
                { value: 'Lead', label: 'Lead' },
                { value: 'Manager', label: 'Manager' },
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Analyze */}
      <PrimaryBtn
        onClick={onAnalyze}
        disabled={loading || !selectedFile || !area}
        loading={loading}
        className="w-full"
      >
        {loading ? (
          'Analisando currículo...'
        ) : (
          <>
            <Sparkles className="w-4 h-4" />
            Analisar Currículo
          </>
        )}
      </PrimaryBtn>

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
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}