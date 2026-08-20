'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText,
  BarChart3,
  LayoutDashboard,
  ChevronLeft,
  ChevronRight,
  Briefcase,
} from 'lucide-react'

type Tool = 'curriculo' | 'mercado' | 'dashboard'

interface SidebarProps {
  activeTool: Tool
  onToolChange: (tool: Tool) => void
}

const tools: { id: Tool; label: string; icon: React.ReactNode; description: string }[] = [
  {
    id: 'curriculo',
    label: 'Análise de Currículo',
    icon: <FileText className="w-5 h-5" />,
    description: 'Diagnóstico ATS e compatibilidade',
  },
  {
    id: 'mercado',
    label: 'Inteligência de Mercado',
    icon: <BarChart3 className="w-5 h-5" />,
    description: 'Análise de vagas e tendências',
  },
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: <LayoutDashboard className="w-5 h-5" />,
    description: 'Visão geral e histórico',
  },
]

export default function Sidebar({ activeTool, onToolChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <>
      {/* Mobile overlay */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-30 lg:hidden"
            onClick={() => setCollapsed(true)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{
          width: collapsed ? 72 : 260,
          flexShrink: 0,
        }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className={`
          fixed top-0 left-0 h-full z-40
          bg-slate-900/95 backdrop-blur-xl
          border-r border-slate-800/60
          flex flex-col
          ${collapsed ? 'w-[72px]' : 'w-[260px]'}
        `}
      >
        {/* Logo */}
        <div className={`flex items-center h-16 px-4 border-b border-slate-800/60 ${collapsed ? 'justify-center' : 'gap-3'}`}>
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0">
            <Briefcase className="w-4 h-4 text-white" />
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                className="text-lg font-extrabold text-white tracking-tight"
              >
                Trivor
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Tools */}
        <nav className="flex-1 py-4 px-3 space-y-1.5">
          {tools.map((tool) => {
            const isActive = activeTool === tool.id
            return (
              <button
                key={tool.id}
                onClick={() => onToolChange(tool.id)}
                className={`
                  w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left transition-all duration-150
                  ${isActive
                    ? 'bg-indigo-600/20 border border-indigo-500/30 text-indigo-300'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                  }
                  ${collapsed ? 'justify-center px-0' : ''}
                `}
                title={collapsed ? tool.label : undefined}
              >
                <span className={`flex-shrink-0 ${isActive ? 'text-indigo-400' : ''}`}>
                  {tool.icon}
                </span>
                <AnimatePresence>
                  {!collapsed && (
                    <motion.div
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -6 }}
                      transition={{ duration: 0.15 }}
                      className="min-w-0"
                    >
                      <div className={`text-sm font-semibold truncate ${isActive ? 'text-indigo-200' : ''}`}>
                        {tool.label}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate mt-0.5">
                        {tool.description}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </button>
            )
          })}
        </nav>

        {/* Collapse button */}
        <div className="p-3 border-t border-slate-800/60">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-slate-500 hover:text-slate-300 hover:bg-slate-800/60 transition-all text-xs font-medium"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  Recolher
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </div>
      </motion.aside>
    </>
  )
}
