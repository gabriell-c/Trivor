from pathlib import Path

BASE_DIR = Path(__file__).parent

# Paths
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
TESTS_DIR = BASE_DIR / "tests"

# Environment
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE = BASE_DIR / ".env.example"

# Database
LOGS_DB = BACKEND_DIR.parent / "data" / "requests.log.db"
MARKET_DB = BACKEND_DIR.parent / "data" / "market.db"

# API
API_HOST = "0.0.0.0"
API_PORT = 8000
FRONTEND_URL = "http://localhost:3000"

# Rate Limiting
RATE_LIMIT_CV = "30/minute"
RATE_LIMIT_IA = "20/minute"
RATE_LIMIT_MARKET = "10/minute"
RATE_LIMIT_LINKEDIN = "20/minute"

# Log retention (days)
LOG_RETENTION_DAYS = 90

# Export formats
EXPORT_FORMATS = ["md", "docx", "pdf"]
