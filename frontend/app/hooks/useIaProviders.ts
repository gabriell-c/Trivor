'use client';
import { useState, useEffect, useCallback } from 'react';

export interface IAProvider {
  id: string;
  name: string;
  provider: 'openai' | 'anthropic' | 'custom';
  apiKey: string;
  apiUrl: string;
  modelName: string;
  usedFor: 'all' | 'curriculo' | 'market' | 'none';
  status: 'unknown' | 'testing' | 'connected' | 'slow' | 'error';
  statusMessage: string;
  lastLatencyMs?: number;
  lastTestedAt?: string;
  created_at: string;
}

const STORAGE_KEY = 'trivor_ia_providers_v2';

export function loadProviders(): IAProvider[] {
  // SSR/build: localStorage não existe — volta vazio em silêncio (o
  // useState de inicialização roda no servidor).
  if (typeof localStorage === 'undefined') return [];
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (err) {
    // JSON corrompido ou storage bloqueado: parte de vazio mas deixa registro.
    console.warn('[Trivor] Falha ao carregar providers do localStorage:', err);
  }
  return [];
}

export function saveProviders(providers: IAProvider[]) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(providers));
  } catch (err) {
    // Quota excedida ou modo privado: a sessão continua funcionando, só não
    // persiste — avisa em vez de cair.
    console.warn('[Trivor] Falha ao salvar providers no localStorage (modo privado/quota?):', err);
  }
}

export function getBestProvider(tools: ('curriculo' | 'market')[]): IAProvider | null {
  const relevant = tools.reduce<IAProvider[]>((acc, tool) => {
    const found = loadProviders().filter((p) => p.usedFor === 'all' || p.usedFor === tool);
    acc.push(...found);
    return acc;
  }, []);
  const unique = Array.from(new Map(relevant.map((p) => [p.id, p])).values());
  return unique[0] ?? null;
}

export function useIaProviders() {
  const [providers, setProviders] = useState<IAProvider[]>(loadProviders);

  useEffect(() => {
    // Polling otimizado: 5 segundos em vez de 1s
    const interval = setInterval(() => setProviders(() => loadProviders()), 5000);
    return () => clearInterval(interval);
  }, []);

  const add = useCallback(
    (p: Omit<IAProvider, 'id' | 'created_at' | 'status' | 'statusMessage'>) => {
      const newProvider: IAProvider = {
        ...p,
        id: Date.now().toString(),
        created_at: new Date().toISOString(),
        status: 'unknown',
        statusMessage: '',
      };
      const updated = [...providers, newProvider];
      setProviders(updated);
      saveProviders(updated);
      return newProvider;
    },
    [providers]
  );

  const remove = useCallback(
    (id: string) => {
      const updated = providers.filter((p) => p.id !== id);
      setProviders(updated);
      saveProviders(updated);
    },
    [providers]
  );

  const updateUsedFor = useCallback(
    (id: string, usedFor: IAProvider['usedFor']) => {
      const updated = providers.map((p) => (p.id === id ? { ...p, usedFor } : p));
      setProviders(updated);
      saveProviders(updated);
    },
    [providers]
  );

  const update = useCallback(
    (id: string, patch: Partial<Omit<IAProvider, 'id' | 'created_at'>>) => {
      const updated = providers.map((p) => (p.id === id ? { ...p, ...patch } : p));
      setProviders(updated);
      saveProviders(updated);
    },
    [providers]
  );

  // Persiste no localStorage: sem isso o polling de 5s em `loadProviders`
  // devolveria o status antigo e apagaria o resultado do teste.
  const updateStatus = useCallback(
    (id: string, status: IAProvider['status'], message?: string, latencyMs?: number) => {
      // unknown/teste novo sem latência limpa a memória do último teste;
      // erro mantém o "quando" mas descarta a latência.
      const stale = status === 'unknown' || status === 'testing';
      const updated = providers.map((p) =>
        p.id === id
          ? {
              ...p,
              status,
              statusMessage: message || '',
              lastLatencyMs: stale ? undefined : latencyMs,
              lastTestedAt: stale ? undefined : new Date().toISOString(),
            }
          : p
      );
      setProviders(updated);
      saveProviders(updated);
    },
    [providers]
  );

  return { providers, add, remove, updateUsedFor, update, updateStatus };
}

export function getGlobalStatus(providers: IAProvider[]): 'green' | 'yellow' | 'red' | 'none' {
  if (providers.length === 0) return 'none';
  // "slow" ainda é um provedor alcançável — conta como conectado.
  const reachable = providers.filter((p) => p.status === 'connected' || p.status === 'slow').length;
  const hasError = providers.some((p) => p.status === 'error');
  if (reachable === providers.length) return 'green';
  if (hasError) return 'red';
  return 'yellow';
}
