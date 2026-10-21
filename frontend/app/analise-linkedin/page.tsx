'use client'
import dynamic from 'next/dynamic'

/* Rota /analise-linkedin — diagnóstico do perfil LinkedIn. */
const LinkedinTool = dynamic(() => import('./linkedin'), {
  ssr: false,
  loading: () => <div className="w-full max-w-4xl h-64 bg-slate-800/50 rounded-2xl animate-pulse" />,
})

export default function Page() {
  return <LinkedinTool />
}
