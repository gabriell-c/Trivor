'use client'
import dynamic from 'next/dynamic'

/* Rota /analise-curriculo — a tool real de CV (5 features: fit determinístico,
 * análise semântica da vaga, simulação de recrutador, cover letter e diff). */
const CurriculoTool = dynamic(() => import('../components/CurriculoTool'), {
  ssr: false,
  loading: () => <div className="w-full max-w-4xl h-64 bg-slate-800/50 rounded-2xl animate-pulse" />,
})

export default function Page() {
  return <CurriculoTool />
}
