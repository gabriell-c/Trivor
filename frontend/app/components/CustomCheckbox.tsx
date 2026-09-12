'use client'
import { Check } from 'lucide-react'

interface CustomCheckboxProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
  disabled?: boolean
  className?: string
}

export function CustomCheckbox({ checked, onChange, label, disabled, className = '' }: CustomCheckboxProps) {
  return (
    <label className={`flex items-center gap-2.5 cursor-pointer select-none group ${className}`}>
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`
          w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all flex-shrink-0
          ${checked
            ? 'bg-indigo-600 border-indigo-500 shadow-sm shadow-indigo-500/20'
            : 'border-slate-600 bg-slate-800 group-hover:border-slate-500'
          }
          ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
        `}
      >
        {checked && <Check className="w-3 h-3 text-white" />}
      </button>
      {label && (
        <span className={`text-sm ${disabled ? 'text-slate-600' : 'text-slate-300 group-hover:text-slate-200'} transition-colors`}>
          {label}
        </span>
      )}
    </label>
  )
}
