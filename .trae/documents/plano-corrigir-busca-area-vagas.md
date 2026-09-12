# Plano: Corrigir busca de vagas — sempre buscar vagas da área solicitada

## Resumo
Ao buscar "Assistente Administrativo", o sistema retorna vagas de "Desenvolvedor Fullstack Júnior" porque os dados ficam **persistidos no DB** entre buscas. A função `generate_mock_jobs_if_empty` só busca vagas novas quando o DB está vazio — se já há dados, ignora a busca e reutiliza vagas antigas de outra área.

## Análise do Problema

### Causa raiz — `market_service.py` linha 275
```python
def generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=None):
    ...
    cursor.execute("SELECT COUNT(*) FROM market_raw_jobs")
    count = cursor.fetchone()[0]

    if count == 0:   # <--- só busca se DB vazio
        # busca JSearch com job_title
```

**Comportamento atual:**
1. Usuário busca "Desenvolvedor Backend" → DB recebe ~97 vagas de Dev
2. Usuário busca "Assistente Administrativo" → DB já tem dados → `count != 0` → **nunca consulta JSearch**
3. O sistema analisa as vagas velhas de Dev (que não têm nada a ver com Assistente Administrativo)
4. O pré-filtro por stack não remove essas vagas porque `target_stack` está vazio (usuário não preencheu)

### Fluxo problemático em `run_market_analysis` (linha 1058-1059):
```python
init_market_db(db_file)
generate_mock_jobs_if_empty(db_file, job_title, ...)  # não busca nada se DB já tem dados
# depois lê do DB e analisa — mas são vagas de outra área
```

---

## Mudanças Propostas

### Arquivo: `backend/market_service.py`

#### Alteração 1 — Limpar DB antes de cada análise
Na função `run_market_analysis` (linha ~1058), adicionar um DELETE antes de chamar `generate_mock_jobs_if_empty`:

```python
# ANTES:
# 1. Garante vagas de amostragem no DB
init_market_db(db_file)
generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys)

# DEPOIS:
# 1. Limpa vagas antigas e garante vagas frescas da área solicitada
init_market_db(db_file)
cursor = conn.cursor()
cursor.execute("DELETE FROM market_raw_jobs")
conn.commit()
generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys)
```

**Por quê:** Garante que cada análise use vagas reais da área que o usuário está pesquisando, nunca dados de buscas anteriores.

#### Alteração 2 — Ajustar o contexto de busca para áreas não-dev
Também precisa verificar se há outro lugar onde a query é mal construída. Já corrigimos a linha 286 (`search_query = job_title.strip()`), mas precisamos garantir que a busca JSearch funcione bem para qualquer área.

O JSearch é baseado no Google for Jobs — ele entende termos em português naturalmente. Não precisa de ajuste adicional na query.

---

## Arquivos a modificar
- `backend/market_service.py` — 1 alteração (adicionar DELETE antes de buscar vagas)

---

## Suposições e Decisões
- O DELETE em `market_raw_jobs` não afeta `market_jobs` (tabela de resultados), que é recriada em cada análise.
- A tabela `jsearch_keys` (armazenamento de chaves da API) não é afetada.
- O tempo de resposta pode aumentar ligeiramente porque sempre busca vagas novas da API — mas isso é desejável (dados frescos > dados cacheados).

---

## Verificação
1. Rodar `py main.py` e confirmar que não há SyntaxError
2. Fazer uma busca por "Assistente Administrativo" e confirmar que as vagas retornadas são dessa área (não de Dev)
3. Fazer uma busca por "Enfermeiro" e confirmar vagas de enfermagem
4. Confirmar que o log mostra `[MARKET] JSearch retornou X vagas reais` em cada busca
5. Confirmar que vagas de áreas diferentes aparecem conforme a busca
