# Stacks — Ferramentas de Medição por Linguagem e Framework

Ao detectar a stack, use esta referência para saber **o que medir e com o quê**.

Regras gerais:
- **Usar o que já existe** no projeto. Não trocar ferramentas.
- **Nunca instalar** dependência sem listar no plano e receber OK.
- **Nunca `--fix`** — tudo em modo check/report.
- Se a ferramenta não existe e o usuário não quer instalar: **gap** no relatório.

---

## Python

### Detecção
- `pyproject.toml`, `requirements.txt`, `setup.py`, `.python-version`, `Pipfile`

### Ferramentas de medição

| Eixo | Ferramenta | Comando (modo check) | Requer instalação? |
|------|-----------|----------------------|-------------------|
| **N+1 queries** | SQLAlchemy echo | `SQLALCHEMY_ECHO=true pytest -s -k "test_endpoint"` | Não (config) |
| **Query analysis** | `EXPLAIN ANALYZE` | Via ORM `.explain()` ou SQL direto | Não |
| **Complexidade** | radon | `radon cc src/ -s -n C` (mostra ≥C) | Sim — perguntar |
| **Código morto** | vulture | `vulture src/ --min-confidence 80` | Sim — perguntar |
| **Lint** | ruff | `ruff check .` (sem --fix) | Geralmente já existe |
| **Types** | mypy / pyright | `mypy . --strict` | Geralmente já existe |
| **Profiling** | cProfile / py-spy | `python -m cProfile -s cumulative script.py` | cProfile = built-in; py-spy = perguntar |
| **Memory** | tracemalloc / memray | `python -c "import tracemalloc; ..."` | tracemalloc = built-in; memray = perguntar |
| **Duplicação** | jscpd / manual grep | `npx jscpd src/ --min-lines 5` | Sim — perguntar |

### ORM-específico (SQLAlchemy)

```python
# Contar queries por request (em teste)
from sqlalchemy import event
queries = []
@event.listens_for(engine, "before_cursor_execute")
def receive_before(conn, cursor, stmt, params, context, executemany):
    queries.append(stmt)

# Depois do request:
assert len(queries) <= 3, f"N+1! {len(queries)} queries"
```

### ORM-específico (Django)

```python
from django.test.utils import override_settings
from django.db import connection, reset_queries

@override_settings(DEBUG=True)
def test_query_count(self):
    reset_queries()
    response = self.client.get("/api/items/")
    assert len(connection.queries) <= 3
```

---

## TypeScript / JavaScript (Node + Frontend)

### Detecção
- `package.json`, `tsconfig.json`, `next.config.*`, `vite.config.*`

### Ferramentas de medição

| Eixo | Ferramenta | Comando (modo check) | Requer instalação? |
|------|-----------|----------------------|-------------------|
| **Bundle size** | next build / vite build | `npx next build` (mostra sizes) | Não |
| **Bundle analysis** | @next/bundle-analyzer / source-map-explorer | `ANALYZE=true npx next build` | Sim — perguntar |
| **Imports pesados** | knip (exports/imports mortos) | `npx knip` | Sim — perguntar |
| **Re-renders** | React DevTools Profiler / leitura manual | Leitura: props instáveis, contexto amplo | Não |
| **Lighthouse** | lighthouse CLI | `npx lighthouse http://localhost:3000 --output=json --chrome-flags="--headless"` | Geralmente disponível |
| **Lint** | eslint | `npx eslint .` (sem --fix) | Geralmente já existe |
| **Types** | tsc | `npx tsc --noEmit` | Geralmente já existe |
| **Complexidade** | eslint-plugin-complexity | Regra `complexity` no `.eslintrc` | Config, não install |
| **Código morto** | knip / ts-prune | `npx knip --reporter compact` | Sim — perguntar |
| **Duplicação** | jscpd | `npx jscpd src/ --min-lines 5 --reporters console` | Sim — perguntar |
| **`any` audit** | grep + tsc strict | `rg ":\s*any\b" --type ts -c` | Não |
| **Node profiling** | clinic.js / 0x | `npx clinic doctor -- node server.js` | Sim — perguntar |

### Next.js específico

```bash
# Bundle por rota (build output)
npx next build
# Mostra "First Load JS" por rota — procurar > 100 KB

# Source map explorer (se habilitado)
ANALYZE=true npx next build
# Abre mapa visual de dependências por chunk
```

### React específico

```
# Re-renders: checar no código
- Props que são objeto/array literal no JSX → referência nova a cada render
- useEffect sem deps ou com deps instáveis
- Context.Provider com value={} literal
- Componentes sem React.memo em listas grandes
```

---

## PHP

### Detecção
- `composer.json`, `artisan`, `phpunit.xml`

### Ferramentas de medição

| Eixo | Ferramenta | Comando (modo check) | Requer instalação? |
|------|-----------|----------------------|-------------------|
| **Queries** | Laravel Debugbar / `DB::getQueryLog()` | `DB::enableQueryLog(); ... DB::getQueryLog()` | Debugbar = dev dep |
| **Complexidade** | phpmd | `./vendor/bin/phpmd src/ text codesize` | Sim — perguntar |
| **Lint / types** | phpstan | `./vendor/bin/phpstan analyse src/ --level=max` | Geralmente já existe |
| **Código morto** | psalm (UnusedMethod, etc.) | `./vendor/bin/psalm --show-info=true` | Sim — perguntar |
| **Duplicação** | phpcpd | `./vendor/bin/phpcpd src/` | Sim — perguntar |
| **Profiling** | Xdebug profiler / Blackfire | Xdebug: `XDEBUG_MODE=profile php script.php` | Config |

### Laravel específico

```php
// Contar queries em teste
DB::enableQueryLog();
$response = $this->get('/api/items');
$queries = DB::getQueryLog();
$this->assertLessThanOrEqual(3, count($queries), 'N+1 detectado!');
```

---

## Go

### Detecção
- `go.mod`, `go.sum`

### Ferramentas de medição

| Eixo | Ferramenta | Comando (modo check) | Requer instalação? |
|------|-----------|----------------------|-------------------|
| **Profiling** | pprof (built-in) | `go test -bench=. -cpuprofile=cpu.prof ./...` | Não |
| **Memory** | pprof (built-in) | `go test -bench=. -memprofile=mem.prof ./...` | Não |
| **Lint** | golangci-lint | `golangci-lint run ./...` | Geralmente já existe |
| **Complexidade** | gocyclo | `gocyclo -over 10 .` | Sim — perguntar |
| **Código morto** | deadcode | `go install golang.org/x/tools/cmd/deadcode@latest && deadcode ./...` | Sim — perguntar |
| **Race detector** | go test -race | `go test -race ./...` | Não (built-in) |
| **Benchmark** | testing.B | `go test -bench=. -benchmem ./...` | Não (built-in) |

---

## Ferramentas Universais (qualquer stack)

| Finalidade | Ferramenta | Uso |
|-----------|-----------|-----|
| **Duplicação de código** | jscpd | `npx jscpd src/ --min-lines 5` |
| **Contagem de linhas / complexidade** | tokei / cloc | `tokei src/` |
| **Busca de padrões** | ripgrep (rg) | `rg "SELECT \*" --type py` |
| **Busca de `any`** | rg | `rg ":\s*any\b" --type ts -c` |
| **Busca de TODO/FIXME/HACK** | rg | `rg "TODO\|FIXME\|HACK\|XXX" src/` |
| **Busca de magic numbers** | rg | `rg "\b\d{2,}\b" --type py` (filtrar constantes) |
| **Busca de `console.log`** | rg | `rg "console\.(log\|debug\|info)" --type ts` |
| **Busca de God files** | wc / tokei | Arquivos > 400 linhas |
| **Imagens sem otimização** | rg + ls | Imagens > 200 KB em `public/` |

---

## Regras de ouro

1. **Usar o que já existe** — não trocar lint/bundler/profiler sem motivo.
2. **Nunca instalar** sem listar no plano e receber OK.
3. **Nunca `--fix`** — modo check/report sempre.
4. **Se não tem ferramenta**: gap no relatório, não estimativa inventada.
5. **Medir ANTES e DEPOIS** se for aplicar correção. Sem baseline = "suspeita".
