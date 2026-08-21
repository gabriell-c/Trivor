'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Key,
  Plus,
  Trash2,
  CheckCircle2,
  XCircle,
  Zap,
  Loader2,
  Globe,
  Sparkles,
} from 'lucide-react'
import { CustomInput } from '../components/CustomInput'
import { CustomSelect } from '../components/CustomSelect'
import { CustomButton } from '../components/CustomButton'
import { useIaProviders, IAProvider, getGlobalStatus } from '../hooks/useIaProviders'

const PROVIDER_CONFIG = {
  openai: { name: 'OpenAI', icon: <Sparkles className="w-4 h-4" />, defaultUrl: 'https://api.openai.com/v1', defaultModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'], color: 'text-emerald-400' },
  anthropic: { name: 'Anthropic', icon: <Zap className="w-4 h-4" />, defaultUrl: 'https://api.anthropic.com/v1', defaultModels: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'], color: 'text-orange-400' },
  custom: { name: 'Personalizada', icon: <Globe className="w-4 h-4" />, defaultUrl: '', defaultModels: ['gpt-4o', 'gpt-4', 'claude-3', 'llama-3'], color: 'text-purple-400' },
}

export default function ApiSettingsPage() {
  const { providers, add, remove, updateUsedFor } = useIaProviders()
  const [showAddForm, setShowAddForm] = useState(false)
  const [newProvider, setNewProvider] = useState({
    name: '',
    providerType: 'openai' as 'openai' | 'anthropic' | 'custom',
    apiKey: '',
    apiUrl: PROVIDER_CONFIG.openai.defaultUrl,
    modelName: 'gpt-4o',
    usedFor: 'all' as IAProvider['usedFor'],
  })
  const [testResult, setTestResult] = useState<{ id: string; ok: boolean; msg: string } | null>(null)

  const config = PROVIDER_CONFIG[newProvider.providerType]
  const globalStatus = getGlobalStatus(providers)

  const testConnection = async (provider: IAProvider) => {
    const body = new FormData()
    body.set('api_key', provider.apiKey)
    body.set('api_url', provider.apiUrl)
    body.set('model_name', provider.modelName)
    body.set('text', 'Olá, responda apenas "ok"')

    try {
      const res = await fetch('http://127.0.0.1:8000/api/test-connection', { method: 'POST', body })
      const data = await res.json()
      if (res.ok) {
        setTestResult({ id: provider.id, ok: true, msg: data.message || 'Conexão OK' })
      } else {
        setTestResult({ id: provider.id, ok: false, msg: data.detail || 'Erro na conexão' })
      }
    } catch (err: any) {
      setTestResult({ id: provider.id, ok: false, msg: err.message || 'Erro na conexão' })
    }
  }

  const addProvider = () => {
    const p = add({ ...newProvider, provider: newProvider.providerType })
    setShowAddForm(false)
    if (p.apiKey.trim()) testConnection(p)
  }

  const resetNewProvider = () => {
    setNewProvider({ name: '', providerType: 'openai', apiKey: '', apiUrl: PROVIDER_CONFIG.openai.defaultUrl, modelName: 'gpt-4o', usedFor: 'all' })
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="w-full max-w-3xl z-10 space-y-6">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold tracking-wider">
          <Key className="w-3.5 h-3.5" />
          API &middot; IAs
        </div>
        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">Configuração de IAs</h1>
        <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">Cadastre suas chaves de API e escolha qual IA usar em cada ferramenta.</p>
      </div>

      {providers.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <div className={`flex items-center gap-2 px-4 py-2 rounded-2xl border ${
            globalStatus === 'green' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' :
            globalStatus === 'yellow' ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' :
            globalStatus === 'red' ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' :
            'bg-slate-800/60 border-slate-700/60 text-slate-400'
          }`}>
            <div className={`w-2.5 h-2.5 rounded-full ${globalStatus === 'green' ? 'bg-emerald-400 animate-pulse' : globalStatus === 'yellow' ? 'bg-amber-400' : globalStatus === 'red' ? 'bg-rose-400' : 'bg-slate-500'}`} />
            <span className="text-xs font-bold">{providers.length} IA{providers.length !== 1 ? 's' : ''} cadastrada{providers.length !== 1 ? 's' : ''}</span>
            <span className="text-slate-500">·</span>
            <span className="text-xs">{providers.filter(p => p.status === 'connected').length} conectada{providers.filter(p => p.status === 'connected').length !== 1 ? 's' : ''}</span>
          </div>
        </div>
      )}

      <div className="flex justify-center">
        <CustomButton onClick={() => { setShowAddForm(!showAddForm); resetNewProvider() }}>
          <Plus className="w-4 h-4" />
          {showAddForm ? 'Cancelar' : 'Adicionar IA'}
        </CustomButton>
      </div>

      <AnimatePresence>
        {showAddForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6 space-y-4 overflow-hidden">
            <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Nova Integração de IA</h3>

            <div className="grid grid-cols-3 gap-3">
              {(['openai', 'anthropic', 'custom'] as const).map(type => {
                const cfg = PROVIDER_CONFIG[type]
                const isSelected = newProvider.providerType === type
                return (
                  <button key={type} onClick={() => setNewProvider(p => ({ ...p, providerType: type, apiUrl: cfg.defaultUrl, modelName: cfg.defaultModels[0] }))}
                    className={`flex flex-col items-center gap-2 p-4 rounded-2xl border transition-all ${isSelected ? 'bg-purple-600/20 border-purple-500/40 text-white' : 'bg-slate-950/60 border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-300'}`}>
                    <span className={isSelected ? cfg.color : 'text-slate-500'}>{cfg.icon}</span>
                    <span className="text-xs font-semibold">{cfg.name}</span>
                  </button>
                )
              })}
            </div>

            <CustomInput placeholder="Nome (opcional)" value={newProvider.name} onChange={v => setNewProvider(p => ({ ...p, name: v }))} className="w-full" />
            <CustomInput type="password" showPasswordToggle placeholder="Chave de API" value={newProvider.apiKey} onChange={v => setNewProvider(p => ({ ...p, apiKey: v }))} className="w-full" />
            {newProvider.providerType === 'custom' && (
              <CustomInput placeholder="Base URL (ex: https://api.openai.com/v1)" value={newProvider.apiUrl} onChange={v => setNewProvider(p => ({ ...p, apiUrl: v }))} className="w-full" />
            )}
            <CustomSelect value={newProvider.modelName} onChange={v => setNewProvider(p => ({ ...p, modelName: v }))} options={config.defaultModels.map(m => ({ value: m, label: m }))} placeholder="Selecionar modelo..." className="w-full" />
            <CustomSelect value={newProvider.usedFor} onChange={v => setNewProvider(p => ({ ...p, usedFor: v as IAProvider['usedFor'] }))} options={[
              { value: 'all', label: 'Todas as ferramentas' },
              { value: 'curriculo', label: 'Só Análise de Currículo' },
              { value: 'market', label: 'Só Inteligência de Mercado' },
              { value: 'none', label: 'Desativada' },
            ]} placeholder="Usar em..." className="w-full" />

            <div className="flex gap-3 pt-2">
              <CustomButton onClick={addProvider} disabled={!newProvider.apiKey.trim()}>
                <CheckCircle2 className="w-4 h-4" />
                Adicionar & Testar
              </CustomButton>
              <CustomButton variant="ghost" onClick={() => { setShowAddForm(false); resetNewProvider() }}>Cancelar</CustomButton>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {testResult && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`flex items-center gap-3 px-4 py-3 rounded-2xl border ${testResult.ok ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-rose-500/10 border-rose-500/20 text-rose-400'}`}>
            {testResult.ok ? <CheckCircle2 className="w-5 h-5 flex-shrink-0" /> : <XCircle className="w-5 h-5 flex-shrink-0" />}
            <span className="text-sm font-medium">{testResult.msg}</span>
            <button onClick={() => setTestResult(null)} className="ml-auto text-slate-500 hover:text-slate-300"><XCircle className="w-4 h-4" /></button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-3">
        {providers.map(provider => {
          const cfg = PROVIDER_CONFIG[provider.provider]
          return (
            <motion.div key={provider.id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="rounded-2xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-5">
              <div className="flex items-center gap-4">
                <div className={`w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0 ${cfg.color}`}>{cfg.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-white truncate">{provider.name}</span>
                    <span className="text-[10px] text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full border border-slate-700">{cfg.name}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-slate-500 font-mono truncate">
                      {provider.apiKey ? `${provider.apiKey.slice(0, 8)}...${provider.apiKey.slice(-4)}` : 'Sem chave'}
                    </span>
                    {provider.apiUrl && provider.provider === 'custom' && (
                      <span className="text-xs text-slate-600 truncate max-w-[200px]" title={provider.apiUrl}>· {provider.apiUrl}</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-600 mt-0.5">{provider.modelName}</div>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    {provider.status === 'connected' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> :
                     provider.status === 'error' ? <XCircle className="w-4 h-4 text-rose-400" /> :
                     <div className="w-4 h-4 rounded-full bg-slate-700" />}
                    <span className={`text-xs font-medium ${provider.status === 'connected' ? 'text-emerald-400' : provider.status === 'error' ? 'text-rose-400' : 'text-slate-500'}`}>
                      {provider.status === 'connected' ? 'Conectado' : provider.status === 'error' ? 'Erro' : 'Não testado'}
                    </span>
                  </div>
                  {provider.statusMessage && <span className="text-[10px] text-slate-600 max-w-[180px] truncate">{provider.statusMessage}</span>}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button onClick={() => testConnection(provider)} className="p-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 transition-all" title="Testar conexão">
                    <Zap className="w-3.5 h-3.5" />
                  </button>
                  <CustomSelect value={provider.usedFor} onChange={v => updateUsedFor(provider.id, v as IAProvider['usedFor'])} options={[
                    { value: 'all', label: 'Todas' },
                    { value: 'curriculo', label: 'Só Currículo' },
                    { value: 'market', label: 'Só Mercado' },
                    { value: 'none', label: 'Desativada' },
                  ]} placeholder="Uso" className="w-32" />
                  <button onClick={() => remove(provider.id)} className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 transition-all" title="Remover">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </motion.div>
          )
        })}

        {providers.length === 0 && !showAddForm && (
          <div className="text-center py-16 space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto">
              <Key className="w-8 h-8 text-slate-600" />
            </div>
            <div>
              <p className="text-slate-300 font-semibold text-sm">Nenhuma IA cadastrada</p>
              <p className="text-slate-500 text-xs mt-1">Adicione sua primeira chave de API para começar.</p>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}
