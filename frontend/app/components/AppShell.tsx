'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { usePathname } from 'next/navigation'
import Sidebar from './Layout'
import ErrorBoundary from './ErrorBoundary'
import { getGlobalStatus, useIaProviders } from '../hooks/useIaProviders'

/* Casca do app: sidebar + área de conteúdo. O conteúdo é o `children` — a
 * página da rota /<slug> atual (cada tool é uma página real de URL). A
 * sidebar destaca o item ativo pela URL; aqui sobrou só o estado de
 * colapso e a animação de troca de rota. */

/* Largura do container por rota (Config. IAs é mais estreita, Candidaturas
 * tem o espaçamento próprio; as demais usam a padrão). */
function paginaCls(pathname: string): string {
  if (pathname === '/config-ias') return 'w-full max-w-3xl'
  if (pathname === '/candidaturas') return 'w-full max-w-4xl space-y-5'
  return 'w-full max-w-4xl space-y-6'
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname() || '/'
  const { providers } = useIaProviders()
  const globalStatus = getGlobalStatus(providers)

  // SSR detection: setMounted(true) only fires on client — safe single-shot pattern
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setMounted(true) }, [])

  if (!mounted) {
    return (
      <div className="min-h-screen bg-[#070a12] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-slate-400 text-sm font-medium">Carregando Trivor...</span>
        </div>
      </div>
    )
  }

  return (
    <ErrorBoundary>
    <div className="relative min-h-screen flex bg-[#070a12]">
      <Sidebar globalStatus={globalStatus} providerCount={providers.length} collapsed={collapsed} onCollapsedChange={setCollapsed} />

      <motion.main initial={false} animate={{ marginLeft: collapsed ? 72 : 260 }} transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="flex-1 min-h-screen flex flex-col p-4 md:p-8 overflow-x-hidden relative">

        <div className="absolute bottom-10 right-10 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <AnimatePresence mode="wait">
          <motion.div key={pathname} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ duration: 0.2 }}
            className="flex-1 flex flex-col justify-center items-center z-10">
            <div className={paginaCls(pathname)}>
              {children}
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.main>
    </div>
    </ErrorBoundary>
  )
}
