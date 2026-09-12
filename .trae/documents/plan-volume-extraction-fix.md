# Plano: Aumentar Volume e Garantir Extração Completa de Skills

## Problemas Identificados

### 1. Volume Baixo (~200-400 vagas)
- `num_pages=1` → cada query retorna apenas ~12 vagas (limite da API)
- 12 queries sequenciais com delay de 3s = lento e limitado
- Rate limit por IP (não por chave) — todas as 6+ chaves do mesmo IP compartilham quota
- Total máximo realista: ~144 vagas (12 queries × 12 vagas) com num_pages=1

### 2. Skills Extraídos de Forma Incompleta
- `_ensure_common_skills` já existe mas pode não cobrir todas variações
- Fallback heurístico pode não estar disparando quando necessário
- Prompt de extração precisa de mais instruções explícitas sobre anos de experiência

### 3. Motivos de Descarte não Exibidos
- `rejected_reasons_sample` veio vazio (0 descartados) — precisa verificar se há vagas rejeitadas

### 4. Soft Skills / Nice-to-have / Idiomas / Anos de Experiência
- Precisa verificar se o prompt de extração em lote pede explicitamente cada um
- Verificar se `_extract_languages` está funcionando corretamente

---

## Análise do Código Atual

### Arquivos Principais
- `backend/market_service.py` — toda a lógica de busca, filtragem, extração
- `backend/main.py` (linha 1430) — endpoint `/api/market/analyze`

### Fluxo Atual
1. `generate_mock_jobs_if_empty()` → busca vagas JSearch (12 queries, num_pages=1)
2. `_pre_filter_jobs()` → pré-filtro geográfico/score
3. `extract_jobs_batched()` → IA extrai dados em lotes de 10
4. `_sanitize_requirements()` → limpa lixo dos requisitos
5. `_ensure_common_skills()` → safety net para skills admin
6. `_extract_languages()` → extrai idiomas
7. Montagem do relatório com estatísticas

### Limitações da JSearch API
- ~12-15 vagas por página por query
- `num_pages` até ~5 funciona (retorna ~60-75 vagas por query)
- Rate limit por IP: ~1000 req/mês por IP
- Com 12 queries × num_pages=5 = 60 requisições por análise — dentro da cota

---

## Mudanças Propostas

### Mudança 1: Aumentar num_pages e otimizar queries [CRÍTICO]

**Arquivo**: `backend/market_service.py`

**O que**: Aumentar `num_pages` de 1 para 5 (máximo que a API suporta sem erro).
**Porquê**: num_pages=1 → ~12 vagas/query. num_pages=5 → ~60 vagas/query. Com 12 queries = ~720 vagas brutas.
**Como**:
```python
# Linha 783 — mudar num_pages=1 para num_pages=5
jobs, rem, tot = _fetch_jsearch_jobs(q, country=country, language=language,
                                       num_pages=5, api_keys=keys_subset, date_posted=date_posted)
```

Também adicionar mais variações de query para cobrir mais resultados:
```python
# Adicionar queries extras:
queries.append(f"{search_query} entrada")
queries.append(f"{search_query} vaga")
queries.append(f"{search_query} no brasil")
queries.append(f"{search_query} online")
queries.append(f"{search_query} home office")
queries.append(f"{search_query} clt emprego")
```

**Delay entre queries**: manter 3s, mas com num_pages=5 cada query leva mais tempo. Total estimado: 18 queries × 3s = 54s de busca + processamento IA.

### Mudança 2: Melhorar prompt de extração em lote [CRÍTICO]

**Arquivo**: `backend/market_service.py` (~linha 1799)

**O que**: Tornar o prompt mais explícito sobre ANOS DE EXPERIÊNCIA, SOFT SKILLS, e separação requirements vs nice_to_have.
**Porquê**: O prompt atual pede "extraia TUDO" mas não especifica campos como exp_years_min/max de forma explícita.
**Como**: Adicionar ao prompt:
```
- exp_years_min/exp_years_max: ANOS de experiência exigidos. Extraia DO TEXTO da vaga.
  Ex: "experiência de 2 a 5 anos" → exp_years_min: 2, exp_years_max: 5
  Ex: "mínimo 3 anos" → exp_years_min: 3, exp_years_max: None
- Para nice_to_have: SEMPRE que a vaga usar "desejável", "diferencial", "vantajoso", "não obrigatório"
  coloque no nice_to_have, NÃO nos requirements.
```

### Mudança 3: Expandir _ensure_common_skills [IMPORTANTE]

**Arquivo**: `backend/market_service.py` (~linha 1576)

**O que**: Adicionar mais padrões de regex para cobrir mais skills e variações.
**Porquê**: Padrões atuais cobrem Word/Excel/PowerPoint/Informática/Digitação/Ensino Médio/Superior/Inglês/Redação/Atenção a detalhes. Falta: Excel (mencionado sozinho), Pacote Office, Análise de dados, etc.
**Como**: Expandir `_ADMIN_COMMON_SKILLS` e `_ADMIN_KEYWORDS`:
```python
_ADMIN_KEYWORDS = [
    "administrativo", "administrativa", "assistente", "escritório", "escritorio",
    "clerical", "secretário", "secretaria", "recepcionista", "analista",
    "vaga", "emprego", "contratação", "contratacao", "departamento",
    "cartório", "financeiro", "contábil", "comercial", "operacional",
]

_ADMIN_COMMON_SKILLS = [
    (r"\bword\b", "Word"),
    (r"\bpower\s*point\b", "PowerPoint"),
    (r"\bpacote\s+office\b", "Excel"),
    (r"\bexcel\b", "Excel"),
    (r"\binformática\b", "Informática"),
    (r"\binformático\b", "Informática"),
    (r"\bdigitação\b", "Digitação"),
    (r"\bredação\b", "Redação"),
    (r"\binglês\b", "Inglês"),
    (r"\benglish\b", "Inglês"),
    (r"\bensino\s+médio\b", "Ensino Médio"),
    (r"\bensino\s+superior\b", "Ensino Superior"),
    (r"\bsuperior\s+completo\b", "Ensino Superior Completo"),
    (r"\bformação\s+superior\b", "Ensino Superior"),
    (r"\bgraduação\b", "Ensino Superior"),
    (r"\bexperiência\s+(?:de\s+)?(?:\d+\s*(?:e|até)\s*)?\d*\s*(?:anos?)?\b", "Experiência na Área"),
    (r"\bexperiencia\s+(?:na)?\s*area\b", "Experiência na Área"),
    (r"\batenção\s+a\s+detalhes\b", "Atenção a Detalhes"),
    (r"\bolho\s+ao\s+detalhe\b", "Atenção a Detalhes"),
    (r"\banálise\s+de\s+dados\b", "Análise de Dados"),
    (r"\banalise\s+de\s+dados\b", "Análise de Dados"),
    (r"\borganiza(?:ção|ao)\b", "Organização"),
    (r"\bcomunicação\b", "Comunicação"),
    (r"\bproatividade\b", "Proatividade"),
    (r"\btrabalho\s+em\s+equipe\b", "Trabalho em Equipe"),
]
```

### Mudança 4: Melhorar fallback heurístico [IMPORTANTE]

**Arquivo**: `backend/market_service.py` (~linha 1710)

**O que**: Tornar o fallback heurístico mais abrangente — extrair também soft skills e anos de experiência.
**Porquê**: O fallback atual só extrai requirements/nice_to_have. Soft skills e exp_years ficam None.
**Como**: Expandir a função `_fallback_extract` ou criar `_fallback_extract_comprehensive` que também extrai:
- Soft skills via regex (proatividade, organização, comunicação, etc.)
- Anos de experiência via regex (já existe em heuristic_extract mas precisa ser chamado)
- Certificações via regex

### Mudança 5: Garantir que rejected_reasons aparecem [VERIFICAR]

**O que**: Verificar por que `rejected_reasons_sample` veio vazio (0 descartados).
**Hipótese**: Com o volume maior e filtro prévio, talvez poucas vagas sejam descartadas. Ou o campo não está sendo populado.
**Ação**: Adicionar logging no pipeline para contar quantas vagas são descartadas vs relevantes. Se houver descartes sem motivo, verificar o prompt de batch extraction.

---

## Ordem de Implementação

1. **Mudança 1** — Aumentar num_pages para 5 e adicionar queries extras (volume)
2. **Mudança 2** — Melhorar prompt de extração (anys de experiência, soft skills, nice_to_have)
3. **Mudança 3** — Expandir _ensure_common_skills (cobertura de skills)
4. **Mudança 4** — Melhorar fallback heurístico (soft skills, exp)
5. **Mudança 5** — Verificar e corrigir rejected_reasons

## Verificação

Após implementação, testar com:
```
job_title: assistente administrativo
target_stack: administrativo
location: Nacional
time_window: 30 dias
jsearch_api_keys: [todas as 6 novas chaves]
```

Métricas esperadas:
- `total_jobs_scanned` > 500 (antes: ~200-400)
- `required_technologies` — Word em 30+ vagas, Excel em 20+ vagas
- `soft_skills` — presença de organização, comunicação, proatividade
- `top_languages` — Inglês presente em varias vagas
- `rejected_reasons_sample` — mostrar motivos para vagas descartadas
