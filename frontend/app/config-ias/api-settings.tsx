'use client'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import {
  Plus, Trash2, CheckCircle2, XCircle, Loader2, Eye, EyeOff,
  AlertCircle, AlertTriangle, RefreshCw, Pencil, X, Check, Copy, ChevronDown,
  ExternalLink, Bot, Zap, Globe, Save, Server, KeyRound, Link2,
  Sparkles, Briefcase,
} from 'lucide-react'
import { useIaProviders, IAProvider } from '../hooks/useIaProviders'
import { API_BASE_URL } from '../lib/api'

const EASE = [0.16, 1, 0.3, 1] as const

// SLA do teste de conexão: ping abaixo de 3s = "Conectado" (verde);
// acima disso o provedor responde, mas a pílula vira "Lento" (âmbar).
const SLOW_THRESHOLD_MS = 3000

// Resposta do endpoint de teste de conexão (/api/test-connection)
interface TestConnData {
  latency_ms?: number
  message?: string
  detail?: string
}

/* ═══════════ Theme — cores sólidas, sem gradiente ═══════════ */
const PROVIDER_THEME = {
  openai: {
    name: 'OpenAI',
    Icon: Bot,
    iconWrap: 'bg-emerald-500/15 border-emerald-400/30',
    iconColor: 'text-emerald-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(16,185,129,0.45)]',
    defaultUrl: 'https://api.openai.com/v1',
    defaultModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
  },
  anthropic: {
    name: 'Anthropic',
    Icon: Zap,
    iconWrap: 'bg-orange-500/15 border-orange-400/30',
    iconColor: 'text-orange-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(249,115,22,0.45)]',
    defaultUrl: 'https://api.anthropic.com/v1',
    defaultModels: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'],
  },
  custom: {
    name: 'Personalizada',
    Icon: Globe,
    iconWrap: 'bg-purple-500/15 border-purple-400/30',
    iconColor: 'text-purple-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(168,85,247,0.45)]',
    defaultUrl: '',
    defaultModels: ['gpt-4o', 'gpt-4', 'claude-3', 'llama-3'],
  },
} as const
type ProviderType = keyof typeof PROVIDER_THEME

const USED_FOR = [
  { value: 'all', label: 'Todas' },
  { value: 'curriculo', label: 'Currículo' },
  { value: 'market', label: 'Mercado' },
  { value: 'none', label: 'Desativada' },
] as const

interface JsearchKeyRecord {
  id: number
  key_prefix: string
  description: string | null
  rate_limit_total: number | null
  rate_limit_remaining: number | null
  used: number | null
  status: string
  last_error?: string | null
  last_tested: string | null
}

interface ToastItem {
  id: number
  kind: 'success' | 'error' | 'info' | 'warning'
  message: string
}

/* ═══════════ Labels ═══════════ */
const labelCls = 'block text-sm font-medium text-slate-200 mb-2'

/* ═══════════ Input custom — grande, alto contraste ═══════════ */
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean
}

function Input({ className = '', mono, ...props }: InputProps) {
  return (
    <input
      {...props}
      className={`w-full h-12 px-4 rounded-xl bg-slate-900 border border-slate-700 text-base font-medium text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-purple-400 focus:ring-4 focus:ring-purple-500/25 focus:bg-slate-900 ${
        mono ? 'font-mono text-sm tracking-tight' : ''
      } ${className}`}
    />
  )
}

/* ═══════════ Select custom — portal, z-index alto, legível ═══════════ */
interface SelectOption {
  value: string
  label: string
}

function Select({
  value,
  onChange,
  options,
  placeholder = 'Selecionar',
  className = '',
  disabled,
  size = 'md',
}: {
  value: string
  onChange: (v: string) => void
  options: readonly SelectOption[]
  placeholder?: string
  className?: string
  disabled?: boolean
  size?: 'sm' | 'md'
}) {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)
  const ddRef = useRef<HTMLDivElement>(null)

  // mounted: evita divergência de hidratação SSR (posição do dropdown só existe no cliente)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), [])

  const recalc = useCallback(() => {
    if (!btnRef.current) return
    const r = btnRef.current.getBoundingClientRect()
    setPos({ top: r.bottom + 6, left: r.left, width: r.width })
  }, [])

  useEffect(() => {
    if (!open) return
    recalc()
    const onScroll = () => recalc()
    const onResize = () => recalc()
    const onPointer = (e: MouseEvent) => {
      if (btnRef.current?.contains(e.target as Node)) return
      if (ddRef.current?.contains(e.target as Node)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onResize)
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, recalc])

  const selected = options.find((o) => o.value === value)
  const sizeCls =
    size === 'sm'
      ? 'h-10 px-3 text-sm font-medium'
      : 'h-12 px-4 text-base font-medium'

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`inline-flex items-center justify-between gap-2 rounded-xl bg-slate-900 border border-slate-700 text-white outline-none transition-all duration-200 hover:border-slate-600 focus:border-purple-400 focus:ring-4 focus:ring-purple-500/25 disabled:opacity-50 disabled:cursor-not-allowed ${
          open ? 'border-purple-400 ring-4 ring-purple-500/25' : ''
        } ${sizeCls} ${className}`}
      >
        <span className={`truncate text-left ${selected ? 'text-white' : 'text-slate-500'}`}>
          {selected?.label ?? placeholder}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 shrink-0 transition-transform duration-200 ${
            open ? 'rotate-180 text-purple-300' : ''
          }`}
        />
      </button>

      {mounted &&
        createPortal(
          <AnimatePresence>
            {open && (
              <motion.div
                ref={ddRef}
                role="listbox"
                initial={{ opacity: 0, y: -6, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.97, transition: { duration: 0.12 } }}
                transition={{ duration: 0.16, ease: EASE }}
                style={{
                  position: 'fixed',
                  top: pos.top,
                  left: pos.left,
                  width: Math.max(pos.width, 180),
                  zIndex: 9999,
                }}
                className="rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl shadow-black/70 max-h-64 overflow-y-auto ring-1 ring-black/40"
              >
                {options.map((o) => {
                  const active = o.value === value
                  return (
                    <button
                      key={o.value}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => {
                        onChange(o.value)
                        setOpen(false)
                      }}
                      className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-sm font-medium text-left transition-colors duration-150 ${
                        active
                          ? 'bg-purple-500/20 text-purple-200'
                          : 'text-slate-200 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      <span className="truncate">{o.label}</span>
                      {active && <Check className="w-4 h-4 shrink-0" strokeWidth={2.5} />}
                    </button>
                  )
                })}
              </motion.div>
            )}
          </AnimatePresence>,
          document.body
        )}
    </>
  )
}

/* ═══════════ Animated number ═══════════ */
function AnimatedNumber({ value, duration = 500 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(value)
  const ref = useRef(value)
  const reduce = useReducedMotion()

  // Movimento reduzido: sem animação — sincroniza o display direto no render (estado derivado)
  const [prevVal, setPrevVal] = useState(value)
  if (reduce && prevVal !== value) {
    setPrevVal(value)
    setDisplay(value)
  }

  useEffect(() => {
    if (reduce) return
    const from = ref.current
    if (from === value) return
    let start: number | null = null
    let raf = 0
    const step = (t: number) => {
      if (start === null) start = t
      const p = Math.min((t - start) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = Math.round(from + (value - from) * eased)
      ref.current = v
      setDisplay(v)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value, duration, reduce])
  return <>{display.toLocaleString('pt-BR')}</>
}

/* ═══════════ Toast ═══════════ */
function ToastStack({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: number) => void }) {
  return (
    <div className="fixed top-4 right-4 z-[70] flex flex-col gap-2.5 pointer-events-none">
      <AnimatePresence>
        {toasts.map((t) => {
          const tone =
            t.kind === 'success'
              ? {
                  bar: 'bg-emerald-500',
                  Icon: CheckCircle2,
                  icon: 'text-emerald-300',
                  glow: 'shadow-[0_0_24px_-6px_rgba(16,185,129,0.5)]',
                }
              : t.kind === 'error'
              ? {
                  bar: 'bg-rose-500',
                  Icon: XCircle,
                  icon: 'text-rose-300',
                  glow: 'shadow-[0_0_24px_-6px_rgba(244,63,94,0.5)]',
                }
              : t.kind === 'warning'
              ? {
                  bar: 'bg-amber-500',
                  Icon: AlertTriangle,
                  icon: 'text-amber-300',
                  glow: 'shadow-[0_0_24px_-6px_rgba(245,158,11,0.5)]',
                }
              : {
                  bar: 'bg-blue-500',
                  Icon: AlertCircle,
                  icon: 'text-blue-300',
                  glow: 'shadow-[0_0_24px_-6px_rgba(59,130,246,0.5)]',
                }
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 320, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 320, scale: 0.95, transition: { duration: 0.2 } }}
              transition={{ type: 'spring', damping: 26, stiffness: 320 }}
              className={`pointer-events-auto relative overflow-hidden bg-slate-900 border border-slate-700 rounded-xl min-w-[300px] max-w-md ${tone.glow}`}
            >
              <div className={`absolute left-0 top-0 bottom-0 w-1 ${tone.bar}`} />
              <div className="flex items-center gap-3 pl-4 pr-2 py-3.5">
                <tone.Icon className={`w-5 h-5 ${tone.icon} shrink-0`} />
                <span className="text-base font-medium text-white flex-1">{t.message}</span>
                <button
                  onClick={() => onDismiss(t.id)}
                  className="text-slate-400 hover:text-white transition-colors p-1.5 rounded-md hover:bg-slate-800"
                  aria-label="Fechar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}

/* ═══════════ Status pill ═══════════ */
function fmtLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1).replace('.', ',')}s` : `${ms}ms`
}

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusPill({
  status,
  testing,
  message,
  latencyMs,
}: {
  status?: 'connected' | 'slow' | 'error' | 'unknown' | 'testing'
  testing?: boolean
  message?: string
  latencyMs?: number
}) {
  if (testing) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-blue-500/15 border border-blue-400/30 text-blue-200">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Testando
      </span>
    )
  }
  if (status === 'connected') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-400/30 text-emerald-200 shadow-[0_0_16px_-4px_rgba(16,185,129,0.4)]"
        title={message}
      >
        <span className="relative flex h-2 w-2">
          <motion.span
            animate={{ scale: [1, 2.4, 1], opacity: [0.6, 0, 0.6] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            className="absolute inset-0 rounded-full bg-emerald-400"
          />
          <span className="relative w-2 h-2 rounded-full bg-emerald-400" />
        </span>
        Conectado{latencyMs != null ? ` · ${fmtLatency(latencyMs)}` : ''}
      </span>
    )
  }
  if (status === 'slow') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-amber-500/15 border border-amber-400/40 text-amber-200"
        title={message}
      >
        <AlertTriangle className="w-3.5 h-3.5" />
        Lento{latencyMs != null ? ` · ${fmtLatency(latencyMs)}` : ''}
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-rose-500/15 border border-rose-400/30 text-rose-200"
        title={message}
      >
        <XCircle className="w-3.5 h-3.5" />
        Erro
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-300">
      <span className="w-2 h-2 rounded-full bg-slate-500" />
      Não testado
    </span>
  )
}

/* ═══════════ Copyable code ═══════════ */
function CopyableCode({ value, display }: { value: string; display?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    })
  }
  return (
    <button
      onClick={copy}
      className="group/code inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 hover:border-purple-400/50 hover:bg-slate-750 hover:bg-slate-800 max-w-full transition-all"
      title={value}
    >
      <code className="font-mono text-sm font-medium text-slate-200 truncate">
        {display ?? value}
      </code>
      <span className="text-slate-400 group-hover/code:text-purple-300 transition-colors shrink-0">
        <AnimatePresence mode="wait" initial={false}>
          {copied ? (
            <motion.span
              key="check"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={{ duration: 0.14 }}
              className="text-emerald-400 block"
            >
              <Check className="w-4 h-4" />
            </motion.span>
          ) : (
            <motion.span
              key="copy"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={{ duration: 0.14 }}
              className="block"
            >
              <Copy className="w-4 h-4" />
            </motion.span>
          )}
        </AnimatePresence>
      </span>
    </button>
  )
}

/* ═══════════ Quota ring ═══════════ */
function QuotaRing({ pct, used, total }: { pct: number; used: number; total: number }) {
  const tone =
    pct >= 90
      ? {
          stroke: 'stroke-rose-500',
          text: 'text-rose-200',
          bg: 'bg-rose-500/15',
          border: 'border-rose-400/30',
        }
      : pct >= 70
      ? {
          stroke: 'stroke-amber-500',
          text: 'text-amber-200',
          bg: 'bg-amber-500/15',
          border: 'border-amber-400/30',
        }
      : {
          stroke: 'stroke-emerald-500',
          text: 'text-emerald-200',
          bg: 'bg-emerald-500/15',
          border: 'border-emerald-400/30',
        }
  return (
    <div className="flex items-center gap-3">
      <div className={`relative w-12 h-12 shrink-0 rounded-full ${tone.bg} border ${tone.border} p-1`}>
        <svg viewBox="0 0 44 44" className="w-full h-full -rotate-90">
          <circle cx="22" cy="22" r="18" fill="none" strokeWidth="3" className="stroke-slate-700" />
          <motion.circle
            cx="22"
            cy="22"
            r="18"
            fill="none"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="113.1 113.1"
            initial={{ strokeDashoffset: 113.1 }}
            animate={{ strokeDashoffset: 113.1 - (pct / 100) * 113.1 }}
            transition={{ duration: 0.8, ease: EASE }}
            className={tone.stroke}
          />
        </svg>
        <span
          className={`absolute inset-0 flex items-center justify-center text-xs font-bold tabular-nums ${tone.text}`}
        >
          {pct}%
        </span>
      </div>
      <div className="text-sm tabular-nums">
        <span className="font-bold text-white text-base">
          <AnimatedNumber value={used} />
        </span>
        <span className="text-slate-400"> / {total}</span>
      </div>
    </div>
  )
}

/* ═══════════ Kbd ═══════════ */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[26px] h-6 px-2 rounded-md border border-slate-700 bg-slate-800 text-slate-200 text-xs font-semibold font-mono shadow-[0_1px_0_rgba(0,0,0,0.4),inset_0_-1px_0_rgba(0,0,0,0.3)]">
      {children}
    </kbd>
  )
}

/* ═══════════ Stat card ═══════════ */
function StatCard({
  icon,
  tone,
  label,
  value,
  delay = 0,
}: {
  icon: React.ReactNode
  tone: string
  label: string
  value: number
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: EASE }}
      whileHover={{ y: -3 }}
      className="group flex items-center gap-4 rounded-xl border border-slate-700 bg-slate-900 p-4 hover:border-slate-600 transition-colors"
    >
      <div
        className={`w-12 h-12 rounded-xl border flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110 ${tone}`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-white leading-tight tabular-nums">
          <AnimatedNumber value={value} />
        </div>
        <div className="text-sm font-medium text-slate-300 mt-0.5 truncate">{label}</div>
      </div>
    </motion.div>
  )
}

/* ═══════════ Page ═══════════ */
export default function ApiSettingsPage() {
  const { providers, add, remove, update, updateUsedFor, updateStatus } = useIaProviders()

  /* toasts */
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const pushToast = useCallback((kind: ToastItem['kind'], message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000)
  }, [])
  const dismissToast = (id: number) => setToasts((t) => t.filter((x) => x.id !== id))

  /* provider form */
  const [showAdd, setShowAdd] = useState(false)
  const [newProv, setNewProv] = useState({
    name: '',
    providerType: 'openai' as ProviderType,
    apiKey: '',
    apiUrl: PROVIDER_THEME.openai.defaultUrl as string,
    modelName: PROVIDER_THEME.openai.defaultModels[0] as string,
    usedFor: 'all' as IAProvider['usedFor'],
  })
  const [urlErr, setUrlErr] = useState('')

  /* expand/test */
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editData, setEditData] = useState<Partial<IAProvider>>({})
  const [testingId, setTestingId] = useState<string | null>(null)

  /* confirm */
  const [confirm, setConfirm] = useState<
    | { kind: 'provider'; id: string; label: string }
    | { kind: 'jsearch'; record: JsearchKeyRecord; label: string }
    | null
  >(null)

  /* jsearch */
  const [keys, setKeys] = useState<JsearchKeyRecord[]>([])
  const [newKey, setNewKey] = useState('')
  const [revealKey, setRevealKey] = useState(false)
  const [testFeedback, setTestFeedback] = useState<
    Record<string, { ok: boolean; message: string; total: number; remaining: number | null }>
  >({})
  const [testingNew, setTestingNew] = useState(false)
  const [editingKeyId, setEditingKeyId] = useState<number | null>(null)
  const [editDesc, setEditDesc] = useState('')
  const [keysLoading, setKeysLoading] = useState(true)

  const meta = PROVIDER_THEME[newProv.providerType]
  const connectedCount = providers.filter((p) => p.status === 'connected' || p.status === 'slow').length
  const jsearchQuota = keys.length * 200

  /* ──────── handlers ──────── */
  const resetNew = useCallback(
    (type?: ProviderType) => {
      const t = type ?? newProv.providerType
      const cfg = PROVIDER_THEME[t]
      setNewProv({
        name: '',
        providerType: t,
        apiKey: '',
        apiUrl: cfg.defaultUrl,
        modelName: cfg.defaultModels[0],
        usedFor: 'all',
      })
      setUrlErr('')
    },
    [newProv.providerType]
  )

  const addProvider = () => {
    if (!newProv.apiKey.trim()) return pushToast('error', 'Informe a chave de API')
    if (newProv.providerType === 'custom') {
      if (!newProv.apiUrl.trim()) {
        setUrlErr('URL é obrigatória')
        return
      }
      try {
        new URL(newProv.apiUrl)
      } catch {
        setUrlErr('URL inválida')
        return
      }
      if (!newProv.modelName.trim()) return pushToast('error', 'Informe o modelo')
    }
    add({
      name: newProv.name || PROVIDER_THEME[newProv.providerType].name,
      provider: newProv.providerType,
      apiKey: newProv.apiKey,
      apiUrl: newProv.apiUrl,
      modelName: newProv.modelName,
      usedFor: newProv.usedFor,
    })
    setShowAdd(false)
    resetNew()
    pushToast('success', 'Provedor adicionado')
  }

  const testProvider = async (p: IAProvider) => {
    setTestingId(p.id)
    const body = new FormData()
    body.set('api_key', p.apiKey)
    body.set('api_url', p.apiUrl)
    body.set('model_name', p.modelName)
    try {
      const res = await fetch(`${API_BASE_URL}/api/test-connection`, { method: 'POST', body })
      const data = await res.json().catch((): TestConnData => ({}))
      if (res.ok) {
        const latency = data.latency_ms
        const slow = latency != null && latency >= SLOW_THRESHOLD_MS
        const detail = data.message || 'Conexão OK'
        updateStatus(p.id, slow ? 'slow' : 'connected', detail, latency)
        if (slow) {
          pushToast('warning', `Respondeu, mas demorou: ${detail} em ${fmtLatency(latency)}`)
        } else {
          pushToast('success', latency != null ? `${detail} em ${fmtLatency(latency)}` : detail)
        }
      } else {
        updateStatus(p.id, 'error', data.detail || 'Erro na conexão')
        pushToast('error', data.detail || 'Erro na conexão')
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : ''
      updateStatus(p.id, 'error', msg || 'Erro na conexão')
      pushToast('error', msg || 'Falha ao contatar o backend')
    } finally {
      setTestingId(null)
    }
  }

  const openEdit = (p: IAProvider) => {
    if (expandedId === p.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(p.id)
    setEditData({ name: p.name, apiKey: p.apiKey, apiUrl: p.apiUrl, modelName: p.modelName, usedFor: p.usedFor })
  }

  const saveEdit = () => {
    if (!expandedId) return
    // Config mudou → resultado do último teste ficou inválido: volta a "não testado".
    update(expandedId, { ...editData, status: 'unknown', statusMessage: '', lastLatencyMs: undefined, lastTestedAt: undefined })
    setExpandedId(null)
    setEditData({})
    pushToast('success', 'Alterações salvas')
  }

  /* ──────── jsearch ──────── */
  const loadKeys = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/keys`)
      const data = await res.json()
      setKeys(data.keys ?? [])
    } catch {
      setKeys([])
    } finally {
      setKeysLoading(false)
    }
  }, [])

  // fetch de dados na montagem: setKeys/setKeysLoading só rodam após o await
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadKeys()
  }, [loadKeys])

  const addKey = async () => {
    const k = newKey.trim()
    if (!k) return
    const form = new FormData()
    form.set('api_key', k)
    form.set('description', '')
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/save-key`, { method: 'POST', body: form })
      const data = await res.json()
      if (data.success) {
        setNewKey('')
        setRevealKey(false)
        await loadKeys()
        pushToast('success', 'Chave salva')
      } else pushToast('error', data.detail || 'Falha ao salvar')
    } catch {
      pushToast('error', 'Erro de conexão')
    }
  }

  const testKey = async () => {
    const k = newKey.trim()
    if (!k) return
    setTestingNew(true)
    const form = new FormData()
    form.set('api_key', k)
    const prefix = k.slice(0, 8) + '…' + k.slice(-4)
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/test`, { method: 'POST', body: form })
      const data = await res.json().catch(() => null)
      if (data) {
        setTestFeedback((prev) => ({
          ...prev,
          [prefix]: data.valid
            ? {
                ok: true,
                message: 'Chave válida',
                total: data.data?.rate_limit ?? 200,
                remaining: data.data?.rate_limit_remaining ?? null,
              }
            : { ok: false, message: data.message ?? 'Chave inválida', total: 200, remaining: null },
        }))
      }
    } catch {
      setTestFeedback((prev) => ({
        ...prev,
        [prefix]: { ok: false, message: 'Erro de conexão', total: 200, remaining: null },
      }))
    } finally {
      setTestingNew(false)
    }
  }

  const saveDesc = async () => {
    if (editingKeyId === null) return
    const form = new FormData()
    form.set('key_id', String(editingKeyId))
    form.set('description', editDesc.trim())
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/update-key`, { method: 'PUT', body: form })
      const data = await res.json().catch(() => null)
      if (data?.success) {
        setEditingKeyId(null)
        setEditDesc('')
        await loadKeys()
        pushToast('success', 'Descrição atualizada')
      }
    } catch {
      pushToast('error', 'Falha ao atualizar')
    }
  }

  const deleteKey = async (record: JsearchKeyRecord) => {
    const form = new FormData()
    form.set('key_id', String(record.id))
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/delete-key`, { method: 'DELETE', body: form })
      const data = await res.json().catch(() => null)
      if (data?.success) {
        await loadKeys()
        pushToast('success', 'Chave removida')
      }
    } catch {
      pushToast('error', 'Falha ao remover')
    }
  }

  const handleConfirm = async () => {
    if (!confirm) return
    if (confirm.kind === 'provider') {
      remove(confirm.id)
      pushToast('success', 'Provedor removido')
    } else {
      await deleteKey(confirm.record)
    }
    setConfirm(null)
  }

  const anyBusy = testingId !== null || testingNew
  const lastUpdated = useMemo(() => {
    if (!keys.length) return null
    const latest = keys
      .map((k) => (k.last_tested ? new Date(k.last_tested).getTime() : 0))
      .reduce((a, b) => Math.max(a, b), 0)
    return latest ? new Date(latest) : null
  }, [keys])

  return (
    <div className="relative w-full max-w-3xl mx-auto pb-10">
      {/* progress bar global */}
      <AnimatePresence>
        {anyBusy && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed top-0 left-0 right-0 h-1 bg-slate-900 z-[67] overflow-hidden"
          >
            <motion.div
              className="h-full w-1/3 bg-purple-500 shadow-[0_0_12px_rgba(168,85,247,0.8)]"
              initial={{ x: '-100%' }}
              animate={{ x: '300%' }}
              transition={{ repeat: Infinity, duration: 1.1, ease: 'linear' }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      {/* ═══════════════ HERO ═══════════════ */}
      <header className="mb-10">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE }}
        >
          <motion.span
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: 0.1, ease: EASE }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/15 border border-purple-400/30 text-purple-200 text-xs font-semibold mb-4"
          >
            <span className="relative flex h-2 w-2">
              <motion.span
                animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
                className="absolute inset-0 rounded-full bg-purple-400"
              />
              <span className="relative w-2 h-2 rounded-full bg-purple-400" />
            </span>
            Configurações
          </motion.span>

          <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight">
            Configuração de IAs
          </h1>
          <p className="text-base text-slate-300 mt-2.5 max-w-xl leading-relaxed">
            Cadastre suas chaves de API e escolha qual IA usar em cada ferramenta.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-8">
            <StatCard
              icon={<Server className="w-6 h-6 text-purple-300" />}
              tone="bg-purple-500/15 border-purple-400/30 shadow-[0_0_20px_-4px_rgba(168,85,247,0.4)]"
              label="Provedores"
              value={providers.length}
              delay={0.05}
            />
            <StatCard
              icon={<CheckCircle2 className="w-6 h-6 text-emerald-300" />}
              tone="bg-emerald-500/15 border-emerald-400/30 shadow-[0_0_20px_-4px_rgba(16,185,129,0.4)]"
              label="Conectados"
              value={connectedCount}
              delay={0.1}
            />
            <StatCard
              icon={<KeyRound className="w-6 h-6 text-blue-300" />}
              tone="bg-blue-500/15 border-blue-400/30 shadow-[0_0_20px_-4px_rgba(59,130,246,0.4)]"
              label="Req/mês JSearch"
              value={jsearchQuota}
              delay={0.15}
            />
          </div>
        </motion.div>
      </header>

      {/* ═══════════════ PROVIDERS ═══════════════ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-50px' }}
        transition={{ duration: 0.5, ease: EASE }}
        className="mb-10"
      >
        <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
          <div>
            <h2 className="text-xl font-bold text-white">Provedores de IA</h2>
            <p className="text-sm text-slate-400 mt-1">
              {providers.length === 0
                ? 'Nenhum provedor cadastrado'
                : `${providers.length} configurado${providers.length > 1 ? 's' : ''}`}
            </p>
          </div>
          {!showAdd && (
            <motion.button
              whileHover={{ scale: 1.03, y: -1 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => {
                setShowAdd(true)
                resetNew()
              }}
              className="inline-flex items-center gap-2 h-11 px-4 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50"
            >
              <Plus className="w-4 h-4" strokeWidth={2.5} />
              Adicionar
            </motion.button>
          )}
        </div>

        <div className="rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden shadow-2xl shadow-black/40">
          {providers.length === 0 && !showAdd && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4 }}
              className="px-6 py-16 text-center"
            >
              <motion.div
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                className="w-16 h-16 rounded-2xl bg-purple-500/15 border border-purple-400/30 shadow-[0_0_30px_-6px_rgba(168,85,247,0.5)] flex items-center justify-center mx-auto mb-5"
              >
                <Server className="w-7 h-7 text-purple-300" />
              </motion.div>
              <h3 className="text-lg font-bold text-white">Nenhum provedor cadastrado</h3>
              <p className="text-base text-slate-300 mt-2 max-w-sm mx-auto leading-relaxed">
                Adicione sua primeira chave de API para habilitar a análise por inteligência artificial.
              </p>
              <motion.button
                whileHover={{ scale: 1.03, y: -1 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => {
                  setShowAdd(true)
                  resetNew()
                }}
                className="mt-5 inline-flex items-center gap-2 h-11 px-4 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all shadow-lg shadow-purple-500/30"
              >
                <Plus className="w-4 h-4" strokeWidth={2.5} />
                Adicionar provedor
              </motion.button>
            </motion.div>
          )}

          <AnimatePresence initial={false}>
            {providers.map((p, idx) => {
              const cfg = PROVIDER_THEME[p.provider as ProviderType] ?? PROVIDER_THEME.custom
              const isOpen = expandedId === p.id
              const isTesting = testingId === p.id

              return (
                <motion.div
                  key={p.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.28, delay: Math.min(idx * 0.04, 0.15), ease: EASE }}
                  className="border-b border-slate-700/80 last:border-b-0"
                >
                  <div
                    onClick={() => openEdit(p)}
                    className={`group flex items-center gap-4 px-5 py-4 cursor-pointer transition-colors ${
                      isOpen ? 'bg-slate-800/60' : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <motion.div
                      whileHover={{ scale: 1.08, rotate: [0, -4, 4, 0] }}
                      transition={{ duration: 0.4 }}
                      className={`w-12 h-12 rounded-xl border flex items-center justify-center shrink-0 transition-shadow ${cfg.iconWrap} ${cfg.glow}`}
                    >
                      <cfg.Icon className={`w-6 h-6 ${cfg.iconColor}`} />
                    </motion.div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-base font-semibold text-white truncate">
                          {p.name || cfg.name}
                        </span>
                        <StatusPill status={p.status} testing={isTesting} message={p.statusMessage} latencyMs={p.lastLatencyMs} />
                      </div>
                      <div className="text-sm text-slate-300 truncate">
                        <span className="font-medium text-slate-200">{p.modelName}</span>
                        <span className="mx-1.5 text-slate-500">·</span>
                        <span className="font-mono text-slate-400">
                          {p.apiKey.slice(0, 8)}…{p.apiKey.slice(-4)}
                        </span>
                      </div>
                      {p.lastTestedAt ? (
                        <div
                          className={`text-[13px] truncate ${
                            p.status === 'error'
                              ? 'text-rose-300/90'
                              : p.status === 'slow'
                                ? 'text-amber-300/90'
                                : 'text-slate-400/80'
                          }`}
                          title={p.status === 'error' ? p.statusMessage : undefined}
                        >
                          {p.status === 'error'
                            ? `Último teste: falhou ${fmtWhen(p.lastTestedAt)}${p.statusMessage ? ` — ${p.statusMessage}` : ''}`
                            : p.lastLatencyMs != null
                              ? `Último teste: ${fmtLatency(p.lastLatencyMs)} · ${fmtWhen(p.lastTestedAt)}`
                              : `Último teste: ${fmtWhen(p.lastTestedAt)}`}
                        </div>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <div className="hidden sm:block">
                        <Select
                          value={p.usedFor}
                          onChange={(v) => updateUsedFor(p.id, v as IAProvider['usedFor'])}
                          options={USED_FOR}
                          size="sm"
                          className="w-32"
                        />
                      </div>
                      <motion.button
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => testProvider(p)}
                        disabled={isTesting}
                        title="Testar conexão"
                        className="h-9 w-9 rounded-lg text-slate-300 hover:text-emerald-300 hover:bg-emerald-500/15 flex items-center justify-center transition-colors disabled:opacity-50"
                      >
                        <Zap className="w-4 h-4" />
                      </motion.button>
                      <motion.button
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => {
                          if (isOpen) setExpandedId(null)
                          else openEdit(p)
                        }}
                        title={isOpen ? 'Fechar' : 'Editar'}
                        className="h-9 w-9 rounded-lg text-slate-300 hover:text-white hover:bg-slate-700 flex items-center justify-center transition-colors"
                      >
                        <ChevronDown
                          className={`w-4 h-4 transition-transform duration-300 ${
                            isOpen ? 'rotate-180' : ''
                          }`}
                        />
                      </motion.button>
                      <motion.button
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() =>
                          setConfirm({ kind: 'provider', id: p.id, label: p.name || cfg.name })
                        }
                        title="Remover"
                        className="h-9 w-9 rounded-lg text-slate-300 hover:text-rose-300 hover:bg-rose-500/15 flex items-center justify-center transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </motion.button>
                    </div>
                  </div>

                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: EASE }}
                        className="overflow-hidden"
                      >
                        <div className="px-5 pb-5 pt-2 bg-slate-950/60 border-t border-slate-700/80 space-y-4">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className={labelCls}>Nome</label>
                              <Input
                                value={editData.name ?? ''}
                                onChange={(e) =>
                                  setEditData((d) => ({ ...d, name: e.target.value }))
                                }
                              />
                            </div>
                            <div>
                              <label className={labelCls}>Modelo</label>
                              {p.provider === 'custom' ? (
                                <Input
                                  mono
                                  value={editData.modelName ?? ''}
                                  onChange={(e) =>
                                    setEditData((d) => ({ ...d, modelName: e.target.value }))
                                  }
                                />
                              ) : (
                                <Select
                                  value={editData.modelName ?? p.modelName}
                                  onChange={(v) => setEditData((d) => ({ ...d, modelName: v }))}
                                  options={cfg.defaultModels.map((m) => ({ value: m, label: m }))}
                                  className="w-full"
                                />
                              )}
                            </div>
                          </div>
                          <div>
                            <label className={labelCls}>Chave de API</label>
                            <Input
                              mono
                              type="password"
                              value={editData.apiKey ?? ''}
                              onChange={(e) =>
                                setEditData((d) => ({ ...d, apiKey: e.target.value }))
                              }
                            />
                          </div>
                          {p.provider === 'custom' && (
                            <div>
                              <label className={labelCls}>URL</label>
                              <Input
                                mono
                                value={editData.apiUrl ?? ''}
                                onChange={(e) =>
                                  setEditData((d) => ({ ...d, apiUrl: e.target.value }))
                                }
                              />
                            </div>
                          )}
                          <div>
                            <label className={labelCls}>Usar em</label>
                            <Select
                              value={editData.usedFor ?? p.usedFor}
                              onChange={(v) =>
                                setEditData((d) => ({ ...d, usedFor: v as IAProvider['usedFor'] }))
                              }
                              options={USED_FOR}
                              className="w-full"
                            />
                          </div>
                          <div className="flex items-center justify-end gap-2 pt-1">
                            <motion.button
                              whileHover={{ scale: 1.02 }}
                              whileTap={{ scale: 0.97 }}
                              onClick={() => setExpandedId(null)}
                              className="h-11 px-4 text-sm font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors"
                            >
                              Cancelar
                            </motion.button>
                            <motion.button
                              whileHover={{ scale: 1.02 }}
                              whileTap={{ scale: 0.97 }}
                              onClick={saveEdit}
                              className="inline-flex items-center gap-2 h-11 px-4 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all shadow-lg shadow-purple-500/30"
                            >
                              <Save className="w-4 h-4" />
                              Salvar
                            </motion.button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )
            })}
          </AnimatePresence>

          <AnimatePresence initial={false}>
            {showAdd && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3, ease: EASE }}
                className="overflow-hidden"
              >
                <div className="px-5 py-5 space-y-4 bg-slate-950/60 border-t border-slate-700/80">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-bold text-white">Novo provedor</h3>
                    <motion.button
                      whileHover={{ scale: 1.1, rotate: 90 }}
                      whileTap={{ scale: 0.9 }}
                      onClick={() => {
                        setShowAdd(false)
                        resetNew()
                      }}
                      className="h-8 w-8 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 flex items-center justify-center transition-colors"
                      aria-label="Fechar"
                    >
                      <X className="w-4 h-4" />
                    </motion.button>
                  </div>

                  <div>
                    <label className={labelCls}>Tipo</label>
                    <div className="grid grid-cols-3 gap-2">
                      {(Object.keys(PROVIDER_THEME) as ProviderType[]).map((t) => {
                        const active = newProv.providerType === t
                        const cfg = PROVIDER_THEME[t]
                        return (
                          <motion.button
                            key={t}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.97 }}
                            onClick={() => {
                              setNewProv((p) => ({ ...p, providerType: t }))
                              resetNew(t)
                            }}
                            className={`relative flex flex-col items-center gap-2 py-3.5 px-2 rounded-xl border-2 transition-all ${
                              active
                                ? 'border-purple-400 bg-purple-500/10 shadow-lg shadow-purple-500/20'
                                : 'border-slate-700 bg-slate-950 hover:border-slate-600'
                            }`}
                          >
                            {active && (
                              <motion.span
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ type: 'spring', stiffness: 500, damping: 25 }}
                                className="absolute top-2 right-2 w-5 h-5 rounded-full bg-purple-500 flex items-center justify-center shadow-lg shadow-purple-500/50"
                              >
                                <Check className="w-3 h-3 text-white" strokeWidth={3} />
                              </motion.span>
                            )}
                            <div
                              className={`w-10 h-10 rounded-lg border flex items-center justify-center ${cfg.iconWrap}`}
                            >
                              <cfg.Icon className={`w-5 h-5 ${cfg.iconColor}`} />
                            </div>
                            <span
                              className={`text-sm font-semibold ${
                                active ? 'text-white' : 'text-slate-300'
                              }`}
                            >
                              {cfg.name}
                            </span>
                          </motion.button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className={labelCls}>Nome (opcional)</label>
                      <Input
                        value={newProv.name}
                        onChange={(e) => setNewProv((p) => ({ ...p, name: e.target.value }))}
                        placeholder={meta.name}
                      />
                    </div>
                    <div>
                      <label className={labelCls}>Chave de API</label>
                      <Input
                        mono
                        type="password"
                        value={newProv.apiKey}
                        onChange={(e) => setNewProv((p) => ({ ...p, apiKey: e.target.value }))}
                        placeholder="sk-…"
                      />
                    </div>
                  </div>

                  {newProv.providerType === 'custom' ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className={labelCls}>URL da API</label>
                        <Input
                          mono
                          value={newProv.apiUrl}
                          onChange={(e) => {
                            setNewProv((p) => ({ ...p, apiUrl: e.target.value }))
                            setUrlErr('')
                          }}
                          placeholder="https://api.exemplo.com/v1"
                        />
                        <AnimatePresence>
                          {urlErr && (
                            <motion.p
                              initial={{ opacity: 0, y: -4 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -4 }}
                              className="text-sm font-medium text-rose-300 mt-2 flex items-center gap-1.5"
                            >
                              <AlertCircle className="w-4 h-4" />
                              {urlErr}
                            </motion.p>
                          )}
                        </AnimatePresence>
                      </div>
                      <div>
                        <label className={labelCls}>Modelo</label>
                        <Input
                          mono
                          value={newProv.modelName}
                          onChange={(e) =>
                            setNewProv((p) => ({ ...p, modelName: e.target.value }))
                          }
                          placeholder="gpt-4o"
                        />
                      </div>
                    </div>
                  ) : (
                    <div>
                      <label className={labelCls}>Modelo</label>
                      <Select
                        value={newProv.modelName}
                        onChange={(v) => setNewProv((p) => ({ ...p, modelName: v }))}
                        options={meta.defaultModels.map((m) => ({ value: m, label: m }))}
                        className="w-full"
                      />
                    </div>
                  )}

                  <div>
                    <label className={labelCls}>Usar em</label>
                    <Select
                      value={newProv.usedFor}
                      onChange={(v) => setNewProv((p) => ({ ...p, usedFor: v as IAProvider['usedFor'] }))}
                      options={USED_FOR}
                      className="w-full"
                    />
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-1">
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => {
                        setShowAdd(false)
                        resetNew()
                      }}
                      className="h-11 px-4 text-sm font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors"
                    >
                      Cancelar
                    </motion.button>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={addProvider}
                      disabled={!newProv.apiKey.trim()}
                      className="h-11 px-4 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-purple-500/30"
                    >
                      Adicionar provedor
                    </motion.button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.section>

      {/* ═══════════════ JSEARCH ═══════════════ */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-50px' }}
        transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
        className="mb-10"
      >
        <div className="flex items-center justify-between gap-4 mb-4 flex-wrap">
          <div>
            <h2 className="text-xl font-bold text-white">Chaves JSearch</h2>
            <p className="text-sm text-slate-400 mt-1">
              {keys.length === 0
                ? 'Nenhuma chave cadastrada'
                : `${keys.length} chave${keys.length > 1 ? 's' : ''} · ~${jsearchQuota} req/mês`}
            </p>
          </div>
          <motion.a
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
            href="https://app.openwebninja.com/signup"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 h-11 px-4 text-sm font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors"
          >
            Obter chaves
            <ExternalLink className="w-4 h-4" />
          </motion.a>
        </div>

        <div className="rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden shadow-2xl shadow-black/40">
          {keysLoading ? (
            <div className="px-5 py-5 space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 rounded-xl bg-slate-800 relative overflow-hidden">
                  <motion.div
                    className="absolute inset-0 bg-slate-700/50"
                    initial={{ x: '-100%' }}
                    animate={{ x: '100%' }}
                    transition={{ repeat: Infinity, duration: 1.4, ease: 'linear' }}
                    style={{ width: '50%' }}
                  />
                </div>
              ))}
            </div>
          ) : (
            <>
              {keys.length === 0 && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.4 }}
                  className="px-6 py-16 text-center"
                >
                  <motion.div
                    animate={{ y: [0, -6, 0] }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                    className="w-16 h-16 rounded-2xl bg-blue-500/15 border border-blue-400/30 shadow-[0_0_30px_-6px_rgba(59,130,246,0.5)] flex items-center justify-center mx-auto mb-5"
                  >
                    <KeyRound className="w-7 h-7 text-blue-300" />
                  </motion.div>
                  <h3 className="text-lg font-bold text-white">Nenhuma chave cadastrada</h3>
                  <p className="text-base text-slate-300 mt-2 max-w-sm mx-auto leading-relaxed">
                    Adicione uma chave JSearch abaixo para habilitar a busca de vagas.
                  </p>
                </motion.div>
              )}

              <AnimatePresence initial={false}>
                {keys.map((record, idx) => {
                  const used = record.used ?? 0
                  const total = record.rate_limit_total ?? 200
                  const remaining = record.rate_limit_remaining
                  const pct = Math.min(
                    100,
                    remaining !== null
                      ? Math.round(((total - remaining) / total) * 100)
                      : Math.round((used / total) * 100)
                  )
                  const isEditing = editingKeyId === record.id

                  let status: { pill: string; label: string; Icon: typeof CheckCircle2 } = {
                    pill: 'bg-slate-800 border border-slate-700 text-slate-300',
                    label: 'Não testada',
                    Icon: AlertCircle,
                  }
                  if (record.status === 'ok')
                    status = {
                      pill: 'bg-emerald-500/15 border border-emerald-400/30 text-emerald-200 shadow-[0_0_16px_-4px_rgba(16,185,129,0.4)]',
                      label: 'Ativa',
                      Icon: CheckCircle2,
                    }
                  else if (record.status === '403')
                    status = {
                      pill: 'bg-rose-500/15 border border-rose-400/30 text-rose-200',
                      label: 'Inválida',
                      Icon: XCircle,
                    }
                  else if (record.status === '429')
                    status = {
                      pill: 'bg-amber-500/15 border border-amber-400/30 text-amber-200',
                      label: 'Limite',
                      Icon: AlertCircle,
                    }

                  return (
                    <motion.div
                      key={record.id}
                      layout
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.28, delay: Math.min(idx * 0.04, 0.15), ease: EASE }}
                      className="flex items-center gap-4 px-5 py-4 border-b border-slate-700/80 last:border-b-0 hover:bg-slate-800/40 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1.5">
                          <CopyableCode value={record.key_prefix} />
                          <span
                            className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md ${status.pill}`}
                            title={record.last_error ?? undefined}
                          >
                            <status.Icon className="w-3.5 h-3.5" />
                            {status.label}
                          </span>
                        </div>
                        <div className="text-sm text-slate-300">
                          {isEditing ? (
                            <input
                              autoFocus
                              value={editDesc}
                              onChange={(e) => setEditDesc(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveDesc()
                                if (e.key === 'Escape') setEditingKeyId(null)
                              }}
                              placeholder="Descrição"
                              className="w-full h-9 px-3 rounded-lg bg-slate-950 border border-blue-400/60 text-sm text-white outline-none focus:ring-4 focus:ring-blue-500/25"
                            />
                          ) : (
                            <span className="truncate">{record.description || 'Sem descrição'}</span>
                          )}
                        </div>
                      </div>
                      <QuotaRing pct={pct} used={used} total={total} />
                      <div className="flex items-center gap-1 shrink-0">
                        {isEditing ? (
                          <>
                            <motion.button
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                              onClick={saveDesc}
                              title="Salvar"
                              className="h-9 w-9 rounded-lg text-emerald-300 hover:bg-emerald-500/15 flex items-center justify-center transition-colors"
                            >
                              <Check className="w-4 h-4" />
                            </motion.button>
                            <motion.button
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                              onClick={() => setEditingKeyId(null)}
                              title="Cancelar"
                              className="h-9 w-9 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 flex items-center justify-center transition-colors"
                            >
                              <X className="w-4 h-4" />
                            </motion.button>
                          </>
                        ) : (
                          <>
                            <motion.button
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                              onClick={() => {
                                setEditingKeyId(record.id)
                                setEditDesc(record.description ?? '')
                              }}
                              title="Editar descrição"
                              className="h-9 w-9 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 flex items-center justify-center transition-colors"
                            >
                              <Pencil className="w-4 h-4" />
                            </motion.button>
                            <motion.button
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                              onClick={() =>
                                setConfirm({
                                  kind: 'jsearch',
                                  record,
                                  label: record.description || record.key_prefix,
                                })
                              }
                              title="Remover"
                              className="h-9 w-9 rounded-lg text-slate-300 hover:text-rose-300 hover:bg-rose-500/15 flex items-center justify-center transition-colors"
                            >
                              <Trash2 className="w-4 h-4" />
                            </motion.button>
                          </>
                        )}
                      </div>
                    </motion.div>
                  )
                })}
              </AnimatePresence>

              <div className="px-5 py-4 bg-slate-950/60 border-t border-slate-700/80">
                <div className="flex flex-col sm:flex-row gap-2">
                  <div className="relative flex-1">
                    <Link2 className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                    <input
                      type={revealKey ? 'text' : 'password'}
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && newKey.trim()) addKey()
                      }}
                      placeholder="Cole uma JSearch API Key..."
                      className="w-full h-12 pl-10 pr-11 rounded-xl bg-slate-900 border border-slate-700 text-base font-mono text-white placeholder:text-slate-500 outline-none transition-all hover:border-slate-600 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/25"
                    />
                    <button
                      type="button"
                      onClick={() => setRevealKey((v) => !v)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1.5 rounded-md hover:bg-slate-800 transition-colors"
                      aria-label={revealKey ? 'Esconder' : 'Mostrar'}
                    >
                      {revealKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={testKey}
                      disabled={!newKey.trim() || testingNew}
                      className="inline-flex items-center gap-2 h-12 px-4 text-sm font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {testingNew ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <RefreshCw className="w-4 h-4" />
                      )}
                      Testar
                    </motion.button>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={addKey}
                      disabled={!newKey.trim()}
                      className="inline-flex items-center gap-2 h-12 px-4 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50"
                    >
                      <Plus className="w-4 h-4" strokeWidth={2.5} />
                      Adicionar
                    </motion.button>
                  </div>
                </div>

                <AnimatePresence>
                  {newKey.trim() &&
                    (() => {
                      const prefix = newKey.trim().slice(0, 8) + '…' + newKey.trim().slice(-4)
                      const fb = testFeedback[prefix]
                      if (!fb) return null
                      const used = fb.total - (fb.remaining ?? 0)
                      return (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          className={`mt-3 flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
                            fb.ok
                              ? 'bg-emerald-500/15 border-emerald-400/30 text-emerald-200'
                              : 'bg-rose-500/15 border-rose-400/30 text-rose-200'
                          }`}
                        >
                          {fb.ok ? (
                            <CheckCircle2 className="w-4 h-4 shrink-0" />
                          ) : (
                            <XCircle className="w-4 h-4 shrink-0" />
                          )}
                          <span>
                            {fb.ok ? `Chave válida — ${used}/${fb.total} usadas` : fb.message}
                          </span>
                        </motion.div>
                      )
                    })()}
                </AnimatePresence>

                <p className="text-sm text-slate-400 mt-3 flex items-start gap-2 leading-relaxed">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  Chaves salvas como hash no servidor. O backend as reusa automaticamente.
                </p>
              </div>
            </>
          )}
        </div>
      </motion.section>

      {/* footer */}
      <footer className="flex items-center justify-between pt-4 border-t border-slate-700 text-sm text-slate-400">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-2">
            <Kbd>Enter</Kbd> adicionar
          </span>
          <span className="flex items-center gap-2">
            <Kbd>Esc</Kbd> cancelar
          </span>
        </div>
        {lastUpdated && (
          <span>
            Verificado:{' '}
            <span className="text-slate-200 font-medium">
              {lastUpdated.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
            </span>
          </span>
        )}
      </footer>

      {/* confirm dialog */}
      <AnimatePresence>
        {confirm && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setConfirm(null)}
              className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[80]"
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              initial={{ opacity: 0, scale: 0.92, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 12 }}
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[81] w-full max-w-md mx-4 bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl shadow-black/70"
            >
              <div className="flex items-start gap-4 mb-5">
                <motion.div
                  initial={{ scale: 0.5, rotate: -20 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: 'spring', damping: 15, stiffness: 300, delay: 0.1 }}
                  className="w-12 h-12 rounded-xl bg-rose-500/15 border border-rose-400/30 shadow-[0_0_24px_-6px_rgba(244,63,94,0.5)] flex items-center justify-center shrink-0"
                >
                  <AlertCircle className="w-6 h-6 text-rose-300" />
                </motion.div>
                <div className="min-w-0 pt-0.5">
                  <h3 className="text-lg font-bold text-white">Remover integração</h3>
                  <p className="text-base text-slate-300 mt-1.5 leading-relaxed">
                    Tem certeza que deseja remover{' '}
                    <span className="font-semibold text-white">{confirm.label}</span>? Esta ação
                    não pode ser desfeita.
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => setConfirm(null)}
                  className="h-11 px-4 text-sm font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors"
                >
                  Cancelar
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={handleConfirm}
                  autoFocus
                  className="h-11 px-4 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-500 rounded-xl transition-all shadow-lg shadow-rose-500/30"
                >
                  Remover
                </motion.button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}