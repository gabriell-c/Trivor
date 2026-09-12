# Plano: Reformulação Completa da Busca de Mercado

## Problemas Atuais

1. **Poucas vagas retornadas** — `num_pages=8` + 1 chave = ~80 vagas máx. Rate limit bloqueia.
2. **Time window ignorado** — `date_posted` mapeia tudo para "month" (30/60/90 dias). API não tem "90 days".
3. **Location complexo** — 4 modos (remoto/estado/pais/outro) com selects aninhados. Usuário quer simplificado: apenas "Nacional" / "Internacional".
4. **Sem detecção de nacional/internacional** — Não há lógica para determinar se uma vaga é BR ou exterior.
5. **Stack vazio = muito restritivo** — Usar job_title como única keyword pode rejeitar vagas válidas.
6. **Negative keywords = substring** — Pode causar falsos positivos (ex: "doc" excluiria "docente").
7. **Seniority sem "Nenhum"** — Cargos como "Auxiliar de Escritório" não têm nível.
8. **Uma só chave JSearch** —usuário forneceu 4 chaves para rodízio.

## Mudanças Propostas

### Arquivo: `backend/market_service.py`

#### 1. Aumentar volume de busca
- `_MAX_JOBS_FOR_ANALYSIS`: 500 → **1000**
- `_BATCH_SIZE`: 6 → **10**
- `num_pages` default: 8 → **12**
- Adicionar suporte a **múltiplas queries** por job title (ex: "enfermeiro", "enfermagem", "tecnico enfermagem")

#### 2. Nova função: `detect_job_nationality(job_text, job_country, salary)`
Detecta se vaga é Nacional ou Internacional:
- **Nacional**: idioma português no texto, moeda BRL/R$, cidade no Brasil
- **Internacional**: idioma inglês no texto, moeda USD/EUR, país != Brasil
- Vagas remotas: usar idioma do texto como critério principal

#### 3. Atualizar `_fetch_jsearch_jobs`
- Parâmetro `num_pages` → default 12
- Adicionar suporte a `queries: List[str]` — faz busca múltipla e combina resultados
- Rodízio inteligente de chaves com delay entre requisições

#### 4. Atualizar `map_time_window_to_date_posted`
- "7 dias" → "3days" (API mais próxima)
- "15 dias" → "week"
- "30 dias" → "month"
- "60 dias" → "month"
- "90 dias" → "all" (API não suporta >30 dias)

#### 5. Refatorar `_keyword_score`
- Adicionar opção "Nenhum" para seniority → sem filtro de seniority
- Quando stack vazio: usar apenas palavras do job_title com **word boundary** (evita falsos positivos)
- Manter seniority como bônus (não rejeição)
- Negative keywords: usar **word boundary regex** para evitar substring matching

#### 6. Atualizar `_pre_filter_jobs`
- Adicionar filtro de nacionalidade baseado na seleção do usuário
- "Remoto Nacional" → rejeita vagas internacionais
- "Remoto Internacional" → rejeita vagas nacionais
- Usar `detect_job_nationality()` para classificar vagas

#### 7. Atualizar `generate_mock_jobs_if_empty`
- Aceitar múltiplos queries (lista de termos de busca)
- Usar todas as chaves JSearch disponíveis
- Aumentar `num_pages` para 12

#### 8. Atualizar `_build_jobs_from_raw`
- Adicionar campo `nationality` (calculado via `detect_job_nationality`)
- Melhorar detecção de idioma do texto

### Arquivo: `frontend/app/market/page.tsx`

#### 1. Simplificar Escopo Geográfico
- Remover `LocationMode` (remoto/estado/pais/outro)
- Substituir por toggle simples: **Nacional** | **Internacional**
- Determinar automaticamente baseado no idioma da vaga (já classificado no backend)

#### 2. Senioridade — adicionar "Nenhum"
- Opções: `['Nenhum', 'Estagiário', 'Júnior', 'Pleno', 'Sênior', 'Especialista']`

#### 3. Janela Temporal — expandir opções
- Opções: `['7 dias', '15 dias', '30 dias', '60 dias', '90 dias']`

#### 4. Atualizar `getLocationValue()`
- Retornar `"Remoto Nacional"` ou `"Remoto Internacional"` baseado no toggle

#### 5. Manter campos existentes
- Área / Cargo-Alvo: manter como está
- Stack / Skills: manter como está
- Palavras-chave Negativas: manter como TagInput

### Arquivo: `backend/main.py`
- Nenhuma mudança necessária — endpoint já passa todos os parâmetros corretamente

## Detalhes de Implementação

### Multi-query search
```python
def _fetch_jsearch_jobs_multi(query, country, language, num_pages, api_keys, date_posted):
    """Faz múltiplas buscas com variações do query e combina resultados."""
    queries = [query]
    # Adicionar variações: adicionar "vaga", "empleo", etc.
    # Mas cuidado para não duplicar resultados
    all_jobs = {}
    for api_key in api_keys:
        for q in queries:
            jobs, rem, tot = _fetch_jsearch_jobs(q, country, language, num_pages, [api_key], date_posted)
            for j in jobs:
                key = j.get("apply_link") or j.get("title", "") + j.get("company", "")
                all_jobs[key] = j
            time.sleep(0.5)  # evitar rate limit
    return list(all_jobs.values())
```

### Detectar nacionalidade
```python
def detect_job_nationality(job_text, job_country, salary=""):
    text_lower = job_text.lower()
    salary_lower = salary.lower()

    # Moeda indica internacional
    if any(c in salary_lower for c in ["$", "usd", "euro", "€", "us dolar"]):
        return "internacional"
    if "r$" in salary_lower or "real" in salary_lower or "brl" in salary_lower:
        return "nacional"

    # País indica
    if job_country and job_country.lower() != "br":
        return "internacional"
    if job_country == "br" or job_country == "Brasil":
        return "nacional"

    # Idioma do texto
    english_patterns = ["english", "required", "native", "bilingual", "fluent", "usd", "dollar"]
    portuguese_patterns = ["português", "portugues", "fluxo", "vaga", "salário", "salario", "brasileiro"]

    eng_count = sum(1 for p in english_patterns if p in text_lower)
    por_count = sum(1 for p in portuguese_patterns if p in text_lower)

    if eng_count > por_count + 2:
        return "internacional"
    if por_count > eng_count:
        return "nacional"

    return "nacional"  # default
```

### Word boundary para negative keywords
```python
# Em vez de: if nk in job_text_lower
# Usar: if re.search(r'\b' + re.escape(nk) + r'\b', job_text_lower)
```

### Word boundary para stack keywords
```python
# Quando stack vazio, usar job_title palavras com word boundary
# Ex: "enfermeiro" deve match "enfermeiro" mas não "enferm"
```

## Verification Steps

1. Testar busca "enfermeiro" com 4 chaves → esperar >=100 vagas
2. Testar busca "enfermeiro" com negative keyword "word" → verificar que nenhuma vaga com "word" aparece
3. Testar busca com stack "excel" → apenas vagas com "excel" aparecem
4. Testar busca com stack vazio → vagas genéricas da área aparecem
5. Testar time_window "30 dias" → date_posted=month
6. Testar time_window "90 dias" → date_posted=all
7. Testar location "Nacional" → rejeita vagas internacionais
8. Testar location "Internacional" → rejeita vagas nacionais
9. Testar seniority "Nenhum" → não filtra por senioridade
10. QA manual via UI: configurar tudo e executar análise completa

## Arquivos a Modificar
- `backend/market_service.py` — todas as mudanças de lógica
- `frontend/app/market/page.tsx` — simplificar location, adicionar "Nenhum", expandir time_window
- `backend/main.py` — nenhuma mudança
