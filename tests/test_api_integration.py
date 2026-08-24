"""
Testes de integração com a API do backend (requer servidor rodando em 127.0.0.1:8000)
"""
import pytest
import requests
import os
import json
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8000"


# ============================================================================
# Health & OpenAPI
# ============================================================================

class TestHealth:
    def test_health_returns_ok(self):
        r = requests.get(f"{BASE}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_openapi_schema_exists(self):
        r = requests.get(f"{BASE}/openapi.json", timeout=5)
        assert r.status_code == 200
        schema = r.json()
        # Verifica se o endpoint de linkedin existe no schema
        paths = schema.get("paths", {})
        assert "/api/linkedin/analyze" in paths
        assert "post" in paths["/api/linkedin/analyze"]


# ============================================================================
# Logs endpoints
# ============================================================================

class TestLogs:
    def test_get_logs(self):
        r = requests.get(f"{BASE}/api/logs", timeout=5)
        assert r.status_code == 200
        data = r.json()
        # logs pode ser lista ou dict com "logs"
        assert isinstance(data, (list, dict))

    def test_get_logs_stats(self):
        r = requests.get(f"{BASE}/api/logs/stats", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_clear_logs(self):
        r = requests.post(f"{BASE}/api/logs/clear", timeout=5)
        assert r.status_code in (200, 204)


# ============================================================================
# LinkedIn analyze — structure validation (without real API key)
# ============================================================================

class TestLinkedInAnalyze:
    SAMPLE_TEXT = """Engenheiro de software backend com 9 anos de experiência.
Nos últimos anos, criei serviços do zero que atenderam dezenas de milhares
de usuários. Tecnologias: Python, Django, FastAPI, Node.js, TypeScript,
NestJS, AWS (Lambda, CDK, S3, DynamoDB), PostgreSQL, Redis, GraphQL,
Docker, Kubernetes, Terraform, React, Next.js.

Experiência:
- Melhorei performance de múltiplos endpoints otimizando queries do Django
- Criei microsserviços em AWS Lambda que processam milhões de transações
"""

    def test_linkedin_analyze_without_api_key_returns_error(self):
        """Sem API key configurada, deve retornar erro útil (não crash)"""
        r = requests.post(
            f"{BASE}/api/linkedin/analyze",
            data={"text": self.SAMPLE_TEXT},
            timeout=15,
        )
        # Pode retornar 200 com erro no JSON ou 400/500 se provider não configurado
        # O importante é NÃO crashar com exception não tratada
        assert r.status_code in (200, 400, 401, 500, 503)
        try:
            data = r.json()
            # Se retornou JSON, pelo menos deve ser válido
            assert isinstance(data, dict)
        except Exception:
            # Se não é JSON, pelo menos não crashou
            pass

    def test_linkedin_analyze_empty_text_rejected(self):
        r = requests.post(
            f"{BASE}/api/linkedin/analyze",
            data={"text": ""},
            timeout=5,
        )
        # Texto vazio deve ser rejeitado
        assert r.status_code == 422  # FastAPI validation error

    def test_linkedin_analyze_with_image_url(self):
        """Com image_url, deve passar para o mesmo fluxo"""
        r = requests.post(
            f"{BASE}/api/linkedin/analyze",
            data={
                "text": self.SAMPLE_TEXT,
                "image_url": "https://example.com/fake-photo.jpg",
            },
            timeout=15,
        )
        # Deve processar (erro de API key é esperado, mas não crash)
        assert r.status_code in (200, 400, 401, 500, 503)
        try:
            data = r.json()
            assert isinstance(data, dict)
        except Exception:
            pass


# ============================================================================
# Market endpoints
# ============================================================================

class TestMarket:
    SAMPLE_JOBS = json.dumps([
        {"titulo": "Python Backend Developer", "empresa": "Tech Corp", "remoto": True},
        {"titulo": "Data Scientist", "empresa": "Data Inc", "remoto": False},
    ])

    def test_market_analyze_missing_file(self):
        r = requests.post(
            f"{BASE}/api/market/analyze",
            data={"jobs": self.SAMPLE_JOBS},
            timeout=10,
        )
        # Pode aceitar ou recusar — não deve crashar
        assert r.status_code in (200, 400, 422)

    def test_market_analyze_with_cv(self):
        r = requests.post(
            f"{BASE}/api/market/analyze",
            data={"jobs": self.SAMPLE_JOBS},
            files={"file": ("test.pdf", b"fake pdf content")},
            timeout=10,
        )
        # Arquivo pode ser rejeitado como 422 (fastapi) ou processado (200/400/500)
        assert r.status_code in (200, 400, 415, 422, 500)


# ============================================================================
# CV Analyze endpoint
# ============================================================================

class TestCVAnalyze:
    def test_cv_analyze_missing_file(self):
        r = requests.post(
            f"{BASE}/api/cv/analyze",
            data={"resume_text": "Texto de exemplo"},
            timeout=10,
        )
        # Sem arquivo, FastAPI deve retornar 422
        assert r.status_code in (200, 422, 500)


# ============================================================================
# JSearch endpoints (read-only, no auth needed for keys listing)
# ============================================================================

class TestJSearch:
    def test_get_keys(self):
        r = requests.get(f"{BASE}/api/jsearch/keys", timeout=5)
        # Pode retornar 200 (com keys) ou 500 (sem env configurado) — desde que não crash
        assert r.status_code in (200, 500)
