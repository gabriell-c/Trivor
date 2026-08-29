# Plano de Correções - Projeto Trivor (Rodada 2)

## Resumo
Correção de 5 problemas críticos identificados na análise completa.

---

## Problemas Identificados

### 1. Missing `exportError` State (page.tsx e linkedin/page.tsx)
**Arquivos**:
- `frontend/app/page.tsx` - Usa `setExportError` mas não declara estado
- `frontend/app/linkedin/page.tsx` - Usa `setExportError` mas não declara estado
- `frontend/app/components/CurriculoTool.tsx` - Já tem o estado declarado

**Fix**: Adicionar `const [exportError, setExportError] = useState<string | null>(null)` em ambos arquivos

### 2. Missing `uuid` Package
**Problema**: `useToast.ts` importa `uuid` mas pacote não está no `package.json`
**Fix**: Remover import do `uuid` e usar `Date.now().toString()` + random

### 3. `any` Types no Dashboard
**Problema**: `useState<any[]>([])` em `dashboard/page.tsx`
**Fix**: Mudar para `useState<LogEntry[]>([])` e adicionar import

### 4. CSS Animations Missing
**Problema**: `animate-spin` e outras classes podem não estar definidas
**Fix**: Verificar e adicionar no `globals.css`

### 5. Verificar Backend
**Status**: Imports já estão corretos (sqlite3, json, os, uuid na linha 22)

---

## Arquivos a Modificar

1. `frontend/app/page.tsx` - Adicionar exportError state
2. `frontend/app/linkedin/page.tsx` - Adicionar exportError state
3. `frontend/app/hooks/useToast.ts` - Remover uuid import
4. `frontend/app/dashboard/page.tsx` - Corrigir tipo any
5. `frontend/app/globals.css` - Adicionar animações se necessário

## Verificação
- [ ] Frontend compila sem TypeScript errors
- [ ] Toast notifications funcionam
- [ ] Animações CSS funcionam
