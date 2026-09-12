# Plano: Corrigir busca de vagas de qualquer área na Inteligência de Mercado

## Resumo
A API JSearch só retorna poucas vagas porque a query de busca é **rígida e errada para áreas não-dev**. O search query sempre adiciona `"desenvolvedor python"` no final, mesmo quando o usuário busca "Analista Financeiro", "Enfermeiro", etc.

---

## Análise do Problema

### Causa raiz — Linha 286 de `market_service.py`
```python
search_query = f"{job_title} desenvolvedor python"
```

Isso é hardcoded para tech. Se o usuário digitar:
- `"Analista Financeiro"` → query vira `"Analista Financeiro desenvolvedor python"` → JSearch não encontra nada relevante
- `"Enfermeiro"` → query vira `"Enfermeiro desenvolvedor python"` → mesmo problema
- `"Designer"` → query vira `"Designer desenvolvedor python"` → resultado escasso

### Fatores agravantes
1. **`num_pages=2`** — só busca 2 páginas de resultados, o que pode ser pouco para áreas populares
2. **Query ruim gera menos resultados** → menos vagas no DB → análise fica com dados insuficientes

---

## Mudanças Propostas

### Arquivo: `backend/market_service.py`

#### Alteração 1 — Linha 286: Remover suffix hardcoded "desenvolvedor python"
**O que:** Usar o `job_title` exatamente como o usuário digitou, sem adicionar palavras técnicas.
**Por quê:** O JSearch já é inteligente o suficiente para buscar vagas reais do Google for Jobs com base no título. Adicionar palavras fixas distorce a busca.
**Decisão:** Usar apenas `job_title.strip()` como query.

```python
# ANTES:
search_query = f"{job_title} desenvolvedor python"

# DEPOIS:
search_query = job_title.strip()
```

#### Alteração 2 — Linha 287: Aumentar num_pages de 2 para 4
**O que:** Buscar mais páginas de resultados.
**Por quê:** Para áreas populares, 2 páginas pode não ser suficiente. 4 páginas traz mais vagas para análise.
**Nota:** Cada página adicional consome mais requisições da API key, mas o rate limit já é tratado (linha 155-157).

```python
# ANTES:
sample_jobs, used_key_remaining, _ = _fetch_jsearch_jobs(search_query, country="br", language="pt", num_pages=2, api_keys=valid_keys)

# DEPOIS:
sample_jobs, used_key_remaining, _ = _fetch_jsearch_jobs(search_query, country="br", language="pt", num_pages=4, api_keys=valid_keys)
```

---

## Arquivos a modificar
- `backend/market_service.py` — 2 alterações pontuais (linha ~286 e ~287)

---

## Suposições e Decisões
- O `country="br"` e `language="pt"` permanecem — o usuário brasileiro quer vagas no Brasil em português.
- Não mudamos o `num_pages` para um valor maior porque cada página adicional consome créditos da API. 4 é um bom equilíbrio.
- Se o usuário colocar palavras demais no job_title (ex: "Desenvolvedor Python Pleno Sênior Remoto SP"), o JSearch filtra bem sozinho — não precisamos adicionar mais nada.

---

## Verificação
1. Rodar `py main.py` e confirmar que não há erro
2. Testar busca com job_title não-dev (ex: "Analista Financeiro") e confirmar que retorna mais de 3 vagas
3. Testar busca com job_title dev (ex: "Desenvolvedor Python") e confirmar que continua funcionando normalmente
4. Verificar no log que o `[MARKET] JSearch retornou X vagas reais` mostra número maior que antes
