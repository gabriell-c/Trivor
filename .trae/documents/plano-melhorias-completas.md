# Plano de Melhorias e Correções — Trivor

## Resumo

Corrigir problemas de segurança, robustez e testes no projeto Trivor.

**Escopo**: Backend (FastAPI), Frontend (Next.js), Testes.

---

## Problemas Identificados

### 🔴 Alta Prioridade

1. **Hardcoding de API keys em logs** — `logging_service.py` salva `api_key_preview` sem truncar. Se o valor passado for a key inteira, fica exposta.
2. **SQLite sem connection pooling** — 15 chamadas `sqlite3.connect()` espalhadas sem contexto gerenciado. Em concorrência, risco de corrupção.
3. **`sys.path.insert` em main.py** — Workaround de importação manual. Quebra portabilidade e causa problemas em ambientes virtuais.
4. **Sem validação de upload de arquivo** — `main.py` aceita qualquer arquivo sem verificar extensão ou tamanho.
5. **Frontend sem catch em fetch** — Vários `fetch()` sem `catch`, deixando erros de rede/redirecionamento silenciosos.

### 🟡 Média Prioridade

6. **Testes unitários fracos** — `test_motor.py` testa função mock local, não o código real.
7. **Sem testes de integração** — `test_api_integration.py` requer servidor rodando; sem FastAPI TestClient.
8. **`DB_FILE` não inicializado em main.py** — Linha 327 referencia `DB_FILE` mas declaração está dentro de função.

### 🟢 Baixa Prioridade

9. **Documentação técnica ausente** — Nenhum arquivo explicando como executar localmente.
10. **Configuração CORS fixa** — `allow_origins` hardcoded; não funciona em produção sem ajustes.

---

## Estado Atual

| Camada | Tecnologia | Arquivo principal | Problema |
|--------|-----------|-------------------|----------|
| Backend | FastAPI + Python 3.11 | `backend/main.py` (~800 linhas) | sys.path hack, SQLite sem pooling |
| Backend | SQLite | `logging_service.py`, `market_service.py` | 15 conexões abertas/fechadas manualmente |
| Frontend | Next.js 16 + React 19 | `frontend/app/page.tsx` | fetch sem try/catch |
| Testes | pytest | `tests/test_motor.py` | Mock, não testa código real |
| Extensão | Chrome MV3 | `extension/` | Funcional, sem problemas críticos |

---

## Mudanças Propostas

### 1. Truncar api_key em logging_service.py

**Arquivo**: `backend/logging_service.py`

**O quê**: Truncar `api_key_preview` para últimos 4 caracteres.

**Como**:
```python
# Antes (linha ~66):
model, api_key_preview,

# Depois:
model, api_key_preview[-4:] if api_key_preview else "",
```

**Por quê**: Evita exposição de chaves API completas em logs do banco.

---

### 2. Conexões SQLite com context manager + WAL mode

**Arquivos**: `backend/logging_service.py`, `backend/market_service.py`, `backend/main.py`

**O quê**: Substituir `sqlite3.connect()` manual por função helper com contexto gerenciado e WAL mode.

**Como**: Criar `backend/db_utils.py`:
```python
import sqlite3
from pathlib import Path

def get_conn(db_path: Path):
    """Retorna conexão com WAL mode e timeout."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn

def close_conn(conn):
    conn.close()
```

Substituir todas as 15 ocorrências de `sqlite3.connect()` por `get_conn()`.

**Por quê**: WAL mode permite leituras concorrentes sem bloqueio. Context manager evita conexões órfãs.

---

### 3. Remover sys.path.insert e usar imports relativos

**Arquivo**: `backend/main.py`

**O quê**: Remover linhas 25-28 (`sys.path.insert`).

**Como**:
```python
# Remover:
# sys.path.insert(0, str(backend_path))
# import pypdfium2 ...

# Manter imports normais (já funcionam se rodar do diretório raiz)
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from export_utils import ...
from market_service import ...
from logging_service import ...
```

Adicionar no `pyproject.toml` a configuração de package:
```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
```

Já existe em `pyproject.toml` — apenas garantir que o `backend/` tenha `__init__.py`.

**Por quê**: `sys.path.insert` é workaround perigoso. Estrutura de package correta é mais portável.

---

### 4. Criar `backend/__init__.py`

**Arquivo**: `backend/__init__.py` (novo)

**Conteúdo vazio** (apenas marcador de package).

**Por quê**: Permite imports relativos e melhora discoverabilidade do package.

---

### 5. Validação de upload de arquivo em main.py

**Arquivo**: `backend/main.py`

**O quê**: Adicionar validação de tipo e tamanho antes de processar upload.

**Como**:
```python
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# No endpoint POST /api/analyze:
file = await file_data
if not file.filename:
    raise HTTPException(status_code=400, detail="Nome do arquivo ausente")

ext = Path(file.filename).suffix.lower()
if ext not in ALLOWED_EXTENSIONS:
    raise HTTPException(status_code=400, detail=f"Extensão não permitida: {ext}")

content = await file.read()
if len(content) > MAX_FILE_SIZE:
    raise HTTPException(status_code=400, detail="Arquivo excede 10MB")
```

**Por quê**: Previne upload de arquivos maliciosos e consumo excessivo de memória.

---

### 6. Frontend: try/catch em todos os fetches

**Arquivos**: `frontend/app/page.tsx`, `frontend/app/linkedin/page.tsx`, `frontend/app/market/page.tsx`, `frontend/app/dashboard/page.tsx`

**O quê**: Adicionar bloco `catch` em todas as chamadas `fetch()`.

**Como** — Exemplo em `page.tsx`:
```typescript
// Antes:
const response = await fetch(...)
if (!response.ok) throw new Error(...)

// Depois:
let response: Response
try {
  response = await fetch(...)
} catch (err) {
  setError(err instanceof Error ? err.message : 'Erro de rede')
  return
}
if (!response.ok) {
  const text = await response.text()
  setError(text || 'Erro na requisição')
  return
}
```

Aplicar o mesmo padrão em todos os `fetch()` dos 4 arquivos listados.

**Por quê**: Erros de rede (offline, timeout) hoje são tratados de forma inconsistente ou ignorados.

---

### 7. Testes de integração com FastAPI TestClient

**Arquivo**: `tests/test_integration.py` (novo)

**O quê**: Criar testes de integração usando `FastAPI TestClient` (sem servidor rodando).

**Como**:
```python
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_openapi_exists():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/analyze" in paths

def test_analyze_missing_file():
    r = client.post("/api/analyze")
    assert r.status_code == 422  # missing required file
```

**Por quê**: `test_api_integration.py` atual exige servidor rodando. TestClient testa a API sem infraestrutura externa.

---

### 8. Fix: DB_FILE em main.py

**Arquivo**: `backend/main.py`

**O quê**: Garantir que `DB_FILE` esteja disponível no escopo do módulo, não apenas dentro de função.

**Como**: Mover declaração para topo do arquivo (junto com `BASE_DIR`):
```python
DB_FILE = Path(__file__).parent / "market.db"
```

**Por quê**: Linhas 458, 507, 526 referenciam `DB_FILE` — se a função que a declara não for chamada,NameError.

---

### 9. CORS dinâmico via环境变量

**Arquivo**: `backend/main.py`

**O quê**: Tornar `allow_origins` configurável via环境变量.

**Como**:
```python
import os
from config import FRONTEND_URL

allow_origins = os.getenv("CORS_ALLOW_ORIGINS", FRONTEND_URL).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    ...
)
```

**Por quê**: Hardcode de origens quebra em produção/ambientes diferentes.

---

### 10. .env.example

**Arquivo**: `.env.example` (novo na raiz do projeto)

**Conteúdo**:
```env
# OpenAI
OPENAI_API_KEY=

# An Anthropic
ANTHROPIC_API_KEY=

# Trivor providers (JSON array)
TRIVOR_IAS=[{"id":"1","name":"OpenAI","provider":"openai","apiKey":"...","apiUrl":"https://api.openai.com/v1","modelName":"gpt-4o","usedFor":"all"}]

# CORS
CORS_ALLOW_ORIGINS=http://localhost:3000

# Frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

**Por quê**: Documenta variáveis necessárias para rodar o projeto localmente.

---

## Arquivos a Modificar

| Arquivo | Tipo de mudança |
|---------|----------------|
| `backend/logging_service.py` | Truncar api_key, usar get_conn |
| `backend/market_service.py` | Usar get_conn |
| `backend/main.py` | Remover sys.path, validar upload, fix DB_FILE, CORS dinâmico |
| `backend/db_utils.py` | Novo — helper de conexão |
| `backend/__init__.py` | Novo — package marker |
| `frontend/app/page.tsx` | try/catch em fetches |
| `frontend/app/linkedin/page.tsx` | try/catch em fetches |
| `frontend/app/market/page.tsx` | try/catch em fetches |
| `frontend/app/dashboard/page.tsx` | try/catch em fetches |
| `tests/test_integration.py` | Novo — FastAPI TestClient |
| `.env.example` | Novo — documentação de vars |
| `frontend/.env.local.example` | Novo — variável frontend |

---

## Ordem de Implementação

1. **db_utils.py** — Criar helper de conexão
2. **logging_service.py** — Truncar api_key + usar get_conn
3. **market_service.py** — Usar get_conn
4. **main.py** — Remover sys.path, fix DB_FILE, validação upload, CORS dinâmico
5. **backend/__init__.py** — Criar
6. **Frontend pages** — try/catch em todos os fetches
7. **tests/test_integration.py** — Criar testes FastAPI
8. **.env.example** — Criar documentação
9. **frontend/.env.local.example** — Criar documentação

---

## Assunções

- SQLite é o banco pretendido (não será migrado para PostgreSQL).
- O projeto roda localmente para desenvolvimento (não há Docker).
- As extensões do Chrome não precisam de mudanças.
- `pyproject.toml` já tem `sqlalchemy` nas dependências, mas não será usado neste plano (WAL mode resolve concorrência sem ORM).

---

## Verificação

1. `pytest tests/ -v` — todos os testes passam
2. `pytest tests/test_integration.py -v` — novos testes de integração passam
3. `python -m backend.main` — servidor inicia sem erro de import
4. Upload de arquivo .exe é rejeitado com 400
5. Logs não exibem chave API completa
6. Frontend não quebra em erro de rede (mostra mensagem ao usuário)
