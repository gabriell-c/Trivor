'use client'
import { useEffect, useRef, useState } from 'react'
import {
  Play, Square, Loader2, FileTerminal, Pin, LogIn, LogOut, RefreshCw,
} from 'lucide-react'
import {
  applyFetch, applyMethod, BOT_NAMES,
  type BotRun, type BotSessao, type LoginState, type DeslogResult,
  cardCls, btnPrimary, btnDanger, btnGhost,
} from './apply-api'
import { SiteIcon, nomeDoSite } from './site-icons'

export default function ExecutarTab() {
  const [runs, setRuns] = useState<Record<string, BotRun> | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [focusBot, setFocusBot] = useState<string>('gupy')
  const [log, setLog] = useState<string[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [sesoes, setSesoes] = useState<Record<string, BotSessao> | null>(null)
  const [logins, setLogins] = useState<Record<string, LoginState>>({})
  const [busyLogin, setBusyLogin] = useState<string | null>(null)
  const [busyDeslog, setBusyDeslog] = useState<string | null>(null)
  const preRef = useRef<HTMLPreElement>(null)

  /* um bot começou a rodar e não é o escolhido → o painel de log acompanha
   * o bot em execução. É derivado no render (não setState dentro de effect,
   * que causaria render em cascata). */
  const runningBot = runs ? Object.values(runs).find(r => r.running) : undefined
  const focus = runningBot && !runs?.[focusBot]?.running ? runningBot.bot : focusBot
  const [logOrigem, setLogOrigem] = useState<'execucao' | 'login'>('execucao')
  const [backendOff, setBackendOff] = useState(false)

  /* poll único e consolidado: /api/apply/state devolve runs + log do bot em
   * destaque (da origem mais relevante, escolhida no backend) + sessões +
   * logins em 1 request. O diff JSON só atualiza o estado (e o re-render)
   * quando algo realmente mudou. Intervalo fixo de 3s: a rota é local e
   * barata, e o aviso "backend off" exige que o poll continue chegando. */
  const ultimaChaveRef = useRef('')
  useEffect(() => {
    let vivo = true
    const tick = async () => {
      try {
        const d = await applyFetch<{
          runs: Record<string, BotRun>
          log: { lines?: string[]; origem?: 'execucao' | 'login' } | null
          sesoes: BotSessao[] | null
          logins: Record<string, LoginState>
        }>(`/api/apply/state${focus ? `?focus=${focus}` : ''}`)
        if (!vivo) return
        const chave = JSON.stringify(d)
        if (chave === ultimaChaveRef.current) return
        ultimaChaveRef.current = chave
        setBackendOff(false)
        setRuns(d.runs)
        setLog(d.log?.lines ?? [])
        setLogOrigem(d.log?.origem ?? 'execucao')
        setSesoes(d.sesoes ? Object.fromEntries(d.sesoes.map(s => [s.bot, s])) : null)
        setLogins(d.logins ?? {})
      } catch {
        // backend fora no tick — mantém o último estado conhecido e avisa:
        // sem o banner, o painel pareceria vivo com dados fantasma
        setBackendOff(true)
      }
    }
    tick()
    const id = setInterval(tick, 3000)
    return () => { vivo = false; clearInterval(id) }
  }, [focus])

  useEffect(() => {
    if (autoScroll && preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [log, autoScroll])

  const agir = async (bot: string, acao: 'start' | 'stop') => {
    setBusy(acao === 'start' ? `iniciar-${bot}` : `parar-${bot}`)
    setMsg(null)
    try {
      const path = acao === 'start' ? '/api/apply/run' : '/api/apply/stop'
      await applyMethod(path, 'POST', { bot })
      setMsg({ kind: 'ok', text: acao === 'start'
        ? `${nomeDoSite(bot, sesoes)} iniciado — acompanhe o log abaixo (o navegador abre nesta máquina).`
        : `${nomeDoSite(bot, sesoes)} parado.` })
      setRuns(await applyFetch<Record<string, BotRun>>('/api/apply/runs'))
    } catch (e) {
      setMsg({ kind: 'err', text: `${nomeDoSite(bot, sesoes)}: ${e instanceof Error ? e.message : 'falha'}` })
    } finally {
      setBusy(null)
    }
  }

  const logar = async (bot: string) => {
    setBusyLogin(bot)
    setMsg(null)
    try {
      await applyMethod('/api/apply/login', 'POST', { bot })
      setLogins(prev => ({ ...prev, [bot]: { bot, estado: 'aguardando' } }))
      setMsg({ kind: 'ok', text: `${nomeDoSite(bot, sesoes)}: login iniciado — uma janela do browser vai abrir nesta máquina; finalize o login nela.` })
    } catch (e) {
      setMsg({ kind: 'err', text: `${nomeDoSite(bot, sesoes)}: ${e instanceof Error ? e.message : 'falha ao iniciar o login'}` })
    } finally {
      setBusyLogin(null)
    }
  }

  const pararLogin = async (bot: string) => {
    setBusyLogin(bot)
    setMsg(null)
    try {
      await applyMethod('/api/apply/login/stop', 'POST', { bot })
      setLogins(prev => ({ ...prev, [bot]: { bot, estado: 'inativo' } }))
      setMsg({ kind: 'ok', text: `${nomeDoSite(bot, sesoes)}: login cancelado.` })
    } catch (e) {
      setMsg({ kind: 'err', text: `${nomeDoSite(bot, sesoes)}: ${e instanceof Error ? e.message : 'falha ao cancelar o login'}` })
    } finally {
      setBusyLogin(null)
    }
  }

  /* Deslogar: apaga a sessão LOCAL do bot (perfis/pickles/storage_state) —
   * o .env nunca é tocado. Só onde a sessão existe (deslogavel). */
  const deslogar = async (bot: string) => {
    setBusyDeslog(bot)
    setMsg(null)
    try {
      const r = await applyMethod<DeslogResult>(`/api/apply/sesoes/${bot}/logout`, 'POST')
      setMsg({ kind: 'ok', text: `${nomeDoSite(bot, sesoes)}: ${r.mensagem}` })
      const atualizadas = await applyFetch<BotSessao[]>('/api/apply/sesoes')
      setSesoes(Object.fromEntries(atualizadas.map(s => [s.bot, s])))
    } catch (e) {
      setMsg({ kind: 'err', text: `${nomeDoSite(bot, sesoes)}: ${e instanceof Error ? e.message : 'falha ao deslogar'}` })
    } finally {
      setBusyDeslog(null)
    }
  }

  const carregando = runs === null || sesoes === null

  return (
    <div className="space-y-4">
      {/* Sites — uma linha por site: sessão (deslogar/logar) + execução */}
      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[13px] font-medium text-slate-400 uppercase tracking-wider">
            <Play className="w-4 h-4 text-indigo-300" />
            Sites
          </div>
          <span className="text-[13px] text-slate-500">sessão + execução por site</span>
        </div>
        {msg && (
          <div className={`mt-3 text-xs rounded-xl px-3 py-2 border ${msg.kind === 'ok'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-rose-500/30 bg-rose-500/10 text-rose-300'}`}>
            {msg.text}
          </div>
        )}
        {backendOff && (
          <div className="mt-3 text-xs rounded-xl px-3 py-2 border border-amber-500/30 bg-amber-500/10 text-amber-300">
            ⚠ sem conexão com o backend — os status acima podem estar desatualizados
          </div>
        )}
        {carregando ? (
          <div className="mt-3 space-y-2">
            {[0, 1, 2, 3, 4].map(i => <div key={i} className="h-16 rounded-xl bg-slate-800/40 animate-pulse" />)}
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {BOT_NAMES.map(name => {
              const s = sesoes?.[name]
              const l = logins[name]
              const run = runs?.[name]
              const isRunning = !!run?.running
              const aguardando = l?.estado === 'aguardando'
              const destacado = focus === name
              const ocupado = busy === `iniciar-${name}` || busy === `parar-${name}`
              const ocupadoLogin = busyLogin === name
              const ocupadoDeslog = busyDeslog === name

              /* status da sessão (o que a linha conta sobre "logado") —
               * "login concluído" só vale enquanto a sessão existir: após
               * Deslogar, tem_sessao é false e a linha volta a contar o
               * detalhe real da sessão */
              const loginConcluidoConta = l?.estado === 'concluido' && s?.tem_sessao
              const texto = aguardando
                ? '⏳ janela do browser aberta — finalize o login nela'
                : l?.estado === 'concluido' && !s?.tem_sessao
                  ? s?.detalhe ?? '…'
                  : loginConcluidoConta
                    ? 'login concluído — sessão atualizada'
                    : l?.estado === 'falhou'
                      ? `login falhou (código ${l.exit_code ?? '?'})`
                      : s?.detalhe ?? '…'
              const cor = l?.estado === 'falhou'
                ? 'bg-rose-400'
                : aguardando
                  ? 'bg-amber-400 animate-pulse'
                  : isRunning
                    ? 'bg-emerald-400 animate-pulse'
                    : s?.tem_sessao
                      ? 'bg-emerald-400'
                      : 'bg-slate-600'

              return (
                <div key={name}
                  className={`rounded-xl border p-3 bg-slate-950/40 transition-colors ${destacado
                    ? 'border-indigo-500/40'
                    : 'border-slate-800/70'}`}>
                  <div className="flex items-center gap-3">
                    <SiteIcon bot={name} />
                    <div className="flex-1 min-w-0">
                      <button onClick={() => setFocusBot(name)}
                        className="text-sm font-medium text-slate-200 hover:text-indigo-300 transition-colors"
                        title="Ver o log deste site abaixo">
                        {nomeDoSite(name, sesoes)}
                      </button>
                      <div aria-live="polite" className="text-[13px] text-slate-500 truncate">
                        {isRunning && run?.started_at
                          ? `rodando desde ${new Date(run.started_at).toLocaleTimeString('pt-BR')} · `
                          : ''}
                        {texto}
                      </div>
                    </div>
                    <span aria-hidden className={`w-2 h-2 rounded-full shrink-0 ${cor}`} />
                    {s?.deslogavel && (
                      <button onClick={() => deslogar(name)}
                        disabled={ocupadoDeslog || isRunning || aguardando}
                        className={btnGhost}
                        title="Apagar a sessão local — o próximo Logar será do zero">
                        {ocupadoDeslog
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <LogOut className="w-3.5 h-3.5" />}
                        Deslogar
                      </button>
                    )}
                    {aguardando ? (
                      <button onClick={() => pararLogin(name)} disabled={ocupadoLogin} className={btnDanger}>
                        {ocupadoLogin
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Square className="w-3.5 h-3.5" />}
                        Cancelar
                      </button>
                    ) : (
                      <button onClick={() => logar(name)}
                        disabled={ocupadoLogin || isRunning}
                        className={btnPrimary}>
                        {ocupadoLogin
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : s?.tem_sessao
                            ? <RefreshCw className="w-3.5 h-3.5" />
                            : <LogIn className="w-3.5 h-3.5" />}
                        {s?.tem_sessao ? 'Renovar' : 'Logar'}
                      </button>
                    )}
                    {isRunning ? (
                      <button onClick={() => agir(name, 'stop')} disabled={ocupado} className={btnDanger}>
                        {ocupado
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Square className="w-3.5 h-3.5" />}
                        Parar
                      </button>
                    ) : (
                      <button onClick={() => agir(name, 'start')}
                        disabled={ocupado || aguardando}
                        className={btnPrimary}>
                        {ocupado
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Play className="w-3.5 h-3.5" />}
                        Iniciar
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* log em tempo real do bot em destaque */}
      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <FileTerminal className="w-4 h-4 text-indigo-300" />
            <span className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">
              Log em tempo real · {nomeDoSite(focus, sesoes)}
            </span>
            {logOrigem === 'login' && (
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                login
              </span>
            )}
            {runs?.[focus]?.running && (
              <span className="flex items-center gap-1.5 text-[13px] text-emerald-300">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> rodando
              </span>
            )}
          </div>
          <label className="flex items-center gap-1.5 text-[13px] text-slate-400 cursor-pointer">
            <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)}
              className="accent-indigo-500" />
            <Pin className="w-3 h-3" /> acompanhar fim
          </label>
        </div>
        <pre ref={preRef}
          className="mt-3 h-[340px] overflow-y-auto rounded-xl bg-slate-950/70 border border-slate-800/70 p-3 text-[13px] leading-relaxed text-slate-300 font-mono whitespace-pre-wrap">
          {log.length === 0
            ? 'Sem log ainda — inicie o site ou faça um login para ver o passo a passo.'
            : log.join('\n')}
        </pre>
      </div>
    </div>
  )
}
