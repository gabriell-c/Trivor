'use client'
import { useState, useEffect, useCallback } from 'react'

export interface IAProvider {
  id: string
  name: string
  provider: 'openai' | 'anthropic' | 'custom'
  apiKey: string
  apiUrl: string
  modelName: string
  usedFor: 'all' | 'curriculo' | 'market' | 'none'
  status: 'unknown' | 'testing' | 'connected' | 'error'
  statusMessage: string
  created_at: string
}

const STORAGE_KEY = 'trivor_ia_providers_v2'

export function loadProviders(): IAProvider[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch {}
  return []
}

export function saveProviders(providers: IAProvider[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(providers))
}

export function getBestProvider(tools: ('curriculo' | 'market')[]): IAProvider | null {
  const relevant = tools.reduce<IAProvider[]>((acc, tool) => {
    const found = loadProviders().filter(p => p.usedFor === 'all' || p.usedFor === tool)
    acc.push(...found)
    return acc
  }, [])
  const unique = Array.from(new Map(relevant.map(p => [p.id, p])).values())
  return unique[0] ?? null
}

export function useIaProviders() {
  const [providers, setProviders] = useState<IAProvider[]>(loadProviders)

  useEffect(() => {
    const interval = setInterval(() => setProviders(loadProviders), 1000)
    return () => clearInterval(interval)
  }, [])

  const add = useCallback((p: Omit<IAProvider, 'id' | 'created_at' | 'status' | 'statusMessage'>) => {
    const newProvider: IAProvider = {
      ...p,
      id: Date.now().toString(),
      created_at: new Date().toISOString(),
      status: 'unknown',
      statusMessage: '',
    }
    const updated = [...providers, newProvider]
    setProviders(updated)
    saveProviders(updated)
    return newProvider
  }, [providers])

  const remove = useCallback((id: string) => {
    const updated = providers.filter(p => p.id !== id)
    setProviders(updated)
    saveProviders(updated)
  }, [providers])

  const updateUsedFor = useCallback((id: string, usedFor: IAProvider['usedFor']) => {
    const updated = providers.map(p => p.id === id ? { ...p, usedFor } : p)
    setProviders(updated)
    saveProviders(updated)
  }, [providers])

  const updateStatus = useCallback((id: string, status: IAProvider['status'], message?: string) => {
    setProviders(prev => prev.map(p => p.id === id ? { ...p, status, statusMessage: message || '' } : p))
  }, [])

  return { providers, add, remove, updateUsedFor, updateStatus }
}

export function getGlobalStatus(providers: IAProvider[]): 'green' | 'yellow' | 'red' | 'none' {
  if (providers.length === 0) return 'none'
  const connected = providers.filter(p => p.status === 'connected').length
  const hasError = providers.some(p => p.status === 'error')
  if (connected === providers.length) return 'green'
  if (hasError) return 'red'
  return 'yellow'
}
