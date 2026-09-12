'use client'
import { useState, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Upload, CheckCircle2, FileText, X } from 'lucide-react'

interface DropzoneProps {
  accept?: string
  maxSizeMB?: number
  onFileSelect: (file: File) => void
  children?: React.ReactNode
}

export function Dropzone({ accept = '.pdf,.docx,.doc', maxSizeMB = 10, onFileSelect }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFile = useCallback((f: File): string | null => {
    const allowed = accept.split(',').map(s => s.trim().toLowerCase())
    const ext = '.' + f.name.split('.').pop()?.toLowerCase()
    if (!allowed.includes(ext)) return `Formato inválido. Aceito: ${allowed.map(a => a.replace('.', '').toUpperCase()).join(', ')}`
    if (f.size > maxSizeMB * 1024 * 1024) return `Arquivo muito grande. Máximo: ${maxSizeMB}MB`
    return null
  }, [accept, maxSizeMB])

  const handleFile = useCallback((f: File | null) => {
    if (!f) return
    const err = validateFile(f)
    if (err) { setError(err); return }
    setError(null)
    setFile(f)
    onFileSelect(f)
  }, [validateFile, onFileSelect])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    handleFile(e.dataTransfer.files[0])
  }, [handleFile])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleFile(e.target.files?.[0] ?? null)
  }, [handleFile])

  const clear = useCallback(() => {
    setFile(null)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
    onFileSelect(null as unknown as File)
  }, [onFileSelect])

  return (
    <div className="space-y-2">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center gap-2
          border-2 border-dashed rounded-2xl cursor-pointer
          transition-all duration-200 select-none
          ${isDragging
            ? 'border-indigo-400 bg-indigo-500/10 scale-[1.02]'
            : file
              ? 'border-emerald-500/40 bg-emerald-500/5 hover:border-emerald-500/60'
              : 'border-slate-700/60 hover:border-indigo-500/40 hover:bg-slate-800/30'
          }
          py-6 px-4
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={handleInput}
          onClick={e => e.stopPropagation()}
        />

        {file ? (
          <>
            <div className="w-12 h-12 rounded-xl bg-emerald-500/15 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-400" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-emerald-400 truncate max-w-[200px]">{file.name}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); clear() }}
              className="absolute top-2 right-2 p-1 rounded-full hover:bg-slate-700/60 text-slate-500 hover:text-slate-300 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </>
        ) : (
          <>
            <motion.div
              animate={isDragging ? { y: [-2, 2, -2] } : {}}
              transition={{ duration: 0.6, repeat: isDragging ? Infinity : 0 }}
            >
              <Upload className={`w-7 h-7 mb-1 ${isDragging ? 'text-indigo-400' : 'text-slate-500'}`} />
            </motion.div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-400">
                {isDragging ? 'Solte o arquivo aqui' : 'Arraste e solte ou clique'}
              </p>
              <p className="text-[10px] text-slate-600 mt-0.5">PDF, DOCX ou DOC — até {maxSizeMB}MB</p>
            </div>
          </>
        )}
      </div>

      {error && (
        <p className="text-xs text-rose-400 text-center">{error}</p>
      )}
    </div>
  )
}
