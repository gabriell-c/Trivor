# Debug: Docling Fallback Issue - RESOLVIDO ✅

## Problema Relatado
Usuário disse que o PDF "Currículo Milena Cardoso.pdf" estava caindo em fallback (pypdfium2) quando enviado pelo navegador.

## Diagnóstico Real
Verificação dos logs no banco de dados SQLite **mostrou que NÃO há fallback**:

### Resumo dos Logs (27 requisições)
| Métrica | Valor |
|---------|-------|
| Total de requisições /api/cv/analyze | 27 |
| Usando docling_parse | 27 (100%) |
| **Com fallback ativado** | **0 (0%)** ✅ |
| Status 200 | 24 |
| Status 500 | 3 (erro de API, não de extração) |

### Teste Final
```
Status: 200 ✅
Tempo: 8.3s
Nota: 52
Score ATS: 48
Extractor: docling_parse (confirmado nos logs)
```

## Problemas Encontrados e Corrigidos

### 1. Exibição incorreta no frontend
**Problema:** O frontend mostrava "Fallback: Não" quando não usava fallback, o que era confuso.

**Correção:** Agora mostra "Fallback: Disponível" com ícone de escudo, indicando que o fallback está como backup, mas não foi ativado.

```typescript
// Antes
{isFallback ? (
  <span>Ativado → {log.fallback_level || 'pypdfium2'}</span>
) : (
  <span>Não</span>  // Confuso!
)}

// Depois
{isFallback ? (
  <span>Ativado → {log.fallback_level || 'pypdfium2'}</span>
) : (
  <span>Disponível</span>  // Claro!
)}
```

### 2. Nome do extractor diferente
**Problema:** Frontend verificava `log.extractor === 'docling'`, mas backend logava `docling_parse`.

**Correção:**
```typescript
const isDocling = log.extractor === 'docling' || log.extractor === 'docling_parse'
```

## Conclusão
**O docling_parse está funcionando perfeitamente!**

Todas as requisições usam docling_parse sem fallback. O sistema está correto.

## Soluções Aplicadas
1. ✅ Workaround ASCII path para bug de Unicode no Windows
2. ✅ Logging detalhado de erros por página
3. ✅ Fallback chain: docling_parse → pdfplumber → pypdfium2
4. ✅ Correção de exibição no frontend (docling_parse vs docling)
5. ✅ Correção de semântica: "Não" → "Disponível"

## Como Verificar no Sistema
1. Abrir aba de **Logs** no frontend
2. Filtrar por endpoint `/api/cv/analyze`
3. Verificar coluna **Extractor** — deve mostrar **Docling** (badge verde)
4. Verificar coluna **Fallback** — deve mostrar **Disponível** (badge cinza)

## Limitações Conhecidas
- PDFs **escaneados/imagem** podem cair em fallback (necessitam OCR)
- Workaround requer cópia do pacote `docling_parse` para temp path a cada restart

## Data do Teste
2026-08-30 19:00 - **RESOLVIDO**
