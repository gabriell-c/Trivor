'use client'
import { ReactNode } from 'react'
import { Activity, ArrowRight, Upload, FileText, BarChart3, Key, Users } from 'lucide-react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

const defaultIcons = {
  default: Activity,
  upload: Upload,
  document: FileText,
  chart: BarChart3,
  key: Key,
  users: Users,
}

export function EmptyState({ icon, title, description, action, className = '' }: EmptyStateProps) {
  const IconComponent = icon || <defaultIcons.default className="w-12 h-12" />

  return (
    <div className={`flex flex-col items-center justify-center py-16 px-4 text-center ${className}`}>
      <div className="w-16 h-16 rounded-full bg-slate-800/50 border border-slate-700/50 flex items-center justify-center mb-4">
        {IconComponent}
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
      <p className="text-slate-400 text-sm max-w-md mb-6">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {action.label}
          <ArrowRight className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
