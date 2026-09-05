# Plano: Melhoria da Análise de Currículo (Não só Dev)

## Resumo das Alterações

1. **Prompt do backend — remover viés Dev, generalizar para qualquer área**
2. **Mover download/export para o topo da página de resultado (select único)**
3. **Seção "Uso de Tokens" — sanfonada e reduzida a: prompt, completion, modelo, total**

---

## 1. Backend — Generalizar o prompt de análise

**Arquivo:** `backend/main.py` (linhas ~279–340)

**O que está errado hoje:**
- Referências a "GitHub", "JavaScript", "stack", "tecnologias", "CRUD" — tudo específico de devs
- Exemplos de frase genérica: `"apaixonado por tecnologia"` — só faz sentido para TI
- Fórmula XYZ mencionada como "Atingi X, mensurado por Y, fazendo Z" com foco em tech
- Erros comuns listam "Tecnologias citadas só na seção de skills"

**O que mudar:**
- Substituir o guia por uma versão genérica focada em **princípios universais de currículo** (estrutura, formatação, clareza, métricas, palavras-chave, ATS)
- Referências a "stack", "GitHub", "JS" → remover ou generalizar para "links profissionais"
- `"apaixonado por tecnologia"` → `"frases genéricas ou clichês"`
- `"tecnologias usadas"` → `"competências/habilidades aplicadas"`
- `"CRUD genérico de tutorial"` → `"projetos sem impacto mensurável"`
- Manter a estrutura de análise por seção (contato, resumo, experiência, educação, habilidades, projetos, certificações, idiomas)
- A `area` já é enviada pelo frontend, já aparece no prompt — já está correto nesse aspecto

---

## 2. Frontend — Mover download para o topo, usar select único

**Arquivos:** `frontend/app/page.tsx` e `frontend/app/components/CurriculoTool.tsx`

### Estado novo
Adicionar `exportFormat` state (padrão `'pdf'`) em ambos os arquivos:
```ts
const [exportFormat, setExportFormat] = useState<'json' | 'md' | 'docx' | 'pdf'>('pdf')
```

### Modificar `handleExport`
Remover o parâmetro de formato e usar `exportFormat` do estado:
```ts
const handleExport = async () => {
  if (!res) return
  setExporting(exportFormat)
  // ... resto igual, usa exportFormat ao invés de param format
}
```

### Mover download para o topo (score card)
No score card (canto direito, ao lado de "Métricas IA" e "Nova análise"), adicionar um select de download:
```tsx
<select
  value={exportFormat}
  onChange={(e) => setExportFormat(e.target.value as 'json' | 'md' | 'docx' | 'pdf')}
  className="px-2 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-300 border border-slate-700/60 focus:outline-none focus:border-indigo-500/40"
>
  <option value="pdf">📄 PDF</option>
  <option value="docx">📄 DOCX</option>
  <option value="md">📝 Markdown</option>
  <option value="json">🔧 JSON</option>
</select>
<button
  onClick={handleExport}
  disabled={exporting !== null}
  className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/60 text-slate-400 border border-slate-700/60 hover:text-white hover:border-indigo-500/40 transition disabled:opacity-50"
>
  {exporting !== null ? (
    <><RefreshCw className="w-3 h-3 animate-spin" /></>
  ) : (
    <><Download className="w-3 h-3" /> Exportar</>
  )}
</button>
```

### Remover seção de tokens/export do final
Apagar completamente a seção `{/* Tokens and export */}` que aparece no final (linhas ~703-742 do page.tsx e ~719-766 do CurriculoTool.tsx).

### Tornar métricas IA sanfonadas (reaproveitar `showMetrics`)
A seção "Métricas IA" já existe (botão no score card). Quando `showMetrics` é true, mostra model, prompt tokens, completion tokens, response time, request ID.

**Atualizar para mostrar apenas:**
- Modelo usado
- Tokens de input (prompt)
- Tokens de output (completion)
- Total de tokens

Remover: response time, request ID, e o botão "Métricas IA" com toggle desnecessário — em vez disso, transformar em uma seção sanfonada nativa usando `<details>`/`<summary>` ou um accordion simples com chevron.

Nova estrutura da seção sanfonada (aparece abaixo do score card, recolhida por padrão):
```tsx
<details className="rounded-2xl bg-slate-900/60 border border-slate-800">
  <summary className="flex items-center justify-between px-5 py-3 cursor-pointer text-xs font-bold text-slate-400 uppercase tracking-wider hover:text-slate-300">
    <span className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-indigo-400" /> Uso de Tokens</span>
    <ChevronDown className="w-4 h-4 transition-transform duration-200" />
  </summary>
  <div className="px-5 pb-4 pt-2 grid grid-cols-4 gap-3">
    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
      <p className="text-[10px] text-slate-500 mb-1">Modelo</p>
      <p className="text-xs font-black text-white font-mono truncate">{res.api_info?.model || '—'}</p>
    </div>
    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
      <p className="text-[10px] text-slate-500 mb-1">Input</p>
      <p className="text-xs font-black text-indigo-300 font-mono">{formatTokens(res.uso_tokens?.prompt_tokens)}</p>
    </div>
    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
      <p className="text-[10px] text-slate-500 mb-1">Output</p>
      <p className="text-xs font-black text-purple-300 font-mono">{formatTokens(res.uso_tokens?.completion_tokens)}</p>
    </div>
    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-center">
      <p className="text-[10px] text-slate-500 mb-1">Total</p>
      <p className="text-xs font-black text-white font-mono">{formatTokens(res.uso_tokens?.total_tokens)}</p>
    </div>
  </div>
</details>
```

### Remover estado `showMetrics`
Como a seção de tokens agora é um `<details>` nativo (sanfonado), o botão "Métricas IA" e o estado `showMetrics` não são mais necessários. Remover de ambos os arquivos.

---

## Checklist de arquivos a modificar

| Arquivo | Alterações |
|---------|-----------|
| `backend/main.py` (linhas 279–340) | Reescrever prompt: remover referências a Dev, generalizar para qualquer área |
| `frontend/app/page.tsx` | Adicionar `exportFormat` state; mover select+botão exportar para score card; remover seção tokens/export do final; transformar métricas IA em `<details>` sanfonado; remover `showMetrics` |
| `frontend/app/components/CurriculoTool.tsx` | Mesmas alterações do page.tsx |

---

## Assunções
- `formatTokens()` já existe no CurriculoTool.tsx (linha 89); em page.tsx verificar se existe ou usar `toLocaleString` direto
- O `<details>`/`<summary>` é suportado nativamente no navegador, não precisa de biblioteca adicional
- O select de export deve usar o ícone `Download` do lucide-react (já importado)
