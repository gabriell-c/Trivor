"""Fixtures compartilhadas para testes de integração com o backend."""
import pytest
import requests
import time


@pytest.fixture(scope="session")
def backend_url():
    return "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def wait_for_backend(backend_url):
    """Espera até o backend responder no health check."""
    for i in range(20):
        try:
            r = requests.get(f"{backend_url}/health", timeout=2)
            if r.status_code == 200:
                return backend_url
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Backend não respondeu após 20s")
