'use client'
/* Ícones dos 5 sites do Job Hunter — SVG inline (lucide não tem marcas;
 * sem asset novo, sem dependência). Badge com a inicial na cor do site:
 * reconhecível pelo padrão nome-ícone que a página já usa (lucide). */

import type { BotSessao } from './apply-api'

const META: Record<string, { letra: string; cor: string; acento: string }> = {
  gupy:     { letra: 'G', cor: '#34d399', acento: 'rgba(52,211,153,0.14)' },
  indeed:   { letra: 'I', cor: '#38bdf8', acento: 'rgba(56,189,248,0.14)' },
  solides:  { letra: 'S', cor: '#fbbf24', acento: 'rgba(251,191,36,0.14)' },
  nerdin:   { letra: 'N', cor: '#a78bfa', acento: 'rgba(167,139,250,0.14)' },
  infojobs: { letra: 'J', cor: '#fb7185', acento: 'rgba(251,113,133,0.14)' },
}

export function SiteIcon({ bot, size = 36 }: { bot: string; size?: number }) {
  const m = META[bot] ?? META.gupy
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden
      className="shrink-0 rounded-xl border border-slate-700/50">
      <rect width="40" height="40" rx="10" fill={m.acento} />
      <text x="20" y="21" textAnchor="middle" dominantBaseline="central"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fontSize="19" fontWeight="700" fill={m.cor}>
        {m.letra}
      </text>
    </svg>
  )
}

/* nome legível do site — cai no próprio key quando a tabela de sessões
 * ainda não carregou */
export function nomeDoSite(bot: string, sesoes: Record<string, BotSessao> | null) {
  return sesoes?.[bot]?.nome ?? bot
}
