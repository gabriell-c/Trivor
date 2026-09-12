# Plano: Aumentar Volume de Vagas Analisadas — Objetivo 500+ vagas

## Objetivo
Aumentar drasticamente o volume de vagas analisadas. Estado atual: ~40 vagas. Meta: 500+.

## Análise do Estado Atual

### Número de vagas por etapa:
- **Brutas (JSearch)**: 18 queries × 4 páginas × ~12-15 vagas/pág ≈ ~864 vagas teóricas
- **Após dedup**: ~200-400 únicas (estimado)
- **Após pré-filtro**: depende do scoring de keywords
- **Analisadas por IA**: ~40 (conforme relatório do usuário)

### Causas raiz do volume baixo:

1. **Rate limiting por IP (principal)** — Todas as 6 chaves compartilham o limite de IP. Quando o limite é atingido, queries retornam 429/vazio. As 18 queries atuais levam tempo suficiente para atingir o rate limit continuamente.

2. **num_pages=4 é conservador** — Cada query retorna ~48-60 vagas máximas. Aumentar para 6 páginas aumenta em 50% o potencial por query.

3. **18 queries com sobreposição** — Muitas queries retornam as mesmas vagas (overlapping). Mais queries não = mais vagas se forem redundantes.

4. **_BATCH_DELAY=2.0s entre batches** — Com parallel execution dentro do batch, esse delay é tempo morto desnecessário.

5. **_MAX_JOBS_FOR_ANALYSIS=1000** — Limite alto, mas o gargalo é antes disso (rate limit na coleta).

## Mudanças Propostas

### 1. Aumentar queries de 18 para 40 (mais diversificadas)
**Arquivo**: `backend/market_service.py` ~linha 744

- Manter as 18 queries atuais
- Adicionar 22 queries extras com variações que buscam pools diferentes:
  - Termos de seniority: "júnior", "estagiário", "trainee", "full time"
  - Termos de plataforma: "linkedin", "catho", "infojobs", "glassdoor"
  - Termos regionais: "sudeste", "sul", "nordeste", "centro-oeste"
  - Termos de modalidade: "vaga CLT", "efetivo", "concursos"
  - Synônimos do cargo: "escriturário", "operacional", "back office"
  - Termos de setor: "banco", "financeiro", "varejo", "indústria", "hospitalar"

### 2. Aumentar num_pages de 4 para 6
**Arquivo**: `backend/market_service.py` ~linha 783

```python
num_pages=6  # aumenta de 4 para 6 (~50% mais vagas por query)
```

**Trade-off**: queries individuais mais lentas (~3-4s cada vs ~2s). Compensado pelo parallel execution.

### 3. Reduzir _BATCH_DELAY de 2.0 para 0.8s
**Arquivo**: `backend/market_service.py` ~linha 30

```python
_BATCH_DELAY = 0.8  # reduzido de 2.0 — parallel execution já distribui carga
```

**Risco**: Pode aumentar chance de 429. Mitigado pelo retry logic (item 5).

### 4. Aumentar _MAX_JOBS_FOR_ANALYSIS de 1000 para 3000
**Arquivo**: `backend/market_service.py` ~linha 24

```python
_MAX_JOBS_FOR_ANALYSIS = 3000  # aumenta de 1000
```

Isso permite que mais vagas passem pelo pré-filtro e cheguem à IA.

### 5. Adicionar retry com backoff exponencial para queries rate-limited
**Arquivo**: `backend/market_service.py` ~linha 777-814

- Se uma query retorna 0 vagas após todas as chaves tentarem, registrar como "rate-limited"
- Após cada batch, verificar se % de queries com 0 vagas > 50%
- Se sim, aplicar delay extra de 15s e retry das queries falhas
- No retry, usar keys diferentes (distribuição round-robin)

### 6. Otimoizar key distribution no parallel execution
**Arquivo**: `backend/market_service.py` ~linha 777-814

- Atualmente todas as queries usam `_fetch_jsearch_jobs` com `api_keys=valid_keys` (todas as 6)
- Melhorar: passar subset de keys por query para distribuir carga entre as chaves
- Exemplo: query 1-6 usam keys[0-5], query 7-12 usam keys[3-0] (shift)

### 7. Aumentar _JSEARCH_MIN_DELAY de 0.3 para 0.5
**Arquivo**: `backend/market_service.py` ~linha 27

```python
_JSEARCH_MIN_DELAY = 0.5  # aumenta de 0.3 para reduzir chance de 429
```

## Resumo das Alterações

| Parâmetro | Antes | Depois | Impacto |
|-----------|-------|--------|---------|
| Queries | 18 | 40 | +122% mais pools de vagas |
| num_pages | 4 | 6 | +50% mais vagas/query |
| _BATCH_DELAY | 2.0s | 0.8s | -60% tempo entre batches |
| _MAX_JOBS_FOR_ANALYSIS | 1000 | 3000 | 3x mais vagas para IA |
| _JSEARCH_MIN_DELAY | 0.3s | 0.5s | Menos 429s |
| Retry logic | Não existe | Exponencial com backoff | Recupera de rate limits |

**Estimativa de volume**:
- 40 queries × 6 páginas × ~12 vagas/pág = ~2880 vagas brutas
- Dedup (estimado 60% unique) = ~1700 vagas únicas
- Pré-filtro (estimado 30% passam) = ~500 vagas para IA
- **Meta: 300-500 vagas relevantes** (vs 27 atuais)

## Arquivos a Modificar
- `backend/market_service.py` — todas as mudanças
- `backend/test_e2e.py` — sem mudanças necessárias (usa as mesmas chaves)

## Passos de Implementação
1. Modificar constantes no topo do arquivo (linhas 24-33)
2. Aumentar lista de queries (linha ~744)
3. Aumentar num_pages (linha ~783)
4. Modificar loop de parallel execution com retry e key distribution (linhas 777-814)
5. Verificar syntax com `python -m py_compile backend/market_service.py`
6. Executar teste E2E

## Verificação
- Rodar `backend/test_e2e.py` e verificar:
  - `total_jobs_scanned` > 500
  - `relevant_jobs_analyzed` > 200
  - Word/Excel mencionados em >30 vagas
  - Soft skills extraídos corretamente
  - Nice to have extraídos corretamente
