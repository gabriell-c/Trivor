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
  Briefcase,
  Eye,
  EyeOff,
  AlertCircle,
  RefreshCw,
  Pencil,
  Save,
  X,
} from 'lucide-react'
import { CustomInput } from '../components/CustomInput'
import { CustomSelect } from '../components/CustomSelect'
import { CustomButton } from '../components/CustomButton'
import { useIaProviders, IAProvider, getGlobalStatus } from '../hooks/useIaProviders'
import { API_BASE_URL } from '../lib/api'

const PROVIDER_CONFIG = {
  openai: { name: 'OpenAI', icon: <Sparkles className="w-4 h-4" />, defaultUrl: 'https://api.openai.com/v1', defaultModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'], color: 'text-emerald-400' },
  anthropic: { name: 'Anthropic', icon: <Zap className="w-4 h-4" />, defaultUrl: 'https://api.anthropic.com/v1', defaultModels: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'], color: 'text-orange-400' },
  custom: { name: 'Personalizada', icon: <Globe className="w-4 h-4" />, defaultUrl: '', defaultModels: ['gpt-4o', 'gpt-4', 'claude-3', 'llama-3'], color: 'text-purple-400' },
}

interface JsearchKeyRecord {
  id: number
  api_key: string
  description: string
  rate_limit_total: number | null
  rate_limit_remaining: number | null
  used: number | null
  status: string
  last_tested: string | null
}

export default function ApiSettingsPage() {
  const { providers, add, remove, update, updateUsedFor, updateStatus } = useIaProviders()
  const [showAddForm, setShowAddForm] = useState(false)
  const [newProvider, setNewProvider] = useState({
    name: '',
    providerType: 'openai' as 'openai' | 'anthropic' | 'custom',
    apiKey: '',
    apiUrl: PROVIDER_CONFIG.openai.defaultUrl,
    modelName: 'gpt-4o',
    usedFor: 'all' as IAProvider['usedFor'],
  })
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null)
  const [editProviderData, setEditProviderData] = useState<Partial<IAProvider>>({})
  const [testResult, setTestResult] = useState<{ id: string; ok: boolean; msg: string } | null>(null)
  const [urlError, setUrlError] = useState('')

  const config = PROVIDER_CONFIG[newProvider.providerType]
  const globalStatus = getGlobalStatus(providers)

  const testConnection = async (provider: IAProvider) => {
    const body = new FormData()
    body.set('api_key', provider.apiKey)
    body.set('api_url', provider.apiUrl)
    body.set('model_name', provider.modelName)
    body.set('text', 'Olá, responda apenas "ok"')

    try {
      const res = await fetch(`${API_BASE_URL}/api/test-connection`, { method: 'POST', body })
      const data = await res.json()
      if (res.ok) {
        setTestResult({ id: provider.id, ok: true, msg: data.message || 'Conexão OK' })
        updateStatus(provider.id, 'connected')
      } else {
        setTestResult({ id: provider.id, ok: false, msg: data.detail || 'Erro na conexão' })
        updateStatus(provider.id, 'error', data.detail || '')
      }
    } catch (err: any) {
      setTestResult({ id: provider.id, ok: false, msg: err.message || 'Erro na conexão' })
      updateStatus(provider.id, 'error', err.message || '')
    }
  }

  const addProvider = () => {
    if (newProvider.providerType === 'custom' && newProvider.apiUrl.trim()) {
      try {
        new URL(newProvider.apiUrl)
      } catch {
        setUrlError('URL inválida')
        return
      }
    }
    if (!newProvider.apiKey.trim()) return
    setUrlError('')
    add({
      name: newProvider.name || PROVIDER_CONFIG[newProvider.providerType].name,
      provider: newProvider.providerType,
      apiKey: newProvider.apiKey,
      apiUrl: newProvider.apiUrl,
      modelName: newProvider.modelName,
      usedFor: newProvider.usedFor,
    })
    setShowAddForm(false)
    resetNewProvider()
  }

  const resetNewProvider = (type?: 'openai' | 'anthropic' | 'custom') => {
    const t = type ?? newProvider.providerType
    const cfg = PROVIDER_CONFIG[t]
    setNewProvider({ name: '', providerType: t, apiKey: '', apiUrl: cfg.defaultUrl, modelName: cfg.defaultModels[0], usedFor: 'all' })
  }

  const startEditProvider = (provider: IAProvider) => {
    setEditingProviderId(provider.id)
    setEditProviderData({ name: provider.name, apiKey: provider.apiKey, apiUrl: provider.apiUrl, modelName: provider.modelName, usedFor: provider.usedFor, provider: provider.provider })
  }
  const cancelEditProvider = () => {
    setEditingProviderId(null)
    setEditProviderData({})
  }
  const saveEditProvider = () => {
    if (!editingProviderId) return
    update(editingProviderId, editProviderData)
    setEditingProviderId(null)
    setEditProviderData({})
  }

  // ── JSearch keys (backend) ──
  const [jsearchKeys, setJsearchKeys] = useState<JsearchKeyRecord[]>([])
  const [newJsearchKey, setNewJsearchKey] = useState('')
  const [showJsearchKey, setShowJsearchKey] = useState(false)
  const [jsearchKeyData, setJsearchKeyData] = useState<Record<string, { ok: boolean; status: string; message: string; rate_limit_total: number; rate_limit_remaining: number | null; rate_limit_used: number }>>({})
  const [testingJsearchKey, setTestingJsearchKey] = useState<number | null>(null)
  const [editingJsearchId, setEditingJsearchId] = useState<number | null>(null)
  const [editJsearchValue, setEditJsearchValue] = useState('')
  const [jsearchLoading, setJsearchLoading] = useState(true)

  useEffect(() => {
    loadJsearchKeys()
  }, [])

  const loadJsearchKeys = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/keys`)
      const data = await res.json()
      setJsearchKeys(data.keys ?? [])
    } catch {
      setJsearchKeys([])
    } finally {
      setJsearchLoading(false)
    }
  }

  const addJsearchKey = async () => {
    const k = newJsearchKey.trim()
    if (!k) return
    const form = new FormData()
    form.set('api_key', k)
    form.set('description', '')
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/save-key`, { method: 'POST', body: form })
      const data = await res.json()
      if (data.success) {
        setNewJsearchKey('')
        await loadJsearchKeys()
      }
    } catch {}
  }

  const testJsearchKey = async (record: JsearchKeyRecord) => {
    setTestingJsearchKey(record.id)
    const form = new FormData()
    form.set('api_key', record.api_key)
    const prefix = record.api_key.slice(0, 8) + '…' + record.api_key.slice(-4)
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/test`, { method: 'POST', body: form })
      const data = await res.json()
      const prefix = record.api_key.slice(0, 8) + '…' + record.api_key.slice(-4)
      const normalized = data.valid
        ? { ok: true, status: 'ok', message: '', rate_limit_total: data.data?.rate_limit ?? 200, rate_limit_remaining: data.data?.rate_limit_remaining ?? null, rate_limit_used: (data.data?.rate_limit ?? 200) - (data.data?.rate_limit_remaining ?? 0) }
        : { ok: false, status: data.status ?? 'error', message: data.message ?? 'Chave inválida', rate_limit_total: 200, rate_limit_remaining: null, rate_limit_used: 0 }
      setJsearchKeyData(prev => ({ ...prev, [prefix]: normalized }))
    } catch {
      setJsearchKeyData(prev => ({ ...prev, [prefix]: { ok: false, status: 'error', message: 'Erro de conexão', rate_limit_total: 200, rate_limit_remaining: null, rate_limit_used: 0 } }))
    }
    setTestingJsearchKey(null)
  }

  const startEditJsearchKey = (record: JsearchKeyRecord) => {
    setEditingJsearchId(record.id)
    setEditJsearchValue(record.api_key)
  }
  const cancelEditJsearchKey = () => {
    setEditingJsearchId(null)
    setEditJsearchValue('')
  }
  const saveEditJsearchKey = async () => {
    const trimmed = editJsearchValue.trim()
    if (!trimmed || !editingJsearchId) return
    const form = new FormData()
    form.set('key_id', String(editingJsearchId))
    form.set('api_key', trimmed)
    form.set('description', '')
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/update-key`, { method: 'PUT', body: form })
      const data = await res.json()
      if (data.success) {
        setEditingJsearchId(null)
        setEditJsearchValue('')
        await loadJsearchKeys()
      }
    } catch {}
  }
  const deleteJsearchKey = async (record: JsearchKeyRecord) => {
    const form = new FormData()
    form.set('key_id', String(record.id))
    try {
      const res = await fetch(`${API_BASE_URL}/api/jsearch/delete-key`, { method: 'DELETE', body: form })
      const data = await res.json()
      if (data.success) {
        setJsearchKeyData(prev => {
          const next = { ...prev }
          const prefix = record.api_key.slice(0, 8) + '…' + record.api_key.slice(-4)
          delete next[prefix]
          return next
        })
        await loadJsearchKeys()
      }
    } catch {}
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="w-full max-w-3xl mx-auto z-10 space-y-6">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold tracking-wider">
          <Key className="w-3.5 h-3.5" />
          API · IAs
        </div>
        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">Configuração de IAs</h1>
        <p className="text-slate-400 text-sm md:text-base max-w-lg mx-auto">Cadastre suas chaves de API e escolha qual IA usar em cada ferramenta.</p>
      </div>

      {providers.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <div className={`flex items-center gap-2 px-4 py-2 rounded-2xl border ${globalStatus === 'green' ? 'bg-emerald-500/10 border-emerald-500/20' : globalStatus === 'red' ? 'bg-rose-500/10 border-rose-500/20' : 'bg-amber-500/10 border-amber-500/20'}`}>
            <div className={`w-2 h-2 rounded-full ${globalStatus === 'green' ? 'bg-emerald-400' : globalStatus === 'red' ? 'bg-rose-400' : 'bg-amber-400'}`} />
            <span className="text-xs font-semibold text-white">{providers.length} ativa(s)</span>
            <span className="text-slate-600">·</span>
            <span className={`text-xs font-semibold ${globalStatus === 'green' ? 'text-emerald-400' : globalStatus === 'red' ? 'text-rose-400' : 'text-amber-400'}`}>
              {globalStatus === 'green' ? 'Todas conectadas' : globalStatus === 'red' ? 'Algumas com erro' : 'Nenhuma testada'}
            </span>
          </div>
          <CustomButton
            onClick={() => { setShowAddForm(true); resetNewProvider() }}
            className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold rounded-2xl transition-all hover:shadow-lg hover:shadow-purple-500/20 active:scale-95"
          >
            <Plus className="w-4 h-4" /> Nova IA
          </CustomButton>
        </div>
      )}

      <div className="rounded-2xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-5 h-5 text-purple-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-bold text-white">IAs Configuradas</h3>
            <p className="text-xs text-slate-500 mt-0.5">Cadastre suas chaves de API para análise de currículos e mercado.</p>
          </div>
          {providers.length === 0 && !showAddForm && (
            <CustomButton
              onClick={() => setShowAddForm(true)}
              className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold rounded-2xl transition-all active:scale-95"
            >
              <Plus className="w-4 h-4" /> Adicionar IA
            </CustomButton>
          )}
        </div>

        <AnimatePresence>
          {showAddForm && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="rounded-2xl bg-slate-950/50 border border-slate-800/60 p-4 space-y-4">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Nova Integração de IA</h3>

              <div className="grid grid-cols-3 gap-3">
                {(['openai', 'anthropic', 'custom'] as const).map(type => {
                  const cfg = PROVIDER_CONFIG[type]
                  const isSelected = newProvider.providerType === type
                  return (
                    <button
                      key={type}
                      onClick={() => { setNewProvider(p => ({ ...p, providerType: type })); resetNewProvider(type) }}
                      className={`p-3 rounded-xl border transition-all text-left ${isSelected ? 'bg-purple-500/10 border-purple-500/50 shadow-lg shadow-purple-500/10' : 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600'}`}
                    >
                      <div className={`text-lg mb-1 ${cfg.color}`}>{cfg.icon}</div>
                      <div className={`text-xs font-semibold ${isSelected ? 'text-white' : 'text-slate-400'}`}>{cfg.name}</div>
                    </button>
                  )
                })}
              </div>

              <CustomInput placeholder="Nome (opcional)" value={newProvider.name} onChange={v => setNewProvider(p => ({ ...p, name: v }))} className="w-full" />
              <CustomInput type="password" showPasswordToggle placeholder="Chave de API" value={newProvider.apiKey} onChange={v => setNewProvider(p => ({ ...p, apiKey: v }))} className="w-full" />
              {newProvider.providerType !== 'custom' && (
                <CustomSelect
                  value={newProvider.modelName}
                  onChange={v => setNewProvider(p => ({ ...p, modelName: v }))}
                  options={config.defaultModels.map(m => ({ value: m, label: m }))}
                  placeholder="Modelo (padrão)"
                  className="w-full"
                />
              )}
              {newProvider.providerType === 'custom' && (
                <>
                  <CustomInput type="password" showPasswordToggle placeholder="Chave de API (custom)" value={newProvider.apiKey} onChange={v => setNewProvider(p => ({ ...p, apiKey: v }))} className="w-full" />
                  <CustomInput placeholder="URL da API (ex: https://api.openai.com/v1)" value={newProvider.apiUrl} onChange={v => setNewProvider(p => ({ ...p, apiUrl: v }))} className="w-full" />
                  {urlError && <p className="text-xs text-rose-400 -mt-2">{urlError}</p>}
                  <CustomInput placeholder="Nome do modelo (ex: gpt-4o, claude-3, llama-3...)" value={newProvider.modelName} onChange={v => setNewProvider(p => ({ ...p, modelName: v }))} className="w-full" />
                </>
              )}
              <CustomSelect
                value={newProvider.usedFor}
                onChange={v => setNewProvider(p => ({ ...p, usedFor: v as IAProvider['usedFor'] }))}
                options={[
                  { value: 'all', label: 'Todas as ferramentas' },
                  { value: 'curriculo', label: 'Só Currículo' },
                  { value: 'market', label: 'Só Mercado' },
                  { value: 'none', label: 'Desativada' },
                ]}
                placeholder="Onde usar"
                className="w-full"
              />
              <div className="flex gap-3 pt-2">
                <CustomButton onClick={() => { setShowAddForm(false); resetNewProvider() }} className="flex-1 py-2.5 text-sm font-semibold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-2xl transition-all">Cancelar</CustomButton>
                <CustomButton onClick={addProvider} disabled={!newProvider.apiKey.trim()} className="flex-1 py-2.5 text-sm font-semibold bg-purple-600 hover:bg-purple-500 text-white rounded-2xl transition-all disabled:opacity-40 disabled:cursor-not-allowed">Adicionar IA</CustomButton>
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

        {providers.length === 0 && !showAddForm ? (
          <div className="text-center py-8">
            <p className="text-slate-500 text-sm">Nenhuma IA configurada ainda.</p>
            <p className="text-slate-600 text-xs mt-1">Clique em "Adicionar IA" para começar.</p>
          </div>
        ) : (
          <>
            {providers.map(provider => {
              const cfg = PROVIDER_CONFIG[provider.provider]
              const isEditing = editingProviderId === provider.id

              return (
                <motion.div key={provider.id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="rounded-2xl bg-slate-950/50 border border-slate-800/60 p-4 space-y-4">
                  {isEditing ? (
                    /* Edit mode */
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 mb-3">
                        <span className={`w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center ${cfg.color}`}>{cfg.icon}</span>
                        <span className="text-sm font-bold text-white">Editar {cfg.name}</span>
                      </div>
                      <CustomInput placeholder="Nome" value={editProviderData.name ?? ''} onChange={v => setEditProviderData(p => ({ ...p, name: v }))} className="w-full" />
                      <CustomInput type="password" showPasswordToggle placeholder="Chave de API" value={editProviderData.apiKey ?? ''} onChange={v => setEditProviderData(p => ({ ...p, apiKey: v }))} className="w-full" />
                      {provider.provider === 'custom' && (
                        <CustomInput placeholder="URL da API" value={editProviderData.apiUrl ?? ''} onChange={v => setEditProviderData(p => ({ ...p, apiUrl: v }))} className="w-full" />
                      )}
                      {provider.provider === 'custom' ? (
                        <CustomInput placeholder="Nome do modelo" value={editProviderData.modelName ?? provider.modelName} onChange={v => setEditProviderData(p => ({ ...p, modelName: v }))} className="w-full" />
                      ) : (
                        <CustomSelect
                          value={editProviderData.modelName ?? provider.modelName}
                          onChange={v => setEditProviderData(p => ({ ...p, modelName: v }))}
                          options={config.defaultModels.map(m => ({ value: m, label: m }))}
                          placeholder="Modelo"
                          className="w-full"
                        />
                      )}
                      <CustomSelect
                        value={editProviderData.usedFor ?? provider.usedFor}
                        onChange={v => setEditProviderData(p => ({ ...p, usedFor: v as IAProvider['usedFor'] }))}
                        options={[
                          { value: 'all', label: 'Todas' },
                          { value: 'curriculo', label: 'Só Currículo' },
                          { value: 'market', label: 'Só Mercado' },
                          { value: 'none', label: 'Desativada' },
                        ]}
                        placeholder="Uso"
                        className="w-full"
                      />
                      <div className="flex gap-2 pt-2">
                        <CustomButton onClick={cancelEditProvider} className="flex-1 py-2 text-sm font-semibold text-slate-400 bg-slate-800 hover:bg-slate-700 rounded-2xl transition-all">Cancelar</CustomButton>
                        <CustomButton onClick={saveEditProvider} className="flex-1 py-2 text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-2xl transition-all"><Save className="w-4 h-4 inline mr-1" />Salvar</CustomButton>
                      </div>
                    </div>
                  ) : (
                    /* View mode */
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0 ${cfg.color}`}>{cfg.icon}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-white truncate">{provider.name || cfg.name}</span>
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
                        {provider.statusMessage && <span className="text-[10px] text-slate-600 max-w-[180px] text-right">{provider.statusMessage}</span>}
                        <div className="flex items-center gap-1 mt-1">
                          <button onClick={() => startEditProvider(provider)} className="p-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-amber-400 hover:border-amber-500/30 transition-all" title="Editar">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
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
                    </div>
                  )}
                </motion.div>
              )
            })}
          </>
        )}
      </div>

      <div className="rounded-2xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-5">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
            <Briefcase className="w-5 h-5 text-blue-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-bold text-white">Busca de Vagas em Tempo Real</h3>
            <p className="text-xs text-slate-500 mt-0.5">Adicione chaves JSearch API da OpenWebNinja (grátis: 200 req/chave/mês). Fallback automático entre múltiplas chaves.</p>
          </div>
          {jsearchKeys.length > 0 && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="text-blue-400 font-semibold">{jsearchKeys.length}</span> chave(s)
              <span className="text-slate-600">·</span>
              <span className="text-slate-400">~{jsearchKeys.length * 200} req/mês</span>
            </div>
          )}
        </div>

        {jsearchLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
          </div>
        ) : (
          <>
            {/* Lista de chaves como cards */}
            {jsearchKeys.map((record) => {
              const isEditing = editingJsearchId === record.id
              const keyPrefix = record.api_key.slice(0, 8) + '…' + record.api_key.slice(-4)
              const data = jsearchKeyData[keyPrefix]
              const isTesting = testingJsearchKey === record.id
              const used = record.used ?? data?.rate_limit_used ?? 0
              const remaining = record.rate_limit_remaining ?? data?.rate_limit_remaining ?? null
              const total = record.rate_limit_total ?? data?.rate_limit_total ?? 200
              const pct = remaining !== null ? Math.round(((total - remaining) / total) * 100) : 0
              let statusBadge = null
              if (isTesting) {
                statusBadge = (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[11px]">
                    <Loader2 className="w-3 h-3 animate-spin" /> Testando...
                  </span>
                )
              } else if (data) {
                if (data.ok) {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px]">
                      <CheckCircle2 className="w-3 h-3" /> OK
                    </span>
                  )
                } else if (data.status === '403') {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">
                      <XCircle className="w-3 h-3" /> Inválida
                    </span>
                  )
                } else if (data.status === '429') {
                  statusBadge = (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[11px]">
                      <AlertCircle className="w-3 h-3" /> Limite
                    </span>
                  )
                }
              } else if (record.last_tested) {
                statusBadge = (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-700/50 border border-slate-600/30 text-slate-400 text-[11px]">
                    Já testada
                  </span>
                )
              }

              return (
                <div key={record.id} className="mb-3 p-4 rounded-2xl bg-slate-950/50 border border-slate-800/60">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-slate-300 truncate">
                          {record.api_key.slice(0, 8)}…{record.api_key.slice(-4)}
                        </span>
                        {statusBadge}
                      </div>
                      {record.description && <p className="text-[11px] text-slate-500 mt-0.5">{record.description}</p>}
                      {(remaining !== null || record.rate_limit_total !== null) && (
                        <div className="mt-2">
                          <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                            <span>Uso da quota</span>
                            <span className={`font-semibold ${pct >= 90 ? 'text-red-400' : pct >= 70 ? 'text-amber-400' : 'text-emerald-400'}`}>
                              {used}/{total} usadas · {remaining !== null ? total - used : '?'} restantes
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-slate-700 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      )}
                      {data && !data.ok && (
                        <p className="text-[11px] text-red-400/70 mt-0.5">{data.message}</p>
                      )}
                      {data?.ok && (
                        <p className="text-[11px] text-emerald-400/70">{data.message}</p>
                      )}
                    </div>
                    {!isEditing && (
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => testJsearchKey(record)}
                          disabled={isTesting}
                          title="Testar chave"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-blue-400 hover:bg-blue-500/10 transition-colors disabled:opacity-40"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={() => startEditJsearchKey(record)}
                          title="Editar chave"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => deleteJsearchKey(record)}
                          title="Remover chave"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                    {isEditing && (
                      <div className="mt-3 pt-3 border-t border-slate-800 flex gap-2 items-center">
                        <input
                          type={showJsearchKey ? 'text' : 'password'}
                          value={editJsearchValue}
                          onChange={e => setEditJsearchValue(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') saveEditJsearchKey(); if (e.key === 'Escape') cancelEditJsearchKey() }}
                          className="flex-1 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white font-mono focus:outline-none focus:border-blue-500/50"
                        />
                        <button onClick={() => saveEditJsearchKey()} title="Salvar" className="p-1.5 rounded text-emerald-400 hover:bg-emerald-500/10 transition-colors"><Save className="w-3.5 h-3.5" /></button>
                        <button onClick={cancelEditJsearchKey} title="Cancelar" className="p-1.5 rounded text-slate-500 hover:bg-slate-700/60 transition-colors"><X className="w-3.5 h-3.5" /></button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {/* Input para adicionar nova chave */}
            <div className="flex gap-2 items-start mt-3">
              <div className="relative flex-1">
                <input
                  type={showJsearchKey ? 'text' : 'password'}
                  value={newJsearchKey}
                  onChange={e => setNewJsearchKey(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && newJsearchKey.trim()) addJsearchKey() }}
                  placeholder="Cole uma nova JSearch API Key e pressione Enter..."
                  className="w-full px-4 py-2.5 pr-10 rounded-xl bg-slate-800/80 border border-slate-700 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
                />
                <button
                  onClick={() => setShowJsearchKey(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  type="button"
                >
                  {showJsearchKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <CustomButton
                onClick={addJsearchKey}
                disabled={!newJsearchKey.trim()}
              >
                <Plus className="w-4 h-4" />
              </CustomButton>
            </div>
            {jsearchKeys.length > 0 && (
              <p className="mt-3 text-[11px] text-slate-600">
                As chaves são salvas no servidor. Adicione quantas quiser para ter fallback automático.
              </p>
            )}

            <div className="mt-3 flex items-center gap-3">
              <p className="text-[11px] text-slate-600">
                Obtenha chaves em{' '}
                <a href="https://app.openwebninja.com/signup" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">
                  OpenWebNinja - JSearch
                </a>{' '}
                (plano gratuito — 200 req/chave/mês)
              </p>
            </div>
          </>
        )}
      </div>

    </motion.div>
  )
}
