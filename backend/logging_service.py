"""
Request Logger – registra todas as requisições de IA com métricas detalhadas.
"""

import sqlite3
import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List


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
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_logs_timestamp ON api_logs(timestamp);
"""


def init_logs_db(db_path: Path = LOGS_DB):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def log_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    model: str,
    api_key_preview: str,
    request_body: Optional[Dict] = None,
    response_summary: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    log_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = sqlite3.connect(LOGS_DB)
    conn.execute(
        """INSERT INTO api_logs
           (id, timestamp, endpoint, method, status_code, duration_ms,
            model, api_key_preview, request_body, response_summary, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            log_id, now, endpoint, method, status_code, duration_ms,
            model, api_key_preview,
            json.dumps(request_body) if request_body else None,
            response_summary,
            error,
        ),
    )
    conn.commit()
    conn.close()
    return log_id


def get_logs(
    limit: int = 100,
    offset: int = 0,
    endpoint: Optional[str] = None,
    error_only: bool = False,
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(LOGS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where = "WHERE 1=1"
    params: list = []
    if endpoint:
        where += " AND endpoint = ?"
        params.append(endpoint)
    if error_only:
        where += " AND error IS NOT NULL"

    c.execute(
        f"""SELECT * FROM api_logs {where}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_logs_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(LOGS_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_logs")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM api_logs WHERE error IS NOT NULL")
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

    conn.close()
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
    conn = sqlite3.connect(LOGS_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_logs")
    count = c.fetchone()[0]
    c.execute("DELETE FROM api_logs")
    conn.commit()
    conn.close()
    return count
