# Stacks Security — Detecção e Tooling

Usar **depois** dos guardrails do `SKILL.md`. Se o host alvo não for local → **não rode** scanners dinâmicos.

---

## 1. Detectar stack e superfícies

| Sinal | Interpretação |
|-------|----------------|
| `pyproject.toml`, `requirements.txt`, `Pipfile` | Python |
| `package.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb` | JS/TS (Node) |
| `composer.json`, `artisan` | PHP (Laravel/…) |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `Gemfile` | Ruby |
| `docker-compose.yml` / `compose.yaml` | Infra local |
| `apps/web`, `src/app`, `*.tsx`, `next.config.*`, `vite.config.*` | Frontend |
| `*.prisma`, `alembic/`, `manage.py`, `ormconfig` | DB via ORM |
| `schema.graphql`, `apollo`, `strawberry`, `graphene` | GraphQL |
| `socket.io`, `websockets`, `channels` | WebSocket |
| `android/`, `ios/`, `capacitor.config.*`, `app.json` (Expo) | Mobile/híbrido |

### Identificar banco

| Pista | DB |
|-------|-----|
| `postgresql://`, `postgres://`, `psycopg`, `asyncpg` | PostgreSQL |
| `mysql://`, `mariadb`, `PyMySQL` | MySQL/MariaDB |
| `sqlite:///` / `*.db` | SQLite |
| `mongodb://`, `mongoose` | MongoDB |
| `redis://`, `ioredis` | Redis (cache/fila — não é RDBMS, mas conta pra NoSQL/injeção de comando em scripts) |

### Resolver alvo LOCAL (obrigatório antes do dinâmico)

1. Ler `README`, scripts (`dev`, `start`), `.env.example`, compose (`ports:`).
2. Portas típicas: API `8000`/`8080`/`3001`, web `3000`/`5173`, DB `5432`/`3306` no compose.
3. Confirmar processo escutando em `127.0.0.1`/`localhost` (ex.: `netstat`/`Get-NetTCPConnection` / `docker compose ps`).
4. Base URL dinâmica permitida **somente** se host ∈ `{localhost, 127.0.0.1, ::1}` ou nome de serviço **só** alcançável no compose da máquina (e ainda assim preferir publicar porta em localhost).

### Regra alvo remoto

Se `DATABASE_URL`, `API_URL`, `REDIS_URL`, etc. apontar para:
- `*.rds.amazonaws.com`, `*.amazonaws.com` (não local),
- domínio público,
- IP não-RFC1918 / não-loopback,

→ **PARE** dinâmico contra esse host. `GAP(alvo-remoto)`. Peça DB/API local ou override explícito do usuário para um alvo localhost. **Nunca** use SSM/prod credentials como alvo de ataque.

---

## 2. Tooling por stack (instalar só com OK)

### Python

| Finalidade | Ferramenta | Comando típico (check) |
|------------|------------|-------------------------|
| SAST | bandit | `bandit -r src/ -ll` |
| SAST regras | semgrep | `semgrep --config=auto .` |
| Deps | pip-audit / safety | `pip-audit` |
| Secrets | gitleaks / trufflehog | ver universal |
| Dinâmico API | httpx/pytest / curl | requests contra `http://127.0.0.1:PORT` |
| SQLi assistido | sqlmap | **só** `-u http://127.0.0.1:...` + OK; sem `--os-shell` destrutivo |

### JavaScript / TypeScript (Node + Front)

| Finalidade | Ferramenta | Comando |
|------------|------------|---------|
| Deps | npm/pnpm/yarn audit | `pnpm audit` / `npm audit --json` |
| Lint segurança | eslint-plugin-security | se já no projeto |
| Secrets no bundle | grep/`gitleaks` em `dist`/`.next` | |
| Front XSS sinks | busca `dangerouslySetInnerHTML`, `innerHTML` | |
| Retire.js (opcional) | `npx retire` | com OK |

### PHP

| Finalidade | Ferramenta |
|------------|------------|
| Deps | `composer audit` |
| Análise | Psalm / PHPStan (nível alto); regras taint se disponíveis |
| Dinâmico | PHPUnit Feature + requests localhost |

### Go

| Finalidade | Ferramenta |
|------------|------------|
| Deps | `govulncheck ./...` |
| Vetores | `gosec ./...` |

### Universal (qualquer stack)

| Finalidade | Ferramenta | Notas |
|------------|------------|-------|
| Secrets | **gitleaks**, trufflehog | mascarar output no relatório |
| Deps/imagem | **trivy** fs/image | opcional |
| Proxy scan | **OWASP ZAP** headless Docker | **só** target `http://127.0.0.1:...` |
| Web scan | nikto | só localhost |
| SQLi | sqlmap | só localhost; não-destrutivo |

Ausente → `GAP(tooling: nome)` + ação (“instalar X com OK”). **Não invente** resultado de scanner.

---

## 3. Como atacar com segurança (dinâmico)

```text
OK:  http://127.0.0.1:8000/v1/...
OK:  http://localhost:3000/...
NO:  https://api.cliente.com/...
NO:  postgresql://user:pass@xxx.rds.amazonaws.com:5432/...
NO:  qualquer host resolvido fora de loopback sem OK escrito
```

Preferências:
1. **In-process** (ASGITransport / test client) quando prova a mesma app local sem rede.
2. Senão HTTP para porta local publicada.
3. Headers de auth de **fixture/dev** — não tokens de produção.

Payloads: ver [catalogo-ataques.md](catalogo-ataques.md). Sempre não-destrutivo.

---

## 4. Comandos úteis (referência)

```bash
# Secrets (se instalado)
gitleaks detect --source . --no-git -v

# Python
bandit -r . -ll -x ./venv,./.venv,./node_modules
pip-audit

# Node
pnpm audit
# ou: npm audit

# PHP
composer audit

# Go
govulncheck ./...
```

PowerShell — checar se porta local escuta:

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::','::1') } |
  Select-Object LocalAddress, LocalPort
```

---

## 5. Mapeamento rápido stack → classes quentes

| Stack | Priorizar |
|-------|-----------|
| FastAPI/Django/Flask + Postgres | A1, A9, A10, A14, A15, B1, C1/C2, F*, G1, G6 |
| Next/React | D1–D7, G1 (bundle), C7 se BFF |
| Laravel/PHP | A1, A7, A20, F*, G1, G6 |
| Express/Nest | A1–A3, C1, C2, C8, D*, G* |
| SQLite embutido | A1, B2; B1 menos crítico mas ainda revisar |
| Mongo | A2 |
| GraphQL | C4, C5 |

N/A continua obrigatório quando a superfície não existe.

---

## 6. Regra de ouro

Adapte-se ao toolchain **já presente**. Não troque o stack do projeto. Scanners extras = OK do usuário. Dinâmico **sempre** localhost-first; remoto = gap, não “quase local”.
