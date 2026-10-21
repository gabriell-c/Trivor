'use client'
import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { applyFetch, applyMethod, cardCls, btnPrimary, inputCls, labelCls } from './apply-api'

/* A aba Perfil edita seções do config.yaml dos bots: dados do candidato,
 * localização, palavras de busca/negativas e pretensões. O backend grava o
 * YAML de volta (escrita atômica) — os bots leem a config na próxima execução. */
interface Perfil {
  nome: string; email: string; telefone: string; cidade_uf: string
  linkedin: string; github: string; portfolio: string
  nivel_ingles: string; dias: string
  aceita_remoto: boolean; aceita_hibrido: boolean; aceita_presencial: boolean
  estados: string
  palavras_chave: string
  palavras_negativas: string
  nivel: string
  pretensao_clt: string; pretensao_pj_hora: string; pretensao_pj_mensal: string; pretensao_estagio: string
}

function paraPerfil(cfg: any): Perfil {
  const c = cfg.candidato || {}
  const loc = cfg.localizacao || {}
  const busca = cfg.busca || {}
  return {
    nome: str(c.nome), email: str(c.email), telefone: str(c.telefone),
    cidade_uf: str(c.cidade_uf), linkedin: str(c.linkedin), github: str(c.github),
    portfolio: str(c.portfolio), nivel_ingles: str(c.nivel_ingles),
    dias: str(c.dias),
    aceita_remoto: !!loc.aceita_remoto, aceita_hibrido: !!loc.aceita_hibrido,
    aceita_presencial: !!loc.aceita_presencial,
    estados: Array.isArray(loc.estados_aceitos) ? loc.estados_aceitos.join(', ') : '',
    palavras_chave: Array.isArray(busca.palavras_chave) ? busca.palavras_chave.join('\n') : '',
    palavras_negativas: Array.isArray(busca.palavras_excluir) ? busca.palavras_excluir.join('\n') : '',
    nivel: Array.isArray(busca.nivel) ? busca.nivel.join(', ') : '',
    pretensao_clt: str(c.pretensao_clt), pretensao_pj_hora: str(c.pretensao_pj_hora),
    pretensao_pj_mensal: str(c.pretensao_pj_mensal), pretensao_estagio: str(c.pretensao_estagio),
  }
}

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

export default function PerfilTab() {
  const [cfg, setCfg] = useState<any | null>(null)
  const [p, setP] = useState<Perfil | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const [sujo, setSujo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const carregar = () => {
    applyFetch('/api/apply/config')
      .then(c => {
        setCfg(c)
        setP(paraPerfil(c))
        setSujo(false)
        setErro(null)
      })
      .catch(e => setErro(e instanceof Error ? e.message : 'Falha ao carregar a config.'))
  }
  useEffect(() => { carregar() }, [])

  const salvar = async () => {
    if (!cfg || !p) return
    setSalvando(true)
    setSalvo(false)
    const cand = cfg.candidato || {}
    cand.nome = p.nome; cand.email = p.email; cand.telefone = p.telefone
    cand.cidade_uf = p.cidade_uf; cand.linkedin = p.linkedin; cand.github = p.github
    cand.portfolio = p.portfolio; cand.nivel_ingles = p.nivel_ingles; cand.dias = p.dias
    cand.pretensao_clt = p.pretensao_clt
    cand.pretensao_pj_hora = p.pretensao_pj_hora
    cand.pretensao_pj_mensal = p.pretensao_pj_mensal
    cand.pretensao_estagio = p.pretensao_estagio
    cfg.candidato = cand

    const loc = cfg.localizacao || {}
    loc.aceita_remoto = p.aceita_remoto; loc.aceita_hibrido = p.aceita_hibrido
    loc.aceita_presencial = p.aceita_presencial
    loc.estados_aceitos = p.estados.split(',').map(s => s.trim().toUpperCase()).filter(Boolean)
    cfg.localizacao = loc

    const busca = cfg.busca || {}
    busca.palavras_chave = p.palavras_chave.split('\n').map(s => s.trim()).filter(Boolean)
    busca.palavras_excluir = p.palavras_negativas.split('\n').map(s => s.trim()).filter(Boolean)
    busca.nivel = p.nivel.split(',').map(s => s.trim()).filter(Boolean)
    cfg.busca = busca

    try {
      await applyMethod('/api/apply/config', 'PUT', cfg)
      setSalvo(true)
      setSujo(false)
      setErro(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao salvar.')
    } finally {
      setSalvando(false)
    }
  }

  if (erro && !p) {
    return (
      <div className={`${cardCls} text-sm text-rose-300`}>
        {erro}
        <button onClick={carregar} className="mt-2 text-xs text-rose-200 underline">
          Tentar de novo
        </button>
      </div>
    )
  }
  if (!p) {
    return <div className={cardCls}><div className="h-48 animate-pulse rounded-xl bg-slate-800/50" /></div>
  }

  const set = (k: keyof Perfil, v: string | boolean) => {
    setP(prev => (prev ? { ...prev, [k]: v } : prev))
    setSujo(true)
  }

  return (
    <div className="space-y-4">
      <div className={cardCls}>
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
            Informações pessoais
          </div>
          <span className="text-[11px] text-slate-500">os bots preenchem os portais com isso</span>
        </div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="Nome"><input className={inputCls} value={p.nome} onChange={e => set('nome', e.target.value)} /></Campo>
          <Campo label="E-mail"><input className={inputCls} value={p.email} onChange={e => set('email', e.target.value)} /></Campo>
          <Campo label="Telefone"><input className={inputCls} value={p.telefone} onChange={e => set('telefone', e.target.value)} /></Campo>
          <Campo label="Cidade / UF"><input className={inputCls} value={p.cidade_uf} onChange={e => set('cidade_uf', e.target.value)} /></Campo>
          <Campo label="LinkedIn"><input className={inputCls} value={p.linkedin} onChange={e => set('linkedin', e.target.value)} placeholder="https://linkedin.com/in/voce" /></Campo>
          <Campo label="GitHub"><input className={inputCls} value={p.github} onChange={e => set('github', e.target.value)} placeholder="https://github.com/voce" /></Campo>
          <Campo label="Portfólio"><input className={inputCls} value={p.portfolio} onChange={e => set('portfolio', e.target.value)} /></Campo>
          <Campo label="Nível de inglês">
            <select className={inputCls} value={p.nivel_ingles} onChange={e => set('nivel_ingles', e.target.value)}>
              {['', 'Basic', 'Intermediate', 'Advanced', 'Fluent'].map(n => <option key={n} value={n}>{n || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Disponibilidade (dias)"><input className={inputCls} value={p.dias} onChange={e => set('dias', e.target.value)} placeholder="ex.: 1" /></Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Localização</div>
        <div className="mt-3 flex flex-wrap gap-4">
          {([['aceita_remoto', 'Remoto'], ['aceita_hibrido', 'Híbrido'], ['aceita_presencial', 'Presencial']] as const)
            .map(([k, rotulo]) => (
              <label key={k} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input type="checkbox" className="accent-indigo-500" checked={p[k]}
                  onChange={e => set(k, e.target.checked)} />
                {rotulo}
              </label>
            ))}
        </div>
        <div className="mt-3">
          <Campo label="Estados aceitos (separe por vírgula)">
            <input className={inputCls} value={p.estados} onChange={e => set('estados', e.target.value)}
              placeholder="SP, MG" />
          </Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Busca</div>
        <div className="mt-3 grid gap-3">
          <Campo label="Níveis alvo (vírgula)"><input className={inputCls} value={p.nivel} onChange={e => set('nivel', e.target.value)} placeholder="estágio, júnior" /></Campo>
          <Campo label="Palavras-chave (uma por linha)">
            <textarea className={`${inputCls} h-28 font-mono text-xs`} value={p.palavras_chave}
              onChange={e => set('palavras_chave', e.target.value)} placeholder={'analista de ti\nestagiário de sistemas'} />
          </Campo>
          <Campo label="Palavras negativas — vagas com qualquer uma dessas são puladas (uma por linha)">
            <textarea className={`${inputCls} h-24 font-mono text-xs border-rose-500/20`} value={p.palavras_negativas}
              onChange={e => set('palavras_negativas', e.target.value)} placeholder={'sênior\nplantão'} />
          </Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Pretensões salariais</div>
        <div className="mt-3 grid sm:grid-cols-4 gap-3">
          <Campo label="CLT (R$)"><input className={inputCls} value={p.pretensao_clt} onChange={e => set('pretensao_clt', e.target.value)} /></Campo>
          <Campo label="PJ hora (R$)"><input className={inputCls} value={p.pretensao_pj_hora} onChange={e => set('pretensao_pj_hora', e.target.value)} /></Campo>
          <Campo label="PJ mensal (R$)"><input className={inputCls} value={p.pretensao_pj_mensal} onChange={e => set('pretensao_pj_mensal', e.target.value)} /></Campo>
          <Campo label="Estágio (R$)"><input className={inputCls} value={p.pretensao_estagio} onChange={e => set('pretensao_estagio', e.target.value)} /></Campo>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={salvar} disabled={salvando} className={btnPrimary}>
          {salvando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Salvar perfil
        </button>
        {sujo && (
          <button onClick={() => { setSujo(false); setSalvo(false); carregar() }}
            disabled={salvando}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800/50 transition-colors">
            Descartar alterações
          </button>
        )}
        {salvo && <span className="text-xs text-emerald-300">Salvo — os próximos bots já usam esses dados.</span>}
        {sujo && !salvo && <span className="text-xs text-amber-300">Alterações não salvas</span>}
        {erro && p && <span className="text-xs text-rose-300">{erro}</span>}
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
