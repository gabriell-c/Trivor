'use client'
import { useEffect, useRef, useState } from 'react'
import { Play, Square, Loader2, FileTerminal, Pin, KeyRound, LogIn } from 'lucide-react'
import {
  applyFetch, applyMethod, BOT_NAMES,
  type BotRun, type BotSessao, type LoginState,
  cardCls, btnPrimary, btnDanger,
} from './apply-api'

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
  const preRef = useRef<HTMLPreElement>(null)
  const anyRunning = !!runs && Object.values(runs).some(r => r.running)

  /* um bot começou a rodar e não é o escolhido → o painel de log acompanha
   * o bot em execução. É derivado no render (não setState dentro de effect,
   * que causaria render em cascata). */
  const runningBot = runs ? Object.values(runs).find(r => r.running) : undefined
  const focus = runningBot && !runs?.[focusBot]?.running ? runningBot.bot : focusBot

  /* poll único e consolidado: /api/apply/state devolve runs + log do bot em
   * destaque + sessões + logins em 1 request (antes eram 4 intervals, até
   * 4 HTTP por tick). O diff JSON só atualiza o estado (e o re-render)
   * quando algo realmente mudou. */
  const ultimaChaveRef = useRef('')
  const aguardando = Object.values(logins).some(l => l?.estado === 'aguardando')
  useEffect(() => {
    let vivo = true
    const tick = async () => {
      try {
        const d = await applyFetch<{
          runs: Record<string, BotRun>
          log: { lines?: string[] } | null
          sesoes: BotSessao[] | null
          logins: Record<string, LoginState>
        }>(`/api/apply/state${focus ? `?focus=${focus}` : ''}`)
        if (!vivo) return
        const chave = JSON.stringify(d)
        if (chave === ultimaChaveRef.current) return
        ultimaChaveRef.current = chave
        setRuns(d.runs)
        setLog(d.log?.lines ?? [])
        setSesoes(d.sesoes ? Object.fromEntries(d.sesoes.map(s => [s.bot, s])) : null)
        setLogins(d.logins ?? {})
      } catch {
        // backend offline nesse tick — mantém o último estado conhecido
      }
    }
    tick()
    const id = setInterval(tick, anyRunning || aguardando ? 3000 : 8000)
    return () => { vivo = false; clearInterval(id) }
  }, [focus, anyRunning, aguardando])

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
        ? `${bot} iniciado — acompanhe o log abaixo (o navegador abre nesta máquina).`
        : `${bot} parado.` })
      setRuns(await applyFetch<Record<string, BotRun>>('/api/apply/runs'))
    } catch (e) {
      setMsg({ kind: 'err', text: `${bot}: ${e instanceof Error ? e.message : 'falha'}` })
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
      setMsg({ kind: 'ok', text: `${bot}: login iniciado — uma janela do browser vai abrir nesta máquina; finalize o login nela.` })
    } catch (e) {
      setMsg({ kind: 'err', text: `${bot}: ${e instanceof Error ? e.message : 'falha ao iniciar o login'}` })
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
      setMsg({ kind: 'ok', text: `${bot}: login cancelado.` })
    } catch (e) {
      setMsg({ kind: 'err', text: `${bot}: ${e instanceof Error ? e.message : 'falha ao cancelar o login'}` })
    } finally {
      setBusyLogin(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* Logins — botão garante a sessão (login-só: não busca, não candidata) */}
      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[13px] font-medium text-slate-400 uppercase tracking-wider">
            <KeyRound className="w-4 h-4 text-indigo-300" />
            Logins
          </div>
          <span className="text-[13px] text-slate-500">garante a sessão — não envia candidatura</span>
        </div>
        {sesoes === null ? (
          <div className="mt-3 space-y-2">
            {[0, 1, 2, 3, 4].map(i => <div key={i} className="h-12 rounded-xl bg-slate-800/40 animate-pulse" />)}
          </div>
        ) : (
        <div className="mt-3 space-y-2">
          {BOT_NAMES.map(name => {
            const s = sesoes[name]
            const l = logins[name]
            const aguardando = l?.estado === 'aguardando'
            const ocupado = busyLogin === name
            const texto = aguardando
              ? '⏳ janela do browser aberta — finalize o login nela'
              : l?.estado === 'concluido'
                ? 'login concluído — sessão atualizada'
                : l?.estado === 'falhou'
                  ? `login falhou (código ${l.exit_code ?? '?'})`
                  : s?.detalhe ?? '…'
            const cor = l?.estado === 'falhou'
              ? 'bg-rose-400'
              : aguardando
                ? 'bg-amber-400 animate-pulse'
                : (l?.estado === 'concluido' || s?.tem_sessao)
                  ? 'bg-emerald-400'
                  : 'bg-slate-600'
            return (
              <div key={name} className="rounded-xl border border-slate-800/70 p-3 bg-slate-950/40">
                <div className="flex items-center gap-3">
                  <span aria-hidden className={`w-2 h-2 rounded-full shrink-0 ${cor}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-200">{s?.nome ?? name}</div>
                    <div aria-live="polite" className="text-[13px] text-slate-500 truncate">{texto}</div>
                  </div>
                  {aguardando ? (
                    <button onClick={() => pararLogin(name)} disabled={ocupado} className={btnDanger}>
                      {ocupado
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Square className="w-3.5 h-3.5" />}
                      Cancelar
                    </button>
                  ) : (
                    <button onClick={() => logar(name)}
                      disabled={ocupado || !!runs?.[name]?.running}
                      className={btnPrimary}>
                      {ocupado
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <LogIn className="w-3.5 h-3.5" />}
                      {s?.tem_sessao ? 'Renovar' : 'Logar'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        )}
      </div>

      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[13px] font-medium text-slate-400 uppercase tracking-wider">
            Bots do Job Hunter
          </div>
          <span className="text-[13px] text-slate-500">iniciar abre um navegador nesta máquina</span>
        </div>
        {msg && (
          <div className={`mt-3 text-xs rounded-xl px-3 py-2 border ${msg.kind === 'ok'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-rose-500/30 bg-rose-500/10 text-rose-300'}`}>
            {msg.text}
          </div>
        )}
        {runs === null ? (
          // carregando o status dos bots
          <div className="mt-3 space-y-2">
            {[0, 1, 2, 3, 4].map(i => <div key={i} className="h-14 rounded-xl bg-slate-800/40 animate-pulse" />)}
          </div>
        ) : (
        <div className="mt-3 space-y-2">
          {BOT_NAMES.map(name => {
            const run = runs?.[name]
            const isRunning = !!run?.running
            const destacado = focus === name
            const ocupado = busy === `iniciar-${name}` || busy === `parar-${name}`
            return (
              <div key={name}
                className={`rounded-xl border p-3 bg-slate-950/40 transition-colors ${destacado
                  ? 'border-indigo-500/40'
                  : 'border-slate-800/70'}`}>
                <div className="flex items-center gap-3">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
                  <div className="flex-1 min-w-0">
                    <button onClick={() => setFocusBot(name)}
                      className="text-sm font-medium text-slate-200 hover:text-indigo-300 transition-colors"
                      title="Ver o log deste bot abaixo">
                      {name}
                    </button>
                    {isRunning && run?.started_at && (
                      <div className="text-[13px] text-slate-500">
                        rodando desde {new Date(run.started_at).toLocaleTimeString('pt-BR')} (pid {run.pid})
                      </div>
                    )}
                  </div>
                  {isRunning ? (
                    <button onClick={() => agir(name, 'stop')} disabled={ocupado} className={btnDanger}>
                      {ocupado
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Square className="w-3.5 h-3.5" />}
                      Parar
                    </button>
                  ) : (
                    <button onClick={() => agir(name, 'start')} disabled={ocupado} className={btnPrimary}>
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
              Log em tempo real · {focus}
            </span>
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
            ? 'Sem log ainda — inicie o bot ou escolha outro na lista acima.'
            : log.join('\n')}
        </pre>
      </div>
    </div>
  )
}
