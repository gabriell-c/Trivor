'use client'
import dynamic from 'next/dynamic'

/* Rota /inteligencia-mercado — mineração de vagas e análise de tendências. */
const MercadoTool = dynamic(() => import('./mercado'), {
  ssr: false,
  loading: () => <div className="w-full max-w-4xl h-64 bg-slate-800/50 rounded-2xl animate-pulse" />,
})

export default function Page() {
  return <MercadoTool />
}
