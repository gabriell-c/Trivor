# Stacks — Adaptadores por Linguagem e Framework

Ao detectar a stack do projeto, use esta referência para toolchain, comandos e convenções de teste.

---

## Python

### Detecção
- `pyproject.toml`, `requirements.txt`, `setup.py`, `.python-version`, `Pipfile`

### Frameworks e toolchain

| Framework | Test runner | HTTP test | Fixtures |
|-----------|-----------|-----------|----------|
| **FastAPI** | pytest + pytest-asyncio | `httpx.AsyncClient` + `ASGITransport` | `conftest.py` com app fixture |
| **Django** | pytest-django | `django.test.Client` / `rest_framework.test.APIClient` | `TestCase` + `fixtures/` |
| **Flask** | pytest | `app.test_client()` | `conftest.py` |
| **Plain Python** | pytest | N/A | `conftest.py` |

### Comandos padrão

```bash
# Lint + types (SEMPRE modo check, nunca --fix)
ruff check .
mypy . --strict  # ou pyright

# Unit + integração
pytest tests/ -v --tb=short

# Cobertura
pytest --cov=src --cov-report=term-missing --cov-branch

# Property testing (requer hypothesis — perguntar antes de instalar)
pytest tests/ -k "property" -v

# Mutation (requer mutmut — perguntar antes de instalar)
mutmut run --paths-to-mutate=src/

# Performance (requer locust — perguntar antes de instalar)
locust -f tests/perf/locustfile.py --headless -u 50 -r 10 --run-time 60s

# Concorrência
pytest tests/ -k "race or concurrent" -v

# Segurança (requer bandit/semgrep — perguntar antes de instalar)
# APENAS contra localhost / ambiente local
bandit -r src/ -ll
semgrep --config=auto src/
```

### Convenções de arquivo

```
tests/
  unit/
    test_<modulo>.py
  integration/
    test_<modulo>_integration.py
  e2e/
    test_e2e_<fluxo>.py
  perf/
    locustfile.py
  property/
    test_<modulo>_property.py
  fuzz/
    test_<modulo>_fuzz.py
```

---

## TypeScript / JavaScript (Node)

### Detecção
- `package.json`, `tsconfig.json`, `bun.lockb`, `pnpm-lock.yaml`

### Frameworks e toolchain

| Framework | Test runner | E2E | HTTP test |
|-----------|-----------|-----|-----------|
| **Next.js** | vitest / jest | Playwright | supertest / fetch mock |
| **React (CRA/Vite)** | vitest / jest | Playwright / Cypress | msw (mock) |
| **Vue / Nuxt** | vitest | Playwright / Cypress | @vue/test-utils |
| **Express / Fastify** | vitest / jest | supertest | supertest |
| **Nest.js** | jest | supertest + Playwright | `@nestjs/testing` |

### Comandos padrão

```bash
# Lint + types (SEMPRE modo check, nunca --fix)
npx eslint .
tsc --noEmit

# Unit + integração
npx vitest run  # ou: npx jest --coverage

# E2E
npx playwright test

# Cobertura
npx vitest run --coverage  # c8/istanbul

# Property testing (requer fast-check — perguntar antes de instalar)
npx vitest run tests/property/

# Mutation (requer stryker — perguntar antes de instalar)
npx stryker run  # precisa stryker.conf.mjs

# Performance (frontend)
npx lighthouse http://localhost:3000 --output=json --chrome-flags="--headless"
# Performance (API — requer k6 — perguntar antes de instalar)
npx k6 run tests/perf/load.js

# Concorrência
# Promise.all([...Array(50)].map(() => fetch(...)))

# Visual regression
npx playwright test --update-snapshots  # baseline
npx playwright test  # comparar

# Acessibilidade (requer @axe-core/playwright — perguntar antes de instalar)
# Dentro do playwright: page.accessibility.snapshot()

# Segurança — APENAS contra localhost / ambiente local
npx semgrep --config=auto src/
```

### Convenções de arquivo

```
tests/               # ou __tests__/ ou src/**/*.test.ts
  unit/
    <modulo>.test.ts
  integration/
    <modulo>.integration.test.ts
  e2e/
    <fluxo>.e2e.test.ts
  perf/
    load.js          # k6
  property/
    <modulo>.property.test.ts
```

---

## PHP

### Detecção
- `composer.json`, `artisan`, `phpunit.xml`

### Frameworks e toolchain

| Framework | Test runner | HTTP test |
|-----------|-----------|-----------|
| **Laravel** | PHPUnit / Pest | `$this->get()`, `$this->post()` |
| **Symfony** | PHPUnit | `KernelTestCase`, `WebTestCase` |
| **Plain PHP** | PHPUnit | N/A |

### Comandos padrão

```bash
# Lint + types (SEMPRE modo check, nunca fix)
./vendor/bin/phpstan analyse src/ --level=max
./vendor/bin/php-cs-fixer fix --dry-run  # --dry-run = só reporta

# Unit + integração
./vendor/bin/phpunit --testsuite=Unit
./vendor/bin/phpunit --testsuite=Feature

# Cobertura
./vendor/bin/phpunit --coverage-text --coverage-html=coverage/

# Mutation
./vendor/bin/infection --min-msi=70

# Performance
# k6 ou Artillery apontando para o app

# Segurança
composer audit
./vendor/bin/phpstan --level=max  # com larastan para Laravel

# Concorrência
# Guzzle pool / curl_multi com N requests simultâneas
```

### Convenções de arquivo

```
tests/
  Unit/
    <Modulo>Test.php
  Feature/
    <Fluxo>Test.php
  E2e/
    <Jornada>Test.php
```

---

## Go

### Detecção
- `go.mod`, `go.sum`

### Comandos padrão

```bash
# Lint + types
golangci-lint run ./...

# Unit + integração
go test ./... -v -race -cover

# Fuzz
go test -fuzz=Fuzz<Nome> ./pkg/...

# Benchmark / perf
go test -bench=. -benchmem ./...

# Concorrência
go test -race ./...  # detector nativo

# Mutation
go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest
go-mutesting ./...
```

---

## Ferramentas Universais (qualquer stack)

| Finalidade | Ferramenta | Instalação |
|-----------|-----------|-----------|
| Carga HTTP | **k6** | `choco install k6` / `brew install k6` |
| Carga HTTP alt. | **Artillery** | `npm i -g artillery` |
| Segurança web | **OWASP ZAP** (headless) | Docker: `owasp/zap2docker-stable` |
| Segurança código | **Semgrep** | `pip install semgrep` |
| Chaos | **Toxiproxy** | Docker: `shopify/toxiproxy` |
| Contract testing | **Schemathesis** (OpenAPI) | `pip install schemathesis` |
| Contract testing | **Pact** | por linguagem |
| Accessibility | **pa11y** | `npm i -g pa11y` |
| Visual diff | **Playwright** screenshots | built-in |
| Synthetic/canary | Script bash + cron | custom |

---

## Regras de ouro

1. Se o projeto **já tem** test runner configurado, **use-o**. Não troque jest por vitest nem pytest por unittest sem motivo. Adapte-se ao que existe (pastas/nomes do repo mandam).
2. Se não tem **nada**, instale o padrão da stack (pytest para Python, vitest para TS/JS moderno, PHPUnit para PHP) — **após perguntar ao usuário**.
3. **Nunca instale deps extras** (hypothesis, fast-check, k6, stryker, axe-core, etc.) sem listar no plano e receber OK. Registre como gap se o usuário recusar.
4. **Lint = modo check.** Nunca `--fix` / `--write` / auto-correct. A skill reporta; o usuário decide se quer o fix.
5. **Ferramentas ofensivas** (ZAP, sqlmap, schemathesis) rodam **exclusivamente** contra `localhost` / containers locais. Nunca produção, staging externo ou domínio de terceiros.
6. **Tempo = do runner ou Stopwatch.** Cole `in 24.10s` / `Duration` / `WALL_MS=…` no relatório. Nunca invente “~40 min”.
7. **`--update-snapshots`** só com OK (cria/atualiza baseline visual); default é comparar, não sobrescrever.
