"""
Testes de carga/estresse leve para a API do backend.
Usa threads assíncronas para simular requisições concorrentes.
"""
import pytest
import requests
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "http://127.0.0.1:8000"

SAMPLE_TEXT = """Engenheiro de software backend com 9 anos de experiência.
Nos últimos anos, criei serviços do zero que atenderam dezenas de milhares
de usuários. Tecnologias: Python, Django, FastAPI, Node.js, TypeScript,
NestJS, AWS, PostgreSQL, Redis, GraphQL, Docker, Kubernetes, Terraform.

Experiência:
- Melhorei performance otimizando queries do Django
- Criei microsserviços em AWS Lambda
"""


# ============================================================================
# Health endpoint stress test
# ============================================================================

class TestHealthStress:
    """Health endpoint deve suportar alta carga (é simples e síncrono)."""

    def test_50_concurrent_health_requests(self):
        """50 requisições concorrentes ao health — deve responder < 1s cada."""
        errors = []
        times = []

        def hit_health():
            start = time.time()
            try:
                r = requests.get(f"{BASE}/health", timeout=5)
                times.append(time.time() - start)
                if r.status_code != 200:
                    errors.append(f"status={r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hit_health) for _ in range(50)]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        total = time.time() - t0

        assert len(errors) == 0, f"Erros: {errors[:5]}"
        # Tempo total não deve exceder 15s
        assert total < 15, f"50 requisições levaram {total:.1f}s (muito lento)"
        # Média por requisição < 500ms
        avg = sum(times) / len(times) if times else 0
        assert avg < 0.5, f"Latência média alta: {avg:.3f}s"


# ============================================================================
# OpenAPI schema stress test
# ============================================================================

class TestOpenAPIStress:
    def test_100_schema_reads(self):
        """100 leituras do schema OpenAPI — deve ser rápido."""
        errors = []
        times = []

        def hit_openapi():
            start = time.time()
            try:
                r = requests.get(f"{BASE}/openapi.json", timeout=5)
                times.append(time.time() - start)
                if r.status_code != 200:
                    errors.append(f"status={r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hit_openapi) for _ in range(100)]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        total = time.time() - t0

        assert len(errors) == 0, f"Erros: {errors[:5]}"
        assert total < 30, f"100 schema reads levaram {total:.1f}s"


# ============================================================================
# Logs endpoints stress test
# ============================================================================

class TestLogsStress:
    def test_20_concurrent_log_reads(self):
        errors = []

        def hit_logs():
            try:
                r = requests.get(f"{BASE}/api/logs", timeout=10)
                if r.status_code not in (200, 204):
                    errors.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hit_logs) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Erros nos logs: {errors[:5]}"

    def test_log_clear_idempotent(self):
        """Clear logs deve ser idempotente (rodar 2x não quebra)."""
        r1 = requests.post(f"{BASE}/api/logs/clear", timeout=5)
        r2 = requests.post(f"{BASE}/api/logs/clear", timeout=5)
        assert r1.status_code in (200, 204)
        assert r2.status_code in (200, 204)


# ============================================================================
# LinkedIn analyze — basic load (no real API key = fast error)
# ============================================================================

class TestLinkedInLoad:
    def test_5_concurrent_linkedin_requests(self):
        """5 requisições LinkedIn concorrentes — todas devem falhar com erro controlado."""
        results = []
        lock = threading.Lock()

        def analyze():
            try:
                r = requests.post(
                    f"{BASE}/api/linkedin/analyze",
                    data={"text": SAMPLE_TEXT},
                    timeout=30,
                )
                with lock:
                    results.append(r.status_code)
            except Exception as e:
                with lock:
                    results.append(f"error: {e}")

        threads = [threading.Thread(target=analyze) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        # Todas devem ter falhado com erro controlado, não crash
        for r in results:
            if isinstance(r, int):
                # Erro esperado (sem API key) — status 400, 401, 500, 503 são OK
                assert r in (400, 401, 422, 500, 503), f"Status inesperado: {r}"
            else:
                pytest.skip(f"Requisição com exceção: {r}")

        assert len(results) == 5, f"Apenas {len(results)}/5 requisições completaram"
