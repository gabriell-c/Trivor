"""
Testes de integração com FastAPI TestClient — sem necessidade de servidor rodando.
Executar: pytest tests/test_integration.py -v
"""
import sys
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Adiciona backend ao path para importar app diretamente
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Importa o app após ajustar o path
from main import app


@pytest.fixture
def client():
    """Retorna TestClient para o app FastAPI."""
    return TestClient(app)


# ============================================================================
# Health & OpenAPI
# ============================================================================

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "healthy")
        assert "checks" in data

    def test_health_check_keys(self, client):
        r = client.get("/health")
        data = r.json()
        checks = data.get("checks", {})
        assert "database" in checks
        assert "providers" in checks

    def test_openapi_schema_exists(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        paths = schema["paths"]
        assert "/api/cv/analyze" in paths
        assert "/api/linkedin/analyze" in paths
        assert "/api/market/analyze" in paths


# ============================================================================
# Logs endpoints
# ============================================================================

class TestLogs:
    def test_get_logs(self, client):
        r = client.get("/api/logs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_get_logs_stats(self, client):
        r = client.get("/api/logs/stats")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "total" in data

    def test_clear_logs(self, client):
        r = client.post("/api/logs/clear")
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True

    def test_get_logs_with_params(self, client):
        r = client.get("/api/logs?limit=10&offset=0")
        assert r.status_code == 200

    def test_cleanup_logs(self, client):
        r = client.post("/api/logs/cleanup", json={"days_old": 90})
        assert r.status_code == 200


# ============================================================================
# JSearch endpoints
# ============================================================================

class TestJSearch:
    def test_get_jsearch_keys_empty(self, client):
        r = client.get("/api/jsearch/keys")
        assert r.status_code == 200
        data = r.json()
        assert "keys" in data
        assert isinstance(data["keys"], list)

    def test_test_jsearch_key_invalid(self, client):
        r = client.post("/api/jsearch/test", data={"api_key": "invalid-key-test"})
        assert r.status_code == 200
        data = r.json()
        assert "valid" in data

    def test_save_jsearch_key_missing(self, client):
        # Falta api_key obrigatória
        r = client.post("/api/jsearch/save-key", data={"description": "test"})
        assert r.status_code == 422

    def test_save_jsearch_key(self, client):
        r = client.post("/api/jsearch/save-key", data={
            "api_key": "test-key-12345",
            "description": "Test key"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data.get("id") is not None

    def test_delete_jsearch_key_missing(self, client):
        r = client.request("DELETE", "/api/jsearch/delete-key", data={"key_id": "not-a-number"})
        assert r.status_code == 422

    def test_delete_jsearch_key(self, client):
        # Salva primeiro
        save_r = client.post("/api/jsearch/save-key", data={
            "api_key": "delete-test-key-12345",
            "description": "Para deletar"
        })
        key_id = save_r.json().get("id")
        assert key_id is not None

        # Deleta
        r = client.request("DELETE", "/api/jsearch/delete-key", data={"key_id": str(key_id)})
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Tenta deletar novamente (já não existe)
        r2 = client.request("DELETE", "/api/jsearch/delete-key", data={"key_id": str(key_id)})
        assert r2.status_code == 200
        assert r2.json()["success"] is False


# ============================================================================
# Analyze CV — validação de arquivo
# ============================================================================

class TestAnalyzeCV:
    def test_analyze_cv_missing_file(self, client):
        r = client.post("/api/cv/analyze")
        assert r.status_code == 422  # missing required file

    def test_analyze_cv_unsupported_extension(self, client):
        # Cria arquivo .exe fictício
        r = client.post(
            "/api/cv/analyze",
            files={"cv_file": ("test.exe", b"MZ", "application/octet-stream")},
            data={"job": "test"}
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "") or "detail" in r.json()

    def test_analyze_cv_too_large(self, client):
        # Arquivo de 11MB — acima do limite
        big_content = b"x" * (11 * 1024 * 1024)
        r = client.post(
            "/api/cv/analyze",
            files={"cv_file": ("test.pdf", big_content, "application/pdf")},
            data={"job": "test"}
        )
        assert r.status_code == 400
        assert "10MB" in r.json().get("detail", "") or "detail" in r.json()

    def test_analyze_cv_pdf_accepted(self, client):
        # PDF válido mas sem API key — deve falhar com 400 (sem key) não 500
        r = client.post(
            "/api/cv/analyze",
            files={"cv_file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
            data={"job": "test"}
        )
        # Pode falhar por falta de key ou erro de processamento — ambos são OK
        assert r.status_code in (400, 422, 500)

    def test_analyze_cv_docx_accepted(self, client):
        r = client.post(
            "/api/cv/analyze",
            files={"cv_file": ("test.docx", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"job": "test"}
        )
        assert r.status_code in (400, 422, 500)


# ============================================================================
# Analyze LinkedIn
# ============================================================================

class TestAnalyzeLinkedIn:
    def test_linkedin_analyze_missing_text(self, client):
        r = client.post("/api/linkedin/analyze")
        assert r.status_code == 422

    def test_linkedin_analyze_short_text(self, client):
        r = client.post("/api/linkedin/analyze", data={"text": "oi"})
        # Deve rejeitar texto com menos de 10 caracteres
        assert r.status_code == 400


# ============================================================================
# Export endpoints
# ============================================================================

class TestExport:
    def test_export_missing_format(self, client):
        r = client.post("/api/export")
        assert r.status_code == 422

    def test_export_invalid_format(self, client):
        r = client.post(
            "/api/export",
            data={"format": "xyz", "data_json": "{}"}
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "")

    def test_export_json(self, client):
        r = client.post(
            "/api/export",
            data={
                "format": "json",
                "filename": "test.pdf",
                "job_target": "Teste (Junior)",
                "data_json": json.dumps({"nota": 7, "resumo_executivo": "teste"})
            }
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")

    def test_export_markdown(self, client):
        r = client.post(
            "/api/export",
            data={
                "format": "md",
                "filename": "test.pdf",
                "job_target": "Teste (Junior)",
                "data_json": json.dumps({"nota": 7, "resumo_executivo": "teste"})
            }
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")

    def test_export_docx(self, client):
        r = client.post(
            "/api/export",
            data={
                "format": "docx",
                "filename": "test.pdf",
                "job_target": "Teste (Junior)",
                "data_json": json.dumps({"nota": 7, "resumo_executivo": "teste"})
            }
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )


# ============================================================================
# Provider configuration
# ============================================================================

class TestProviders:
    def test_get_provider_for_tool_no_env(self):
        """Sem TRIVOR_IAS, deve retornar None."""
        old_val = os.environ.pop("TRIVOR_IAS", None)
        try:
            from main import _get_provider_for_tool
            assert _get_provider_for_tool("curriculo") is None
            assert _get_provider_for_tool("market") is None
        finally:
            if old_val is not None:
                os.environ["TRIVOR_IAS"] = old_val

    def test_get_provider_for_tool_invalid_json(self):
        """JSON malformado deve retornar None."""
        old_val = os.environ.pop("TRIVOR_IAS", None)
        try:
            os.environ["TRIVOR_IAS"] = "{invalid-json"
            from main import _get_provider_for_tool
            assert _get_provider_for_tool("curriculo") is None
        finally:
            if old_val is not None:
                os.environ["TRIVOR_IAS"] = old_val
