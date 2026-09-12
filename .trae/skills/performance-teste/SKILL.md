---
name: performance-teste
description: Audita performance e boas práticas em código já existente no repositório (não é code review de diff — isso é outra ferramenta). Mede antes de opinar: só reporta achados com número ou localização exata comprovada, nada especulativo. Use quando o usuário pedir "teste de performance", "auditoria de performance", "análise de boas práticas", "performance teste" ou pedir para medir eficiência/gargalos do código — não usar para testes funcionais gerais nem para segurança.
user-invocable: true
---

# Performance Teste — Auditoria de Boas Práticas

Skill para auditar **código existente em repouso** — não review de diff (isso é Bugbot).

Princípio: **medir primeiro, opinar depois**. Sem número ou localização exata, o achado não entra no relatório.

---

## Modos de uso

```
/performance-teste                    → auditoria completa (todos os eixos)
/performance-teste performance        → só perf backend + frontend
/performance-teste escalabilidade     → só escalabilidade + infra
/performance-teste legibilidade       → só clareza + manutenibilidade
/performance-teste arquitetura        → acoplamento, camadas, padrões do repo
/performance-teste /dashboard         → todos os eixos, só no escopo /dashboard
/performance-teste performance /admin → perf, só no escopo /admin
```

---

## Passo 1 — Parse do Escopo

| O que ele disse | Escopo resultante |
|-----------------|-------------------|
| `/performance-teste /admin` | Só rotas/componentes sob `/admin` |
| `/performance-teste apps/api/services/produtos.py` | Arquivo + dependências diretas |
| `/performance-teste frontend` | Todo o app frontend |
| `/performance-teste` (sem argumento) | Projeto inteiro |

Se ambíguo, **pergunte** qual escopo antes de prosseguir.

---

## Passo 2 — Detectar Stack

Identifique antes de qualquer medição:

1. **Linguagem**: Python, TypeScript, JavaScript, PHP, Go, etc.
2. **Framework**: FastAPI, Django, Next.js, React, Vue, Laravel, Express, etc.
3. **ORM / banco**: SQLAlchemy, Prisma, Django ORM, Eloquent, TypeORM, etc.
4. **Bundler**: webpack, vite, turbopack, esbuild, etc.
5. **Infra**: Docker, Redis, filas (Celery/BullMQ), CDN, etc.
6. **Ferramentas existentes**: já tem profiler? coverage? lint config?

Consulte [stacks.md](stacks.md) para ferramentas de medição por stack.

---

## Passo 3 — Inventariar Superfícies

Mapeie **tudo** no escopo:

### Backend
- Rotas / endpoints (método + path)
- Queries (ORM ou SQL raw) — contar por endpoint
- Services com lógica pesada (loops, aggregations, chamadas externas)
- Jobs / workers / crons
- Serialização / deserialização (JSON, validação)
- Conexões (pool de DB, Redis, HTTP clients)

### Frontend
- Páginas / rotas
- Componentes pesados (tabelas, listas, gráficos, forms grandes)
- Imports (tamanho de dependências)
- Imagens / assets
- Re-renders (props instáveis, contextos amplos, stores globais)
- Data fetching (cache, dedup, waterfall)

### Ambos
- Camadas (router → service → repo → DB está claro?)
- Duplicação real (não "parecida" — código idêntico em >1 lugar)
- Código morto (imports não usados, exports não consumidos, branches nunca alcançados)
- Tipos / contratos (`any`, `unknown`, schema frouxo)

---

## Passo 4 — Medir (não opinar)

**REGRA:** toda observação precisa de **evidência**. Sem número ou arquivo:linha, não entra.

### O que medir por eixo

Consulte [catalogo.md](catalogo.md) para detalhes de cada eixo.

| Eixo | O que medir | Evidência |
|------|-------------|-----------|
| **Perf backend** | N+1 queries, queries sem índice, serialização pesada, chamadas síncronas que deveriam ser async | Log SQL / `EXPLAIN` / contagem de queries por request |
| **Perf frontend** | Bundle size por rota, imports pesados, re-renders, imagens sem otimização, LCP/CLS/FCP | `next build` / `vite build` / `source-map-explorer` / Lighthouse |
| **Escalabilidade** | Paginação ausente, `SELECT *` em tabela grande, job síncrono bloqueante, cache inexistente, estado global mutável | Grep + leitura de queries + contagem de registros |
| **Legibilidade** | Complexidade ciclomática, funções >50 linhas, aninhamento >3 níveis, arquivos >400 linhas, nomes inconsistentes | Lint rules / contagem / radon (Python) / eslint-plugin-complexity |
| **Manutenibilidade** | Código morto, duplicação, acoplamento, `any` em TS, falta de tipos, magic numbers | Grep / tsc strict / knip / vulture |
| **Arquitetura** | `if tipo == x` espalhado (deveria ser registry/strategy), lógica de negócio em router/componente, God object, camadas misturadas | Leitura estrutural + grep por padrões |

### Como medir (fluxo)

1. **Ferramentas automáticas primeiro** — rodar o que já existe (lint, build analyzer, profiler).
2. **Leitura manual depois** — para o que ferramenta não pega (arquitetura, duplicação semântica, naming).
3. **Registrar tudo com localização** — arquivo, linha, trecho, número.

---

## Passo 5 — Apresentar Plano e Achados

### Antes de executar

Apresente ao usuário:
- Eixos que serão auditados
- Ferramentas que vai rodar
- Estimativa de tempo
- Pergunta: **"Plano completo (~Xmin) ou só os eixos X e Y?"**

**Nunca** rode tudo sem OK em escopo grande.

### Classificar achados

Cada achado tem:

| Campo | Obrigatório | Exemplo |
|-------|-------------|---------|
| **Eixo** | sim | Performance backend |
| **Severidade** | sim | CRÍTICO / ALTO / MÉDIO / BAIXO / INFO |
| **Localização** | sim | `apps/api/services/produtos.py:142` |
| **Evidência** | sim | "12 queries por request (N+1 em `itens` → `categorias`)" |
| **Impacto** | sim | "~800ms em listagem com 50 registros" |
| **Sugestão** | sim | "Usar `selectinload(Ideia.temas)` ou subquery" |
| **Esforço** | sim | Baixo / Médio / Alto |

### Priorizar por impacto × esforço

Apresente os achados ordenados:
1. **CRÍTICO + Baixo esforço** — quick wins (resolver primeiro)
2. **ALTO + Baixo/Médio esforço** — alto retorno
3. **MÉDIO** — melhorias sólidas
4. **BAIXO / INFO** — bom saber, prioridade baixa

---

## Passo 6 — Aplicar (só com autorização)

Esta skill é **read-only por default**. Ela diagnostica e propõe.

Após apresentar o relatório, pergunte:
> "Quer que eu aplique alguma das correções? Se sim, quais (por número)?"

Regras de aplicação:
- Só refatora o que o usuário autorizou (por número ou "todos os quick wins")
- Mede **depois** da mudança e compara com o antes
- Se não dá para medir o impacto (sem ferramenta / sem dados), rotula como "suspeita aplicada — medir em produção"

---

## Regras Invioláveis

1. **Nunca opine sem evidência** — sem número, sem arquivo:linha, não entra no relatório. "O código parece lento" é proibido. "12 queries em `GET /produtos` (N+1 via `itens.categorias`)" é aceito.
2. **Nunca refatore sem autorização** — skill é auditoria read-only. Mudanças só após OK explícito.
3. **Nunca instale dependências sem perguntar** — se a medição precisa de ferramenta não instalada, liste como gap e peça OK.
4. **Nunca rode `--fix` / `--write`** — lint e formatadores em modo **check/report**. Nunca alteram código.
5. **Nunca confunda com review de diff** — esta skill audita código em repouso. Para review de PR/diff, use Bugbot.
6. **Nunca invente métricas** — se não rodou profiler/analyzer, não estime tempo. Diga "sem medição disponível" e sugira como medir.
7. **Baseline obrigatório** — "otimizei" sem número antes e depois é chute. Se não tem como medir, rotule como "suspeita — validar com dados reais".
8. **Escopo não cobre segurança** — XSS, injection, auth bypass, IDOR não entram aqui. Indicar que existe skill separada para isso.
9. **Achado cosmético ≠ achado de impacto** — "variável poderia ter nome melhor" é INFO no máximo. Nunca ALTO/CRÍTICO para estilo.
10. **Não repita o óbvio** — se o lint do projeto já pega, não liste como achado. Foque no que as ferramentas automáticas NÃO pegam.

---

## Exemplo concreto

**Input:** `/performance-teste performance /produtos`

**Passo 1 — Escopo:** rotas `/produtos/*` + services `produtos*.py` + componentes `Produtos*.tsx`.

**Passo 2 — Stack:** Python 3.12 / FastAPI / SQLAlchemy (async) + Next.js / React / Tailwind.

**Passo 3 — Inventário:**
- Backend: 6 endpoints, 3 services, ~15 queries ORM
- Frontend: 1 página, 4 componentes, 2 hooks, 1 fetch com TanStack Query

**Passo 4 — Medição:**

| O que mediu | Ferramenta | Resultado |
|-------------|-----------|-----------|
| Queries por request `GET /produtos` | Log SQL (echo=True) | 14 queries (N+1 em `itens → categorias → tags`) |
| Bundle size `/produtos` | `next build` | 187 KB (fast-check importado mas não usado: 42 KB) |
| Complexidade ciclomática `produtos_service.py` | radon | `calcular_preco()` = 18 (muito alto) |
| Re-renders `ProdutosLista.tsx` | React DevTools / leitura | `useProdutos()` retorna objeto novo a cada fetch → todo card re-renderiza |

**Passo 5 — Achados apresentados:**

```
#1 CRÍTICO · Perf backend · produtos.py:89
   14 queries em GET /produtos (N+1: itens → categorias → tags)
   Impacto: ~600ms com 30 itens
   Sugestão: selectinload(Item.categorias, Item.tags)
   Esforço: Baixo

#2 ALTO · Perf frontend · ProdutosLista.tsx:23
   useProdutos() retorna referência nova a cada poll → 30 cards re-renderizam
   Impacto: jank visível em lista > 20 itens
   Sugestão: useMemo no seletor ou structuralSharing no TanStack Query
   Esforço: Baixo

#3 MÉDIO · Perf frontend · page.tsx (build)
   fast-check importado mas não usado na página: +42 KB no bundle
   Sugestão: remover import ou mover para tests/
   Esforço: Baixo

#4 MÉDIO · Legibilidade · produtos_service.py:45
   calcular_preco() complexidade ciclomática 18 (>10 = alto)
   Sugestão: extrair blocos de desconto e taxa em funções
   Esforço: Médio

#5 INFO · Manutenibilidade · estoque.py:112
   3 magic numbers (30, 0.7, 5) sem constante nomeada
   Sugestão: extrair para constantes no topo do módulo
   Esforço: Baixo
```

> "5 achados (1 crítico, 1 alto, 2 médios, 1 info). Quer que eu aplique algum? Quick wins: #1, #2, #3, #5."

---

## Referências adicionais

- [stacks.md](stacks.md) — Ferramentas de medição por linguagem/framework
- [catalogo.md](catalogo.md) — Cada eixo de auditoria em detalhe
- [report-template.md](report-template.md) — Template do relatório final