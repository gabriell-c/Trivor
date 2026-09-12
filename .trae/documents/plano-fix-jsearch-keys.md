# Fix: JSearch Keys não são usadas na análise de mercado

## Problema

O frontend da página de mercado (`market/page.tsx`) lê as chaves JSearch do `localStorage('trivor_jsearch_keys')`, que está sempre vazio. A página de configurações (`api-settings/page.tsx`) salva as chaves no backend SQLite via `/api/jsearch/save-key`, mas nunca sincroniza com o localStorage.

Resultado: a análise de mercado é enviada sem chaves JSearch → backend retorna "Chave inválida" ou 0 vagas.

## Fluxo Atual (quebrado)

```
api-settings/page.tsx
  → POST /api/jsearch/save-key (salva no SQLite)
  → NÃO atualiza localStorage

market/page.tsx
  → localStorage.getItem('trivor_jsearch_keys') → null/vazio
  → formData.set('jsearch_api_keys', '') → backend recebe string vazia
  → backend: jsearch_api_keys=[] → nenhuma chave usada
```

## Solução

Fazer o market page buscar as chaves do backend via API antes de rodar a análise.

### Arquivos a modificar

#### 1. `frontend/app/market/page.tsx` (linha 111-114)

**Antes:**
```typescript
const jsearchKeysRaw = localStorage.getItem('trivor_jsearch_keys')
const jsearchKeys = jsearchKeysRaw ? JSON.parse(jsearchKeysRaw) : []
formData.set('jsearch_api_keys', Array.isArray(jsearchKeys) ? jsearchKeys.join(',') : '')
```

**Depois:**
```typescript
// Busca chaves JSearch do backend (onde são salvas na página de settings)
let jsearchKeysStr = ''
try {
  const res = await fetch(`${API_BASE_URL}/api/jsearch/keys`)
  if (res.ok) {
    const data = await res.json()
    jsearchKeysStr = (data.keys || [])
      .map((k: { api_key: string }) => k.api_key)
      .join(',')
  }
} catch {}
formData.set('jsearch_api_keys', jsearchKeysStr)
```

### Mudança única — 1 arquivo

## Testes de QA

1. **Teste manual:** Adicionar chave JSearch em `/api-settings` → ir para `/market` → executar análise → verificar se vagas são retornadas
2. **Teste E2E:** Simular fluxo completo do usuário: configurar chave → analisar mercado → verificar resultados

## Arquivo a modificar

- `frontend/app/market/page.tsx` (linha ~111)
