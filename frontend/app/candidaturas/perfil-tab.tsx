'use client'
import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { applyFetch, applyMethod, cardCls, btnPrimary, inputCls, labelCls, type ApplyConfig } from './apply-api'

/* A aba Perfil edita seções do config.yaml dos bots: dados do candidato,
 * localização, palavras de busca/negativas e pretensões. O backend grava o
 * YAML de volta (escrita atômica) — os bots leem a config na próxima execução. */
interface Perfil {
  nome: string; email: string; telefone: string; cidade_uf: string
  linkedin: string; github: string; portfolio: string
  nivel_ingles: string; dias: string
  data_nascimento: string; possui_pj: boolean
  pais: string; estado_nome: string; estado_uf: string; cidade_end: string
  raca_cor: string; genero: string; orientacao_sexual: string; pcd: boolean
  aceita_remoto: boolean; aceita_hibrido: boolean; aceita_presencial: boolean
  aceita_mudanca: boolean
  estados: string
  palavras_chave: string
  palavras_negativas: string
  nivel: string
  pretensao_clt: string; pretensao_pj_hora: string; pretensao_pj_mensal: string; pretensao_estagio: string
}

/* Opções fixas que os bots esperam no config (Gupy casa por substring,
 * Sólides mapeia p/ valores do select, Indeed por palavra-chave). */
const UF_BR = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']
const RACAS = ['Pardo','Branco','Preto','Amarelo','Indígena']
const GENEROS = ['Homem cisgênero','Mulher cisgênero','Homem transgênero','Mulher transgênero','Não-binário','Prefiro não responder']
const ORIENTACOES = ['Heterossexual','Homossexual','Bissexual','Prefiro não responder']

/* Valor já salvo fora da lista não é descartado: ele entra como opção extra,
 * senão o <select> some com o dado (e o React avisa sobre option ausente). */
function opcoes(lista: string[], atual: string): string[] {
  const valor = atual.trim()
  if (!valor || lista.some(x => x.toLowerCase() === valor.toLowerCase())) return ['', ...lista]
  return ['', valor, ...lista]
}

/* Data de nascimento: o config guarda DD/MM/AAAA (Sólides faz strptime
 * rígido nesse formato); o <input type="date"> só fala AAAA-MM-DD. */
function isoParaDmy(iso: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return ''
  const [ano, mes, dia] = iso.split('-')
  return `${dia}/${mes}/${ano}`
}
function dmyParaIso(dmy: unknown): string {
  const m = str(dmy).match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  return m ? `${m[3]}-${m[2]}-${m[1]}` : ''
}

function paraPerfil(cfg: ApplyConfig): Perfil {
  const c = cfg.candidato ?? {}
  const loc = cfg.localizacao ?? {}
  const busca = cfg.busca ?? {}
  const end = cfg.endereco ?? {}
  const div = cfg.diversidade ?? {}
  return {
    nome: str(c.nome), email: str(c.email), telefone: str(c.telefone),
    cidade_uf: str(c.cidade_uf), linkedin: str(c.linkedin), github: str(c.github),
    portfolio: str(c.portfolio), nivel_ingles: str(c.nivel_ingles),
    dias: str(c.disponibilidade_dias),
    data_nascimento: dmyParaIso(c.data_nascimento), possui_pj: !!c.possui_pj,
    pais: str(end.pais), estado_nome: str(end.estado_nome),
    estado_uf: str(end.estado_uf), cidade_end: str(end.cidade),
    raca_cor: str(div.raca_cor), genero: str(div.genero),
    orientacao_sexual: str(div.orientacao_sexual), pcd: !!div.pcd,
    aceita_remoto: !!loc.aceita_remoto, aceita_hibrido: !!loc.aceita_hibrido,
    aceita_presencial: !!loc.aceita_presencial, aceita_mudanca: !!loc.aceita_mudanca,
    estados: Array.isArray(loc.estados_aceitos) ? (loc.estados_aceitos as string[]).join(', ') : '',
    palavras_chave: Array.isArray(busca.palavras_chave) ? (busca.palavras_chave as string[]).join('\n') : '',
    palavras_negativas: Array.isArray(busca.palavras_excluir) ? (busca.palavras_excluir as string[]).join('\n') : '',
    nivel: Array.isArray(busca.nivel) ? (busca.nivel as string[]).join(', ') : '',
    pretensao_clt: str(c.pretensao_clt), pretensao_pj_hora: str(c.pretensao_pj_hora),
    pretensao_pj_mensal: str(c.pretensao_pj_mensal), pretensao_estagio: str(c.pretensao_estagio),
  }
}

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

export default function PerfilTab() {
  const [cfg, setCfg] = useState<ApplyConfig | null>(null)
  const [p, setP] = useState<Perfil | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const [sujo, setSujo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const carregar = () => {
    applyFetch<ApplyConfig>('/api/apply/config')
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

    // Monta um novo objeto em vez de mutar o cfg (valor de estado).
    const novoCfg: ApplyConfig = {
      ...cfg,
      candidato: {
        ...(cfg.candidato ?? {}),
        nome: p.nome, email: p.email, telefone: p.telefone,
        cidade_uf: p.cidade_uf, linkedin: p.linkedin, github: p.github,
        portfolio: p.portfolio, nivel_ingles: p.nivel_ingles,
        disponibilidade_dias: p.dias,
        data_nascimento: isoParaDmy(p.data_nascimento), possui_pj: p.possui_pj,
        pretensao_clt: p.pretensao_clt, pretensao_pj_hora: p.pretensao_pj_hora,
        pretensao_pj_mensal: p.pretensao_pj_mensal, pretensao_estagio: p.pretensao_estagio,
      },
      localizacao: {
        ...(cfg.localizacao ?? {}),
        aceita_remoto: p.aceita_remoto, aceita_hibrido: p.aceita_hibrido,
        aceita_presencial: p.aceita_presencial, aceita_mudanca: p.aceita_mudanca,
        estados_aceitos: p.estados.split(",").map(x => x.trim().toUpperCase()).filter(Boolean),
      },
      endereco: {
        ...(cfg.endereco ?? {}),
        pais: p.pais, estado_nome: p.estado_nome, estado_uf: p.estado_uf, cidade: p.cidade_end,
      },
      diversidade: {
        ...(cfg.diversidade ?? {}),
        raca_cor: p.raca_cor, genero: p.genero,
        orientacao_sexual: p.orientacao_sexual, pcd: p.pcd,
      },
      busca: {
        ...(cfg.busca ?? {}),
        palavras_chave: p.palavras_chave.split("\n").map(x => x.trim()).filter(Boolean),
        palavras_excluir: p.palavras_negativas.split("\n").map(x => x.trim()).filter(Boolean),
        nivel: p.nivel.split(",").map(x => x.trim()).filter(Boolean),
      },
    }

    try {
      await applyMethod<unknown>("/api/apply/config", "PUT", novoCfg)
      setSalvo(true)
      setSujo(false)
      setErro(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao salvar.")
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
          <Campo label="E-mail"><input type="email" className={inputCls} value={p.email} onChange={e => set('email', e.target.value)} placeholder="voce@exemplo.com" /></Campo>
          <Campo label="Telefone (com DDD)"><input inputMode="tel" className={inputCls} value={p.telefone} onChange={e => set('telefone', e.target.value)} placeholder="(16) 99999-9999" /></Campo>
          <Campo label="Cidade / UF"><input className={inputCls} value={p.cidade_uf} onChange={e => set('cidade_uf', e.target.value)} placeholder="Cidade - UF" /></Campo>
          <Campo label="Data de nascimento">
            <input type="date" className={inputCls} value={p.data_nascimento} onChange={e => set('data_nascimento', e.target.value)} />
          </Campo>
          <Campo label="Possui empresa aberta (PJ)">
            <label className="flex items-center gap-2 h-9.5 text-sm text-slate-300 cursor-pointer">
              <input type="checkbox" className="accent-indigo-500" checked={p.possui_pj}
                onChange={e => set('possui_pj', e.target.checked)} />
              Sim — o Nerdin responde a pergunta com isso
            </label>
          </Campo>
          <Campo label="LinkedIn"><input className={inputCls} value={p.linkedin} onChange={e => set('linkedin', e.target.value)} placeholder="https://linkedin.com/in/voce" /></Campo>
          <Campo label="GitHub"><input className={inputCls} value={p.github} onChange={e => set('github', e.target.value)} placeholder="https://github.com/voce" /></Campo>
          <Campo label="Portfólio"><input className={inputCls} value={p.portfolio} onChange={e => set('portfolio', e.target.value)} /></Campo>
          <Campo label="Nível de inglês">
            <select className={inputCls} value={p.nivel_ingles} onChange={e => set('nivel_ingles', e.target.value)}>
              {['', 'Basic', 'Intermediate', 'Advanced', 'Fluent'].map(n => <option key={n} value={n}>{n || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Disponibilidade (dias)"><input type="number" min={0} max={7} className={inputCls} value={p.dias} onChange={e => set('dias', e.target.value)} placeholder="ex.: 1" /></Campo>
        </div>
        {!p.data_nascimento && (
          <div className="mt-2 text-xs text-amber-300">
            Sólides e Indeed precisam da data de nascimento (DD/MM/AAAA) para responder as perguntas — preencha para evitar falha no formulário.
          </div>
        )}
      </div>

      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Endereço</div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="País"><input className={inputCls} value={p.pais} onChange={e => set('pais', e.target.value)} placeholder="Brasil" /></Campo>
          <Campo label="Estado (nome)"><input className={inputCls} value={p.estado_nome} onChange={e => set('estado_nome', e.target.value)} placeholder="São Paulo" /></Campo>
          <Campo label="UF">
            <select className={inputCls} value={p.estado_uf} onChange={e => set('estado_uf', e.target.value)}>
              {opcoes(UF_BR, p.estado_uf).map(u => <option key={u} value={u}>{u || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Cidade"><input className={inputCls} value={p.cidade_end} onChange={e => set('cidade_end', e.target.value)} placeholder="Cidade" /></Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Diversidade & inclusão</div>
        <div className="text-[11px] text-slate-500 mt-1">os portais (Gupy, InfoJobs, Sólides, Indeed) perguntam isso — os bots respondem com estes dados</div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="Raça / cor">
            <select className={inputCls} value={p.raca_cor} onChange={e => set('raca_cor', e.target.value)}>
              {opcoes(RACAS, p.raca_cor).map(r => <option key={r} value={r}>{r || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Gênero">
            <select className={inputCls} value={p.genero} onChange={e => set('genero', e.target.value)}>
              {opcoes(GENEROS, p.genero).map(g => <option key={g} value={g}>{g || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Orientação sexual">
            <select className={inputCls} value={p.orientacao_sexual} onChange={e => set('orientacao_sexual', e.target.value)}>
              {opcoes(ORIENTACOES, p.orientacao_sexual).map(o => <option key={o} value={o}>{o || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Pessoa com deficiência">
            <label className="flex items-center gap-2 h-9.5 text-sm text-slate-300 cursor-pointer">
              <input type="checkbox" className="accent-indigo-500" checked={p.pcd}
                onChange={e => set('pcd', e.target.checked)} />
              Sou PCD
            </label>
          </Campo>
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
          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
            <input type="checkbox" className="accent-indigo-500" checked={p.aceita_mudanca}
              onChange={e => set('aceita_mudanca', e.target.checked)} />
            Aceita mudança de cidade/estado (o Indeed filtra vagas por isso)
          </label>
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
          <Campo label="CLT (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_clt} onChange={e => set('pretensao_clt', e.target.value)} /></Campo>
          <Campo label="PJ hora (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_pj_hora} onChange={e => set('pretensao_pj_hora', e.target.value)} /></Campo>
          <Campo label="PJ mensal (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_pj_mensal} onChange={e => set('pretensao_pj_mensal', e.target.value)} /></Campo>
          <Campo label="Estágio (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_estagio} onChange={e => set('pretensao_estagio', e.target.value)} /></Campo>
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
