'use client'
import dynamic from 'next/dynamic'

/* Rota /dashboard — visão geral e histórico do sistema. A tool monta só no
 * cliente (ssr:false), como fazia o AppShell antigo. */
const DashboardTool = dynamic(() => import('./dashboard'), {
  ssr: false,
  loading: () => <div className="w-full max-w-4xl h-64 bg-slate-800/50 rounded-2xl animate-pulse" />,
})

export default function Page() {
  return <DashboardTool />
}
