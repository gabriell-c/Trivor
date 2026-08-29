# Plano de Melhorias - Projeto Trivor

## Resumo
Melhorias de robustez, profissionalismo, UI/UX e funcionalidades faltantes.

---

## FASE 1: Backend - Robustez e Profissionalismo

### 1.1 Adicionar Pydantic Models para Validação
**Arquivo**: `backend/main.py`
- Criar models: `CVAnalysisRequest`, `IAAnalysisRequest`, `MarketAnalysisRequest`, `LinkedinAnalysisRequest`
- Validar inputs antes de processar
- Retornar erros estruturados com detalhamento

### 1.2 Adicionar Rate Limit Exception Handler
**Arquivo**: `backend/main.py`
- Handler para `RateLimitExceeded`
- Retornar 429 com mensagem amigável
- Adicionar cabeçalho `Retry-After`

### 1.3 Adicionar Health Check Robusto
**Arquivo**: `backend/main.py`
- Endpoint `GET /health` com verificação de:
  - Banco de dados SQLite
  - Providers IA configurados
  - Tempo de resposta
- Retornar status 200/503 com detalhes

### 1.4 Adicionar Middleware de Logging Estruturado
**Arquivo**: `backend/main.py`
- Middleware que loga:
  - Método HTTP
  - Path
  - Status code
  - Tempo de resposta
  - User-Agent
  - IP do cliente
- Formatar como JSON para facilitar análise

### 1.5 Adicionar Resposta de Erro Consistente
**Arquivo**: `backend/main.py`
- Função `error_response()` que padroniza erros
- Formato: `{ "error": { "code": "...", "message": "...", "details": {...} } }`
- Usar em todos os HTTPException

### 1.6 Adicionar Graceful Shutdown
**Arquivo**: `backend/main.py`
- Handler para sinais SIGTERM/SIGINT
- Finalizar conexões ativas
- Salvar estado dos logs
- Documentar no README

---

## FASE 2: Frontend - UI/UX Profissional

### 2.1 Sistema de Toast Notifications
**Novo arquivo**: `frontend/app/components/Toast.tsx`
- Componente Toast reutilizável
- Suportar: success, error, warning, info
- Auto-dismiss após 5s
- Posição: bottom-right
- Animação: slide-in/slide-out

**Novo hook**: `frontend/app/hooks/useToast.ts`
- Gerenciador de toasts global
- Funções: `showToast()`, `showSuccess()`, `showError()`, `showWarning()`

**Uso**: Substituir `alert()` e erros inline em:
- `CurriculoTool.tsx`
- `page.tsx`
- `linkedin/page.tsx`
- `api-settings/page.tsx`

### 2.2 Loading Skeletons
**Arquivo**: `frontend/app/components/Skeleton.tsx`
- Componente Skeleton reutilizável
- Variantes: card, table, list, text

**Aplicar em**:
- `dashboard/page.tsx` - Skeleton nos stat cards
- `logs/page.tsx` - Skeleton na tabela
- `market/page.tsx` - Skeleton nos gráficos
- `CurriculoTool.tsx` - Skeleton durante análise

### 2.3 Empty States
**Arquivo**: `frontend/app/components/EmptyState.tsx`
- Componente reutilizável
- Props: icon, title, description, action
- Visual consistente com design system

**Aplicar em**:
- `dashboard/page.tsx` - Quando não há logs
- `logs/page.tsx` - Quando não há logs
- `market/page.tsx` - Quando não há resultados
- `api-settings/page.tsx` - Quando não há providers

### 2.4 Error Boundaries por Página
**Arquivo**: `frontend/app/components/PageErrorBoundary.tsx`
- Wrapper com ErrorBoundary + toast
- Tratar erros de carregamento de dados
- Botão "Tentar novamente" que refetcha

**Aplicar em**:
- `dashboard/page.tsx`
- `logs/page.tsx`
- `market/page.tsx`
- `api-settings/page.tsx`

### 2.5 ARIA Labels e Acessibilidade
**Arquivo**: `frontend/app/components/Layout.tsx`
- Adicionar aria-label em todos os botões
- Adicionar aria-label nas navegações
- Adicionar skip link para main content

**Arquivo**: `frontend/app/components/CustomInput.tsx`
- Adicionar aria-describedby para erros
- Adicionar aria-invalid quando inválido

### 2.6 Keyboard Shortcuts
**Novo hook**: `frontend/app/hooks/useKeyboardShortcuts.ts`
- Atalhos:
  - `Ctrl+K` - Abrir busca (future)
  - `Ctrl+L` - Ir para logs
  - `Ctrl+D` - Ir para dashboard
  - `Escape` - Fechar modais

---

## FASE 3: Funcionalidades Faltantes

### 3.1 Export Market Analysis na UI
**Arquivo**: `frontend/app/market/page.tsx`
- Adicionar botão de export na seção de resultados
- Opções: MD, DOCX, PDF
- Usar endpoint `/api/export` existente

### 3.2 Busca em Logs
**Arquivo**: `frontend/app/logs/page.tsx`
- Adicionar campo de busca por texto
- Buscar em: endpoint, error, ip
- Debounce de 300ms

### 3.3 Filtros Avançados no Market
**Arquivo**: `frontend/app/market/page.tsx`
- Adicionar filtro por modality (remoto/híbrido/presencial)
- Adicionar filtro por salary range
- Adicionar filtro por seniority

### 3.4 Histórico de Análises
**Backend**:
- Criar tabela `analyses` no SQLite
- Salvar resultados de análises
- Endpoint `GET /api/analyses` - listar análises
- Endpoint `GET /api/analyses/{id}` - detalhes

**Frontend**:
- Página `/analyses` para histórico
- Componente para mostrar histórico na página de análise
- Botão "Salvar análise"

### 3.5 Upload em Batch
**Backend**:
- Endpoint `POST /api/cv/analyze/batch`
- Aceitar múltiplos arquivos
- Processar em paralelo
- Retornar resultados agrupados

**Frontend**:
- Modificar upload para aceitar múltiplos arquivos
- Mostrar progresso individual
- Mostrar resultados em lista

---

## FASE 4: Configuração e DevOps

### 4.1 Adicionar pyproject.toml
**Novo arquivo**: `backend/pyproject.toml`
- Metadados do projeto
- Dependências
- Configuração de lint/teste
- Script de entrada

### 4.2 Adicionar Makefile
**Novo arquivo**: `Makefile`
- Comandos: `make dev`, `make test`, `make lint`, `make clean`
- Frontend: `make frontend-dev`, `make frontend-build`
- Backend: `make backend-dev`, `make backend-test`

### 4.3 Adicionar Dockerfile
**Novo arquivo**: `Dockerfile`
- Multi-stage build
- Backend e frontend separados
- Variáveis de ambiente

### 4.4 Adicionar docker-compose.yml
**Novo arquivo**: `docker-compose.yml`
- Serviços: backend, frontend, database
- Volumes para dados
- Variáveis de ambiente
- Health checks

---

## FASE 5: Testes e Qualidade

### 5.1 Adicionar Testes de Integração
**Novo arquivo**: `tests/test_integrations.py`
- Testar endpoints principais
- Testar com providers reais (mock)
- Testar exportações

### 5.2 Adicionar linting
**Backend**:
- Adicionar `ruff` ao requirements.txt
- Configurar `ruff.toml`
- Adicionar script de lint no Makefile

**Frontend**:
- Adicionar `eslint-plugin-jsx-a11y`
- Configurar regras de acessibilidade
- Adicionar script de lint no package.json

### 5.3 Adicionar prettier
**Novo arquivo**: `.prettierrc`
- Configurar formatação consistente
- Adicionar ao git hook (pre-commit)

---

## FASE 6: Documentação

### 6.1 Atualizar README
**Arquivo**: `README.md`
- Adicionar seção de toast notifications
- Adicionar seção de keyboard shortcuts
- Adicionar seção de batch upload
- Adicionar screenshots da UI
- Adicionar contribuição guia

### 6.2 Adicionar API Documentation
**Backend**:
- Adicionar OpenAPI/Swagger documentation
- Documentar todos os endpoints
- Adicionar exemplos de request/response

---

## Checklist de Verificação

### Backend
- [ ] Pydantic models para validação
- [ ] Rate limit exception handler
- [ ] Health check robusto
- [ ] Logging estruturado
- [ ] Erros consistentes
- [ ] Graceful shutdown

### Frontend
- [ ] Sistema de toast notifications
- [ ] Loading skeletons
- [ ] Empty states
- [ ] Error boundaries por página
- [ ] ARIA labels
- [ ] Keyboard shortcuts

### Funcionalidades
- [ ] Export market analysis na UI
- [ ] Busca em logs
- [ ] Filtros avançados no market
- [ ] Histórico de análises
- [ ] Upload em batch

### Configuração
- [ ] pyproject.toml
- [ ] Makefile
- [ ] Dockerfile
- [ ] docker-compose.yml

### Testes
- [ ] Testes de integração
- [ ] Linting backend
- [ ] Linting frontend
- [ ] Prettier

### Documentação
- [ ] README atualizado
- [ ] API documentation

---

## Arquivos a Criar/Modificar

### Novos Arquivos
1. `backend/pyproject.toml`
2. `Makefile`
3. `Dockerfile`
4. `docker-compose.yml`
5. `frontend/app/components/Toast.tsx`
6. `frontend/app/components/Skeleton.tsx`
7. `frontend/app/components/EmptyState.tsx`
8. `frontend/app/components/PageErrorBoundary.tsx`
9. `frontend/app/hooks/useToast.ts`
10. `frontend/app/hooks/useKeyboardShortcuts.ts`
11. `tests/test_integrations.py`
12. `.prettierrc`
13. `ruff.toml`

### Arquivos a Modificar
1. `backend/main.py`
2. `backend/requirements.txt`
3. `frontend/app/layout.tsx`
4. `frontend/app/components/Layout.tsx`
5. `frontend/app/components/CustomInput.tsx`
6. `frontend/app/dashboard/page.tsx`
7. `frontend/app/logs/page.tsx`
8. `frontend/app/market/page.tsx`
9. `frontend/app/components/CurriculoTool.tsx`
10. `frontend/app/page.tsx`
11. `frontend/app/linkedin/page.tsx`
12. `frontend/app/api-settings/page.tsx`
13. `README.md`
14. `frontend/package.json`
