'use client'
import dynamic from 'next/dynamic'

/* Rota /config-ias — gerenciamento das chaves de API dos provedores. */
const ConfigIasTool = dynamic(() => import('./api-settings'), {
  ssr: false,
  loading: () => <div className="w-full max-w-4xl h-64 bg-slate-800/50 rounded-2xl animate-pulse" />,
})

export default function Page() {
  return <ConfigIasTool />
}
