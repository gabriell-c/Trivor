'use client'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'default' | 'danger'
  /* Mensagem de erro renderizada dentro do diálogo (ex.: ação falhou e o
   * diálogo permanece aberto para o usuário tentar de novo). */
  error?: string | null
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  variant = 'default',
  error,
}: ConfirmDialogProps) {
  const [isLoading, setIsLoading] = useState(false)
  const titleId = useId()
  const cancelRef = useRef<HTMLButtonElement>(null)
  /* Gatilho que abriu o diálogo — recebe o foco de volta ao fechar. */
  const gatilhoRef = useRef<HTMLElement | null>(null)
  /* Espelho dos handlers/estado para o listener de teclado (deps do effect
   * principal só [isOpen], para o refocus não disparar a cada re-render do pai).
   * Atualizado em effect — escrita em ref durante render é proibida. */
  const handlersRef = useRef({ onCancel, isLoading })
  useEffect(() => {
    handlersRef.current = { onCancel, isLoading }
  })

  const handleConfirm = async () => {
    setIsLoading(true)
    try {
      await onConfirm()
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    gatilhoRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !handlersRef.current.isLoading) handlersRef.current.onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      gatilhoRef.current?.focus()
    }
  }, [isOpen])

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            onClick={onCancel}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-0 flex items-center justify-center z-50 px-4"
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl max-w-md w-full p-6"
            >
              <div className="flex items-start gap-4">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                  variant === 'danger' ? 'bg-red-500/20' : 'bg-indigo-500/20'
                }`}>
                  <AlertTriangle className={`w-5 h-5 ${
                    variant === 'danger' ? 'text-red-400' : 'text-indigo-400'
                  }`} />
                </div>
                <div className="flex-1">
                  <h3 id={titleId} className="text-lg font-semibold text-white">{title}</h3>
                  <p className="text-slate-400 mt-1 text-sm">{message}</p>
                  {error && (
                    <p className="mt-2 text-xs font-medium text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-2.5 py-1.5">
                      {error}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button
                  ref={cancelRef}
                  onClick={onCancel}
                  disabled={isLoading}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-slate-700 text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
                >
                  {cancelLabel}
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={isLoading}
                  className={`flex-1 px-4 py-2.5 rounded-xl font-medium transition-colors disabled:opacity-50 ${
                    variant === 'danger'
                      ? 'bg-red-500 hover:bg-red-600 text-white'
                      : 'bg-indigo-500 hover:bg-indigo-600 text-white'
                  }`}
                >
                  {isLoading ? '...' : confirmLabel}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
