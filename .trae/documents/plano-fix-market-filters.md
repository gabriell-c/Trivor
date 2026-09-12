# Fix: Pré-filtro agressivo, time window ignorado, poucas vagas

## Problemas

1. **Pre-filtro rejeita vagas injustamente** — seniority é filtro rígido (rejeita), mas deveria ser preferencial. Quando stack está vazio, usa job_title como fallback mas ainda pode rejeitar por seniority.
2. **time_window ignorado** — query JSearch sempre usa `date_posted=all`, ignorando a janela temporal do usuário.
3. **Poucas vagas** — `num_pages=4` limita a ~40 vagas. API suporta até `num_pages=8` (~80 vagas).

## Estado Atual vs Correção

| Problema | Atual | Correção |
|----------|-------|----------|
| num_pages | 4 (~40 vagas) | 8 (~80 vagas) |
| date_posted | "all" fixo | mapeado de time_window ("month") |
| Seniority | rejeição rígida | bônus suave (não rejeita) |
| Keywords vazio | usa job_title (strito) | passa todas vagas do cargo |

## Arquivos a Modificar

### 1. `backend/market_service.py`

**a) Linha 23-24**: Aumentar `_MAX_JOBS_FOR_ANALYSIS` de 300 → 500

**b) Linha 124-136**: Adicionar parâmetro `date_posted` em `_fetch_jsearch_jobs`:
```python
def _fetch_jsearch_jobs(query, country="br", language="pt", num_pages=8, api_keys=None, date_posted="all"):
    url_template = f"...&num_pages={num_pages}&date_posted={date_posted}"
```

**c) Nova função** (após linha 523, antes de `_keyword_score`):
```python
def map_time_window_to_date_posted(time_window: str) -> str:
    """Mapeia time_window do frontend para valor da API JSearch."""
    tw = time_window.lower().strip()
    if '30' in tw or '60' in tw or '90' in tw:
        return 'month'
    return 'all'
```

**d) Linhas 537-546**: Remover rejeição rígida de seniority, manter como bônus:
```python
# ANTES: rejeita se seniority não bater
# DEPOIS: apenas bônus, não rejeita
```

**e) Linhas 525-535**: Quando `target_stack` vazio, não rejeitar vagas que tenham pelo menos uma palavra do job_title no título (não na descrição):
```python
# Se target_stack vazio, usar job_title como keyword mas ser mais permissivo:
# Se job_title contém palavras que aparecem NO TÍTULO da vaga → passa direto
```

**f) Linha 265**: Adicionar parâmetro `date_posted="all"` em `generate_mock_jobs_if_empty`

**g) Linha 287**: `num_pages=4` → `num_pages=8`, passar `date_posted`

**h) Linha 1062**: Passar `date_posted` mapeado para `generate_mock_jobs_if_empty`:
```python
date_posted = map_time_window_to_date_posted(time_window)
generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys, date_posted=date_posted)
```

### 2. `backend/main.py` — Nenhuma mudança necessária
Já passa `time_window` para `run_market_analysis` (linha 1488).

## Passos de Implementação

1. Adicionar `map_time_window_to_date_posted`
2. Atualizar `_fetch_jsearch_jobs` com `date_posted` e `num_pages=8`
3. Tornar seniority soft (remover rejeição)
4. Tornar keyword score mais permissivo quando stack vazio
5. Passar `date_posted` em `generate_mock_jobs_if_empty`
6. Passar `date_posted` em `run_market_analysis`
7. Aumentar `_MAX_JOBS_FOR_ANALYSIS`

## Verificação

1. Testar com "Assistente Administrativo", sem stack, sem seniority restriction → todas as vagas passam
2. Testar time_window "30 dias" → usa `date_posted=month`
3. Testar time_window "90 dias" → usa `date_posted=month`
4. Verificar que `num_pages=8` retorna ~80 vagas
5. Verificar que negative keywords ainda funcionam (rejeição rígida)
6. QA manual: rodar análise completa e verificar número de vagas analisadas
