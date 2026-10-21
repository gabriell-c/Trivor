'use client'
import { useEffect, useState } from 'react'
import {
  Plus, Trash2, Pencil, Star, Loader2, Zap, Check, X,
} from 'lucide-react'
import {
  applyFetch, applyMethod,
  type IaProvider, type IaState, cardCls, btnPrimary, btnDanger, inputCls, labelCls,
} from './apply-api'

interface IaForm {
  id?: string
  nome: string
  tipo: 'openai' | 'anthropic'
  base_url: string
  api_key: string
  modelo: string
  temperatura: string
  max_tokens: string
}

const FORM_VAZIO: IaForm = {
  nome: '', tipo: 'openai', base_url: '', api_key: '',
  modelo: '', temperatura: '0.5', max_tokens: '500',
}

const BASE_URLS_SUGERIDAS = [
  'https://api.groq.com/openai/v1',
  'https://api.openai.com/v1',
  'http://localhost:11434/v1',
  'https://api.together.ai/v1',
]

export default function IATab() {
  const [ia, setIa] = useState<IaState | null>(null)
  const [form, setForm] = useState<IaForm>(FORM_VAZIO)
  const [salvando, setSalvando] = useState(false)
  const [testando, setTestando] = useState(false)
  const [teste, setTeste] = useState<{ ok: boolean; texto: string } | null>(null)
  const [testeDe, setTesteDe] = useState<string>('form')
  const [erro, setErro] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const recarregar = () => applyFetch('/api/apply/ia').then(setIa).catch(e => setErro(msgErr(e)))
  useEffect(() => { recarregar() }, [])

  const editar = (p: IaProvider) => {
    setForm({
      id: p.id, nome: p.nome || p.id, tipo: (p.tipo as IaForm['tipo']) || 'openai',
      base_url: p.base_url || '', api_key: '',
      modelo: p.modelo || '',
      temperatura: String(p.temperatura ?? 0.5), max_tokens: String(p.max_tokens ?? 500),
    })
    setTeste(null)
  }

  const salvar = async () => {
    setSalvando(true)
    setErro(null)
    const corpo: Record<string, unknown> = {
      nome: form.nome.trim() || form.id || form.modelo,
      tipo: form.tipo,
      base_url: form.base_url.trim(),
      api_key: form.api_key.trim(),
      modelo: form.modelo.trim(),
      temperatura: parseFloat(form.temperatura) || 0.5,
      max_tokens: parseInt(form.max_tokens, 10) || 500,
    }
    if (form.tipo === 'anthropic') delete corpo.base_url
    try {
      if (form.id) {
        await applyMethod(`/api/apply/ia/${form.id}`, 'PATCH', corpo)
        setMsg(`Provedor ${form.nome || form.id} atualizado.`)
      } else {
        await applyMethod('/api/apply/ia', 'POST', corpo)
        setMsg(`Provedor ${corpo.nome} criado.`)
      }
      setForm(FORM_VAZIO)
      await recarregar()
    } catch (e) {
      setErro(msgErr(e))
    } finally {
      setSalvando(false)
    }
  }

  const excluir = async (p: IaProvider) => {
    if (!window.confirm(`Excluir o provedor "${p.nome || p.id}"?`)) return
    setErro(null)
    try {
      await applyMethod(`/api/apply/ia/${p.id}`, 'DELETE')
      if (form.id === p.id) setForm(FORM_VAZIO)
      setMsg(`Provedor ${p.id} excluído.`)
      await recarregar()
    } catch (e) {
      setErro(msgErr(e))
    }
  }

  const ativar = async (p: IaProvider) => {
    setErro(null)
    try {
      await applyMethod(`/api/apply/ia/${p.id}/active`, 'POST')
      await recarregar()
    } catch (e) {
      setErro(msgErr(e))
    }
  }

  /* Testar conexão: com id no form envia o corpo ainda não salvo;
   * a partir da lista, testa o provider salvo pelo id. */
  const testar = async (alvo?: IaProvider) => {
    setTestando(true)
    setTeste(null)
    setTesteDe(alvo ? alvo.id : 'form')
    setErro(null)
    const corpo = alvo ? { id: alvo.id } : {
      id: form.id, tipo: form.tipo, base_url: form.base_url.trim(),
      api_key: form.api_key.trim(), modelo: form.modelo.trim(),
    }
    try {
      const r = await applyMethod('/api/apply/ia/test', 'POST', corpo)
      setTeste(r.ok
        ? { ok: true, texto: `Pong recebido: "${(r.resposta || '').slice(0, 120)}"` }
        : { ok: false, texto: r.detalhe || 'Falha sem detalhe.' })
    } catch (e) {
      setErro(msgErr(e))
    } finally {
      setTestando(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* ── Lista de providers ── */}
      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
          Provedores configurados
        </div>
        {erro && !ia && <ErroBox text={erro} onRetry={recarregar} />}
        {ia && ia.providers.length === 0 && (
          <div className="mt-3 text-sm text-slate-400">
            Nenhum provedor. Preencha o formulário abaixo (aceita qualquer API compatível com OpenAI — Groq, OpenAI, Ollama, LM Studio, vLLM — ou a Anthropic).
          </div>
        )}
        <div className="mt-3 space-y-2">
          {(ia?.providers || []).map(p => {
            const ativo = ia?.ativo === p.id
            return (
              <div key={p.id}
                className={`rounded-xl border p-3 bg-slate-950/40 ${ativo ? 'border-emerald-500/40' : 'border-slate-800/70'}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-200">{p.nome || p.id}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full border border-slate-700 text-slate-400">{p.tipo}</span>
                  {p.api_key_masked && <span className="text-[11px] text-slate-500 font-mono">{p.api_key_masked}</span>}
                  {ativo && (
                    <span className="flex items-center gap-1 text-[11px] text-emerald-300">
                      <Star className="w-3 h-3 fill-emerald-300" /> ativo
                    </span>
                  )}
                </div>
                <div className="mt-1 text-[11px] text-slate-500">
                  {p.modelo}{p.base_url && <> · {p.base_url}</>}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {!ativo && (
                    <button onClick={() => ativar(p)} className={btnPrimary}>
                      <Star className="w-3.5 h-3.5" /> Usar como ativo
                    </button>
                  )}
                  <button onClick={() => editar(p)}
                    className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800/50 transition-colors">
                    <Pencil className="w-3.5 h-3.5" /> Editar
                  </button>
                  <button onClick={() => testar(p)} disabled={testando}
                    className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800/50 transition-colors disabled:opacity-50">
                    {testando && testeDe === p.id
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Zap className="w-3.5 h-3.5" />}
                    Testar
                  </button>
                  <button onClick={() => excluir(p)} className={btnDanger}>
                    <Trash2 className="w-3.5 h-3.5" /> Excluir
                  </button>
                </div>
                {teste && testeDe === p.id && (
                  <div className={`mt-2 text-xs rounded-xl px-3 py-2 border font-mono ${teste.ok
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : 'border-rose-500/30 bg-rose-500/10 text-rose-300'}`}>
                    {teste.ok ? '✅ ' : '❌ '}{teste.texto}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Form (criar / editar) ── */}
      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
          {form.id ? `Editando ${form.nome || form.id}` : 'Novo provedor'}
        </div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="Nome">
            <input className={inputCls} value={form.nome}
              onChange={e => setForm({ ...form, nome: e.target.value })}
              placeholder="Groq, Claude, Ollama local…" />
          </Campo>
          <Campo label="Tipo de API">
            <select className={inputCls} value={form.tipo}
              onChange={e => setForm({ ...form, tipo: e.target.value as IaForm['tipo'] })}>
              <option value="openai">OpenAI compatível (Groq, Ollama, LM Studio, vLLM…)</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </Campo>
          {form.tipo === 'openai' && (
            <Campo label="URL base (deixe vazio p/ OpenAI)">
              <input className={inputCls} value={form.base_url}
                onChange={e => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://api.groq.com/openai/v1" list="baseUrls" />
              <datalist id="baseUrls">
                {BASE_URLS_SUGERIDAS.map(u => <option key={u} value={u} />)}
              </datalist>
            </Campo>
          )}
          <Campo label="Modelo">
            <input className={inputCls} value={form.modelo}
              onChange={e => setForm({ ...form, modelo: e.target.value })}
              placeholder="llama-3.3-70b-versatile, claude-sonnet-5-5…" />
          </Campo>
          <Campo label={`API key ${form.id && !form.api_key ? '(vazio mantém a atual)' : ''}`}>
            <input type="password" className={inputCls} value={form.api_key}
              onChange={e => setForm({ ...form, api_key: e.target.value })}
              placeholder={ia?.providers.find(p => p.id === form.id)?.api_key_masked || 'sk-…'} />
          </Campo>
          <div className="grid grid-cols-2 gap-3">
            <Campo label="Temperatura">
              <input type="number" step="0.1" min="0" max="2" className={inputCls}
                value={form.temperatura} onChange={e => setForm({ ...form, temperatura: e.target.value })} />
            </Campo>
            <Campo label="Máx. tokens">
              <input type="number" min="32" className={inputCls}
                value={form.max_tokens} onChange={e => setForm({ ...form, max_tokens: e.target.value })} />
            </Campo>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={salvar} disabled={salvando || !form.modelo.trim()} className={btnPrimary}>
            {salvando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            {form.id ? 'Salvar alterações' : 'Adicionar provedor'}
          </button>
          <button onClick={() => testar()} disabled={testando || !form.modelo.trim()}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-50">
            {testando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Testar conexão
          </button>
          {form.id && (
            <button onClick={() => { setForm(FORM_VAZIO); setTeste(null) }}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800/50 transition-colors">
              <X className="w-3.5 h-3.5" /> Cancelar
            </button>
          )}
        </div>
        {teste && (
          <div className={`mt-3 text-xs rounded-xl px-3 py-2 border font-mono ${teste.ok
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-rose-500/30 bg-rose-500/10 text-rose-300'}`}>
            {teste.ok ? '✅ ' : '❌ '}{teste.texto}
          </div>
        )}
        {msg && <div className="mt-2 text-xs text-emerald-300">{msg}</div>}
        {erro && ia && <ErroBox text={erro} onRetry={recarregar} />}
      </div>
    </div>
  )
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  )
}

function ErroBox({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div className="mt-3 text-xs rounded-xl px-3 py-2 border border-rose-500/30 bg-rose-500/10 text-rose-300 flex items-center justify-between gap-3">
      <span>{text}</span>
      <button onClick={onRetry} className="shrink-0 text-rose-200 hover:text-white transition-colors">
        Tentar de novo
      </button>
    </div>
  )
}

function msgErr(e: unknown): string {
  return e instanceof Error ? e.message : 'Falha ao falar com o backend.'
}
