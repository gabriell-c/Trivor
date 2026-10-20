'use client'
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { Send, RefreshCw, ExternalLink, Search, Inbox } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'
import { friendlyError } from '../lib/errors'

// Mesca a resposta de erro do backend (detail em PT-BR) antes de usar o fallback genérico
async function applyFetch(path: string): Promise<any> {
  const r = await fetch(`${API_BASE_URL}${path}`)
  if (!r.ok) {
    let detail = ''
    try { detail = (await r.json()).detail || '' } catch { /* resposta não-JSON */ }
    throw new Error(detail || friendlyError(new Error(`HTTP ${r.status}`), 'Falha ao falar com o backend.'))
  }
  return r.json()
}

/* ═══ Contratos do backend (/api/apply/*) ═══ */
interface ApplyOverview {
  available: boolean
  path?: string | null
  hint?: string
  total: number
  por_bucket: { sucesso: number; parcial: number; skip: number; falha: number }
  por_site: Record<string, number>
  periodo: { primeiro: string | null; ultimo: string | null }
}

interface ApplyRecord {
  vaga: string
  link?: string
  local?: string
  site?: string
  status: string
  status_bucket: 'sucesso' | 'parcial' | 'skip' | 'falha'
  data?: string
  horario?: string
  curriculo?: string
}

interface ApplyPage {
  items: ApplyRecord[]
  total: number
  limit: number
  offset: number
}

/* ═══ Aparência dos status ═══ */
const BUCKET_META: Record<ApplyRecord['status_bucket'], { label: string; cls: string }> = {
  sucesso: { label: 'Enviado', cls: 'bg-emerald-500/15 border-emerald-400/30 text-emerald-300' },
  parcial: { label: 'Sem confirmação', cls: 'bg-amber-500/15 border-amber-400/30 text-amber-300' },
  skip: { label: 'Já aplicado', cls: 'bg-slate-500/15 border-slate-400/30 text-slate-300' },
  falha: { label: 'Falhou', cls: 'bg-rose-500/15 border-rose-400/30 text-rose-300' },
}

// O apply embute texto de erro no status ("erro: Page.goto: ...") — mostra curto, completo no tooltip
function statusLabel(status: string): string {
  if (status.startsWith('erro:')) return 'Erro de navegação'
  if (status.length > 40) return status.slice(0, 40) + '…'
  return status
}

/* ═══ Widgets ═══ */
function StatCard({ label, value, tone = 'slate', glow }: { label: string; value: string; tone?: 'slate' | 'green' | 'amber' | 'red' | 'blue'; glow?: boolean }) {
  const tones = {
    slate: 'text-slate-200',
    green: 'text-emerald-300',
    amber: 'text-amber-300',
    red: 'text-rose-300',
    blue: 'text-indigo-300',
  }
  const glows = {
    slate: '',
    green: 'shadow-[0_0_24px_-8px_rgba(16,185,129,0.45)]',
    amber: 'shadow-[0_0_24px_-8px_rgba(245,158,11,0.45)]',
    red: 'shadow-[0_0_24px_-8px_rgba(244,63,94,0.45)]',
    blue: 'shadow-[0_0_24px_-8px_rgba(99,102,241,0.45)]',
  }
  return (
    <div className={`rounded-2xl border border-slate-800/70 bg-slate-900/60 p-4 ${glow ? glows[tone] : ''}`}>
      <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">{label}</div>
      <div className={`mt-1.5 text-2xl font-bold ${tones[tone]}`}>{value}</div>
    </div>
  )
}

export default function CandidaturasPage() {
  const [overview, setOverview] = useState<ApplyOverview | null>(null)
  const [page, setPage] = useState<ApplyPage | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [site, setSite] = useState('')
  const [bucket, setBucket] = useState('')
  const [q, setQ] = useState('')
  const [qDebounced, setQDebounced] = useState('')
  const [limit, setLimit] = useState(30)
  const [reloadKey, setReloadKey] = useState(0)
  const reduce = useReducedMotion()

  // debounce simples da busca (mesmo padrão dos demais painéis, 300ms)
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 300)
    return () => clearTimeout(t)
  }, [q])

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const [ov, list] = await Promise.all([
        applyFetch('/api/apply/overview'),
        applyFetch(
          `/api/apply/applications?limit=${limit}&site=${encodeURIComponent(site)}&bucket=${encodeURIComponent(bucket)}&q=${encodeURIComponent(qDebounced)}`
        ),
      ])
      setOverview(ov as ApplyOverview)
      if (ov.available) {
        setPage(list as ApplyPage)
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Falha ao carregar')
    } finally {
      setLoading(false)
    }
  }, [limit, site, bucket, qDebounced, reloadKey])

  useEffect(() => { load() }, [load])

  const loadMore = () => setLimit(l => l + 30)

  /* ── estados especiais ── */
  if (err && !overview) {
    return (
      <div className="w-full max-w-4xl">
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-200 flex items-start gap-3">
          <Inbox className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Não foi possível carregar as candidaturas</div>
            <div className="text-sm mt-1 text-rose-300/90">{err}</div>
            <button onClick={() => setReloadKey(k => k + 1)}
              className="mt-3 flex items-center gap-2 text-xs font-medium text-rose-200 hover:text-white transition-colors">
              <RefreshCw className="w-3.5 h-3.5" /> Tentar de novo
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (overview && !overview.available) {
    return (
      <div className="w-full max-w-4xl">
        <PageHeader onRefresh={() => setReloadKey(k => k + 1)} loading={loading} />
        <div className="mt-5 rounded-2xl border border-slate-800/70 bg-slate-900/60 p-8 text-center">
          <Inbox className="w-8 h-8 text-slate-500 mx-auto" />
          <div className="mt-3 font-semibold text-slate-200">Projeto apply não encontrado</div>
          <div className="mt-1.5 text-sm text-slate-400 max-w-md mx-auto">{overview.hint}</div>
        </div>
      </div>
    )
  }

  const ov = overview!
  const pg = page!
  const sites = ov.por_site ? Object.keys(ov.por_site) : []

  return (
    <div className="w-full max-w-4xl space-y-5">
      <PageHeader onRefresh={() => setReloadKey(k => k + 1)} loading={loading} />

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Candidaturas" value={String(ov.total)} tone="blue" glow />
        <StatCard label="Enviadas" value={String(ov.por_bucket.sucesso)} tone="green" glow />
        <StatCard label="Sem confirmação" value={String(ov.por_bucket.parcial)} tone="amber" />
        <StatCard label="Falhas" value={String(ov.por_bucket.falha)} tone="red" />
      </div>

      {/* Portais + período */}
      <div className="rounded-2xl border border-slate-800/70 bg-slate-900/60 p-4 flex flex-wrap items-center gap-2">
        {sites.map(s => (
          <button key={s} onClick={() => setSite(site === s ? '' : s)}
            className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${site === s
              ? 'bg-indigo-500/20 border-indigo-400/40 text-indigo-200'
              : 'border-slate-700/70 text-slate-300 hover:border-slate-500'}`}>
            {s} · {ov.por_site[s]}
          </button>
        ))}
        {(ov.periodo.primeiro || ov.periodo.ultimo) && (
          <span className="ml-auto text-[11px] text-slate-500">
            {ov.periodo.primeiro && `desde ${ov.periodo.primeiro}`}
            {ov.periodo.primeiro && ov.periodo.ultimo && ' — '}
            {ov.periodo.ultimo && `até ${ov.periodo.ultimo}`}
          </span>
        )}
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-2.5">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar por nome da vaga…"
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900/70 border border-slate-800 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500/50 transition-colors" />
        </div>
        <select value={bucket} onChange={e => setBucket(e.target.value)}
          className="px-3 py-2.5 rounded-xl bg-slate-900/70 border border-slate-800 text-sm text-slate-300 focus:outline-none focus:border-indigo-500/50">
          <option value="">Todos os status</option>
          <option value="sucesso">Enviadas</option>
          <option value="parcial">Sem confirmação</option>
          <option value="skip">Já aplicadas</option>
          <option value="falha">Falhas</option>
        </select>
      </div>

      {/* Tabela */}
      {pg.items.length === 0 ? (
        <div className="rounded-2xl border border-slate-800/70 bg-slate-900/60 p-8 text-center text-sm text-slate-400">
          Nenhuma candidatura com esses filtros.
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-800/70 bg-slate-900/60 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-800/70">
                <th className="px-4 py-3 font-medium">Data</th>
                <th className="px-4 py-3 font-medium">Portal</th>
                <th className="px-4 py-3 font-medium">Vaga</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence initial={!reduce}>
                {pg.items.map((r, i) => {
                  const meta = BUCKET_META[r.status_bucket] || BUCKET_META.falha
                  return (
                    <motion.tr key={`${r.link || r.vaga}-${i}`}
                      initial={reduce ? false : { opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.15, delay: Math.min(i, 8) * 0.02 }}
                      className="border-b border-slate-800/40 last:border-0 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                        {r.data || '—'}{r.horario && <span className="ml-1.5 text-[11px] text-slate-600">{r.horario}</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{r.site || '—'}</td>
                      <td className="px-4 py-3 min-w-[180px]">
                        {r.link ? (
                          <a href={r.link} target="_blank" rel="noopener noreferrer"
                            className="text-slate-200 font-medium hover:text-indigo-300 transition-colors inline-flex items-center gap-1.5 max-w-[320px]">
                            <span className="truncate">{r.vaga}</span>
                            <ExternalLink className="w-3 h-3 flex-shrink-0 text-slate-500" />
                          </a>
                        ) : (
                          <span className="text-slate-200 font-medium">{r.vaga}</span>
                        )}
                        {r.local && <div className="text-[11px] text-slate-500 mt-0.5">{r.local}</div>}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span title={r.status}
                          className={`inline-block text-[11px] font-semibold px-2.5 py-1 rounded-full border ${meta.cls}`}>
                          {statusLabel(r.status)}
                        </span>
                      </td>
                    </motion.tr>
                  )
                })}
              </AnimatePresence>
            </tbody>
          </table>
          {limit < pg.total && (
            <div className="p-3 border-t border-slate-800/40 text-center">
              <button onClick={loadMore}
                className="text-xs font-medium text-indigo-300 hover:text-indigo-200 transition-colors">
                Mostrar mais (restam {pg.total - limit})
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PageHeader({ onRefresh, loading }: { onRefresh: () => void; loading: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
          <Send className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Candidaturas</h1>
          <p className="text-xs text-slate-400">Histórico dos bots de envio automático (Job Hunter)</p>
        </div>
      </div>
      <button onClick={onRefresh} disabled={loading}
        className="flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-white transition-colors disabled:opacity-50">
        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Atualizar
      </button>
    </div>
  )
}
