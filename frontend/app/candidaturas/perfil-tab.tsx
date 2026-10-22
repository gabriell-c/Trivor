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
  logradouro: string; numero: string; complemento: string; bairro: string; cep: string
  raca_cor: string; genero: string; orientacao_sexual: string; pcd: boolean
  aceita_remoto: boolean; aceita_hibrido: boolean; aceita_presencial: boolean
  aceita_mudanca: boolean
  estados: string
  palavras_chave: string
  palavras_negativas: string
  nivel: string
  tecnologias: string
  pretensao_clt: string; pretensao_pj_hora: string; pretensao_pj_mensal: string; pretensao_estagio: string
  formacaoCurso: string; formacaoInstituicao: string; formacaoAno: string; formacaoSituacao: string
  certificacoes: string; experiencia: string; idiomas: string; sobre: string
  inicio: string; horasSemana: string
}

/* Segredos que a aba gerencia no apply/.env — mesma lista do backend
 * (APPLY_ENV_KEYS); *_SENHA chegam mascaradas do GET. */
type EnvApply = Record<string, string>

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
    logradouro: str(end.logradouro), numero: str(end.numero),
    complemento: str(end.complemento), bairro: str(end.bairro), cep: str(end.cep),
    raca_cor: str(div.raca_cor), genero: str(div.genero),
    orientacao_sexual: str(div.orientacao_sexual), pcd: !!div.pcd,
    aceita_remoto: !!loc.aceita_remoto, aceita_hibrido: !!loc.aceita_hibrido,
    aceita_presencial: !!loc.aceita_presencial, aceita_mudanca: !!loc.aceita_mudanca,
    estados: Array.isArray(loc.estados_aceitos) ? (loc.estados_aceitos as string[]).join(', ') : '',
    palavras_chave: Array.isArray(busca.palavras_chave) ? (busca.palavras_chave as string[]).join('\n') : '',
    palavras_negativas: Array.isArray(busca.palavras_excluir) ? (busca.palavras_excluir as string[]).join('\n') : '',
    nivel: Array.isArray(busca.nivel) ? (busca.nivel as string[]).join(', ') : '',
    tecnologias: Object.entries((cfg.tecnologias as Record<string, unknown>) ?? {})
      .map(([nome, nv]) => `${nome}: ${str(nv)}`).join('\n'),
    pretensao_clt: str(c.pretensao_clt), pretensao_pj_hora: str(c.pretensao_pj_hora),
    pretensao_pj_mensal: str(c.pretensao_pj_mensal), pretensao_estagio: str(c.pretensao_estagio),
    formacaoCurso: str((c.formacao as Record<string, unknown> | undefined)?.curso),
    formacaoInstituicao: str((c.formacao as Record<string, unknown> | undefined)?.instituicao),
    formacaoAno: str((c.formacao as Record<string, unknown> | undefined)?.ano_conclusao),
    formacaoSituacao: str((c.formacao as Record<string, unknown> | undefined)?.situacao),
    certificacoes: paraLista(c.certificacoes),
    experiencia: paraLista(c.experiencia),
    idiomas: paraLista(c.idiomas),
    sobre: str(c.sobre),
    inicio: str(c.inicio),
    horasSemana: str(c.horas_semana),
  }
}

/* "Python: Avançado" (uma por linha) → dict p/ o config.yaml. Linha sem
 * "nome: nível" é descartada (o bot espera o formato nome→nível). */
function paraTecnologias(texto: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const linha of texto.split('\n').map(l => l.trim()).filter(Boolean)) {
    const i = linha.indexOf(':')
    if (i <= 0) continue
    out[linha.slice(0, i).trim()] = linha.slice(i + 1).trim()
  }
  return out
}

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

/* O config guarda listas (certificações, experiências, idiomas) como
 * arrays de linhas; a UI edita tudo em um textarea, uma linha por item. */
function paraLista(v: unknown): string {
  if (Array.isArray(v)) return v.map(x => str(x)).join('\n')
  return str(v)
}
function paraLinhas(texto: string): string[] {
  return texto.split('\n').map(x => x.trim()).filter(Boolean)
}

export default function PerfilTab() {
  const [cfg, setCfg] = useState<ApplyConfig | null>(null)
  const [p, setP] = useState<Perfil | null>(null)
  const [env, setEnv] = useState<EnvApply | null>(null)
  const [envSujo, setEnvSujo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const [sujo, setSujo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  /* "Ver o contexto da IA" — o bloco exato que os bots injetam nos prompts
   * (GET /api/apply/perfil-contexto), para conferir se a IA enxerga tudo. */
  const [ctxIa, setCtxIa] = useState<string | null>(null)
  const [ctxErro, setCtxErro] = useState<string | null>(null)

  const verContextoIa = () => {
    if (ctxIa !== null) { setCtxIa(null); return }
    setCtxErro(null)
    applyFetch<{ texto: string }>('/api/apply/perfil-contexto')
      .then(r => setCtxIa(r.texto))
      .catch(e => setCtxErro(e instanceof Error ? e.message : 'Falha ao carregar o contexto.'))
  }

  const carregar = () => {
    applyFetch<ApplyConfig>('/api/apply/config')
      .then(c => {
        setCfg(c)
        setP(paraPerfil(c))
        setSujo(false)
      })
      .catch(e => setErro(e instanceof Error ? e.message : 'Falha ao carregar a config.'))
    applyFetch<EnvApply>('/api/apply/env')
      .then(v => { setEnv(v); setEnvSujo(false) })
      .catch(e => setErro(e instanceof Error ? e.message : 'Falha ao carregar os segredos (.env).'))
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
        formacao: {
          curso: p.formacaoCurso, instituicao: p.formacaoInstituicao,
          ano_conclusao: p.formacaoAno, situacao: p.formacaoSituacao,
        },
        certificacoes: paraLinhas(p.certificacoes),
        experiencia: paraLinhas(p.experiencia),
        idiomas: paraLinhas(p.idiomas),
        sobre: p.sobre,
        inicio: p.inicio,
        horas_semana: p.horasSemana,
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
        logradouro: p.logradouro, numero: p.numero, complemento: p.complemento,
        bairro: p.bairro, cep: p.cep,
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
      tecnologias: paraTecnologias(p.tecnologias),
    }

    try {
      await applyMethod<unknown>("/api/apply/config", "PUT", novoCfg)
      // .env só é reescrito se a UI mexeu nele (evita sobrescrever chave
      // que o usuário editou manualmente entre o load e o save).
      if (envSujo && env) await applyMethod<unknown>("/api/apply/env", "PUT", env)
      setSalvo(true)
      setSujo(false)
      setEnvSujo(false)
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

  const setEnvField = (k: string, v: string) => {
    setEnv(prev => (prev ? { ...prev, [k]: v } : prev))
    setEnvSujo(true)
  }

  return (
    <div className="space-y-4">
      <div className={cardCls}>
        <div className="flex items-center justify-between">
          <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">
            Informações pessoais
          </div>
          <span className="text-[13px] text-slate-500">os bots preenchem os portais com isso</span>
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
        <div className="flex items-center justify-between">
          <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Endereço</div>
          <span className="text-[13px] text-slate-500">o bot preenche o formulário de endereço com isso</span>
        </div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="País"><input className={inputCls} value={p.pais} onChange={e => set('pais', e.target.value)} placeholder="Brasil" /></Campo>
          <Campo label="Estado (nome)"><input className={inputCls} value={p.estado_nome} onChange={e => set('estado_nome', e.target.value)} placeholder="São Paulo" /></Campo>
          <Campo label="UF">
            <select className={inputCls} value={p.estado_uf} onChange={e => set('estado_uf', e.target.value)}>
              {opcoes(UF_BR, p.estado_uf).map(u => <option key={u} value={u}>{u || '—'}</option>)}
            </select>
          </Campo>
          <Campo label="Cidade"><input className={inputCls} value={p.cidade_end} onChange={e => set('cidade_end', e.target.value)} placeholder="Cidade" /></Campo>
          <Campo label="Logradouro"><input className={inputCls} value={p.logradouro} onChange={e => set('logradouro', e.target.value)} placeholder="Av. Brasil" /></Campo>
          <Campo label="Número"><input className={inputCls} value={p.numero} onChange={e => set('numero', e.target.value)} placeholder="123 ou S/N" /></Campo>
          <Campo label="Complemento"><input className={inputCls} value={p.complemento} onChange={e => set('complemento', e.target.value)} placeholder="Apto 42" /></Campo>
          <Campo label="Bairro"><input className={inputCls} value={p.bairro} onChange={e => set('bairro', e.target.value)} placeholder="Centro" /></Campo>
          <Campo label="CEP"><input className={inputCls} value={p.cep} onChange={e => set('cep', e.target.value)} placeholder="14010-000" /></Campo>
        </div>
        <p className="mt-2 text-[13px] text-slate-500">
          Se você preencher o bloco “Endereço (.env)” abaixo, ele tem prioridade sobre estes valores nos bots.
        </p>
      </div>

      <div className={cardCls}>
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Diversidade & inclusão</div>
        <div className="text-[13px] text-slate-500 mt-1">os portais (Gupy, InfoJobs, Sólides, Indeed) perguntam isso — os bots respondem com estes dados</div>
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
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Localização</div>
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
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Busca</div>
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
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Pretensões salariais</div>
        <div className="mt-3 grid sm:grid-cols-4 gap-3">
          <Campo label="CLT (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_clt} onChange={e => set('pretensao_clt', e.target.value)} /></Campo>
          <Campo label="PJ hora (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_pj_hora} onChange={e => set('pretensao_pj_hora', e.target.value)} /></Campo>
          <Campo label="PJ mensal (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_pj_mensal} onChange={e => set('pretensao_pj_mensal', e.target.value)} /></Campo>
          <Campo label="Estágio (R$)"><input type="number" min={0} className={inputCls} value={p.pretensao_estagio} onChange={e => set('pretensao_estagio', e.target.value)} /></Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Tecnologias &amp; Conhecimentos</div>
        <div className="text-[13px] text-slate-500 mt-1">
          usadas pelo Indeed (perguntas de experiência) e pelo Nerdin (contexto do LLM) — uma por linha, no formato <code className="text-slate-400">tecnologia: nível</code>
        </div>
        <div className="mt-3">
          <Campo label="Tecnologias (nome: nível — uma por linha)">
            <textarea
              className={`${inputCls} h-28 font-mono text-xs`}
              value={p.tecnologias}
              onChange={e => set('tecnologias', e.target.value)}
              placeholder={'Python: Pleno\nSQL: Básico\ndbt: Acadêmico'}
            />
          </Campo>
        </div>
      </div>

      <div className={cardCls}>
        <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Formação &amp; Experiência</div>
        <div className="text-[13px] text-slate-500 mt-1">
          a IA usa isso nas perguntas abertas dos portais (Gupy, InfoJobs, Indeed, Sólides, Nerdin)
        </div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <Campo label="Curso"><input className={inputCls} value={p.formacaoCurso} onChange={e => set('formacaoCurso', e.target.value)} placeholder="Engenharia de Software" /></Campo>
          <Campo label="Instituição"><input className={inputCls} value={p.formacaoInstituicao} onChange={e => set('formacaoInstituicao', e.target.value)} placeholder="Estácio" /></Campo>
          <Campo label="Ano de conclusão"><input className={inputCls} value={p.formacaoAno} onChange={e => set('formacaoAno', e.target.value)} placeholder="2029" /></Campo>
          <Campo label="Situação"><input className={inputCls} value={p.formacaoSituacao} onChange={e => set('formacaoSituacao', e.target.value)} placeholder="Cursando / Concluído" /></Campo>
          <Campo label="Início"><input className={inputCls} value={p.inicio} onChange={e => set('inicio', e.target.value)} placeholder="Imediata" /></Campo>
          <Campo label="Horas por semana"><input type="number" min={0} className={inputCls} value={p.horasSemana} onChange={e => set('horasSemana', e.target.value)} placeholder="40" /></Campo>
        </div>
        <div className="mt-3 grid gap-3">
          <Campo label="Certificações (nome: ano — uma por linha)">
            <textarea className={`${inputCls} h-20 font-mono text-xs`} value={p.certificacoes}
              onChange={e => set('certificacoes', e.target.value)}
              placeholder={'AWS Cloud Practitioner: 2025\nHTML: 2024'} />
          </Campo>
          <Campo label="Experiência & projetos (uma por linha)">
            <textarea className={`${inputCls} h-24 font-mono text-xs`} value={p.experiencia}
              onChange={e => set('experiencia', e.target.value)}
              placeholder={'Freelancer Python/React: 2022-2026\nProjeto X (GitHub): 2024'} />
          </Campo>
          <Campo label="Idiomas (idioma: nível — uma por linha)">
            <textarea className={`${inputCls} h-20 font-mono text-xs`} value={p.idiomas}
              onChange={e => set('idiomas', e.target.value)}
              placeholder={'Espanhol: Básico\nFrancês: Intermediário'} />
          </Campo>
          <Campo label="Sobre si (1-2 frases — para perguntas como 'fale sobre você')">
            <textarea className={`${inputCls} h-16 text-xs`} value={p.sobre}
              onChange={e => set('sobre', e.target.value)} />
          </Campo>
        </div>
      </div>

      {ctxIa !== null && (
        <div className={cardCls}>
          <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Contexto que a IA recebe</div>
          <p className="text-[13px] text-slate-500 mt-1">
            o exato bloco que os bots injetam nos prompts — gerado do config + .env salvos (exclui alterações acima não salvas)
          </p>
          <pre className="mt-3 rounded-xl border border-slate-800/60 bg-slate-950/60 p-3 text-xs font-mono text-slate-300 whitespace-pre-wrap overflow-auto max-h-96">{ctxIa}</pre>
        </div>
      )}

      {env && (
        <>
          <div className={cardCls}>
            <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Documentos &amp; Filiação</div>
            <div className="text-[13px] text-slate-500 mt-1">
              salvos no <code className="text-slate-400">apply/.env</code> — os portais (Indeed, Gupy, Sólides) pedem isso no formulário
            </div>
            <div className="mt-3 grid sm:grid-cols-2 gap-3">
              <Campo label="CPF"><input className={inputCls} value={env.CANDIDATO_CPF ?? ''} onChange={e => setEnvField('CANDIDATO_CPF', e.target.value)} placeholder="000.000.000-00" /></Campo>
              <Campo label="RG"><input className={inputCls} value={env.CANDIDATO_RG ?? ''} onChange={e => setEnvField('CANDIDATO_RG', e.target.value)} placeholder="0000000-0" /></Campo>
              <Campo label="CNH"><input className={inputCls} value={env.CANDIDATO_CNH ?? ''} onChange={e => setEnvField('CANDIDATO_CNH', e.target.value)} placeholder="000000000-0" /></Campo>
              <Campo label="Nacionalidade">
                <input className={inputCls} value={env.CANDIDATO_NACIONALIDADE ?? ''} onChange={e => setEnvField('CANDIDATO_NACIONALIDADE', e.target.value)} placeholder="Brasileiro" />
              </Campo>
              <Campo label="Nome do pai">
                <input className={inputCls} value={env.CANDIDATO_NOME_PAI ?? ''} onChange={e => setEnvField('CANDIDATO_NOME_PAI', e.target.value)} placeholder="para a pergunta de filiação" />
              </Campo>
              <Campo label="Nome da mãe">
                <input className={inputCls} value={env.CANDIDATO_NOME_MAE ?? ''} onChange={e => setEnvField('CANDIDATO_NOME_MAE', e.target.value)} placeholder="para a pergunta de filiação" />
              </Campo>
            </div>
          </div>

          <div className={cardCls}>
            <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Endereço (.env)</div>
            <div className="text-[13px] text-slate-500 mt-1">
              quando preenchido, tem <b className="text-slate-400">prioridade</b> sobre o bloco Endereço acima nos bots
            </div>
            <div className="mt-3 grid sm:grid-cols-2 gap-3">
              {([['ENDERECO_LOGRADOURO', 'Logradouro'], ['ENDERECO_NUMERO', 'Número'], ['ENDERECO_COMPLEMENTO', 'Complemento'], ['ENDERECO_BAIRRO', 'Bairro'], ['ENDERECO_CEP', 'CEP'], ['ENDERECO_CIDADE', 'Cidade'], ['ENDERECO_ESTADO', 'Estado']] as const)
                .map(([k, rotulo]) => (
                  <Campo key={k} label={rotulo}>
                    <input className={inputCls} value={env[k] ?? ''} onChange={e => setEnvField(k, e.target.value)} />
                  </Campo>
                ))}
            </div>
          </div>

          <div className={cardCls}>
            <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">Credenciais dos Portais</div>
            <div className="text-[13px] text-slate-500 mt-1">
              salvos no <code className="text-slate-400">apply/.env</code> para o bot logar sozinho — senha aparece mascarada;
              para trocar, digite a nova completa; sem mexer na senha, ela não é reescrita
            </div>
            <div className="mt-3 grid sm:grid-cols-2 gap-3">
              {([['gupy', 'Gupy'], ['infojobs', 'InfoJobs'], ['nerdin', 'Nerdin'], ['solides', 'Sólides']] as const)
                .map(([nome, rotulo]) => (
                  <div key={nome} className="rounded-xl border border-slate-800 p-3 space-y-2.5">
                    <div className="text-xs font-semibold text-slate-300">{rotulo}</div>
                    <Campo label="E-mail">
                      <input type="email" className={inputCls} value={env[`${nome}_EMAIL`.toUpperCase()] ?? ''}
                        onChange={e => setEnvField(`${nome}_EMAIL`.toUpperCase(), e.target.value)} />
                    </Campo>
                    <Campo label="Senha">
                      <input type="password" className={inputCls} value={env[`${nome}_SENHA`.toUpperCase()] ?? ''}
                        onChange={e => setEnvField(`${nome}_SENHA`.toUpperCase(), e.target.value)}
                        placeholder="•••• (mascarada — para manter, não mexa)" />
                    </Campo>
                  </div>
                ))}
            </div>
          </div>
        </>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={salvar} disabled={salvando} className={btnPrimary}>
          {salvando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Salvar perfil
        </button>
        {(sujo || envSujo) && (
          <button onClick={() => { setSujo(false); setEnvSujo(false); setSalvo(false); carregar() }}
            disabled={salvando}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800/50 transition-colors">
            Descartar alterações
          </button>
        )}
        <button onClick={verContextoIa}
          className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800/50 transition-colors">
          {ctxIa !== null ? 'Fechar contexto da IA' : 'Ver o contexto da IA'}
        </button>
        {ctxErro && <span className="text-xs text-rose-300">{ctxErro}</span>}
        {salvo && <span className="text-xs text-emerald-300">Salvo — os próximos bots já usam esses dados.</span>}
        {(sujo || envSujo) && !salvo && <span className="text-xs text-amber-300">Alterações não salvas</span>}
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
