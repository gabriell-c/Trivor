/**
 * Tom de cor consistente para score 0-100 em todas as telas (CV e mercado):
 * >= 80 bom (emerald), >= 60 médio (amber), abaixo ruim (rose).
 */
export function scoreTone(score: number = 0) {
  if (score >= 80) return { text: 'text-emerald-400', stroke: '#34d399', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' }
  if (score >= 60) return { text: 'text-amber-400', stroke: '#fbbf24', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
  return { text: 'text-rose-400', stroke: '#fb7185', bg: 'bg-rose-500/10', border: 'border-rose-500/30' }
}
