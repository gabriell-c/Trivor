---
name: full-teste
description: Executa suíte completa de testes de ponta a ponta no projeto: testes unitários, de integração, E2E e de estresse. Use quando o usuário pedir "teste completo", "roda todos os testes", "full teste", "testa tudo" ou pedir cobertura ampla — sem foco específico em segurança ou performance isolada.
user-invocable: true
---

# Full Teste — Esteira de Testes Completa

**Full = todos os testes que fazem sentido para ESTE projeto, executados de fato.**

Três garantias inegociáveis:

1. **Seleção honesta** — só entram na esteira os tipos que se aplicam ao projeto (sem frontend → sem React/a11y/visual; sem estado compartilhado → sem race; etc.).
2. **Execução exaustiva** — todo tipo que entrou na esteira **roda** (evidência) ou vira **N/A justificado**. Nada fica `PENDENTE`. A esteira só fecha com a fila zerada.
3. **Sem enrolação** — orçamento de tempo; ordena por valor; estoura o teto → o que sobrou vira **GAP explícito** no relatório, nunca um silêncio.

---

## Passo 1 — Escopo

| Pedido                           | Escopo                                                                 |
| -------------------------------- | ---------------------------------------------------------------------- |
| `/full-teste /estudio`           | Router + services + workers + UI + testes + **consumidores** do módulo |
| `/full-teste caminho/arquivo.py` | Arquivo + o que ele importa/é importado                                |
| `/full-teste` (vazio)            | Projeto/repo inteiro                                                   |

Inclua **consumidores**: mexeu em `x.py` → rode também quem importa `x.py`, não só arquivos com o nome do módulo.

---

## Passo 2 — Detectar o Projeto

Colete sinais (não presuma):

- **Linguagens/apps:** `pyproject.toml`, `package.json`, `go.mod`, `composer.json`, `artisan`, `Cargo.toml`.
- **Tem frontend?** app web/UI (`apps/web`, `src/app`, `.tsx`, framework React/Vue/…). Se **não** → nada de React/a11y/visual/browser.
- **Tem HTTP/API?** routers/controllers/endpoints.
- **Tem banco/estado compartilhado?** DB, Redis, cache, contadores, saldo, fila → habilita race/concorrência.
- **Tem input externo/parser?** upload, JSON/CSV/query, form → habilita fuzz/property/segurança.
- **Tem jobs/workers/cron?** → habilita idempotência/retry.
- **Multi-tenant?** workspace/tenant/org → habilita IDOR.
- **Toolchain existente:** pytest/vitest/jest/PHPUnit/go test, playwright, etc. ([stacks.md](stacks.md) = fallback).
- **Tooling extra instalado?** hypothesis, stryker/mutmut, k6, axe — o que **não** existe vira gap (não instale sem OK).

---

## Passo 3 — Montar a ESTEIRA (seleção por aplicabilidade)

Para **cada** tipo do catálogo, decida `APLICÁVEL` / `N/A` com base nos sinais. Esta é a linha de montagem — só o que é `APLICÁVEL` entra na fila de execução.

| Tipo              | Entra se…                            | N/A quando…                            |
| ----------------- | ------------------------------------ | -------------------------------------- |
| Lint + types      | sempre há linter                     | — (sempre entra)                       |
| Unit              | há lógica não-trivial                | só glue/config                         |
| Integração        | há HTTP/DB/fila/cache                | lib pura sem I/O                       |
| E2E (HTTP)        | há API com jornada                   | lib/CLI sem fluxo                      |
| E2E browser       | **há frontend**                      | **sem frontend**                       |
| Smoke             | app sobe / módulo importa            | —                                      |
| Regressão         | há bug fix / histórico               | greenfield sem histórico               |
| Property          | parsers, transforms, validadores     | CRUD trivial                           |
| Fuzz              | processa input externo não confiável | inputs já validados upstream           |
| Concorrência/race | **estado compartilhado mutável**     | stateless puro                         |
| Performance       | SLA/latência/query pesada            | protótipo sem SLA (vira gap, não some) |
| Segurança (local) | recebe input / exposto               | CLI interna sem input externo          |
| Acessibilidade    | **UI pública**                       | **sem frontend** / API pura            |
| Mutation          | tooling existe + crítico             | sem runner de mutação (gap)            |
| Chaos             | infra distribuída c/ retry           | monolito local sem recuperação         |
| Carga/stress      | precisa provar volume                | fora do pedido                         |
| Visual regression | **UI com baseline**                  | **sem frontend**                       |
| Contract          | API com múltiplos consumers          | monolito 1 consumer                    |
| Compatibilidade   | multi-runtime/browser                | ambiente único                         |

Saída deste passo = **a esteira**: lista ordenada só dos `APLICÁVEL`, cada um com um item de trabalho. Detalhe por tipo: [catalogo.md](catalogo.md).

**Ordem de execução (rápido → lento, barato → caro):**
`lint → unit → integração → smoke → segurança/IDOR local → race → E2E (HTTP) → E2E browser → property/fuzz → perf → mutation/chaos/carga`.
Assim o feedback de bug vem cedo e o caro fica pro fim (protegido pelo orçamento).

---

## Passo 4 — Inventário de superfícies + Orçamento

### 4.1 Matriz de superfícies (o QUE testar)

Liste **todas** as superfícies do escopo (todo `@router.*`, service, worker, UI interativa, helper de path/auth). Marque já-tem-teste / buraco. `rg`/grep obrigatório — nada de cherry-pick de “arquivos principais”.

### 4.2 Orçamento de tempo (para não durar o dia)

- **Teto default:** ~15 min de execução de runners (ajuste se o usuário der outro).
- **Timeout por suíte:** se uma suíte estoura (ex.: > 5 min), corta, marca `GAP (timeout)` e segue — não trava a esteira.
- Estourou o teto total → tipos restantes **não somem**: viram `GAP (orçamento)` no relatório, na ordem em que ficaram.
- O usuário pode dizer “sem teto” → aí roda tudo até o fim.

### 4.3 Plano + OK

Apresente: a **esteira** (tipos APLICÁVEL/N/A), superfícies com buraco, nº de testes novos estimado, tempo estimado, gaps de tooling. Pergunte: **"Executo a esteira completa (~Tmin)?"** — não ofereça “só amostra” a menos que o usuário peça.

---

## Passo 5 — Executar a esteira item a item (com ledger)

Mantenha um **ledger** onde cada item da esteira tem um estado. **Proibido encerrar com qualquer item em `TODO`/`RODANDO`.**

Estados terminais **fechados** (não existe outro): `OK | FALHOU | N/A(justif.) | GAP(motivo)`.
**Proibido** qualquer estado inventado tipo “não investigado”, “pendente”, “a verificar”, “parcial”, “ver depois”. Se apareceu um achado, ele **tem** que cair num dos quatro:

- É problema real do produto/código → `FALHOU` (vira bug no relatório).
- Ferramenta/baseline/ambiente impediu de rodar → `GAP(motivo)` **com item de correção**.
- Não se aplica ao projeto → `N/A(motivo)`.
- Rodou e passou → `OK` (com evidência).

Para **cada** item, em ordem:

1. **Baseline do tipo** — rode os testes já existentes desse tipo no escopo (lista completa; comando + `N passed` + duração + exit).
2. **Fechar buracos** — escreva os testes que faltam para as superfícies daquele tipo (por endpoint: happy + erro + auth/IDOR). Oráculo = spec/issue/doc, **nunca** o return atual do código (exceto `# characterization` rotulado).
3. **Rodar e medir** — wall-clock real (`in 24.10s` / Stopwatch). Cole evidência.
4. **Marcar o ledger** — um dos quatro estados terminais. Nada de meio-termo.
5. **Só então** passe ao próximo item.

### Harness quebrado = tipo NÃO executado (`GAP(harness)`)

Se o runner falhou por **infra do teste**, não por asserção — ex.: alias `@/lib` não resolve, import quebrado, DB não sobe, fixture ausente, config de test faltando — então aquele tipo **não rodou**. Marque `GAP(harness: <o quê>)` **+ item de correção obrigatório** (“corrigir alias no vitest.config”, “subir Postgres local”). **Proibido** contar esse tipo como `OK`, tratar como “gap de escopo”, ou deixar como nota solta. Harness quebrado que dá pra consertar em minutos: conserte e rode; só vira `GAP` se depender de decisão/tooling do usuário.

### Achado de segurança / dependência = estado terminal

Vulnerabilidade (`npm audit`/`pip-audit`) HIGH/CRITICAL **não** pode ficar “não investigada”. Investigue na hora: se afeta o escopo → `FALHOU` (bug de segurança). Se é transitiva/sem correção agora → `GAP(vuln: <pkg> HIGH)` **+ ação** (bump/override/aceite documentado). Silêncio ou “não investigado” é proibido.

Regras de execução:

- **Race real:** paralelismo em produção (HTTP/DB). Proibido `Lock` no mock ou N reads de função pura.
- **Spot-check do verificador:** em 1–3 asserts críticos novos, inverta → veja vermelho → reverta. Sem isso, não diga “suíte forte”.
- **Sem green-wash:** proibido skip cosmético, afrouxar assert, subir timeout pra passar, mockar a dep que falhou, apagar teste, `--fix` no lint.
- **Não patch de produção** durante o teste; fix é passo separado, só com OK; depois mostra vermelho→verde.
- Falha pré-existente = “baseline quebrada”, não bug novo.

### Checagem de fechamento (obrigatória)

Antes do relatório, confirme item a item:

1. **Todo** item está num dos quatro estados terminais — zero `TODO`/`RODANDO`, zero estado inventado.
2. **Todo achado** citado no texto (bug, vuln, erro TS, smoke que não rodou) está amarrado a uma linha do ledger — nada solto em bullet sem estado.
3. Todo `GAP(harness)` e `GAP(vuln)` tem **ação de correção** escrita.
   Se qualquer um falhar, a esteira **não terminou** — volte.

---

## Passo 6 — Relatório

Use [report-template.md](report-template.md). Deve conter:

- **Ledger da esteira** — cada tipo com estado terminal (nenhum `TODO`).
- **Matriz de superfícies** — cobertas / buracos.
- Contagem honesta: baseline | novos | total.
- **Evidência bruta** (comando + exit + sumário + tempo) por suíte.
- Tempo total **medido** (nunca chutado).
- Bugs, gaps (tooling/orçamento/timeout), spot-check.

Veredito:

| Veredito              | Quando                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------------- |
| **VERDE — COMPLETO**  | Todos os `APLICÁVEL` = `OK`; matriz 100%; sem `TODO`; nenhum achado solto                    |
| **AMARELO — PARCIAL** | Algum `APLICÁVEL` virou `GAP` (orçamento/tooling/harness/vuln) — liste quais + ação          |
| **VERMELHO**          | Qualquer `FALHOU` (bug, erro TS, vuln HIGH que afeta escopo) ou baseline quebrada sem acordo |

Todo tipo com harness quebrado conta como **não executado** (`GAP`), nunca como verde. Vuln HIGH/CRITICAL sem tratamento → no mínimo AMARELO.

`N/A` justificado **não** derruba o VERDE (era fora do projeto). `GAP` de tipo aplicável **sim** → no máximo AMARELO.

---

## Regras Invioláveis

1. Esteira = só tipos `APLICÁVEL`; `N/A` sempre com motivo (sem frontend → sem React/a11y/visual/browser).
2. **Nenhum item aplicável fica `PENDENTE`** — roda ou vira `GAP` explícito no relatório.
3. Esteira não fecha com item em `TODO`/`RODANDO`.
4. Ordem rápido→caro; orçamento de tempo; timeout por suíte; estouro → `GAP`, nunca silêncio.
5. Re-rode **todos** os testes existentes do escopo (+ consumidores).
6. Por endpoint: happy + erro + auth/IDOR antes de `OK`.
7. Tempo **medido**; contagem baseline vs novos separada.
8. Evidência bruta por suíte (comando + exit + sumário).
9. Oráculo ≠ output atual (exceto characterization rotulado).
10. Sem green-wash; lint check-only; ofensivo só localhost.
11. Race só com estado compartilhado real; sem lock teatral.
12. Spot-check vermelho nos oráculos novos críticos.
13. Smoke estático ≠ E2E browser.
14. Deps novas só com OK (senão `GAP`).

---

## Exemplos de esteira por projeto

**API Python sem frontend** (`/full-teste` num repo FastAPI puro):
`APLICÁVEL`: lint, unit, integração, E2E HTTP, smoke, segurança local, race (tem DB), property/fuzz (tem parsers), perf (se SLA).
`N/A`: E2E browser, a11y, visual regression (**sem UI**).

**Lib pura** (parser sem HTTP/DB):
`APLICÁVEL`: lint, unit, property, fuzz, mutation (se tooling).
`N/A`: integração, E2E, race, a11y, visual, chaos.

**App full-stack** (`/full-teste /checkout`):
`APLICÁVEL`: tudo do backend **+** E2E browser, a11y, visual (tem UI e baseline).

Em cada caso a esteira roda **item a item até zerar**, e o relatório mostra o ledger com todos em estado terminal.

---

## Referências

- [stacks.md](stacks.md) — comandos por stack
- [catalogo.md](catalogo.md) — cada tipo: quando aplica / quando N/A
- [report-template.md](report-template.md) — relatório + ledger
