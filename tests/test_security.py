"""
Testes de segurança local — in-process (TestClient), sem servidor.
Cobrem as superfícies que recebem input do usuário:
- SQL injection nos parâmetros /api/logs e /api/jsearch/*
- Header injection / path traversal em /api/export
- Command injection via /api/apply (whitelist de bots)
Executar: pytest tests/test_security.py -v
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Adiciona backend ao path para importar app diretamente
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from apply_runner import ApplyRunError, bot_log, start_bot, stop_bot
from main import app


@pytest.fixture
def client():
    """Retorna TestClient para o app FastAPI."""
    return TestClient(app)


# ============================================================================
# SQL injection — parâmetros de usuário em queries
# ============================================================================

class TestSqlInjection:
    """Payloads SQL em parâmetros devem ser tratados como valor literal
    (queries parametrizadas com ?), nunca interpolados."""

    def test_logs_endpoint_drop_table_payload(self, client):
        r = client.get(
            "/api/logs",
            params={"endpoint": "api_logs' WHERE 1=1; DROP TABLE api_logs; --", "limit": 5},
        )
        assert r.status_code == 200
        # Payload não é endpoint real → zero logs (valor literal)
        assert r.json()["logs"] == []
        # Tabela continua viva
        stats = client.get("/api/logs/stats").json()
        assert "total" in stats

    def test_logs_endpoint_or_injection(self, client):
        r = client.get("/api/logs", params={"endpoint": "x' OR '1'='1"})
        assert r.status_code == 200
        assert r.json()["logs"] == []

    def test_logs_limit_must_be_int(self, client):
        r = client.get("/api/logs", params={"limit": "5; DROP TABLE api_logs"})
        assert r.status_code == 422

    def test_jsearch_save_update_delete_with_payloads(self, client):
        api_key = "trivor-sec-test-key-0001"
        payload_desc = "x'); DROP TABLE jsearch_keys; --"
        r = client.post(
            "/api/jsearch/save-key",
            data={"api_key": api_key, "description": payload_desc},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        key_id = body["id"]
        assert key_id is not None

        # Payload armazenado como texto literal (tabela intacta)
        keys = client.get("/api/jsearch/keys").json()["keys"]
        row = next((k for k in keys if k.get("id") == key_id), None)
        assert row is not None
        assert row["description"] == payload_desc

        r2 = client.put(
            "/api/jsearch/update-key",
            data={"key_id": key_id, "api_key": "", "description": "y' OR '1'='1"},
        )
        assert r2.status_code == 200
        assert r2.json()["success"] is True

        # Só a linha do id foi afetada — payload segue literal
        keys = client.get("/api/jsearch/keys").json()["keys"]
        row = next((k for k in keys if k.get("id") == key_id), None)
        assert row["description"] == "y' OR '1'='1"

        r3 = client.request(
            "DELETE",
            "/api/jsearch/delete-key",
            content=f"key_id={key_id}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r3.status_code == 200
        assert r3.json()["success"] is True

        keys = client.get("/api/jsearch/keys").json()["keys"]
        assert all(k.get("id") != key_id for k in keys)


# ============================================================================
# /api/export — filename do usuário não pode vazar pro header
# ============================================================================

class TestExportSafety:
    """Content-Disposition usa apenas nome com uuid gerado no servidor:
    path traversal e header injection via `filename` são impossíveis."""

    def test_filename_traversal_not_in_header(self, client):
        r = client.post(
            "/api/export",
            data={"format": "json", "filename": "../../../evil.json", "data_json": "{}"},
        )
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "../../../" not in cd
        assert re.search(r'attachment; filename="diagnostico_[0-9a-f]{6}\.json"', cd)

    def test_filename_newline_not_in_header(self, client):
        r = client.post(
            "/api/export",
            data={"format": "json", "filename": "a\nX-Injected: 1", "data_json": "{}"},
        )
        cd = r.headers.get("content-disposition", "")
        assert "X-Injected" not in cd
        assert re.search(r'diagnostico_[0-9a-f]{6}\.json"', cd)

    def test_invalid_data_json_rejected(self, client):
        r = client.post(
            "/api/export",
            data={"format": "json", "filename": "x", "data_json": "{inválido"},
        )
        assert r.status_code in (400, 500)


# ============================================================================
# /api/apply — whitelist de bots impede command injection
# ============================================================================

class TestApplyCommandInjection:
    """A API só aceita nomes de bot da lista APPLY_BOTS — a execução é
    sempre [sys.executable, script_fixo], sem shell=True e sem input
    do usuário no comando."""

    def test_start_bot_rejects_unknown(self):
        with pytest.raises(ApplyRunError):
            start_bot("evil && rm -rf /")

    def test_stop_bot_rejects_unknown(self):
        with pytest.raises(ApplyRunError):
            stop_bot("../../windows")

    def test_bot_log_rejects_unknown(self):
        with pytest.raises(ApplyRunError):
            bot_log("payload")

    def test_http_log_route_rejects_unknown_bot(self, client):
        r = client.get("/api/apply/log/payload")
        assert r.status_code == 404


# ============================================================================
# /api/jsearch/test — SSRF: URL de destino é fixa (characterization)
# ============================================================================

class TestJSearchSsrf:
    """# characterization — documenta o comportamento atual: o endpoint de
    teste só chama api.openwebninja.com com query fixa 'test' (quote_plus),
    então não há SSRF nem URL injection pelo usuário."""

    def test_test_key_url_is_hardcoded(self):
        src = (BACKEND_DIR / "jsearch_routes.py").read_text(encoding="utf-8")
        assert "api.openwebninja.com/jsearch/search-v2?query={query}" in src
        assert 'urllib.parse.quote_plus("test")' in src
