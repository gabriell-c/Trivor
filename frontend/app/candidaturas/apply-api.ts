/* Client HTTP do painel de Candidaturas — fala com /api/apply/* do backend.
 * Erros vêm com `detail` em PT-BR; o fallback genérico só roda quando o
 * backend responde não-JSON (404 de rota, 502 do proxy, ...).
 */
import { API_BASE_URL } from '../lib/api'
import { friendlyError } from '../lib/errors'

async function handle(r: Response): Promise<any> {
  if (!r.ok) {
    let detail = ''
    try {
      const j = await r.json()
      // FastAPI costuma mandar `detail` string (nossas rotas) ou array de
      // erros de validação (422) — só usamos texto legível
      detail = typeof j?.detail === 'string' ? j.detail : ''
    } catch { /* resposta não-JSON */ }
    if (!detail) {
      detail = r.status === 422
        ? 'Requisito incompleto (faltou campo obrigatório — ex.: arquivo do upload).'
        : ''
    }
    throw new Error(detail || friendlyError(new Error(`HTTP ${r.status}`), 'Falha ao falar com o backend.'))
  }
  return r.json()
}

/* Converte a falha de rede (backend fora do ar) na mensagem PT-BR do
 * friendlyError — sem isso o TypeError cru ("Failed to fetch") vaza
 * pros caixas de erro da UI. Erros já tratados por `handle` passam intactos. */
function traduzFalhaDeRede<T>(p: Promise<T>): Promise<T> {
  return p.catch(err => {
    if (err instanceof TypeError) throw new Error(friendlyError(err))
    throw err
  })
}

export function applyFetch(path: string): Promise<any> {
  return traduzFalhaDeRede(fetch(`${API_BASE_URL}${path}`).then(handle))
}

export function applyMethod(
  path: string,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  body?: unknown,
): Promise<any> {
  return traduzFalhaDeRede(fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle))
}

/* multipart — só para upload de currículos (Content-Type vem do FormData) */
export function applyUpload(path: string, form: FormData): Promise<any> {
  return traduzFalhaDeRede(fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form }).then(handle))
}

/* ═══ Contratos do backend (/api/apply/*) ═══ */
export interface BotRun {
  bot: string
  running: boolean
  pid: number | null
  started_at: string | null
  log_tail: string[]
}

export const BOT_NAMES = ['gupy', 'infojobs', 'nerdin', 'indeed', 'solides'] as const

export interface IaProvider {
  id: string
  nome: string
  tipo: 'openai' | 'anthropic' | string
  base_url: string
  api_key_masked?: string
  modelo: string
  temperatura?: number
  max_tokens?: number
}

export interface IaState {
  ativo: string | null
  providers: IaProvider[]
}

export interface ResumeItem {
  id: string
  nome: string
  descricao: string
  arquivo: string
  existe: boolean
}

/* ═══ Aparência compartilhada das abas (mesma linguagem dos cards da página) ═══ */
export const inputCls = 'w-full px-3 py-2 rounded-xl bg-slate-950/50 border border-slate-800 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors'
export const labelCls = 'text-[11px] font-medium text-slate-400 uppercase tracking-wider'
export const btnPrimary = 'flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-indigo-500/40 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20 transition-colors disabled:opacity-50'
export const btnDanger = 'flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20 transition-colors disabled:opacity-50'
export const cardCls = 'rounded-2xl border border-slate-800/70 bg-slate-900/60 p-4'
