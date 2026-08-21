'use client'

interface CustomButtonProps {
  children: React.ReactNode
  onClick?: () => void
  className?: string
  disabled?: boolean
  loading?: boolean
  variant?: 'primary' | 'danger' | 'ghost'
  type?: 'button' | 'submit'
}

export function CustomButton({ children, onClick, className = '', disabled, loading, variant = 'primary', type = 'button' }: CustomButtonProps) {
  const baseClasses = 'flex items-center justify-center gap-2 px-5 py-3 rounded-2xl text-sm font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed'
  const variantClasses = {
    primary: 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/25 border border-purple-500',
    danger: 'bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20',
    ghost: 'bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-slate-200 hover:border-slate-600',
  }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`${baseClasses} ${variantClasses[variant]} ${className}`}
    >
      {loading && (
        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  )
}
