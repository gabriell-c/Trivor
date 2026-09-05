# Plano: Corrigir anos de experiência em requirements + Box de Idiomas

## Resumo
Dois ajustes no módulo de inteligência de mercado:
1. Remover strings de "anos de experiência" dos campos `requirements`/`soft_skills` (safety net regex + reforço no prompt).
2. Adicionar box de idiomas no frontend com níveis classificados (Básico/Intermediário/Avançado).

---

## Estado Atual

### Backend (`market_service.py`)
- `_sanitize_requirements` (linha 868): remove benefícios, modalidades e processos dos requirements. **Não filtra anos de experiência.**
- `_extract_languages` (linha 906): já existe e funciona — extrai idiomas de requirements/nice_to_have e os remove dos campos. **Porém o resultado é descartado na linha 1282** (`extracted_languages = _extract_languages(extracted)` — valor nunca usado).
- Verificação Final no prompt (linhas 818-825 e 1127-1134): instrui a IA a não colocar benefícios/processos em requirements, mas **não menciona anos de experiência**.
- Agregação de stats (linha 1349-1354): não há contador de idiomas.
- `report_result["statistics"]` (linha 1432-1444): não tem `top_languages`.

### Frontend (`page.tsx`)
- Box de Certificações existe (linha 511-536).
- Não há box de idiomas.
- `MarketReportStatistics` em `analysis.ts` (linha 148-156): não tem `top_languages`.

---

## Mudanças Propostas

### 1. Backend — Remover anos de experiência dos requirements (safety net)

**Arquivo:** `c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\market_service.py`

#### 1a. Adicionar padrão de experiência ao `_sanitize_requirements` (linha ~892)
Adicionar uma nova lista `experience_patterns` com regex para capturar strings como:
- "2 a 5 Anos De Experiência"
- "3+ anos de experiência"
- "1 ano de experiência"
- "Experiência de 2 a 5 anos"

Inserir no `combined` regex e filtrar como as outras categorias.

```python
experience_patterns = [
    r"[\d]+\s*(?:a\s+[\d]+)?\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
    r"[\d]+\s*[\+]\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
    r"[\d]+\s*[\+]\s*ano?\s*(?:de\s*)?(?:experiência|experiencia)",
    r"experiência\s+(?:de\s+)?[\d]+\s*anos?",
    r"[\d]+\s*(?:a|até)\s*[\d]+\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
]
```

Adicionar ao `combined` na linha 894:
```python
combined = "|".join(benefit_patterns + modality_patterns + process_patterns + experience_patterns)
```

#### 1b. Reforçar o Verificação Final nos dois prompts
**Prompt `extract_job_with_ai`** (linha ~824, antes de "SOMENTE se a PESSOA..."):
Adicionar linha:
```
- ANOS DE EXPERIÊNCIA (X anos, 2-5 anos, mínimo X anos) -> vai para exp_years_min/exp_years_max, NÃO é skill
```

**Prompt `extract_jobs_batched`** (linha ~1133, mesma posição):
Mesma adição.

---

### 2. Backend — Agregação e persistência de idiomas

**Arquivo:** `c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\market_service.py`

#### 2a. Capturar idiomas no loop de extração (linha ~1282)
Já existe: `extracted_languages = _extract_languages(extracted)`.
Substituir por uso real — passar para o dict `extracted_jobs`.

No `extracted_jobs.append` (linha 1320-1340), adicionar:
```python
"languages": extracted_languages,
```

#### 2b. Agregação de idiomas (linha ~1349-1354)
Adicionar variável:
```python
language_counts = {}  # {"Inglês": count, "Espanhol": count, ...}
```

No loop `for ej in extracted_jobs:` (linha 1356), adicionar:
```python
for lang in ej.get("languages", []):
    lang_name = lang.get("name", "Desconhecido")
    language_counts[lang_name] = language_counts.get(lang_name, 0) + 1
```

#### 2c. Ranking de idiomas (após linha 1388, antes de exp_years_sorted)
```python
language_ranking = [
    {"name": name, "count": count, "percentage": round((count / rel_total) * 100, 1)}
    for name, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True)
]
```

#### 2d. Adicionar `top_languages` ao `report_result["statistics"]` (linha ~1441)
```python
"top_languages": [
    {"name": k, "count": v} for k, v in sorted(language_counts.items(), key=lambda x: x[1], reverse=True)[:15]
],
```

#### 2e. Adicionar `top_languages` ao dict de retorno vazio (linha ~1256)
```python
"top_languages": [],
```

---

### 3. Frontend — Atualizar tipos TypeScript

**Arquivo:** `c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\frontend\app\types\analysis.ts`

Adicionar campo em `MarketReportStatistics` (linha 155, após `top_certifications`):
```typescript
top_languages: { name: string; count: number }[]
```

---

### 4. Frontend — Box de Idiomas

**Arquivo:** `c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\frontend\app\market\page.tsx`

#### 4a. Adicionar state para paginação (linha ~60)
```typescript
const [langPage, setLangPage] = useState(0)
```

#### 4b. Importar ícone de idioma (linha ~4-28)
Adicionar `Languages` (ou `Globe`) ao import de `lucide-react`.

#### 4c. Inserir box após o box de Certificações (linha ~537, antes do `{/* Confidence */}`)
Criar box idêntico ao de Certificações, com:
- Ícone `Globe` + título "Idiomas Mais Requisitados"
- Lista paginada de `R.statistics.top_languages`
- Cada item mostra: nome do idioma + badge de nível (se disponível) + contagem
- Como os dados agregados só têm `name` e `count` (sem nível), exibir apenas nome + count. Se quiser mostrar nível, seria necessário agregar também os níveis separadamente — mas o usuário pediu "lista organizada com IDIOMAS" e "saber exatamente quais idiomas são mais pedidos e em que nível". Para isso, preciso agregar também por nível.

**Decisão:** Vou agregar idiomas mantendo os níveis. Em vez de só contar por nome, vou contar por `(nome, nível)` e exibir agrupado por idioma com os níveis mais citados.

Alternativa mais simples (e suficiente): agregar `top_languages` como `{name, count, level?: string}` onde `level` é o nível mais frequente para aquele idioma.

Para simplificar e seguir o padrão existente, vou manter a agregação simples `{name, count}` no statistics e adicionar uma segunda agregação `language_levels` que mostra os níveis mais comuns por idioma. O box exibirá: idioma + nível mais comum + count.

Na verdade, para não complicar, vou fazer a agregação direta: cada idioma com seu nível mais citado. Vou criar um dicionário `language_level_counts = {}` que acumula `(nome, nível) -> count`, e no ranking escolho o nível com maior count para cada idioma.

```python
language_level_counts = {}  # {"Inglês": {"B2": 5, "C1": 3}, "Espanhol": {"B1": 2}}
```

No loop:
```python
for lang in ej.get("languages", []):
    lname = lang.get("name", "Desconhecido")
    llevel = lang.get("level") or "Não especificado"
    if lname not in language_level_counts:
        language_level_counts[lname] = {}
    language_level_counts[lname][llevel] = language_level_counts[lname].get(llevel, 0) + 1
```

Depois gerar o ranking:
```python
language_ranking = []
for lname, levels in sorted(language_level_counts.items(), key=lambda x: sum(x[1].values()), reverse=True):
    top_level = max(levels.items(), key=lambda x: x[1])
    language_ranking.append({
        "name": lname,
        "count": sum(top_level[1] for top_level in [max(levels.items(), key=lambda x: x[1])]),
        "top_level": top_level[0],
    })
```

E no statistics:
```python
"top_languages": [
    {"name": r["name"], "count": r["count"], "top_level": r["top_level"]}
    for r in language_ranking[:15]
],
```

#### 4d. Render do box no frontend
Depois do box de Certificações (linha ~537):
```tsx
<div className="rounded-3xl bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-6">
  <h3 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
    <Globe className="w-4 h-4 text-blue-400" />
    Idiomas Mais Requisitados
  </h3>
  <div className="space-y-2">
    {R.statistics.top_languages.slice(langPage * STAT_PAGE_SIZE, (langPage + 1) * STAT_PAGE_SIZE).length > 0
      ? R.statistics.top_languages.slice(langPage * STAT_PAGE_SIZE, (langPage + 1) * STAT_PAGE_SIZE).map(l => (
        <div key={l.name} className="flex items-center justify-between p-2 rounded-xl bg-slate-950/60">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-300">{l.name}</span>
            {l.top_level && l.top_level !== 'Não especificado' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-blue-500/15 text-blue-300 border border-blue-500/20">
                {l.top_level}
              </span>
            )}
          </div>
          <span className="text-[10px] text-slate-500">{l.count}x</span>
        </div>
      ))
      : <p className="text-xs text-slate-500">Nenhum idioma extraído.</p>
    }
  </div>
  {R.statistics.top_languages.length > STAT_PAGE_SIZE && (
    <div className="flex items-center justify-center gap-2 mt-3 pt-3 border-t border-slate-800">
      <button onClick={() => setLangPage(p => Math.max(0, p - 1))} disabled={langPage === 0}
        className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
        Anterior
      </button>
      <span className="text-xs text-slate-500">{langPage + 1} / {Math.ceil(R.statistics.top_languages.length / STAT_PAGE_SIZE)}</span>
      <button onClick={() => setLangPage(p => p + 1)} disabled={(langPage + 1) * STAT_PAGE_SIZE >= R.statistics.top_languages.length}
        className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
        Próximo
      </button>
    </div>
  )}
</div>
```

---

## Ordem de Execução

1. **Backend — `_sanitize_requirements`**: adicionar `experience_patterns` e incluir no combined regex.
2. **Backend — Prompts**: adicionar regra de anos de experiência na Verificação Final (ambos os prompts).
3. **Backend — Agregação de idiomas**: modificar `_extract_languages` call para capturar resultados, adicionar agregação por `(nome, nível)`, adicionar `top_languages` ao statistics.
4. **Frontend — Tipos**: adicionar `top_languages` em `MarketReportStatistics`.
5. **Frontend — Box Idiomas**: adicionar state, ícone, e render do box.

---

## Casos de Borda

- **Idioma sem nível**: `_extract_languages` já trata com `level = None`. No ranking, nível ausente será exibido como "Não especificado" ou omitido.
- **Nenhum idioma extraído**: box mostra "Nenhum idioma extraído."
- **Anos de experiência já removidos pela IA**: safety net é redundante mas segura (regex não casa → nada acontece).
- **Experiência com vírgula/formatação variada**: patterns cobrem "2 a 5", "2-5", "2+", "mínimo 2", "até 5".

---

## Arquivos Modificados

1. `backend/market_service.py` — safety net + prompts + agregação de idiomas
2. `frontend/app/types/analysis.ts` — tipo `top_languages`
3. `frontend/app/market/page.tsx` — box de idiomas
