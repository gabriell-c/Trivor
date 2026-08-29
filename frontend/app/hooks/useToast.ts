'use client'
import { useState, useCallback } from 'react'
import type { Toast, ToastType } from '../components/Toast'

let toasts: Toast[] = []

export function useToast() {
  const [toastsState, setToastsState] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, title: string, message?: string, duration?: number) => {
    const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    const toast: Toast = { id, type, title, message, duration }
    setToastsState((prev) => [...prev, toast])
    return id
  }, [])

  const removeToast = useCallback((id: string) => {
    setToastsState((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback((type: ToastType, title: string, message?: string, duration?: number) => {
    addToast(type, title, message, duration)
  }, [addToast])

  const showSuccess = useCallback((title: string, message?: string) => {
    showToast('success', title, message)
  }, [showToast])

  const showError = useCallback((title: string, message?: string) => {
    showToast('error', title, message)
  }, [showToast])

  const showWarning = useCallback((title: string, message?: string) => {
    showToast('warning', title, message)
  }, [showToast])

  const showInfo = useCallback((title: string, message?: string) => {
    showToast('info', title, message)
  }, [showToast])

  return {
    toasts: toastsState,
    removeToast,
    showToast,
    showSuccess,
    showError,
    showWarning,
    showInfo,
  }
}
