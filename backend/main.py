"""Trivor — aplicação FastAPI (setup, middlewares, health e registro dos
routers por domínio).

As rotas de negócio moram em módulos de domínio (*_routes.py); os helpers
compartilhados em llm_core (infra LLM), cv_helpers (CV/PDF), rate_limit
(limiter slowapi) e app_log (logger padrão da aplicação). Este arquivo só
monta o app, aplica o middleware de logs, o health check e expõe a facade
de nomes históricos para os testes.
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.concurrency import run_in_threadpool

# Carrega .env (raiz do projeto) antes de qualquer os.getenv de chave;
# override=False: variáveis já definidas no sistema prevalecem sobre o .env
load_dotenv(override=False)

from app_log import get_app_logger

logger = get_app_logger(__name__)

# Adiciona o diretório backend ao Python path para importar os módulos de domínio
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import market_db
from apply_routes import router as apply_router
from cv_routes import router as cv_router
from ia_routes import router as ia_router
from jsearch_routes import router as jsearch_router
from linkedin_routes import router as linkedin_router
from llm_core import KNOWLEDGE_DIR
from logging_service import LOGS_DB, init_logs_db, log_request
from logs_routes import router as logs_router
from market_routes import router as market_router
from market_service import init_market_db
from rate_limit import limiter

DB_FILE = market_db.DB_FILE

app = FastAPI(
    title="Trivor - Motor de Análise de Currículos",
    description="API para análise de currículos, market intelligence e diagnóstico profissional",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    # CORS configurável via env (CLAUDE.md §13 — nada hardcoded); fallback são as origens locais de dev
    allow_origins=[o.strip() for o in os.getenv('CORS_ALLOW_ORIGINS', '').split(',') if o.strip()]
    or ['http://localhost:3000', 'http://127.0.0.1:3000'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Muitas requisições. Aguarde e tente novamente.",
                "details": {
                    "limit": str(exc.limit) if hasattr(exc, 'limit') else "unknown"
                }
            }
        },
        headers={"Retry-After": "60"}
    )

# Inicializa DB de logs
init_logs_db()
# Garante as tabelas do market DB (inclui jsearch_keys) desde o start
init_market_db(DB_FILE)

# ---------------------------------------------------------------------------
# Middleware de log de requests
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    # Skip logging for endpoints that create their own detailed logs
    if request.url.path == "/api/cv/analyze":
        return response
    try:
        # SQLite é síncrono: roda em thread pool para não bloquear o event
        # loop no INSERT de todo request.
        await run_in_threadpool(
            lambda: log_request(
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
                model="",
                api_key_preview="",
            )
        )
    except Exception:
        # Falha no log não derruba o request — mas nunca engolida em silêncio:
        # deixa rastro com stack.
        logger.exception("[LOGS] Falha ao registrar request de %s", request.url.path)
    return response


# ---------------------------------------------------------------------------
# Routers por domínio
# ---------------------------------------------------------------------------

app.include_router(cv_router)
app.include_router(ia_router)
app.include_router(market_router)
app.include_router(jsearch_router)
app.include_router(apply_router)
app.include_router(logs_router)
app.include_router(linkedin_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check robusto com verificação de dependências."""
    import sqlite3
    from datetime import datetime

    checks = {}
    overall_status = "healthy"

    # Verificar banco de dados — SQLite síncrono roda em thread pool
    def _check_logs_db() -> dict:
        conn = sqlite3.connect(LOGS_DB)
        try:
            return {"status": "ok", "logs_count": conn.execute("SELECT COUNT(*) FROM api_logs").fetchone()[0]}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()

    try:
        result = await run_in_threadpool(_check_logs_db)
        checks["database"] = result
        if result["status"] != "ok":
            overall_status = "degraded"
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall_status = "degraded"

    # Verificar providers IA
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        checks["providers"] = {
            "status": "ok" if providers else "warning",
            "count": len(providers)
        }
    except Exception as e:
        checks["providers"] = {"status": "error", "message": str(e)}
        overall_status = "degraded"

    # Verificar diretório de conhecimento
    try:
        knowledge_exists = KNOWLEDGE_DIR.exists() and (KNOWLEDGE_DIR / 'system_prompt.md').exists()
        checks["knowledge"] = {"status": "ok" if knowledge_exists else "warning"}
    except Exception as e:
        checks["knowledge"] = {"status": "error", "message": str(e)}

    status_code = 200 if overall_status == "healthy" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "checks": checks
        }
    )


# ---------------------------------------------------------------------------
# Facade de compatibilidade — superfície histórica main.<nome> que os testes
# importam (from main import X) e patches (patch("main.OpenAI")). Os nomes
# moram nos módulos de origem; main apenas os reexporta.
# ---------------------------------------------------------------------------

from cv_helpers import NICE_TO_HAVE_WEIGHT, _compute_job_fit, _detect_abbreviations, calc_fit_score  # noqa: F401
from cv_routes import (  # noqa: F401
    _cover_letter_validate,
    _diff_cv_deterministic,
    _diff_cv_validate,
    _recruiter_sim_validate,
    _semantic_fit_evidence_valid,
    _semantic_fit_validate,
)
from llm_core import _get_provider_for_tool  # noqa: F401
from openai import OpenAI  # noqa: F401

if __name__ == "__main__":
    import signal

    import uvicorn

    def graceful_shutdown(signum, frame):
        logger.info("Recebido sinal de encerramento. Finalizando graceful...")
        logger.info("Logs salvos com sucesso.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    uvicorn.run(app, host="0.0.0.0", port=8000)
