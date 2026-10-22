"""
Testes do leitor de dados do Job Hunter (apply_service.py) — Nível 1.

Cobrem: resolução de diretório (APPLY_DIR), resumo agregado, buckets de
status, filtros/paginação e os endpoints /api/apply/* (incluindo estados
ausentes e arquivo corrompido).
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_PATH = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_PATH))

import apply_service as asvc
from apply_service import ApplyDataError

SAMPLE = {
    "candidaturas": [
        {"vaga": "Dev Jr", "link": "https://x.dev/1", "local": "SP", "site": "Gupy",
         "status": "enviado", "data": "10/03/2026", "horario": "09:00:00", "curriculo": "fullstack.pdf"},
        {"vaga": "Analista Suporte", "link": "https://x.dev/2", "local": "Remoto", "site": "InfoJobs",
         "status": "preenchido_sem_confirmacao", "data": "12/03/2026", "horario": "10:00:00", "curriculo": "dados.pdf"},
        {"vaga": "Dev Backend", "link": "https://x.dev/3", "local": "SP", "site": "Gupy",
         "status": "erro: Page.goto: Timeout 15000ms exceeded.", "data": "08/03/2026", "horario": "11:00:00", "curriculo": "fullstack.pdf"},
        {"vaga": "Estágio TI", "link": "https://x.dev/4", "local": "MG", "site": "Nerdin",
         "status": "ja_candidatado", "data": "05/03/2026", "horario": "08:00:00", "curriculo": "dados.pdf"},
        {"vaga": "Help Desk", "link": "https://x.dev/5", "local": "SP", "site": "Indeed",
         "status": "botao_nao_encontrado", "data": "12/03/2026", "horario": "07:30:00", "curriculo": "fullstack.pdf"},
    ],
    "ja_candidatado": [{"vaga": "Outra", "site": "Gupy"}],
}


@pytest.fixture
def apply_dir(tmp_path, monkeypatch):
    """Diretório apply de teste (relatorio/candidaturas.json) apontado via APPLY_DIR."""
    d = tmp_path / "apply"
    (d / "relatorio").mkdir(parents=True)
    (d / "relatorio" / "candidaturas.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setenv("APPLY_DIR", str(d))
    return d


@pytest.fixture
def no_apply(tmp_path, monkeypatch):
    """APPLY_DIR aponta para um inexistente → resolução deve dar None (determinístico)."""
    monkeypatch.setenv("APPLY_DIR", str(tmp_path / "naoexiste"))
    return tmp_path / "naoexiste"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# ============================================================================
# resolve_apply_dir
# ============================================================================

class TestResolveApplyDir:
    def test_env_wins(self, apply_dir):
        assert asvc.resolve_apply_dir() == apply_dir

    def test_missing_dir_returns_none(self, no_apply):
        assert asvc.resolve_apply_dir() is None

    def test_env_dir_without_json_returns_none(self, tmp_path, monkeypatch):
        empty = tmp_path / "vazio"
        empty.mkdir()
        monkeypatch.setenv("APPLY_DIR", str(empty))
        assert asvc.resolve_apply_dir() is None


# ============================================================================
# apply_overview
# ============================================================================

class TestApplyOverview:
    def test_aggregation(self, apply_dir):
        ov = asvc.apply_overview()
        assert ov["available"] is True
        assert ov["total"] == 5
        assert ov["por_bucket"] == {"sucesso": 1, "parcial": 1, "skip": 1, "falha": 2}
        assert ov["por_site"]["Gupy"] == 2
        assert ov["periodo"] == {"primeiro": "05/03/2026", "ultimo": "12/03/2026"}

    def test_unavailable_shape(self, no_apply):
        ov = asvc.apply_overview()
        assert ov["available"] is False
        assert "APPLY_DIR" in ov["hint"]


# ============================================================================
# apply_applications
# ============================================================================

class TestApplyApplications:
    def test_sorted_most_recent_first(self, apply_dir):
        out = asvc.apply_applications()
        nomes = [r["vaga"] for r in out["items"]]
        assert nomes == ["Analista Suporte", "Help Desk", "Dev Jr", "Dev Backend", "Estágio TI"]

    def test_site_filter(self, apply_dir):
        out = asvc.apply_applications(site="Gupy")
        assert out["total"] == 2
        assert all(r["site"] == "Gupy" for r in out["items"])

    def test_bucket_filter(self, apply_dir):
        out = asvc.apply_applications(bucket="falha")
        assert out["total"] == 2
        assert all(r["status_bucket"] == "falha" for r in out["items"])

    def test_q_search_case_insensitive(self, apply_dir):
        out = asvc.apply_applications(q="DEV BACKEND")
        assert out["total"] == 1
        assert out["items"][0]["vaga"] == "Dev Backend"

    def test_limit_capped_at_200(self, apply_dir, monkeypatch):
        out = asvc.apply_applications(limit=9999)
        assert out["limit"] == 200

    def test_pagination_offset(self, apply_dir):
        out = asvc.apply_applications(limit=2, offset=2)
        assert len(out["items"]) == 2
        assert out["total"] == 5

    def test_missing_dir_raises(self, no_apply):
        with pytest.raises(ApplyDataError):
            asvc.apply_applications()

    def test_corrupt_json_raises(self, tmp_path, monkeypatch):
        d = tmp_path / "apply_corrupto"
        (d / "relatorio").mkdir(parents=True)
        (d / "relatorio" / "candidaturas.json").write_text("{invalido", encoding="utf-8")
        monkeypatch.setenv("APPLY_DIR", str(d))
        with pytest.raises(ApplyDataError):
            asvc.apply_applications()


# ============================================================================
# Endpoints /api/apply/*
# ============================================================================

class TestApplyEndpoints:
    def test_env_endpoint_roundtrip(self, client, apply_dir):
        env = apply_dir / ".env"
        env.write_text("NERDIN_SENHA=abc123\n", encoding="utf-8")
        r = client.get("/api/apply/env")
        assert r.status_code == 200
        assert "abc123" not in r.json()["NERDIN_SENHA"]  # senha mascarada
        body = {**r.json(), "CANDIDATO_CPF": "11122233344"}
        r2 = client.put("/api/apply/env", json=body)
        assert r2.status_code == 200
        conteudo = env.read_text(encoding="utf-8")
        assert "NERDIN_SENHA=abc123" in conteudo.replace('"', "")  # mask devolvido → real mantido
        assert "11122233344" in conteudo

    def test_env_endpoint_chave_inconheita_rejeitada(self, client, apply_dir):
        r = client.get("/api/apply/env")
        body = {**r.json(), "CHAVE_INVALIDA": "x"}
        r2 = client.put("/api/apply/env", json=body)
        assert r2.status_code == 400

    def test_overview_available(self, client, apply_dir):
        r = client.get("/api/apply/overview")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["total"] == 5

    def test_overview_unavailable_is_200_with_flag(self, client, no_apply):
        r = client.get("/api/apply/overview")
        assert r.status_code == 200
        assert r.json()["available"] is False

    def test_applications_200(self, client, apply_dir):
        r = client.get("/api/apply/applications", params={"bucket": "sucesso"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "enviado"

    def test_applications_bad_bucket_400(self, client, apply_dir):
        r = client.get("/api/apply/applications", params={"bucket": "xyz"})
        assert r.status_code == 400

    def test_applications_missing_dir_404(self, client, no_apply):
        r = client.get("/api/apply/applications")
        assert r.status_code == 404

    def test_applications_corrupt_502(self, client, tmp_path, monkeypatch):
        d = tmp_path / "apply_corrupto2"
        (d / "relatorio").mkdir(parents=True)
        (d / "relatorio" / "candidaturas.json").write_text("]", encoding="utf-8")
        monkeypatch.setenv("APPLY_DIR", str(d))
        r = client.get("/api/apply/applications")
        assert r.status_code == 502
