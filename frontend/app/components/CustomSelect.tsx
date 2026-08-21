'use client'
import { useState, useRef, useEffect } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface CustomSelectProps {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  className?: string
  disabled?: boolean
}

export function CustomSelect({ value, onChange, options, placeholder = 'Selecione...', className = '', disabled }: CustomSelectProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selected = options.find(o => o.value === value)

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(!open)}
        className={`w-full flex items-center justify-between gap-2 px-4 py-3 rounded-2xl text-sm transition-all border ${
          disabled
            ? 'bg-slate-950/40 border-slate-800 text-slate-600 cursor-not-allowed'
            : open
            ? 'bg-slate-950 border-purple-500/60 ring-1 ring-purple-500/30 text-white'
            : 'bg-slate-950/80 border-slate-700/80 text-slate-300 hover:border-slate-600'
        }`}
      >
        <span className={`truncate ${!selected ? 'text-slate-500' : 'text-white'}`}>
          {selected ? selected.label : placeholder}
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-slate-500 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-500 flex-shrink-0" />}
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-2 w-full bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl shadow-black/50 overflow-hidden">
          <div className="max-h-60 overflow-y-auto py-1">
            {options.map(opt => (
              <button
                key={opt.value}
                onClick={() => { onChange(opt.value); setOpen(false); }}
                className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                  value === opt.value
                    ? 'bg-purple-600/20 text-purple-300 font-semibold'
                    : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
