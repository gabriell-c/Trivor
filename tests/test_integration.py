"""
Testes de integração com FastAPI TestClient — sem necessidade de servidor rodando.
Executar: pytest tests/test_integration.py -v
"""
import sys
import json
import os
import sqlite3
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
        assert "/api/market/cv-fit" in paths
        assert "/api/cv/semantic-fit" in paths
        assert "/api/cv/recruiter-sim" in paths


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
        # PDF válido mas SEM API key — deve falhar com 400 (sem key), não 500.
        # Isola o ambiente para não depender dos providers configurados na máquina
        # do desenvolvedor (TRIVOR_IAS / OPENAI_API_KEY no .env).
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "", "TRIVOR_IAS": "[]"}),
            patch("main._get_provider_for_tool", return_value=None),
        ):
            r = client.post(
                "/api/cv/analyze",
                files={"cv_file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
                data={"job": "test"}
            )
        assert r.status_code == 400
        assert "Chave de API" in r.json().get("detail", "")

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


# ============================================================================
# Fit CV × Vaga — camada determinística (sem LLM)
# ============================================================================

class TestJobFitUnit:
    def test_compute_job_fit_covers_present_terms(self):
        from main import _compute_job_fit
        cv = "Experiência: Python, Django, PostgreSQL. Liderei equipe com 5 pessoas. Excel avançado."
        job = "Requisitos: Python, Django\nDiferencial: Kubernetes"
        fit = _compute_job_fit(cv, job)
        assert fit["calculado"] is True
        assert "Python" in fit["requisitos_cobertos"]
        assert "Kubernetes" in fit["desejaveis_faltantes"]
        # 2 requisitos cobertos, nenhum dos 2 + 1 desejável coberto → 80.0
        assert fit["nota"] >= 75

    def test_compute_job_fit_no_requirements(self):
        from main import _compute_job_fit
        fit = _compute_job_fit("Sou analista administrativo.", "Vaga para pessoa motivada, comunicativa e organizada.")
        assert fit["calculado"] is False
        assert fit["nota"] is None

    def test_compute_job_fit_acento_agnostic(self):
        from main import _compute_job_fit
        cv = "Experiência com CRM, Excel e vendas B2B. Negociacao de contratos."
        job = "Requisitos: CRM, Excel\nDiferencial: Inglês"
        fit = _compute_job_fit(cv, job)
        assert "CRM" in fit["requisitos_cobertos"]
        assert "Excel" in fit["requisitos_cobertos"]
        assert "Inglês" in fit["desejaveis_faltantes"]


class TestMarketCvFit:
    @pytest.fixture
    def market_db(self, tmp_path, monkeypatch):
        """Base de market_jobs isolada (tmp) com duas vagas relevantes."""
        import market_service
        db = tmp_path / "market_fit.db"
        market_service.init_market_db(db)
        monkeypatch.setattr("main.DB_FILE", db)
        conn = sqlite3.connect(db)
        conn.execute("""
            INSERT INTO market_jobs (id, raw_job_id, title, company, location, modality, source, source_url, is_relevant, requirements, nice_to_have)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            "fit-job-1", "raw-1", "Dev Backend", "ACME", "São Paulo", "Remoto", "test", "",
            json.dumps(["Python", "FastAPI"]), json.dumps(["Docker"]),
        ))
        conn.execute("""
            INSERT INTO market_jobs (id, raw_job_id, title, company, location, modality, source, source_url, is_relevant, requirements, nice_to_have)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            "fit-job-2", "raw-2", "Analista Administrativo", "Globex", "Remoto", "Híbrido", "test", "",
            json.dumps(["Excel", "Power BI"]), json.dumps([]),
        ))
        conn.commit()
        conn.close()
        return db

    def test_empty_db_returns_400(self, client, tmp_path, monkeypatch):
        import market_service
        db = tmp_path / "market_fit_empty.db"
        market_service.init_market_db(db)
        monkeypatch.setattr("main.DB_FILE", db)
        r = client.post(
            "/api/market/cv-fit",
            files={"cv_file": ("cv.txt", b"Texto do curriuclo", "text/plain")},
        )
        assert r.status_code == 400
        assert "Base de mercado vazia" in r.json().get("detail", "")

    def test_ranks_jobs_by_score(self, client, market_db):
        r = client.post(
            "/api/market/cv-fit",
            files={"cv_file": ("cv.txt", b"Experiencia com Python e FastAPI. Excel basico.", "text/plain")},
            data={"limit": "5"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_vagas"] == 2
        scores = [v["score"] for v in data["vagas"]]
        assert scores == sorted(scores, reverse=True)
        # Vaga 1 cobre Python+FastAPI (80); vaga 2 cobre só Excel (50)
        assert data["vagas"][0]["id"] == "fit-job-1"
        assert data["vagas"][0]["score"] >= data["vagas"][1]["score"]
        assert "Docker" in data["vagas"][0]["desejaveis_faltantes"]

    def test_unsupported_extension(self, client):
        r = client.post(
            "/api/market/cv-fit",
            files={"cv_file": ("cv.exe", b"MZ", "application/octet-stream")},
        )
        assert r.status_code == 400


# ============================================================================
# Fit Semântico CV × Vaga (LLM) — /api/cv/semantic-fit
# ============================================================================

# Descrição de vaga ≥ 40 caracteres para passar na validação de entrada
LONG_JOB_DESC = (
    "Analista de dados pleno. Requisitos: Python, SQL, Power BI, 3 anos de "
    "experiência, Inglês intermediário. Diferencial: certificação em nuvem, machine learning."
)


class TestSemanticFitEndpoint:
    def test_short_description_returns_400(self, client):
        r = client.post(
            "/api/cv/semantic-fit",
            files={"cv_file": ("cv.txt", b"curriculo", "text/plain")},
            data={"job_description": "curto"},
        )
        assert r.status_code == 400
        assert "40 caracteres" in r.json().get("detail", "")

    def test_unsupported_extension(self, client):
        r = client.post(
            "/api/cv/semantic-fit",
            files={"cv_file": ("cv.exe", b"MZ", "application/octet-stream")},
            data={"job_description": LONG_JOB_DESC},
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "")

    def test_missing_api_key_returns_400(self, client):
        # Sem provider no ambiente nem OPENAI_API_KEY → 400 (e não 500).
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "", "TRIVOR_IAS": "[]"}),
            patch("main._get_provider_for_tool", return_value=None),
        ):
            r = client.post(
                "/api/cv/semantic-fit",
                files={"cv_file": ("cv.txt", b"Texto do curriculo", "text/plain")},
                data={"job_description": LONG_JOB_DESC},
            )
        assert r.status_code == 400
        assert "Chave de API" in r.json().get("detail", "")


class TestSemanticFitValidation:
    """Validação anti-alucinação (pós-processo), testável diretamente."""

    def test_evidence_in_cv_is_kept(self):
        from main import _semantic_fit_validate
        cv = "Experiência: Python e PostgreSQL. Gerenciei pipelines com Docker."
        fit = {
            "requisitos": [
                {"termo": "banco relacional", "tipo": "obrigatorio", "presente": True,
                 "evidencia": "PostgreSQL", "alias_encontrado": "PostgreSQL"},
                {"termo": "Inglês", "tipo": "diferencial", "presente": False,
                 "evidencia": None, "alias_encontrado": None},
            ],
            "sugestoes_de_reescrita": [
                {"secao": "Experiência", "texto_atual": "Gerenciei pipelines com Docker",
                 "sugerido": "s", "motivo": "m"},
            ],
        }
        out = _semantic_fit_validate(fit, cv)
        assert out["requisitos"][0]["evidencia"] == "PostgreSQL"
        assert out["requisitos"][0]["presente"] is True
        assert out["requisitos"][1]["presente"] is False
        assert out["sugestoes_de_reescrita"][0]["texto_atual"] == "Gerenciei pipelines com Docker"

    def test_hallucinated_evidence_is_zeroed(self):
        from main import _semantic_fit_validate
        cv = "Experiência: Python e PostgreSQL."
        fit = {
            "requisitos": [
                {"termo": "Kubernetes", "tipo": "diferencial", "presente": True,
                 "evidencia": "administrei cluster Kubernetes na empresa X",
                 "alias_encontrado": "Kubernetes"},
            ],
            "sugestoes_de_reescrita": [
                {"secao": "Experiência",
                 "texto_atual": "texto inventado que nao esta no curriculo",
                 "sugerido": "s", "motivo": "m"},
            ],
        }
        out = _semantic_fit_validate(fit, cv)
        assert out["requisitos"][0]["evidencia"] is None
        assert out["requisitos"][0]["presente"] is False
        assert out["requisitos"][0]["alias_encontrado"] is None
        assert out["sugestoes_de_reescrita"][0]["texto_atual"] is None

    def test_evidence_valid_helper_rules(self):
        from main import _semantic_fit_evidence_valid
        cv = "Experiência com Python e bancos PostgreSQL no trabalho."
        # Substring exato (normalizado) → válido
        assert _semantic_fit_evidence_valid("PostgreSQL", cv) is True
        # Mesmas palavras em outra ordem → válido (fallback por palavras)
        assert _semantic_fit_evidence_valid("bancos postgresql python", cv) is True
        # Palavras relevantes ausentes no CV → inválido
        assert _semantic_fit_evidence_valid("banco relacional", cv) is False
        # Citação curta demais (1 palavra relevante) e sem match exato → inválido
        assert _semantic_fit_evidence_valid("Docker", cv) is False


# ============================================================================
# Simulador de Recrutador CV × Vaga (LLM) — /api/cv/recruiter-sim
# ============================================================================

class TestRecruiterSimEndpoint:
    def test_short_description_returns_400(self, client):
        r = client.post(
            "/api/cv/recruiter-sim",
            files={"cv_file": ("cv.txt", b"curriculo", "text/plain")},
            data={"job_description": "curto"},
        )
        assert r.status_code == 400
        assert "40 caracteres" in r.json().get("detail", "")

    def test_unsupported_extension(self, client):
        r = client.post(
            "/api/cv/recruiter-sim",
            files={"cv_file": ("cv.exe", b"MZ", "application/octet-stream")},
            data={"job_description": LONG_JOB_DESC},
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "")

    def test_missing_api_key_returns_400(self, client):
        # Sem provider no ambiente nem OPENAI_API_KEY → 400 (e não 500).
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "", "TRIVOR_IAS": "[]"}),
            patch("main._get_provider_for_tool", return_value=None),
        ):
            r = client.post(
                "/api/cv/recruiter-sim",
                files={"cv_file": ("cv.txt", b"Texto do curriculo", "text/plain")},
                data={"job_description": LONG_JOB_DESC},
            )
        assert r.status_code == 400
        assert "Chave de API" in r.json().get("detail", "")


class TestRecruiterSimValidation:
    """Pós-processo do simulador (normalização), testável diretamente."""

    def test_normalizes_and_truncates(self):
        from main import _recruiter_sim_validate
        sim = {
            "veredito": "DUVIDA",
            "confianca": 12,
            "por_que": ["a", "", "b", "c", "d", "e", "f", "g"],
            "sinais_vermelhos": ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"],
            "perguntas_de_entrevista": ["p1", "p2"],
        }
        out = _recruiter_sim_validate(sim)
        assert out["veredito"] == "duvida"
        assert out["confianca"] == 10.0
        assert out["por_que"] == ["a", "b", "c", "d", "e", "f"]
        assert out["sinais_vermelhos"] == ["s1", "s2", "s3", "s4", "s5"]
        assert out["perguntas_de_entrevista"] == ["p1", "p2"]

    def test_invalid_verdict_and_confidence_fall_back(self):
        from main import _recruiter_sim_validate
        out = _recruiter_sim_validate({"veredito": "nao_sei", "confianca": "alto"})
        assert out["veredito"] == "duvida"
        assert out["confianca"] == 5
        assert out["por_que"] == []
        assert out["sinais_vermelhos"] == []
        assert out["perguntas_de_entrevista"] == []
