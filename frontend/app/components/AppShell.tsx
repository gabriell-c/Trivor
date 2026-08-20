'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import dynamic from 'next/dynamic'
import Sidebar from './Layout'
import { LayoutDashboard } from 'lucide-react'

type Tool = 'curriculo' | 'mercado' | 'dashboard'

const CurriculoPage = dynamic(() => import('../page').then(m => m.default), { ssr: false })
const MarketPage = dynamic(() => import('../market/page').then(m => m.default), { ssr: false })

export default function AppShell() {
  const [mounted, setMounted] = useState(false)
  const [activeTool, setActiveTool] = useState<Tool>('curriculo')

  useEffect(() => {
    setMounted(true)
  }, [])

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
    <div className="relative min-h-screen flex bg-[#070a12]">
      <Sidebar activeTool={activeTool} onToolChange={setActiveTool} />

      <motion.main
        initial={false}
        animate={{ marginLeft: 72 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="flex-1 min-h-screen flex flex-col items-center p-4 md:p-8 overflow-x-hidden relative"
      >
        {/* Background glow */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-tr from-indigo-600/20 via-purple-600/20 to-pink-600/10 rounded-full animate-pulse-glow pointer-events-none" />
        <div className="absolute bottom-10 right-10 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <AnimatePresence mode="wait">
          {activeTool === 'curriculo' && (
            <motion.div
              key="curriculo"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-4xl z-10 space-y-6"
            >
              <CurriculoPage />
            </motion.div>
          )}
          {activeTool === 'mercado' && (
            <motion.div
              key="mercado"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
              className="w-full z-10"
            >
              <MarketPage />
            </motion.div>
          )}
          {activeTool === 'dashboard' && (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-4xl z-10 text-center py-20"
            >
              <div className="w-20 h-20 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto mb-6">
                <LayoutDashboard className="w-10 h-10 text-slate-600" />
              </div>
              <h2 className="text-2xl font-extrabold text-white mb-2">Dashboard</h2>
              <p className="text-slate-500 text-sm">Em desenvolvimento...</p>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.main>
    </div>
  )
}
