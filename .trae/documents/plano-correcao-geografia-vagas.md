# Plano: Corrigir busca de vagas — nacional vs internacional

## Resumo
Ao selecionar "Remoto Nacional" o sistema busca vagas com `country="br"` e `language="pt"`, mas **ignora o parâmetro `location`** passado ao JSearch. Além disso, as queries de busca não incluem contexto geográfico (ex: "Brasil"), fazendo a API retornar vagas gringas mesmo quando não deveria.

## Análise do estado atual

### Código afetado
- **`backend/market_service.py`** linha 1150: `generate_mock_jobs_if_empty` é chamado sem passar `location`
- **`backend/market_service.py`** linha 267: assinatura da função não aceita `location`
- **`backend/market_service.py`** linha 302: `_fetch_jsearch_jobs` é chamado com `country="br", language="pt"` hardcoded, independentemente da seleção do usuário
- **`frontend/app/market/page.tsx`** linha 66-68: `getLocationValue()` retorna "Remoto Nacional" ou "Remoto Internacional" — correto
- **`frontend/app/market/page.tsx`** linha 88: `location` é enviado no formData — correto
- **`backend/main.py`** linha 1488: `location` é passado para `run_market_analysis` — correto

### Raízes do bug
1. **Semana raiz**: `generate_mock_jobs_if_empty` não recebe `location`, então não sabe se deve buscar BR ou US
2. **Sintoma 1**: Queries de busca não incluem contexto geográfico ("Brasil", "Brazil") — a JSearch retorna resultados mistos
3. **Sintoma 2**: `country="br"` é hardcoded — buscas internacionais funcionam apenas se o usuário selecionar "Internacional" no frontend, mas mesmo assim o backend não altera os parâmetros

## Mudanças propostas

### 1. `backend/market_service.py` — Função `generate_mock_jobs_if_empty`

**O quê**: Adicionar parâmetro `location` e usar para determinar `country`/`language` das queries JSearch.

**Como**:
```python
def generate_mock_jobs_if_empty(
    db_file: Path,
    job_title: str = "Desenvolvedor Backend",
    jsearch_api_keys: List[str] = None,
    date_posted: str = "all",
    location: str = "Remoto Nacional"
):
```

Dentro da função, mapear `location` para country/language:
```python
def _get_jsearch_params(location: str):
    loc = location.lower()
    if "internacional" in loc:
        return "us", "en", ["Brazil", "Brazilian", "Latam", "Latin America"]
    return "br", "pt", ["Brasil", "Brazil"]
```

Adicionar o contexto geográfico às queries de busca:
```python
queries = [search_query]
geo_terms = _get_geo_terms_for_query(location)
for term in geo_terms:
    queries.append(f"{search_query} {term}")
# também variações com "vaga", "emprego", "remoto"
```

Na chamada `_fetch_jsearch_jobs`, usar os params dinâmicos:
```python
country, language, geo_terms = _get_jsearch_params(location)
jobs, rem, tot = _fetch_jsearch_jobs(q, country=country, language=language,
    num_pages=12, api_keys=valid_keys, date_posted=date_posted)
```

### 2. `backend/market_service.py` — Chamada em `run_market_analysis`

**O quê**: Passar `location` para `generate_mock_jobs_if_empty`.

**Como**: Linha 1150, alterar de:
```python
generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys, date_posted=date_posted)
```
para:
```python
generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys, date_posted=date_posted, location=location)
```

### 3. `backend/market_service.py` — Helpers de geografia

**O quê**: Criar duas funções auxiliares para mapear location → country/language e queries geográficas.

**Como**:
```python
def _get_jsearch_country_language(location: str):
    """Retorna (country, language) baseado na seleção do usuário."""
    loc = location.lower()
    if "internacional" in loc:
        return "us", "en"
    return "br", "pt"

def _get_geo_keywords(location: str) -> List[str]:
    """Retorna palavras-chave geográficas para adicionar às queries de busca."""
    loc = location.lower()
    if "internacional" in loc:
        return ["Brazil", "Latam", "Latin America", "Brazilian"]
    return ["Brasil", "Brazil", "São Paulo", "Rio de Janeiro", "Brasil remoto"]
```

## Arquivos modificados
1. `backend/market_service.py` — função `generate_mock_jobs_if_empty` (+2 funções auxiliares, ~15 linhas)
2. `backend/market_service.py` — linha 1150 (passar `location`)

## Assunções
- A JSearch API aceita `country=us` + `language=en` para vagas internacionais (incluindo vagas brasileiras em inglês)
- A JSearch API aceita `country=br` + `language=pt` para vagas nacionais
- O número `num_pages=12` já é suficiente para volume, o problema é a falta de contexto geográfico nas queries

## Passo a passo de implementação
1. Adicionar funções `_get_jsearch_country_language` e `_get_geo_keywords` em `market_service.py`
2. Modificar assinatura de `generate_mock_jobs_if_empty` para aceitar `location`
3. Dentro da função, usar os helpers para determinar country/language e adicionar keywords geográficas às queries
4. Atualizar chamada em `run_market_analysis` (linha 1150)
5. Testar: com `location="Remoto Nacional"` deve buscar vagas no Brasil; com `"Remoto Internacional"` deve buscar vagas em inglês/US com contexto LATAM

## Verificação
- Rodar `python -m py_compile backend/market_service.py` — sem erros
- Testar no frontend: selecionar "Nacional" → buscar "Desenvolvedor Python" → resultado deve ter vagas brasileiras
- Testar: selecionar "Internacional" → buscar "Software Engineer" → resultado deve ter vagas em inglês
