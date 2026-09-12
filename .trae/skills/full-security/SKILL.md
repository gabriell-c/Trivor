---
name: full-security
description: Executa auditoria de segurança completa e automatizada no projeto: varredura de vulnerabilidades reais (XSS, SQLi, depth-limit, etc.) restrita ao que se aplica a este projeto, testada localmente e sem destruição. Use quando o usuário pedir "teste de segurança", "full security", "auditoria de segurança", "red team", "pentest" ou verificação de vulnerabilidades — não usar para testes funcionais gerais ou de performance.
user-invocable: true
---

# Full Security — Auto-Red-Team Local

**Segurança é EXTREMAMENTE SÉRIA.** Esta skill não “dá uma olhada”: monta uma **esteira** de classes de ataque, executa item a item, e só fecha com ledger zerado.

Três garantias:
1. **Seleção honesta** — só classes aplicáveis a ESTE projeto (sem front → sem XSS; sem DB → sem SQLi; sem GraphQL → sem depth-limit).
2. **Ataque real, não-destrutivo, só local** — alvo = processo/compose deste workspace em `127.0.0.1`/`localhost`. Nunca URL externa, staging, prod, RDS remoto.
3. **Ledger terminal** — cada classe: `SEGURO | VULNERÁVEL | N/A | GAP`. Proibido “não investigado / pendente”.

---

## Guardrails inegociáveis (ler ANTES de qualquer ação)

1. **Alvo exclusivo:** `127.0.0.1`, `localhost`, ou containers do `docker-compose` **deste** projeto.
2. **Alvo remoto = PARE:** se `DATABASE_URL`, base URL da API, host Redis, etc. apontar pra RDS, domínio público, IP não-local → marque `GAP(alvo-remoto)`, **não ataque**, peça override local ou DB/API local. Credenciais de prod/SSM **nunca** são alvo de ataque.
3. **Não-destrutivo:** proibido `DROP`/`TRUNCATE`/wipe/mass-delete em massa. Injection prova com boolean/`SLEEP`/`version()`/eco seguro. Path traversal lê só marcadores inócuos. Upload só em temp. Dados criados no ataque → revertidos. Payloads destrutivos **só** em DB efêmero com OK explícito.
4. **Report-only:** reporta falha + correção sugerida. **Não** patcha código de produção sem OK do usuário.
5. **Tooling ausente:** `GAP(tooling)` — não finja. Instalar só com OK.
6. **Harness/app fora:** `GAP(harness)` + ação (subir API local, corrigir config). Não conte como `SEGURO`.

Detalhe de stacks/ferramentas: [stacks-security.md](stacks-security.md).  
Catálogo completo de classes: [catalogo-ataques.md](catalogo-ataques.md).  
Relatório: [report-template.md](report-template.md).

---

## Passo 1 — Escopo

| Pedido | Escopo |
|--------|--------|
| `/full-security` | Projeto/repo inteiro (default) |
| `/full-security /api` ou módulo | Superfícies daquele módulo + consumidores |
| `/full-security apps/api/...` | Arquivo/pasta + dependências |

Pergunte só se o escopo estiver ambíguo.

---

## Passo 2 — Detectar superfícies (sinais reais)

Não presuma. Colete:

| Superfície | Sinais |
|------------|--------|
| Backend / lógica | routers, controllers, services, workers |
| Banco | `DATABASE_URL`, Prisma, Alembic, `*.sql`, compose postgres/mysql/mongo |
| Tipo de DB | postgres / mysql / sqlite / mongodb / redis |
| API REST | FastAPI/Flask/Django/Express/Laravel/… |
| GraphQL | schema, apollo, strawberry, graphene |
| WebSocket | socket.io, ws, channels |
| Frontend | React/Next/Vue/Vite, `apps/web`, `.tsx` |
| Mobile/híbrido | React Native, Capacitor, Flutter |
| Auth/sessão | JWT, cookies, sessions, OAuth, API keys |
| Infra local | `docker-compose.yml`, portas em uso |

**Resolver alvo local:** leia scripts/`README`/compose; descubra host:porta da API e do front. Se nada sobe → `GAP(harness: app não está rodando)` e peça pra subir, ou use ASGI/WSGI in-process **só se** for o mesmo código local (sem bater em host remoto).

Regra: host resolvido ≠ local → **não continue o dinâmico**.

---

## Passo 3 — Montar a ESTEIRA

Para **cada** classe em [catalogo-ataques.md](catalogo-ataques.md), marque `APLICÁVEL` ou `N/A(motivo)` pelos sinais.

Resumo rápido (detalhe no catálogo):

| Grupo | Exemplos | N/A típico |
|-------|----------|------------|
| Backend/lógica | SQLi, Command, SSTI, SSRF, path traversal, IDOR, race, mass assignment, … | Sem HTTP/DB/parser |
| Banco | least privilege, crypto de campo, dump/debug | Sem DB |
| API | JWT, CORS, over-fetch, GraphQL depth, WS, open redirect | Sem API / sem GraphQL / sem WS |
| Frontend | XSS, prototype pollution, CSP, postMessage, secrets no bundle | Sem frontend |
| Mobile | local storage, pinning, deeplink | Sem mobile |
| Auth/sessão | brute force, CSRF, sessão, crypto keys | Sem auth |
| Cross-cutting | secrets, deps, eval, upload, stack traces | Quase sempre aplicável em parte |

**Ordem (barato → caro):**
1. Estático: secrets, deps/audit, config perigosa, padrões no código (semgrep/bandit/grep).
2. Dinâmico local: auth bypass, IDOR, injection controlada, path traversal, CORS/JWT probes.
3. Frontend dinâmico (se houver UI local): XSS refletido/DOM leve.
4. Scanners locais (ZAP/sqlmap headless) **só** se instalados + OK + alvo local.

Saída = fila ordenada só de `APLICÁVEL`.

---

## Passo 4 — Orçamento

- **Teto default:** ~25 min de wall-clock de execução (ajustável; “sem teto” se o usuário pedir).
- Timeout por classe/scanner (~5 min): corta → `GAP(timeout)`.
- Estourou o teto → restantes `GAP(orçamento)` **listados**, nunca omitidos.
- Apresente a esteira + estimativa + N/A e peça: **"Executo a esteira de segurança (~Tmin) no localhost?"**

---

## Passo 5 — Executar item a item (ledger)

Estados terminais **fechados** (só estes quatro):

| Estado | Significado |
|--------|-------------|
| `SEGURO` | Classe aplicável testada; **nenhuma** evidência de falha nesta rodada |
| `VULNERÁVEL` | Evidência reproduzível (estática e/ou dinâmica local) |
| `N/A` | Fora do projeto (com motivo) |
| `GAP` | Aplicável mas não executada: tooling / harness / orçamento / timeout / alvo-remoto |

**Proibido:** “não investigado”, “a verificar”, “parcial”, bullet solto sem linha no ledger.

Para **cada** item `APLICÁVEL`:

1. Marque `RODANDO`.
2. **Estático** (quando couber): grep/semgrep/bandit/audit no escopo.
3. **Dinâmico local** (quando couber e alvo local OK): prova controlada, não-destrutiva.
4. Cole evidência (comando, trecho de código, request/response sanitizado — **sem** colar secrets reais).
5. Feche: `SEGURO` | `VULNERÁVEL` | `GAP(motivo)` + **ação** se GAP.
6. Só então o próximo.

**Harness quebrado** (app down, alias, DB remoto): `GAP(harness|alvo-remoto)` + ação. Não `SEGURO`.

**Deps vulneráveis (audit HIGH/CRITICAL):** investigar na hora → `VULNERÁVEL` se afeta o escopo, ou `GAP(vuln: pkg)` + ação (bump/aceite). Silêncio proibido.

**Race / lógica de negócio:** paralelismo real ou bypass de fluxo com oráculo da regra de negócio — não teatro.

### Checagem de fechamento

Antes do relatório:
1. Zero `TODO`/`RODANDO`.
2. Todo achado citado amarra a uma linha do ledger.
3. Todo `GAP` tem ação.
4. Nenhum ataque foi feito contra host não-local.

---

## Passo 6 — Traduzir para produção + Relatório

Para cada `VULNERÁVEL`, preencha **impacto em produção** (a lógica frágil em local costuma ser a mesma em prod; borda/WAF/SG **não** foram testados — diga isso).

Entregue no chat usando [report-template.md](report-template.md):

- Resumo + veredito (`CRÍTICO` / `ALTO` / `SEM FALHAS NA ESTEIRA` — **nunca** “sistema seguro”).
- Ledger completo.
- Findings por severidade (CWE/OWASP, repro localhost, impacto prod, correção).
- Gaps com ação.
- Seção **O que NÃO foi testado** (borda, rede, TLS edge, WAF, dados reais de prod).

| Veredito | Quando |
|----------|--------|
| **CRÍTICO / VERMELHO** | ≥1 finding Crítico, ou auth/IDOR/RCE/injection explorável |
| **ALTO / AMARELO** | Findings Altos, ou GAPs graves (alvo-remoto, harness bloqueando dinâmico) |
| **SEM FALHAS ENCONTRADAS NA ESTEIRA** | Todos aplicáveis `SEGURO` ou `N/A`; GAPs só de tooling opcional documentados |

---

## Regras Invioláveis

1. Localhost-only; remoto → pare.
2. Não-destrutivo; sem wipe.
3. Report-only sem OK de patch.
4. Esteira = só aplicáveis; N/A com motivo.
5. Nenhum aplicável fica pendente — roda ou `GAP` explícito.
6. Ledger com 4 estados; nada inventado.
7. Evidência bruta (sem vazar secrets).
8. Audit HIGH/CRITICAL tem estado terminal + ação.
9. Harness quebrado ≠ seguro.
10. Orçamento respeitado; estouro = GAP listado.
11. Nunca declarar “à prova de hacker” / “100% seguro”.

---

## Exemplos de esteira

**API FastAPI + Postgres local, sem frontend:**  
APLICÁVEL: SQLi, IDOR, auth/JWT, CORS, SSRF, path traversal, mass assignment, race, secrets, deps, error leakage, rate limit…  
N/A: XSS, prototype pollution, clickjacking, mobile, GraphQL (se não houver).

**SPA React/Vite só front (API mock):**  
APLICÁVEL: XSS DOM, secrets no bundle, postMessage, deps client, CSP…  
N/A: SQLi, SSRF server, least-privilege DB.

**Lib PHP pura sem HTTP:**  
APLICÁVEL: type juggling, deserialização, insecure randomness, secrets…  
N/A: CORS, WebSocket, XSS browser.

---

## Referências

- [catalogo-ataques.md](catalogo-ataques.md)
- [stacks-security.md](stacks-security.md)
- [report-template.md](report-template.md)