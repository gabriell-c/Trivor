# Makefile - Trivor

.PHONY: help dev backend-dev frontend-dev test test-backend test-frontend lint lint-backend lint-frontend clean build docker-up docker-down

help: ## Mostra ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================
# Desenvolvimento
# ============================================

dev: frontend-dev backend-dev ## Inicia ambos os servers (frontend + backend)

backend-dev: ## Inicia backend em modo desenvolvimento
	@echo "🚀 Iniciando backend..."
	cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend-dev: ## Inicia frontend em modo desenvolvimento
	@echo "🎨 Iniciando frontend..."
	cd frontend && npm run dev

# ============================================
# Testes
# ============================================

test: test-backend test-frontend ## Roda todos os testes

test-backend: ## Roda testes do backend
	@echo "🧪 Rodando testes do backend..."
	cd backend && python -m pytest tests/ -v

test-frontend: ## Roda testes do frontend
	@echo "🧪 Rodando testes do frontend..."
	cd frontend && npm test

# ============================================
# Linting
# ============================================

lint: lint-backend lint-frontend ## Roda lint em todos os projetos

lint-backend: ## Roda lint no backend
	@echo "🔍 Rodando lint no backend..."
	cd backend && python -m ruff check .

lint-frontend: ## Roda lint no frontend
	@echo "🔍 Rodando lint no frontend..."
	cd frontend && npm run lint

# ============================================
# Build
# ============================================

build: build-backend build-frontend ## Constrói ambos os projetos

build-backend: ## Constrói o backend
	@echo "📦 Construindo backend..."
	cd backend && python -m py_compile main.py

build-frontend: ## Constrói o frontend
	@echo "📦 Construindo frontend..."
	cd frontend && npm run build

# ============================================
# Docker
# ============================================

docker-up: ## Inicia containers Docker
	@echo "🐳 Iniciando containers..."
	docker-compose up -d

docker-down: ## Para containers Docker
	@echo "🛑 Parando containers..."
	docker-compose down

docker-logs: ## Mostra logs dos containers
	docker-compose logs -f

# ============================================
# Limpeza
# ============================================

clean: ## Limpa arquivos de build e cache
	@echo "🧹 Limpando arquivos..."
	rm -rf backend/__pycache__
	rm -rf backend/**/*.pyc
	rm -rf frontend/.next
	rm -rf frontend/node_modules/.cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-all: clean ## Limpa tudo incluindo node_modules e venv
	@echo "🧹 Limpando tudo..."
	rm -rf backend/venv
	rm -rf frontend/node_modules
	rm -rf frontend/.next
	rm -rf frontend/build

# ============================================
# Instalar dependências
# ============================================

install-backend: ## Instala dependências do backend
	@echo "📦 Instalando dependências do backend..."
	cd backend && python -m pip install -r requirements.txt

install-frontend: ## Instala dependências do frontend
	@echo "📦 Instalando dependências do frontend..."
	cd frontend && npm install

install: install-backend install-frontend ## Instala todas as dependências
