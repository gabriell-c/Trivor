'use client'
import { useEffect, useCallback } from 'react'

interface Shortcut {
  key: string
  ctrl?: boolean
  alt?: boolean
  shift?: boolean
  action: () => void
  description?: string
}

const shortcuts: Shortcut[] = [
  { key: 'l', ctrl: true, action: () => window.location.assign('/logs'), description: 'Ir para Logs' },
  { key: 'd', ctrl: true, action: () => window.location.assign('/dashboard'), description: 'Ir para Dashboard' },
  { key: 'c', ctrl: true, action: () => window.location.assign('/'), description: 'Análise de Currículo' },
  { key: 'm', ctrl: true, action: () => window.location.assign('/market'), description: 'Inteligência de Mercado' },
  { key: 'k', ctrl: true, action: () => window.location.assign('/api-settings'), description: 'Configurações de IA' },
  { key: 'Escape', action: () => {
    const modal = document.querySelector('[role="dialog"]')
    if (modal) modal.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  }},
]

export function useKeyboardShortcuts() {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const shortcut = shortcuts.find(
      (s) =>
        s.key.toLowerCase() === e.key.toLowerCase() &&
        s.ctrl === !!e.ctrlKey &&
        s.alt === !!e.altKey &&
        s.shift === !!e.shiftKey
    )

    if (shortcut) {
      e.preventDefault()
      shortcut.action()
    }
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return shortcuts
}

export function getShortcutDescription(shortcutKey: string, ctrl?: boolean, alt?: boolean, shift?: boolean): string {
  const parts: string[] = []
  if (ctrl) parts.push('Ctrl')
  if (alt) parts.push('Alt')
  if (shift) parts.push('Shift')
  parts.push(shortcutKey.toUpperCase())
  return parts.join('+')
}
