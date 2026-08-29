# Trivor — Motor de Análise e Diagnóstico de Currículos

> **Trivor** é uma plataforma completa de análise de currículos com IA, market intelligence e diagnóstico profissional.

---

## 📌 Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| 📄 **Análise de Currículo** | Diagnóstico completo com pontuação ATS, verificação de gargalos e sugestões de melhoria |
| 💼 **Market Intelligence** | Análise de vagas de mercado, comparação de stacks tecnológicos e salários |
| 🔗 **Análise de LinkedIn** | Auditoria de perfil profissional com diagnóstico de visibilidade e relevância |
| ⚙️ **Configuração de IAs** | Gerenciamento multi-provider (OpenAI, Anthropic, custom) com priorização inteligente |
| 📊 **Dashboard & Logs** | Métricas de uso, saúde do sistema e histórico completo de requisições |
| 📥 **Exportação** | Relatórios em Markdown, DOCX e PDF |

---

## 🏗️ Arquitetura

```
trivor/
├── backend/                 # FastAPI (Python 3.11+)
│   ├── main.py             # API principal com rate limiting
│   ├── market_service.py   # Pipeline de análise de mercado (JSearch + IA)
│   ├── logging_service.py  # Persistência de logs em SQLite
│   ├── export_utils.py     # Exportação (MD, DOCX, PDF)
│   └── market_export.py    # Exportação específica de market
├── frontend/               # Next.js 16 + React 19 + TypeScript
│   ├── app/
│   │   ├── page.tsx        # Análise de currículo
│   │   ├── market/page.tsx # Market intelligence
│   │   ├── linkedin/page.tsx # Análise LinkedIn
│   │   ├── dashboard/page.tsx # Dashboard
│   │   ├── logs/page.tsx    # Logs detalhados
│   │   ├── api-settings/page.tsx # Configuração de IAs
│   │   └── components/      # Componentes reutilizáveis
│   ├── hooks/
│   ├── lib/
│   └── types/
└── extension/              # Extensão Chrome (Manifest V3)
```

---

## 🚀 Instalação

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python main.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Variáveis de Ambiente

```bash
# Copiar exemplo
cp .env.example .env.local

# Configurar chaves de API
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

---

## 🔗 Endpoints da API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/cv/analyze` | Análise de currículo |
| POST | `/api/ia/analyze` | Análise com IA customizada |
| POST | `/api/market/analyze` | Análise de mercado |
| POST | `/api/linkedin/analyze` | Análise de perfil LinkedIn |
| GET | `/api/logs` | Listar logs (com filtros) |
| GET | `/api/logs/stats` | Estatísticas de logs |
| DELETE | `/api/logs` | Limpar todos os logs |
| POST | `/api/logs/cleanup` | Limpar logs antigos (>90 dias) |
| POST | `/api/export` | Exportar relatório |
| GET | `/health` | Health check |

---

## 📦 Tecnologias

### Backend
- **FastAPI** — Framework web assíncrono
- **OpenAI SDK** — Integração com IA
- **SQLite** — Persistência de logs
- **slowapi** — Rate limiting
- **docling** — Conversão de documentos
- **pypdfium2** — Manipulação de PDF

### Frontend
- **Next.js 16** — Framework React
- **React 19** — Biblioteca UI
- **TypeScript** — Tipagem estática
- **Tailwind CSS** — Estilização
- **Framer Motion** — Animações
- **Lucide React** — Ícones

---

## 🎨 Interface e UX

- **Toast Notifications** — Feedback visual para ações (sucesso, erro, aviso)
- **Loading Skeletons** — Estados de carregamento suaves
- **Empty States** — Mensagens claras quando não há dados
- **Error Boundaries** — Tratamento de erros por página
- **Keyboard Shortcuts** — `Ctrl+L` (logs), `Ctrl+D` (dashboard), `Ctrl+C` (currículo)
- **Acessibilidade** — ARIA labels e navegação por teclado

---

## 🛡️ Recursos de Segurança

- ✅ Rate limiting em todos os endpoints críticos
- ✅ API keys gerenciadas via UI (nunca hardcodadas)
- ✅ Logs de todas as requisições com sanitização
- ✅ Cleanup automático de logs antigos (90 dias)
- ✅ `.gitignore` protege credenciais
- ✅ Templates de prompt isolados do código sensível
- ✅ Validação de inputs com Pydantic
- ✅ Respostas de erro padronizadas
- ✅ Graceful shutdown

---

## 📊 Status do Projeto

| Item | Status |
|------|--------|
| Análise de Currículo | ✅ Completo |
| Market Intelligence | ✅ Completo |
| Análise LinkedIn | ✅ Completo |
| Dashboard & Logs | ✅ Completo |
| Configuração de IAs | ✅ Completo |
| Exportação | ✅ Completo |
| Docker | ✅ Configurado |
| Testes | 🔄 Em desenvolvimento |

---

## 🚀 Comandos Rápidos

```bash
# Iniciar desenvolvimento
make dev

# Iniciar apenas backend
make backend-dev

# Iniciar apenas frontend
make frontend-dev

# Rodar testes
make test

# Lint
make lint

# Build
make build

# Docker
make docker-up
make docker-down
```

---

## 📄 Licença

MIT
