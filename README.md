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
- **Retenção automática**: o histórico de relatórios de mercado guarda as 30 análises mais recentes — cada relatório é um JSON de ~300 KB, então o cap mantém o banco local enxuto sem perder o histórico útil.

### 5. ⚙️ Central de Configuração Multi-Provider de IA
- Gerenciamento dinâmico e seguro de chaves API (OpenAI, Anthropic, Gemini, Groq, custom endpoints).
- **Teste de conexão por provider** (ping de 1 token, custo mínimo): resposta imediata com a latência; acima de 3s fica amarelo ("lento"); em erro, mostra a causa sem vazar a chave. O histórico do último teste (latência + data/hora) fica no cartão do provider.
- Sistema inteligente de *fallback* e balanceamento de chamadas.
- **Chaves JSearch com segurança**: o backend guarda apenas um resumo de cada chave (prefixo + hash) — o texto puro nunca é persistido. O pool de busca usa as chaves re-digitadas na aba "Busca de Vagas" + a variável `JSEARCH_API_KEY` do `.env` do backend.

### 6. 📜 Histórico & Logs de Requisições
- Tabela detalhada em tempo real com Timestamp, Método HTTP, Endpoint, Status Code, Duração e Modal de erro completo.

### 7. 🎯 Fit Inteligente do CV com a Vaga (determinístico + LLM)
- **Nota de Fit (0-100) sem IA**: cruzamento determinístico entre requisitos da vaga (extraídos por heurística + dicionário de skills) e o texto do CV, com itens cobertos, faltantes e diferenciais.
- **Ranking "Meu CV × Mercado"**: sua nota contra as N vagas mais relevantes da base de mercado, com os tópicos onde você mais perde pontos.
- **Análise Semântica da Vaga (LLM)**: requisitos obrigatórios/diferenciais de verdade, evidência LITERAL do CV para cada item, resumo do gap e sugestões de reescrita priorizadas no formato XYZ (ação + ferramenta + resultado), prontas para copiar.
- **Simulação de Recrutador**: veredito (aprovado/duvida/reprovado), confiança, por quê, sinais vermelhos e 3 perguntas de entrevista prováveis — agnóstico de área.
- **Geração de Cover Letter**: formatos curta (2 parágrafos) e completa (5 parágrafos), com fatos auditáveis (cada afirmação precisa existir no seu CV).
- Anti-alucinação em todas as etapas: citações inventadas pela IA são removidas no pós-processo do backend.

### 8. 🔁 Comparação de Versões de CV (Diff)
- Envia versão anterior + nova e recebe: o que melhorou, o que piorou e a próxima melhoria recomendada.
- Sinais objetivos determinísticos (bullets, métricas numéricas, palavras-chave adicionadas/removidas) + narrativa LLM com evidência literal de cada versão.

### 9. ⚙️ Análise de CV em 2 Passes
- Pass 1: estrutura, ortografia, ordem de seções e ATS.
- Pass 2: qualidade (XYZ, métricas, narrativa) usando o resumo do pass 1 como contexto — resultados mais estáveis e criticidades ancoradas em trechos citados do próprio CV.
- **Especificidade obrigatória**: cada crítica nomeia o item concreto (empresa + cargo + período, bullet ou seção); a análise ATS lista, em ordem de impacto, o que falta para a nota chegar a 100. Trechos como "Next.js"/"React.js" não são flaggados como abreviação.

### 10. 📨 Job Hunter (Candidaturas) — automação de envios
- 5 bots de navegação automática (`gupy.py`, `indeed.py`, `infojobs.py`, `nerdin.py`, `solides.py`) que buscam vagas e enviam o CV nos portais; vivem em `apply/`.
- Roteador de LLM local (Groq → Gemini → Mistral → local) decide o preenchimento de formulários.
- Os bots gravam o histórico em `apply/relatorio/candidaturas.json`; a aba **Candidaturas** do Trivor lê esse arquivo e mostra resumo, portais e status (sucesso/parcial/falha) — sem escrever no diretório.
- Setup: `pip install -r apply/requirements-apply.txt` e, como browsers, **patchright/camoufox** (não `playwright install` — as engines reais dos bots são o patchright e o camoufox; o playwright é só fallback/camada):
  ```bash
  patchright install chromium
  camoufox fetch
  ```
  > **Workaround OneDrive (caminho não-ASCII)**: o pacote `indexed_zstd` falha ao abrir `fpgen/data/values.dat.zst` em caminho com "Área de Trabalho" — decomprima 1x para `values.dat` (o fpgen para de usar o `indexed_zstd`):
  > ```bash
  > venv/Scripts/python -c "import zstandard,pathlib; d=pathlib.Path('venv/Lib/site-packages/fpgen/data'); (d/'values.dat').write_bytes(zstandard.ZstdDecompressor().decompress((d/'values.dat.zst').read_bytes()))"
  > ```
- Copie `apply/config.example.yaml` → `apply/config.yaml` e preencha (o `config.yaml` real, sessões de login e relatórios ficam fora do git).

---

## 🛠️ Tecnologias Utilizadas

### **Frontend**
- **Framework**: Next.js 16 (App Router) + React 19 + TypeScript
- **Estilização**: Tailwind CSS + Lucide Icons + Framer Motion
- **Componentes**: Radix UI / Shadcn UI

### **Backend**
- **Framework**: FastAPI (Python 3.11+) + Uvicorn
- **Processamento de PDF**: PyMuPDF (`fitz`), pdfplumber, PyPDF
- **Persistência**: SQLite (arquivo local `backend/market.db`)
- **Modelos de IA**: OpenAI API (GPT-4o, GPT-4o-mini) / OmniRoute Fallback
- **Performance**: trabalho bloqueante (chamadas LLM, pipeline de mercado com pausas de 15s, extração de PDF) roda em thread pool — o servidor não trava durante uma análise; health, logs e configurações continuam respondendo mesmo com o provider lento em voo.

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
│   ├── app/                 # Rotas /<slug> (dashboard, analise-curriculo, analise-linkedin, inteligencia-mercado, candidaturas, config-ias, logs)
│   ├── components/          # Componentes reutilizáveis de UI
│   ├── hooks/               # Custom React Hooks
│   └── lib/                 # Utilitários de API e formatadores
├── extension/               # Extensão Manifest V3 para Google Chrome
├── apply/                   # Job Hunter — bots de candidatura (code versionado; config/sessões/dados fora do git)
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
# Criar e ativar o ambiente virtual (na RAIZ do projeto)
python -m venv venv

# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Linux/macOS:
# source venv/bin/activate

# Instalar dependências — escolha o escopo:
#  (a) só a API (enxuto, sem torch/Crawl4AI/bots — o suficiente p/ subir o servidor):
pip install -r backend/requirements-api.txt
#  (b) API + ambiente dos bots do Job Hunter (lock completo do venv raiz;
#  inclui torch/Crawl4AI/selenium/patchright/camoufox — é o que os .bat usam):
pip install -r backend/requirements.txt

# (Opcional) Configurar variáveis de ambiente — veja .env.example
copy .env.example .env   # Windows; Linux/macOS: cp .env.example .env

# Iniciar o servidor FastAPI (a partir da pasta backend)
cd backend
python main.py
```
> O backend estará rodando em `http://127.0.0.1:8000`.
> **Caminho oficial no Windows**: `start_backend.bat` (backend) + `npm run dev` na pasta `frontend` (frontend, em outra janela). Os `.bat` usam o Python do **venv da raiz** (`venv\Scripts\python`) — não o global; se `venv/` ainda não existir, crie-o na raiz com `python -m venv venv` e instale as dependências acima.
> **Exposição na rede**: por padrão o backend fica em `127.0.0.1:8000` (só a máquina local). Para expor na LAN (outros dispositivos acessarem), defina `TRIVOR_ALLOW_LAN=1` antes de subir o backend.
> **`backend/pyproject.toml`**: é um manifest solto que ninguém usa — a fonte de verdade das dependências são os arquivos `requirements*` acima. Nunca use `pip install -e backend/` (as dependências declaradas nele estão defasadas em relação ao lock).
> Chaves de IA: defina no `.env` (`OPENAI_API_KEY` / `TRIVOR_IAS`) ou pela aba de Configurações do app — sem chave, os endpoints de IA respondem com erro 400 claro.
> **Busca de vagas reais (JSearch)**: opcional. Defina `JSEARCH_API_KEY` no `.env` (ou re-digite suas chaves na aba *Configurações → Busca de Vagas*). Sem chave, a análise de mercado segue com a heurística local (sem dados fabricados).
> **Upgrade**: chaves JSearch antigas em texto puro foram removidas do banco por segurança — re-salve suas chaves na UI. O `.env` é carregado no boot via `load_dotenv()` (valores do ambiente já existentes têm prioridade).

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
>
> **Rotas** — cada ferramenta é uma página real com slug próprio (a sidebar navega por URL):
>
> | Rota | Página |
> |---|---|
> | `/` e `/dashboard` | Dashboard — visão geral e histórico |
> | `/analise-curriculo` | Análise de Currículo — diagnóstico ATS e compatibilidade |
> | `/analise-linkedin` | Análise de LinkedIn — diagnóstico do perfil |
> | `/inteligencia-mercado` | Inteligência de Mercado — vagas e tendências |
> | `/candidaturas` | Job Hunter — histórico, execução, IA, perfil e currículos |
> | `/config-ias` | Config. IAs — chaves de API dos provedores |
> | `/logs` | Logs — requisições e performance |

---

## 🐳 Execução via Docker

Se preferir rodar toda a aplicação via containers Docker:

```bash
docker-compose up --build -d
```

> - **Docker = backend + frontend, SEM o Job Hunter**: a imagem não inclui a pasta `apply/` (bots + credenciais), então os endpoints de candidatura respondem 404 e a aba **Candidaturas** fica indisponível no container. O Job Hunter roda apenas no ambiente local (venv com `backend/requirements.txt`).
> - **Porta do backend**: o frontend aponta para `http://localhost:8000` (`NEXT_PUBLIC_API_URL`) — a porta **8000 precisa estar visível/aberta pelo browser** (firewall da máquina).
> - **Dados**: o banco de mercado e os logs de requisições persistem em `./data/` (`market.db` entra no container via symlink `/app/backend/market.db` → `/app/data/market.db`). O `.gitignore` cobre `data/*` e `*.db` — os dados nunca vão para o git.

---

## 📄 Licença

Este projeto está licenciado sob a licença [MIT](LICENSE).

---
<p center align="center">Desenvolvido com 💙 para transformar a gestão de carreira e inteligência de recrutamento.</p>
