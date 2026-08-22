'use client'
import { useState, useRef, useEffect } from 'react'
import { X } from 'lucide-react'

interface TagInputProps {
  value: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  className?: string
}

export function TagInput({ value, onChange, placeholder = 'Digite e pressione Enter...', className = '' }: TagInputProps) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const addTag = (raw: string) => {
    const tag = raw.trim().toLowerCase()
    if (tag && !value.includes(tag)) {
      onChange([...value, tag])
    }
    setInputValue('')
  }

  const removeTag = (tag: string) => {
    onChange(value.filter(t => t !== tag))
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(inputValue)
    } else if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
      removeTag(value[value.length - 1])
    }
  }

  // Focus input when clicking outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('.tag-input-container')) {
        // Don't blur - just let it be
      }
    }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [])

  return (
    <div className={`tag-input-container relative w-full`}>
      <div className={`flex flex-wrap gap-1.5 p-2 min-h-10 border border-slate-700/80 rounded-xl bg-slate-950/80 focus-within:border-indigo-500/60 focus-within:ring-1 focus-within:ring-indigo-500/30 transition-all ${className}`}>
        {value.map(tag => (
          <span key={tag} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-medium bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {tag}
            <button onClick={() => removeTag(tag)} className="rounded hover:bg-indigo-500/30 transition">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => inputValue.trim() && addTag(inputValue)}
          placeholder={value.length === 0 ? placeholder : ''}
          className="flex-1 min-w-24 bg-transparent text-sm text-white placeholder-slate-600 focus:outline-none"
        />
      </div>
      {value.length > 0 && (
        <p className="text-[10px] text-slate-600 mt-1">
          Pressione Enter ou vírgula para adicionar · Backspace para remover
        </p>
      )}
    </div>
  )
}
