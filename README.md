# 🚀 Trivor — Plataforma de Inteligência Profissional & Análise de Mercado com IA

> **Trivor** é um ecossistema completo e inteligente projetado para potencializar o desenvolvimento de carreira, otimização de currículos para sistemas ATS (Applicant Tracking Systems) e inteligência preditiva de mercado de trabalho.

---

## 💡 Sobre o Projeto

O **Trivor** nasceu com a missão de resolver o grande descompasso entre candidatos e recrutadores. Com a automação massiva de triagem baseada em IA e filtros ATS no mercado de trabalho moderno, milhares de profissionais qualificados são descartados por falhas de formatação, falta de palavras-chave estratégicas ou perfis desalinhados com a realidade do mercado.

A plataforma unifica **Engenharia de Prompt**, **Parsing Inteligente de Documentos** e **Mineração em Tempo Real de Vagas** em uma única interface moderna, rápida e intuitiva.

---

## 🔥 Principais Módulos & Funcionalidades

### 1. 📊 Dashboard de Métricas & Execução
- Visão unificada da saúde do sistema, total de análises realizadas e logs de requisições.
- Gráficos e indicadores de performance do backend FastAPI.

### 2. 📄 Análise Inteligente de Currículo (Diagnóstico ATS)
- **Extração OCR & Leitura Direta**: Leitura precisa de PDFs com suporte a extração estruturada.
- **Pontuação ATS (0-100)**: Cálculo de alinhamento com sistemas automatizados de recrutamento.
- **Auditoria Detalhada**:
  - Identificação de erros ortográficos, gramaticais e de pontuação.
  - Análise de impacto de conquistas e métricas quantitativas.
  - Verificação de legibilidade, estrutura de seções e links quebrados/inválidos.

### 3. 🔗 Auditoria de Perfil LinkedIn
- Análise diagnóstica da presença digital profissional.
- Verificação de Título, Resumo/Sobre, Experiências e Habilidades.
- Sugestões estratégicas de palavra-chave para aumentar a visibilidade nas buscas de recrutadores.

### 4. 📈 Inteligência de Mercado (Market Intelligence)
- **Mineração Massiva de Vagas**: Integração em tempo real com buscadores de empregos (JSearch/Google for Jobs).
- **Extração 100% Agnóstica a Área**: IA configurada para extrair requisitos reais de qualquer profissão (TI, Engenharia, Mecânica, Vendas, Saúde, etc.).
- **Análise Estatística de Requisitos**:
  - Top Hard Skills e Tecnologias mais exigidas.
  - Soft Skills e Certificações indispensáveis.
  - Requisitos desejáveis (*Nice-to-Have*) e distribuição de modalidades (Remoto, Híbrido, Presencial).
  - Vagas detalhadas analisadas vs. descartadas com justificativa lógica.

### 5. ⚙️ Central de Configuração Multi-Provider de IA
- Gerenciamento dinâmico e seguro de chaves API (OpenAI, Anthropic, Gemini, Groq, custom endpoints).
- Sistema inteligente de *fallback* e balanceamento de chamadas.

### 6. 📜 Histórico & Logs de Requisições
- Tabela detalhada em tempo real com Timestamp, Método HTTP, Endpoint, Status Code, Duração e Modal de erro completo.

---

## 🛠️ Tecnologias Utilizadas

### **Frontend**
- **Framework**: Next.js 16 (App Router) + React 19 + TypeScript
- **Estilização**: Tailwind CSS + Lucide Icons + Framer Motion
- **Componentes**: Radix UI / Shadcn UI

### **Backend**
- **Framework**: FastAPI (Python 3.11+) + Uvicorn
- **Processamento de PDF**: PyMuPDF (`fitz`), pdfplumber, PyPDF
- **Persistência**: SQLite (Async Engine)
- **Modelos de IA**: OpenAI API (GPT-4o, GPT-4o-mini) / OmniRoute Fallback

### **Extensão Browser**
- Extensão Google Chrome (Manifest V3) para captura direta de perfis e dados de vagas.

---

## 🏗️ Arquitetura de Pastas

```
curriculo/
├── backend/                 # API REST FastAPI (Python 3.11+)
│   ├── main.py              # Endpoints principais, middleware e rotas
│   ├── market_service.py    # Motor de inteligência de mercado e integração JSearch
│   ├── logging_service.py   # Sistema de logs e persistência SQLite
│   ├── export_utils.py      # Gerador de relatórios (Markdown, DOCX, PDF)
│   └── market_export.py     # Pipeline de exportação de dados de mercado
├── frontend/                # Aplicação web Next.js
│   ├── app/                 # Páginas (Dashboard, Currículo, LinkedIn, Mercado, Logs, Config)
│   ├── components/          # Componentes reutilizáveis de UI
│   ├── hooks/               # Custom React Hooks
│   └── lib/                 # Utilitários de API e formatadores
├── extension/               # Extensão Manifest V3 para Google Chrome
├── knowledge/               # Prompts e engenharia de contexto para IA
├── tests/                   # Suíte de testes automatizados (Pytest)
├── docker-compose.yml       # Orquestração de serviços com Docker
└── Dockerfile               # Build de produção do backend
```

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
- **Node.js**: v18.0.0+
- **Python**: v3.11+
- **Git**

### 1. Clonar o Repositório
```bash
git clone https://github.com/gabriell-c/Trivor.git
cd Trivor
```

### 2. Configurar & Executar o Backend

```bash
# Navegar para a pasta do backend
cd backend

# Criar e ativar o ambiente virtual
python -m venv venv

# No Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt

# Iniciar o servidor FastAPI
python main.py
```
> O backend estará rodando em `http://127.0.0.1:8000`.

### 3. Configurar & Executar o Frontend

Em um novo terminal:

```bash
# Navegar para a pasta do frontend
cd frontend

# Instalar dependências
npm install

# Rodar em modo de desenvolvimento
npm run dev
```
> A aplicação web estará acessível em `http://localhost:3000`.

---

## 🐳 Execução via Docker

Se preferir rodar toda a aplicação via containers Docker:

```bash
docker-compose up --build -d
```

---

## 📄 Licença

Este projeto está licenciado sob a licença [MIT](LICENSE).

---
<p center align="center">Desenvolvido com 💙 para transformar a gestão de carreira e inteligência de recrutamento.</p>
