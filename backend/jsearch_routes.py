"""Rotas de gestão das chaves JSearch: /api/jsearch/keys, /test, /save-key,
/update-key, /delete-key. Movidas do main.py — corpos inalterados.

DB_FILE agora mora em market_db; as helpers acessam por market_db.DB_FILE
para os testes poderem apontar o DB via monkeypatch.
"""

import hashlib
import sqlite3

import market_db
from app_log import get_app_logger
from fastapi import APIRouter, Form
from llm_core import _mask_key_preview
from starlette.concurrency import run_in_threadpool

logger = get_app_logger(__name__)
router = APIRouter()


def _list_jsearch_key_rows() -> list:
    """Leitura síncrona dos registros de chaves JSearch (SQLite) —
    chamar via run_in_threadpool."""
    conn = sqlite3.connect(market_db.DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(r)
            for r in conn.execute(
                'SELECT id, key_hash, key_prefix, description, rate_limit_total, rate_limit_remaining, '
                'status, last_error, last_tested, created_at FROM jsearch_keys ORDER BY rowid'
            ).fetchall()
        ]
    finally:
        conn.close()


@router.get('/api/jsearch/keys')
async def api_get_jsearch_keys():
    """Retorna os registros de chaves JSearch (status e uso).
    Nunca retorna a chave em si — apenas preview/descrição (o texto puro não
    é mais persistido; a busca usa as chaves informadas no form + JSEARCH_API_KEY do ambiente)."""
    rows = await run_in_threadpool(_list_jsearch_key_rows)
    keys = []
    for key_data in rows:
        # Calcula usado com base no remaining
        used = max(0, key_data['rate_limit_total'] - key_data['rate_limit_remaining']) if key_data['rate_limit_remaining'] is not None else None
        key_data['used'] = used
        keys.append(key_data)
    return {"keys": keys}

@router.post('/api/jsearch/test')
async def api_test_jsearch_key(
    api_key: str = Form(...),
):
    """Testa uma chave JSearch e retorna status."""
    import json
    import urllib.request
    try:
        import urllib.parse
        query = urllib.parse.quote_plus("test")
        req = urllib.request.Request(
            f'https://api.openwebninja.com/jsearch/search-v2?query={query}&country=br&language=pt&num_pages=1',
            headers={
                'X-API-Key': api_key,
                'Accept': 'application/json'
            },
            method='GET'
        )
        http_resp = await run_in_threadpool(urllib.request.urlopen, req, timeout=10)
        with http_resp as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("data", {}).get("jobs", [])
            return {
                "valid": True,
                "data": {
                    "rate_limit": resp.headers.get("x-ratelimit-limit"),
                    "rate_limit_remaining": resp.headers.get("x-ratelimit-remaining"),
                    "total_results": len(jobs)
                }
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}

def _save_jsearch_key_record(key_hash: str, key_prefix: str, description: str, created_at: str) -> dict:
    """Upsert síncrono do registro de chave JSearch (SQLite) —
    chamar via run_in_threadpool. Retorna {"success": ..., "id"|"error": ...}."""
    conn = sqlite3.connect(market_db.DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO jsearch_keys (key_hash, key_prefix, description, created_at, status) "
            "VALUES (?, ?, ?, ?, 'ok') "
            "ON CONFLICT(key_hash) DO UPDATE SET "
            "key_prefix = excluded.key_prefix, description = excluded.description",
            (key_hash, key_prefix, description, created_at)
        )
        conn.commit()
        row = cursor.execute("SELECT id FROM jsearch_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        return {"success": True, "id": row[0] if row else None}
    except sqlite3.Error as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


@router.post('/api/jsearch/save-key')
async def api_save_jsearch_key(
    api_key: str = Form(...),
    description: str = Form(""),
):
    """Salva o REGISTRO de uma chave JSearch — apenas hash/prefixo/descrição.
    O texto puro da chave NÃO é persistido (decisão de segurança): a busca usa
    as chaves informadas no form de análise + JSEARCH_API_KEY do ambiente.
    Upsert por key_hash: re-salvar a mesma chave apenas atualiza o preview/descrição."""
    from datetime import datetime
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    key_prefix = (api_key[:8] + "…" + api_key[-4:]) if len(api_key) > 12 else _mask_key_preview(api_key)
    try:
        result = await run_in_threadpool(
            _save_jsearch_key_record, key_hash, key_prefix, description, datetime.now().isoformat()
        )
    except sqlite3.Error as e:
        logger.error(f"[JSEARCH] Falha ao salvar chave: {e}")
        return {"success": False, "error": str(e)}
    if not result["success"]:
        logger.error(f"[JSEARCH] Falha ao salvar chave: {result['error']}")
    return result


def _update_jsearch_key_description(key_id: int, description: str) -> bool:
    """Atualiza descrição de um registro (SQLite) — chamar via run_in_threadpool."""
    conn = sqlite3.connect(market_db.DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE jsearch_keys SET description = ? WHERE id = ?",
            (description, key_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


@router.put('/api/jsearch/update-key')
async def api_update_jsearch_key(
    key_id: int = Form(...),
    api_key: str = Form(""),
    description: str = Form(""),
):
    """Atualiza a descrição de um registro de chave JSearch.
    O parâmetro api_key permanece no contrato por compatibilidade com a UI,
    mas é IGNORADO: o texto puro da chave não é mais persistido — para trocar
    a chave em si, use save-key com a nova chave (upsert por hash)."""
    try:
        ok = await run_in_threadpool(_update_jsearch_key_description, key_id, description)
        return {"success": ok}
    except sqlite3.Error as e:
        logger.error(f"[JSEARCH] Falha ao atualizar chave: {e}")
        return {"success": False, "error": str(e)}

def _delete_jsearch_key(key_id: int) -> int:
    """Remove um registro de chave (SQLite) — chamar via run_in_threadpool.
    Retorna rowcount."""
    conn = sqlite3.connect(market_db.DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM jsearch_keys WHERE id = ?", (key_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


@router.delete('/api/jsearch/delete-key')
async def api_delete_jsearch_key(
    key_id: int = Form(...)
):
    """Remove uma chave JSearch do DB."""
    rowcount = await run_in_threadpool(_delete_jsearch_key, key_id)
    return {"success": rowcount > 0}
