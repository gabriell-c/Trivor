"""Camada de persistência SQLite da Inteligência de Mercado.

Schema (market_raw_jobs / market_jobs / market_reports / jsearch_keys),
migrações idempotentes e registro de uso do pool de chaves JSearch —
as chaves persistem SOMENTE como hash/prefixo, nunca em texto puro.
"""

import hashlib
import sqlite3
from pathlib import Path

from market_log import logger

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_raw_jobs (
    id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    description TEXT,
    location TEXT,
    modality TEXT,
    source TEXT,
    source_url TEXT,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS market_jobs (
    id TEXT PRIMARY KEY,
    raw_job_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    modality TEXT,
    source TEXT,
    source_url TEXT,
    is_relevant INTEGER,
    rejection_reason TEXT,
    requirements TEXT,
    nice_to_have TEXT,
    role_level TEXT,
    exp_years_min REAL,
    exp_years_max REAL,
    soft_skills TEXT,
    certifications TEXT,
    salary_min REAL,
    salary_max REAL,
    currency TEXT,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS market_reports (
    id TEXT PRIMARY KEY,
    job_title TEXT,
    target_stack TEXT,
    seniority TEXT,
    location TEXT,
    time_window TEXT,
    total_jobs INTEGER,
    relevant_jobs INTEGER,
    confidence_score TEXT,
    report_data TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS jsearch_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT UNIQUE,
    key_prefix TEXT,
    description TEXT,
    rate_limit_total INTEGER,
    rate_limit_remaining INTEGER,
    status TEXT,
    last_error TEXT,
    last_tested TEXT,
    created_at TEXT
);
"""


def _connect_market_db(db_file) -> sqlite3.Connection:
    """Conexão padrão do serviço de mercado: WAL + busy_timeout p/ uso concorrente.
    WAL é persistido no arquivo (aplicar uma vez basta p/ todo o DB);
    busy_timeout é por conexão — prazo de 30s p/ escrita evita crash por lock
    com análises paralelas + endpoints jsearch escrevendo no mesmo arquivo."""
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_market_db(db_file: Path) -> None:
    """Cria as tabelas do DB de inteligência de mercado."""
    conn = _connect_market_db(db_file)
    conn.executescript(DB_SCHEMA)
    # Migração: adicionar colunas que podem não existir
    for table, col in [
        ("market_raw_jobs", "source_url"),
        ("market_jobs", "source_url"),
        ("market_jobs", "rejection_reason"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # coluna já existe
        except sqlite3.Error as exc:
            logger.warning(f"[MARKET] migração {table}.{col} falhou: {exc}")
    _migrate_jsearch_keys_remove_plaintext(conn)
    _ensure_jsearch_keys_hash_unique(conn)
    conn.commit()
    conn.close()


def _migrate_jsearch_keys_remove_plaintext(conn: sqlite3.Connection) -> None:
    """Migração idempotente: remove a coluna api_key (texto puro) da jsearch_keys.
    DBs novos nascem sem a coluna; DBs legados têm a coluna descartada e o
    resto (hash/prefixo/descrição) preservado. A chave em si nunca mais é
    persistida — o pool de busca usa chaves re-digitadas na UI + JSEARCH_API_KEY
    do ambiente. Se a migração falhar, a coluna fica órfã mas parada:
    o código atual não lê nem escreve mais api_key."""
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(jsearch_keys)")]
    except sqlite3.Error as exc:
        logger.warning(f"[MIGRATION] jsearch_keys inacessível p/ migração: {exc}")
        return
    if "api_key" not in cols:
        return
    try:
        conn.execute("ALTER TABLE jsearch_keys DROP COLUMN api_key")
        logger.warning(
            "[MIGRATION] Chaves JSearch locais (texto puro) foram removidas do banco "
            "por segurança. Re-salve suas chaves na UI; a busca também usa "
            "JSEARCH_API_KEY (ambiente)."
        )
    except sqlite3.Error as exc:
        logger.warning(f"[MIGRATION] DROP COLUMN api_key em jsearch_keys falhou: {exc}")


def _ensure_jsearch_keys_hash_unique(conn: sqlite3.Connection) -> None:
    """Garante constraint UNIQUE em jsearch_keys.key_hash (DBs legados a criaram
    sem UNIQUE). Necessário p/ o upsert dos endpoints (ON CONFLICT(key_hash)).
    Idempotente: se já houver índice/constraint único cobrindo a coluna, sai."""
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jsearch_keys)")]
    except sqlite3.Error as exc:
        logger.warning(f"[MIGRATION] table_info(jsearch_keys) inacessível: {exc}")
        return
    if "key_hash" not in cols:
        return
    for _seq, name, unique, _origin, _partial in conn.execute("PRAGMA index_list(jsearch_keys)"):
        if not unique or name is None:
            continue
        # PRAGMA index_info: (seqno, cid, nome_da_coluna)
        covered = {row[2] for row in conn.execute(f'PRAGMA index_info("{name}")')}
        if "key_hash" in covered:
            return
    # DBs antigos acumulavam várias linhas p/ a MESMA chave (mesmo hash) —
    # consolida mantendo a mais recente; senão o índice único não se cria.
    try:
        cur = conn.execute('''
            DELETE FROM jsearch_keys
            WHERE key_hash IS NOT NULL AND rowid NOT IN (
                SELECT a.rowid FROM jsearch_keys a
                WHERE a.key_hash IS NOT NULL AND a.rowid = (
                    SELECT b.rowid FROM jsearch_keys b
                    WHERE b.key_hash = a.key_hash
                    ORDER BY b.last_tested DESC, b.rowid DESC
                    LIMIT 1
                )
            )
        ''')
        if cur.rowcount:
            logger.info(f"[MIGRATION] {cur.rowcount} registro(s) duplicado(s) de jsearch_keys consolidado(s) por key_hash")
    except sqlite3.Error as exc:
        logger.warning(f"[MIGRATION] consolidação de jsearch_keys por key_hash falhou: {exc}")
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jsearch_keys_hash ON jsearch_keys (key_hash)")
        logger.info("[MIGRATION] jsearch_keys.key_hash passou a ser único (índice criado)")
    except sqlite3.Error as exc:
        # Linhas com key_hash duplicado impedem o índice — loga; upsert segue sem ele
        logger.warning(f"[MIGRATION] índice único em jsearch_keys.key_hash não criado (linhas duplicadas?): {exc}")


def _mask_jsearch_key(key: str) -> str:
    """Log: apenas o sufixo da chave (últimos 4 chars) — mesmo padrão de _mask_key_preview do main.
    O prefixo não vai para os logs."""
    if not key or len(key) <= 4:
        return "***"
    return f"…{key[-4:]}"


def _update_jsearch_usage(db_file: Path, key: str, remaining: int):
    """Atualiza o rate limit remaining de uma chave JSearch no DB.
    Persiste SOMENTE hash/prefixo + uso — nunca o texto puro da chave.
    Chamado depois do fetch: falha aqui não pode derrubar a análise, então loga e segue."""
    try:
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        # Prefixo é apenas um preview mascarado — para chaves curtas, só o sufixo
        key_prefix = (key[:8] + "…" + key[-4:]) if len(key) > 12 else _mask_jsearch_key(key)
        conn = _connect_market_db(db_file)
        try:
            conn.execute('''
                INSERT INTO jsearch_keys (key_hash, key_prefix, last_tested, rate_limit_total, rate_limit_remaining, status, last_error)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, 'ok', '')
                ON CONFLICT(key_hash) DO UPDATE SET
                    key_prefix = excluded.key_prefix,
                    last_tested = CURRENT_TIMESTAMP,
                    rate_limit_remaining = excluded.rate_limit_remaining
            ''', (key_hash, key_prefix, 200, remaining))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[_update_jsearch_usage] não foi possível atualizar uso da chave: {e}")


# Retenção: market_reports guarda no máximo as N análises mais recentes.
# Cada linha tem ~300KB de JSON (report_data) e a tabela era sem limite —
# 55 relatórios = 8MB; o DELETE libera páginas que o SQLite reusa.
_REPORTS_KEEP_LAST = 30


def _apply_reports_retention(cursor, keep: int | None = None) -> None:
    """Mantém apenas as _REPORTS_KEEP_LAST análises mais recentes em market_reports.
    A ordem é de inserção (rowid): relatórios mais novos entram por rowid crescente.
    `keep` permite o caller determinar o limite (a facade do market_service injeta o
    próprio, porque os testes monkeypatch o atributo no módulo service)."""
    keep = _REPORTS_KEEP_LAST if keep is None else keep
    cursor.execute(
        "DELETE FROM market_reports WHERE rowid NOT IN "
        "(SELECT rowid FROM market_reports ORDER BY rowid DESC LIMIT ?)",
        (keep,),
    )
