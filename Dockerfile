# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# API enxuta: sem torch/bots — a imagem só serve o backend + o frontend.
# O Job Hunter (apply/) não roda no container (pasta não copiada; a aba
# Candidaturas responde 404 — documentado no README).
COPY backend/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy backend code
COPY backend/ ./backend/

# market.db: o código (market_db.py) resolve DB_FILE como
# Path(__file__).parent/"market.db" (= /app/backend/market.db no container).
# O arquivo real vive em /app/data (mount de ./data) via symlink — um
# bind-mount de arquivo em clone limpo vira um diretório no container e o
# SQLite não abre. rm -f é um guard (o .dockerignore já exclui *.db do
# contexto; impede que um DB local entre acidentalmente na imagem).
RUN rm -f /app/backend/market.db && ln -s /app/data/market.db /app/backend/market.db

# Copy LLM prompt knowledge (endpoints de IA caem em fallback silencioso sem isso)
COPY knowledge/ ./knowledge/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run backend
CMD ["python", "backend/main.py"]
