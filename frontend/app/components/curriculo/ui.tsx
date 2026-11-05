'use client'
import { motion } from 'framer-motion'
import { RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react'
import { getBestProvider } from '../../hooks/useIaProviders'

export const EASE = [0.16, 1, 0.3, 1] as const

/* ═══════════ Tons semânticos ═══════════ */
export const TONE = {
  indigo: {
    wrap: 'bg-indigo-500/15 border-indigo-400/30 text-indigo-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(99,102,241,0.45)]',
  },
  purple: {
    wrap: 'bg-purple-500/15 border-purple-400/30 text-purple-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(168,85,247,0.45)]',
  },
  emerald: {
    wrap: 'bg-emerald-500/15 border-emerald-400/30 text-emerald-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(16,185,129,0.45)]',
  },
  amber: {
    wrap: 'bg-amber-500/15 border-amber-400/30 text-amber-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(245,158,11,0.45)]',
  },
  rose: {
    wrap: 'bg-rose-500/15 border-rose-400/30 text-rose-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(244,63,94,0.45)]',
  },
  blue: {
    wrap: 'bg-blue-500/15 border-blue-400/30 text-blue-300',
    glow: 'shadow-[0_0_20px_-4px_rgba(59,130,246,0.45)]',
  },
} as const

export type Tone = keyof typeof TONE

/* ═══════════ Card ═══════════ */
export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/30 ${className}`}
    >
      {children}
    </div>
  )
}

/* ═══════════ Section head ═══════════ */
export function SectionHead({
  icon,
  tone,
  title,
  subtitle,
  right,
}: {
  icon: React.ReactNode
  tone: Tone
  title: string
  subtitle?: string
  right?: React.ReactNode
}) {
  const cls = TONE[tone]
  return (
    <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className={`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 ${cls.wrap} ${cls.glow}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-white leading-tight truncate">{title}</h2>
          {subtitle && <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  )
}

/* ═══════════ Input custom ═══════════ */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean
}
export function Input({ className = '', mono, ...props }: InputProps) {
  return (
    <input
      {...props}
      className={`w-full h-12 px-4 rounded-xl bg-slate-950 border border-slate-700 text-base text-white placeholder:text-slate-500 outline-none transition-all duration-200 hover:border-slate-600 focus:border-indigo-400 focus:ring-4 focus:ring-indigo-500/25 ${
        mono ? 'font-mono text-sm' : ''
      } ${className}`}
    />
  )
}

/* ═══════════ Botão primário ═══════════ */
export function PrimaryBtn({
  children,
  onClick,
  disabled,
  loading,
  className = '',
  tone = 'indigo',
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  loading?: boolean
  className?: string
  tone?: 'indigo' | 'emerald'
}) {
  const bg =
    tone === 'emerald'
      ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/30 hover:shadow-emerald-500/50'
      : 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-500/30 hover:shadow-indigo-500/50'
  return (
    <motion.button
      whileHover={disabled ? {} : { scale: 1.02, y: -1 }}
      whileTap={disabled ? {} : { scale: 0.98 }}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 h-12 px-5 rounded-xl text-base font-semibold text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg ${bg} ${className}`}
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

/* ═══════════ Botão secundário (small action) ═══════════ */
export function GhostBtn({
  children,
  onClick,
  disabled,
  className = '',
  tone = 'slate',
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  className?: string
  tone?: 'slate' | 'indigo' | 'emerald' | 'rose'
}) {
  const cls =
    tone === 'indigo'
      ? 'bg-indigo-500/10 text-indigo-200 border-indigo-400/30 hover:bg-indigo-500/20'
      : tone === 'emerald'
      ? 'bg-emerald-500/10 text-emerald-200 border-emerald-400/30 hover:bg-emerald-500/20'
      : tone === 'rose'
      ? 'bg-rose-500/10 text-rose-200 border-rose-400/30 hover:bg-rose-500/20'
      : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
  return (
    <motion.button
      whileHover={disabled ? {} : { scale: 1.03 }}
      whileTap={disabled ? {} : { scale: 0.97 }}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-xs font-semibold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${cls} ${className}`}
    >
      {children}
    </motion.button>
  )
}

/* ═══════════ Score badge ═══════════ */
export function ScoreBadge({
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
  const high = score >= 80
  const mid = score >= 60
  const cls = high
    ? {
        wrap: 'bg-emerald-500/15 border-emerald-400/30',
        text: 'text-emerald-300',
        glow: 'shadow-[0_0_24px_-6px_rgba(16,185,129,0.45)]',
      }
    : mid
    ? {
        wrap: 'bg-amber-500/15 border-amber-400/30',
        text: 'text-amber-300',
        glow: 'shadow-[0_0_24px_-6px_rgba(245,158,11,0.45)]',
      }
    : {
        wrap: 'bg-rose-500/15 border-rose-400/30',
        text: 'text-rose-300',
        glow: 'shadow-[0_0_24px_-6px_rgba(244,63,94,0.45)]',
      }
  const big = size === 'lg'
  return (
    <div className="flex items-center gap-3">
      <div
        className={`rounded-xl border flex items-center justify-center shrink-0 ${cls.wrap} ${cls.glow} ${
          big ? 'w-16 h-16' : 'w-12 h-12'
        }`}
      >
        <span className={`font-bold tabular-nums ${cls.text} ${big ? 'text-2xl' : 'text-lg'}`}>
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
export function StatusPill({ status }: { status?: 'ok' | 'atencao' | 'critico' }) {
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

/* ═══════════ Kbd ═══════════ */
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[22px] h-5 px-1.5 rounded border border-slate-600 bg-slate-800 text-slate-200 text-xs font-semibold font-mono shadow-[0_1px_0_rgba(0,0,0,0.4)]">
      {children}
    </kbd>
  )
}

/* ═══════════ LLM provider boilerplate (untouched) ═══════════ */
export function addLlmProvider(formData: FormData, tools: ('curriculo' | 'market')[]) {
  const provider = getBestProvider(tools)
  if (!provider) return
  formData.set('api_key', provider.apiKey)
  formData.set('api_url', provider.apiUrl)
  formData.set('model_name', provider.modelName)
}

export const SECTION_LABELS: Record<string, string> = {
  contato: 'Contato',
  summary: 'Profile Summary',
  experiencia: 'Experiência',
  educacao: 'Educação',
  habilidades: 'Habilidades',
  projetos: 'Projetos',
  certificacoes: 'Certificações',
  idiomas: 'Idiomas',
}

export const ERROR_TYPE_LABELS: Record<string, string> = {
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
  formatacao_inconsistente: 'Formatação inconsistente',
}

/* ═══════════ Helper puro ═══════════ */
export function formatTokens(num?: number) {
  if (num === undefined || num === null) return '0'
  if (num >= 1000) {
    const formattedNum = num.toLocaleString('pt-BR')
    const kValue = (num / 1000).toFixed(1).replace('.', ',')
    return `${formattedNum} (${kValue}k)`
  }
  return num.toString()
}
