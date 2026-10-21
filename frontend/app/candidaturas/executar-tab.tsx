'use client'
import { useEffect, useRef, useState } from 'react'
import { Play, Square, Loader2, FileTerminal, Pin } from 'lucide-react'
import {
  applyFetch, applyMethod, BOT_NAMES,
  type BotRun, cardCls, btnPrimary, btnDanger,
} from './apply-api'

export default function ExecutarTab() {
  const [runs, setRuns] = useState<Record<string, BotRun> | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [focusBot, setFocusBot] = useState<string>('gupy')
  const [log, setLog] = useState<string[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const preRef = useRef<HTMLPreElement>(null)
  const anyRunning = !!runs && Object.values(runs).some(r => r.running)

  /* status de todos os bots — mais rápido de poll enquanto algo roda */
  useEffect(() => {
    let vivo = true
    const tick = async () => {
      try {
        const d = await applyFetch('/api/apply/runs')
        if (vivo) setRuns(d)
      } catch {
        // backend offline nesse tick — mantém o último estado conhecido
      }
    }
    tick()
    const id = setInterval(tick, anyRunning ? 3000 : 8000)
    return () => { vivo = false; clearInterval(id) }
  }, [anyRunning])

  /* log do bot em destaque (a UI mostra exatamente o passo a passo) */
  useEffect(() => {
    let vivo = true
    const tick = async () => {
      try {
        const d = await applyFetch(`/api/apply/log/${focusBot}?lines=400`)
        if (vivo) setLog(d.lines || [])
      } catch {
        // mantém o log último conhecido
      }
    }
    tick()
    const id = setInterval(tick, anyRunning ? 3000 : 8000)
    return () => { vivo = false; clearInterval(id) }
  }, [focusBot, anyRunning])

  useEffect(() => {
    if (autoScroll && preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [log, autoScroll])

  /* um bot começou a rodar e não é o destacado → para ele (o log é dele) */
  useEffect(() => {
    if (!runs) return
    const roda = Object.values(runs).find(r => r.running)
    if (roda && !runs[focusBot]?.running) setFocusBot(roda.bot)
  }, [runs, focusBot])

  const agir = async (bot: string, acao: 'start' | 'stop') => {
    setBusy(acao === 'start' ? `iniciar-${bot}` : `parar-${bot}`)
    setMsg(null)
    try {
      const path = acao === 'start' ? '/api/apply/run' : '/api/apply/stop'
      await applyMethod(path, 'POST', { bot })
      setMsg({ kind: 'ok', text: acao === 'start'
        ? `${bot} iniciado — acompanhe o log abaixo (o navegador abre nesta máquina).`
        : `${bot} parado.` })
      setRuns(await applyFetch('/api/apply/runs'))
    } catch (e) {
      setMsg({ kind: 'err', text: `${bot}: ${e instanceof Error ? e.message : 'falha'}` })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
            Bots do Job Hunter
          </div>
          <span className="text-[11px] text-slate-500">iniciar abre um navegador nesta máquina</span>
        </div>
        {msg && (
          <div className={`mt-3 text-xs rounded-xl px-3 py-2 border ${msg.kind === 'ok'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-rose-500/30 bg-rose-500/10 text-rose-300'}`}>
            {msg.text}
          </div>
        )}
        <div className="mt-3 space-y-2">
          {BOT_NAMES.map(name => {
            const run = runs?.[name]
            const isRunning = !!run?.running
            const destacado = focusBot === name
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
                      <div className="text-[11px] text-slate-500">
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
      </div>

      {/* log em tempo real do bot em destaque */}
      <div className={cardCls}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <FileTerminal className="w-4 h-4 text-indigo-300" />
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
              Log em tempo real · {focusBot}
            </span>
            {runs?.[focusBot]?.running && (
              <span className="flex items-center gap-1.5 text-[11px] text-emerald-300">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> rodando
              </span>
            )}
          </div>
          <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer">
            <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)}
              className="accent-indigo-500" />
            <Pin className="w-3 h-3" /> acompanhar fim
          </label>
        </div>
        <pre ref={preRef}
          className="mt-3 h-[340px] overflow-y-auto rounded-xl bg-slate-950/70 border border-slate-800/70 p-3 text-[11px] leading-relaxed text-slate-300 font-mono whitespace-pre-wrap">
          {log.length === 0
            ? 'Sem log ainda — inicie o bot ou escolha outro na lista acima.'
            : log.join('\n')}
        </pre>
      </div>
    </div>
  )
}
