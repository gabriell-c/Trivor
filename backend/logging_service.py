"""
Request Logger – registra todas as requisições de IA com métricas detalhadas.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).parent.parent / "data"
LOGS_DB = LOGS_DIR / "requests.log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    endpoint TEXT,
    method TEXT,
    status_code INTEGER,
    duration_ms REAL,
    model TEXT,
    api_key_preview TEXT,
    request_body TEXT,
    response_summary TEXT,
    error TEXT,
    extracted_text TEXT,
    llm_prompt TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_logs_timestamp ON api_logs(timestamp);
"""

# Conexões por thread (o event loop roda tudo em thread pool): cada thread
# tem SUA conexão longa com WAL + synchronous=NORMAL. O custo medido de
# connect+INSERT+COMMIT era ~124ms por request (banco num disco sob
# sync do OneDrive); reutilizando a conexão a escrita cai pra milissegundos.
_local = threading.local()


def _conn(db_path: Path = LOGS_DB) -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is not None:
        # 'closed' não é atributo confiável do sqlite3 — sonda a conexão
        try:
            c.execute("SELECT 1")
            return c
        except sqlite3.Error:
            pass
    c = sqlite3.connect(str(db_path), check_same_thread=False, timeout=2.0)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    _local.conn = c
    return c


def init_logs_db(db_path: Path = LOGS_DB):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _conn(db_path)
    conn.commit()
    # Prune automático (mesma política de 90 dias da rota /api/logs/cleanup):
    # a tabela não pode crescer para sempre entre restarts do backend
    cleanup_logs(days_old=90)


def log_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    model: str,
    api_key_preview: str,
    request_body: dict | None = None,
    response_summary: str | None = None,
    error: str | None = None,
    extracted_text: str | None = None,
    llm_prompt: str | None = None,
) -> str:
    log_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = _conn()
    conn.execute(
        """INSERT INTO api_logs
           (id, timestamp, endpoint, method, status_code, duration_ms,
            model, api_key_preview, request_body, response_summary, error,
            extracted_text, llm_prompt)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            log_id, now, endpoint, method, status_code, duration_ms,
            model, api_key_preview,
            json.dumps(request_body) if request_body else None,
            response_summary,
            error,
            extracted_text,
            llm_prompt,
        ),
    )
    conn.commit()
    return log_id


def get_logs(
    limit: int = 100,
    offset: int = 0,
    endpoint: str | None = None,
    error_only: bool = False,
) -> list[dict[str, Any]]:
    conn = _conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where = "WHERE 1=1"
    params: list = []
    if endpoint:
        where += " AND endpoint = ?"
        params.append(endpoint)
    if error_only:
        where += " AND status_code >= 400"

    c.execute(
        f"""SELECT id, timestamp, endpoint, method, status_code, duration_ms,
                   model, api_key_preview, request_body, response_summary,
                   error, extracted_text, llm_prompt
            FROM api_logs {where}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    rows = c.fetchall()
    return [dict(r) for r in rows]


def get_logs_stats() -> dict[str, Any]:
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_logs")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM api_logs WHERE status_code >= 400")
    errors = c.fetchone()[0]

    c.execute("SELECT AVG(duration_ms) FROM api_logs")
    avg_ms = c.fetchone()[0] or 0

    c.execute("SELECT model, COUNT(*) FROM api_logs GROUP BY model ORDER BY COUNT(*) DESC")
    model_counts = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT endpoint, COUNT(*) FROM api_logs GROUP BY endpoint ORDER BY COUNT(*) DESC")
    endpoint_counts = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT MIN(timestamp) FROM api_logs")
    first = c.fetchone()[0]
    c.execute("SELECT MAX(timestamp) FROM api_logs")
    last = c.fetchone()[0]

    return {
        "total": total,
        "errors": errors,
        "avg_duration_ms": round(avg_ms, 1),
        "model_counts": model_counts,
        "endpoint_counts": endpoint_counts,
        "first_request": first,
        "last_request": last,
    }


def clear_logs() -> int:
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_logs")
    count = c.fetchone()[0]
    c.execute("DELETE FROM api_logs")
    conn.commit()
    return count


def cleanup_logs(days_old: int = 90) -> int:
    """Remove logs com mais de N dias. Retorna quantidade removida."""
    conn = _conn()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM api_logs WHERE timestamp < ? OR timestamp IS NULL",
        ((datetime.now() - timedelta(days=days_old)).isoformat(),)
    )
    count = c.fetchone()[0]
    if count > 0:
        c.execute(
            "DELETE FROM api_logs WHERE timestamp < ? OR timestamp IS NULL",
            ((datetime.now() - timedelta(days=days_old)).isoformat(),)
        )
        conn.commit()
    return count
