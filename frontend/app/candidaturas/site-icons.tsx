'use client'
/* Logos oficiais dos 5 sites do Job Hunter — assets estáticos em
 * /public/logos (baixados dos próprios sites; o da Nerdin é JPEG).
 * Tile branco estilo "favicon": cada logo oficial é legível sobre
 * fundo claro e o branco uniformiza a fila. Se a imagem falhar
 * (asset ausente, CDN cortado), cai no badge de letra de antes. */

import { useState } from 'react'
import type { BotSessao } from './apply-api'

const LOGOS: Record<string, { src: string; letra: string; cor: string }> = {
  gupy:     { src: '/logos/gupy.svg',   letra: 'G', cor: '#34d399' },
  indeed:   { src: '/logos/indeed.svg', letra: 'I', cor: '#38bdf8' },
  solides:  { src: '/logos/solides.png', letra: 'S', cor: '#fbbf24' },
  nerdin:   { src: '/logos/nerdin.jpg', letra: 'N', cor: '#a78bfa' },
  infojobs: { src: '/logos/infojobs.svg', letra: 'J', cor: '#fb7185' },
}

/* fallback para logo que não carregou ou bot fora da tabela */
function BadgeLetra({ letra, cor, size }: { letra: string; cor: string; size: number }) {
  return (
    <div aria-hidden
      className="flex shrink-0 items-center justify-center rounded-xl border border-slate-700/50 bg-slate-800/60"
      style={{ width: size, height: size }}>
      <span className="font-bold" style={{ color: cor, fontSize: Math.round(size * 0.52) }}>{letra}</span>
    </div>
  )
}

export function SiteIcon({ bot, size = 36 }: { bot: string; size?: number }) {
  const [falhou, setFalhou] = useState(false)
  const m = LOGOS[bot]
  if (!m || falhou) {
    return <BadgeLetra letra={m?.letra ?? '?'} cor={m?.cor ?? '#94a3b8'} size={size} />
  }
  /* box interno com folga de ~4px por lado; logos amplos (wordmarks)
   * mantêm a proporção via object-contain */
  const box = Math.max(16, size - 10)
  return (
    <div aria-hidden
      className="flex shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-700/50 bg-white"
      style={{ width: size, height: size }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={m.src} alt="" width={box} height={box}
        className="object-contain" style={{ maxWidth: box, maxHeight: box }}
        onError={() => setFalhou(true)} />
    </div>
  )
}

/* nome legível do site — cai no próprio key quando a tabela de sessões
 * ainda não carregou */
export function nomeDoSite(bot: string, sesoes: Record<string, BotSessao> | null) {
  return sesoes?.[bot]?.nome ?? bot
}
