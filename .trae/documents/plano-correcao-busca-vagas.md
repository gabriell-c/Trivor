# Plano: Corrigir busca de vagas — resultados vazios e incorretos

## Problemas identificados

### 1. `_fetch_jsearch_jobs` para na PRIMEIRA chave que responde OK
- Se a Key 1 retorna 5 vagas, para. Nunca tenta Key 2, 3, 4.
- **Correção**: Acumular resultados de TODAS as chaves, tentar cada uma.

### 2. `num_pages=12` é agressivo demais
- Cada query gasta muitas requisições, rate limitima as chaves rápido.
- **Correção**: Reduzir para `num_pages=4` por query, mas fazer mais queries com variações.

### 3. Deduplicação usa `title + company` como fallback quando `apply_link` é vazio
- Vagas da mesma empresa com títulos parecidos são perdidas.
- **Correção**: Usar `job_id` (campo da API) quando disponível, ou hash do título+empresa+localização.

### 4. `detect_job_nationality` é muito agressivo
- Vagas brasileiras remotas que mencionam "English required" ou "bilingual" são marcadas como "internacional" e descartadas no pré-filtro.
- **Correção**: Se a JSearch retornou `job_country="br"`, confiar no país da API em vez de re-analisar o texto.

### 5. Queries de busca não cobrem o suficiente
- Com 4-5 queries e num_pages=12, o rate limit chega rápido.
- **Correção**: Mais queries variadas com num_pages=4, cobrindo: termo principal, termo+Brasil, termo+vaga, termo+remoto, termo+emprego.

## Mudanças propostas

### Arquivo: `backend/market_service.py`

#### 1. Refatorar `_fetch_jsearch_jobs` para agregar todas as chaves
- Remover `return jobs` do loop
- Acumular resultados em lista
- Retornar soma de todas as chaves
- Logar resultados de cada chave separadamente

#### 2. Reduzir `num_pages` de 12 para 4

#### 3. Melhorar deduplicação em `generate_mock_jobs_if_empty`
- Usar `j.get("job_id", "")` como chave primária quando disponível
- Fallback para hash de (título, empresa, localização)
- Logar vagas duplicadas removidas

#### 4. Corrigir `detect_job_nationality`
- Adicionar parâmetro `job_country` (já retornado pela API)
- Se `job_country == "br"` → retornar "nacional" diretamente
- Manter análise de texto apenas como fallback

#### 5. Atualizar `_build_jobs_from_raw`
- Retornar também `job_id` e `job_country` do raw job
- Atualizar INSERT no DB para incluir esses campos (ou usar os existentes)

#### 6. Atualizar `_pre_filter_jobs`
- Usar `job_country` do banco ao invés de re-analisar texto quando disponível
- Tornar a detecção de nacionalidade mais permissiva

### Arquivo: `backend/market_service.py` — Helpers de queries

#### 7. Função `_build_search_queries`
- Dada a query original e ge_keywords, gerar 8-10 variações
- Ex: "Python Developer" → ["Python Developer", "Python Developer Brasil", "Python Developer remoto", "Python vaga", "Desenvolvedor Python", etc.]

## Testes a realizar

### Teste 1 — Desenvolvedor Python (Nacional, Pleno)
- Query: "Python Developer"
- Local: Remoto Nacional
- Seniority: Pleno
- Esperado: 50+ vagas brasileiras, em português, CLT/PJ

### Teste 2 — Data Analyst (Internacional, Pleno)
- Query: "Data Analyst"
- Local: Remoto Internacional
- Seniority: Pleno
- Esperado: 30+ vagas em inglês, salário em USD

### Teste 3 — Designer UX/UI (Nacional, Júnior)
- Query: "UX Designer"
- Local: Remoto Nacional
- Seniority: Júnior
- Esperado: 20+ vagas brasileiras, com "júnior" no título ou descrição

### Teste 4 — Dev Fullstack (Nacional, com stack)
- Query: "Fullstack Developer"
- Stack: "React, Node.js"
- Local: Remoto Nacional
- Seniority: Pleno
- Esperado: Vagas com React e Node.js mencionados

### Teste 5 — Com palavras negativas
- Query: "Backend Developer"
- Negativas: "estágio", "trainee"
- Esperado: Nenhuma vaga de estágio no resultado

### Teste 6 — Sem stack (busca aberta)
- Query: "Analista de Sistemas"
- Stack: nenhum
- Local: Remoto Nacional
- Esperado: Todas as vagas analisadas, sem rejeição por stack

## Verificação
- `python -m py_compile backend/market_service.py`
- `python -m py_compile backend/main.py`
- Teste E2E com each API key
- Verificar logs de cada query
