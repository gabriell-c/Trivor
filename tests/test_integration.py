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
        assert "/api/cv/cover-letter" in paths
        assert "/api/cv/diff" in paths


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
# Análise de CV em 2 passes (estrutura + qualidade) — LLM mockada
# ============================================================================

class _FakeLLMUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class _FakeLLMResponse:
    """Simula a resposta de chat.completions.create (provider mockado):
    .choices[0].message.content = JSON do passo; .usage = tokens do passo."""

    def __init__(self, payload: dict, prompt_tokens: int = 0, completion_tokens: int = 0):
        class _Message:
            def __init__(self, content: str):
                self.content = content

        class _Choice:
            def __init__(self):
                self.message = _Message(json.dumps(payload, ensure_ascii=False))

        self.choices = [_Choice()]
        self.usage = _FakeLLMUsage(prompt_tokens, completion_tokens)


class TestAnalyzeCVTwoPasses:
    def test_analyze_cv_two_passes_merged(self, client):
        """Com o client OpenAI mockado, os 2 passes rodam sequenciais e a
        resposta final é o merge dos campos: estrutura do pass 1 + pontos de
        qualidade do pass 2, com citações validadas contra o texto do CV."""
        cv_text = (
            "Maria Silva\n"
            "maria.silva@email.com | São Paulo, SP\n"
            "Linkedin: linkedin.com/in/mariasilva\n"
            "\n"
            "Resumo\n"
            "Analista de suporte com 4 anos de experiência em atendimento.\n"
            "\n"
            "Experiência\n"
            "Empresa ABC — Analista de Suporte (Mar/2022 – Presente)\n"
            "- Migrei 300 clientes para o novo CRM, reduzindo tempo de resposta em 40%\n"
            "- Usei MySQL 8.0 para relatórios diários\n"
            "\n"
            "Formação\n"
            "Técnico em Administração — SENAC (2018-2020)\n"
        )
        passo1 = {
            "nota": 74.0,
            "score_ats": 80,
            "resumo_executivo": "Currículo estruturado, com experiência bem apresentada.",
            "foto_detectada": False,
            "foto_recomendada": False,
            "ordem_secoes": {"correta": True, "problema": None, "como_corrigir": None},
            "palavras_chave_presentes": ["CRM", "atendimento"],
            "palavras_chave_faltantes": [],
            "erros_ortograficos": [],
            "erros_comuns_detectados": [],
            "analise_secoes": {
                "experiencia_profissional": {
                    "status": "ok", "score": 80, "problema": None, "como_corrigir": None, "presente": True
                }
            },
            "analise_ats": {
                "score_ats": 80,
                "palavras_chave_faltantes": [],
                "gargalos_formatacao": [],
                "veredito_robos": "aprovado",
                "explicacao": "Formatação limpa e seções completas.",
            },
        }
        passo2 = {
            "pontos_fortes": [
                "Métricas concretas nos bullets (trecho: 'Migrei 300 clientes para o novo CRM, reduzindo tempo de resposta em 40%')",
                "Experiência relevante e quantificada (trecho: 'Analista de suporte com 4 anos de experiência em atendimento')",
            ],
            "pontos_fracos": [
                "Formação sem detalhes de conteúdo (trecho: 'trecho inventado que não existe no CV')",
            ],
        }

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-teste-1234567890", "TRIVOR_IAS": "[]"}),
            patch("main._extract_cv_text", return_value=(cv_text, "mock", False)),
            patch("main.OpenAI") as mock_openai,
        ):
            mock_openai.return_value.chat.completions.create.side_effect = [
                _FakeLLMResponse(passo1, 100, 200),
                _FakeLLMResponse(passo2, 300, 400),
            ]
            r = client.post(
                "/api/cv/analyze",
                files={"cv_file": ("Maria_Silva_CV.txt", cv_text.encode("utf-8"), "text/plain")},
                data={"api_key": "sk-teste-1234567890", "area": "suporte"},
            )

        assert r.status_code == 200, r.text
        data = r.json()

        # Os 2 passes rodaram sequenciais (passo 1 → passo 2)
        assert mock_openai.return_value.chat.completions.create.call_count == 2

        # Merge: campos estruturais vêm do passo 1
        assert data["nota"] == 74.0
        assert data["resumo_executivo"].startswith("Currículo estruturado")
        assert data["analise_ats"]["veredito_robos"] == "aprovado"
        assert data["analise_secoes"]["experiencia_profissional"]["status"] == "ok"

        # Merge: campos de qualidade vêm do passo 2, com citação válida mantida
        assert any("Métricas concretas" in p for p in data["pontos_fortes"])
        assert any("Migrei 300 clientes" in p for p in data["pontos_fortes"])
        assert any("Experiência relevante" in p for p in data["pontos_fortes"])

        # Citação inventada foi removida; o item permaneceu sem o trecho
        assert data["pontos_fracos"] == ["Formação sem detalhes de conteúdo"]

        # uso_tokens = soma dos 2 passes
        assert data["uso_tokens"]["prompt_tokens"] == 400
        assert data["uso_tokens"]["completion_tokens"] == 600
        assert data["uso_tokens"]["total_tokens"] == 1000


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


class TestCalcFitScore:
    """Nota determinística reutilizada por _compute_job_fit e /api/market/cv-fit."""

    def test_all_requirements_covered_scores_100(self):
        from main import calc_fit_score
        assert calc_fit_score(["a", "b", "c"], [], 3.0) == 100.0

    def test_nice_to_have_counts_half(self):
        from main import calc_fit_score
        # 1 obrigatório coberto + 1 desejável coberta em total de 2 + 0.5 = 2.5
        # → 100 * (1 + 0.5) / 2.5 = 60.0
        assert calc_fit_score(["python"], ["docker"], 2.5) == 60.0

    def test_nothing_covered_scores_0(self):
        from main import calc_fit_score
        assert calc_fit_score([], [], 3.0) == 0.0

    def test_nice_weight_constant_is_half(self):
        from main import NICE_TO_HAVE_WEIGHT
        assert NICE_TO_HAVE_WEIGHT == 0.5

    def test_compute_job_fit_uses_shared_formula(self):
        """_compute_job_fit e o ranking do cv-fit devem concordar com calc_fit_score."""
        from main import calc_fit_score, _compute_job_fit
        cv = "Experiência: Python, Django, PostgreSQL. Liderei equipe com 5 pessoas. Excel avançado."
        job = "Requisitos: Python, Django\nDiferencial: Kubernetes"
        fit = _compute_job_fit(cv, job)
        assert fit["calculado"] is True
        total = len(fit["requisitos_cobertos"]) + len(fit["requisitos_faltantes"])
        nice = len(fit["desejaveis_cobertas"]) + len(fit["desejaveis_faltantes"])
        esperado = calc_fit_score(fit["requisitos_cobertos"], fit["desejaveis_cobertas"],
                                  total + 0.5 * nice)
        assert fit["nota"] == esperado


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


# ============================================================================
# Geração de Cover Letter CV × Vaga (LLM) — /api/cv/cover-letter
# ============================================================================

class TestCoverLetterEndpoint:
    def test_short_description_returns_400(self, client):
        r = client.post(
            "/api/cv/cover-letter",
            files={"cv_file": ("cv.txt", b"curriculo", "text/plain")},
            data={"job_description": "curto"},
        )
        assert r.status_code == 400
        assert "40 caracteres" in r.json().get("detail", "")

    def test_invalid_formato_returns_400(self, client):
        r = client.post(
            "/api/cv/cover-letter",
            files={"cv_file": ("cv.txt", b"curriculo", "text/plain")},
            data={"job_description": LONG_JOB_DESC, "formato": "media"},
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "")

    def test_unsupported_extension(self, client):
        r = client.post(
            "/api/cv/cover-letter",
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
                "/api/cv/cover-letter",
                files={"cv_file": ("cv.txt", b"Texto do curriculo", "text/plain")},
                data={"job_description": LONG_JOB_DESC},
            )
        assert r.status_code == 400
        assert "Chave de API" in r.json().get("detail", "")


class TestCoverLetterValidation:
    """Auditoria anti-alucinação da cover letter (pós-processo), testável
    diretamente."""

    def test_hallucinated_facts_are_dropped(self):
        from main import _cover_letter_validate
        cv = "Experiência: Python e PostgreSQL. Gerenciei pipelines com Docker."
        carta = {
            "texto": "Prezado(a) Senhor(a), tenho experiência com Docker...",
            "formato": "completa",
            "fatos_usados": [
                "Gerenciei pipelines com Docker",
                "Treinei equipes com Kubernetes",  # não está no CV
            ],
        }
        out = _cover_letter_validate(carta, cv, "completa")
        assert out["fatos_usados"] == ["Gerenciei pipelines com Docker"]
        assert out["texto"].startswith("Prezado(a)")

    def test_invalid_formato_falls_back_to_requested(self):
        from main import _cover_letter_validate
        carta = {"texto": "abc", "formato": "ultra", "fatos_usados": []}
        out = _cover_letter_validate(carta, "cv texto", "curta")
        assert out["formato"] == "curta"
        assert out["texto"] == "abc"
        assert out["fatos_usados"] == []

    def test_non_string_texto_and_fatos_are_cleared(self):
        from main import _cover_letter_validate
        out = _cover_letter_validate(
            {"texto": 123, "formato": "curta", "fatos_usados": "nao-lista"},
            "cv texto",
            "curta",
        )
        assert out["texto"] == ""
        assert out["fatos_usados"] == []

    def test_formato_case_insensitive_and_deduped(self):
        from main import _cover_letter_validate
        cv = "Experiência: Python e PostgreSQL."
        carta = {
            "texto": "carta",
            "formato": "CURTA",
            "fatos_usados": ["Python", "python", "PostgreSQL", ""],
        }
        out = _cover_letter_validate(carta, cv, "completa")
        assert out["formato"] == "curta"
        assert out["fatos_usados"] == ["Python", "PostgreSQL"]


# ============================================================================
# Comparação de Duas Versões de CV (Diff) — /api/cv/diff
# ============================================================================

# Duas versões do mesmo CV para os testes do diff (antiga sem métricas;
# nova com bullets, métricas numéricas e termos-chave novos)
CV_DIFF_ANTIGO = """Experiência
Empresa A (2021-2023)
- Responsável por relatórios
- Suporte a clientes
- Manutenção de Excel
- Utilização de Excel

Formação
- Graduação em Administração
"""

CV_DIFF_NOVO = """Experiência
Empresa A (2021-2023)
- Relatórios automatizados com Power BI e PostgreSQL, redução em 40%
- Suporte a clientes com Power BI e PostgreSQL, aumentei a satisfação em 15 pontos
Empresa B (2023-2025)
- Pipelines com Docker e PostgreSQL, economizei R$ 120 mil
- Atendimento com Power BI e PostgreSQL, reduzi o retrabalho em 20%
- Mentoria de estagiários com PostgreSQL, aumentei a retenção em 30%

Formação
- Graduação em Administração
"""


class TestCVDiffEndpoint:
    def test_missing_files_returns_400(self, client):
        # Nenhum arquivo enviado → 400 com mensagem orientando os dois uploads
        r = client.post("/api/cv/diff", data={"area": "Tecnologia"})
        assert r.status_code == 400
        assert "dois arquivos" in r.json().get("detail", "")

    def test_single_file_returns_400(self, client):
        # Só a versão nova → 400 (falta a anterior)
        r = client.post(
            "/api/cv/diff",
            files={"cv_file_novo": ("cv_novo.txt", b"Experiencia com Python.", "text/plain")},
        )
        assert r.status_code == 400

    def test_unsupported_extension_returns_400(self, client):
        r = client.post(
            "/api/cv/diff",
            files={
                "cv_file_novo": ("cv.exe", b"MZ", "application/octet-stream"),
                "cv_file_anterior": ("cv.txt", b"Antiga", "text/plain"),
            },
        )
        assert r.status_code == 400
        assert "Formato" in r.json().get("detail", "")

    def test_missing_api_key_returns_400(self, client):
        # Dois .txt válidos, sem provider nem OPENAI_API_KEY → 400 no
        # sub-caminho LLM (o diff determinístico roda antes, mas sem chave
        # a chamada LLM não pode ser feita).
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "", "TRIVOR_IAS": "[]"}),
            patch("main._get_provider_for_tool", return_value=None),
        ):
            r = client.post(
                "/api/cv/diff",
                files={
                    "cv_file_novo": ("cv_novo.txt", CV_DIFF_NOVO.encode("utf-8"), "text/plain"),
                    "cv_file_anterior": ("cv_antigo.txt", CV_DIFF_ANTIGO.encode("utf-8"), "text/plain"),
                },
            )
        assert r.status_code == 400
        assert "Chave de API" in r.json().get("detail", "")


class TestCVDiffDeterministic:
    """Camada determinística do diff, testável diretamente (sem LLM)."""

    def test_metrics_grow_in_new_version(self):
        from main import _diff_cv_deterministic
        diff = _diff_cv_deterministic(CV_DIFF_ANTIGO, CV_DIFF_NOVO)
        assert diff["metricas_numericas"]["anterior"] == 0
        assert diff["metricas_numericas"]["novo"] >= 3

    def test_bullets_grow_in_new_version(self):
        from main import _diff_cv_deterministic
        diff = _diff_cv_deterministic(CV_DIFF_ANTIGO, CV_DIFF_NOVO)
        assert diff["bullets_experiencia"]["novo"] > diff["bullets_experiencia"]["anterior"]
        # A seção de formação (bullets depois de "Formação") não conta
        assert diff["bullets_experiencia"]["anterior"] == 4

    def test_terms_added_and_removed(self):
        from main import _diff_cv_deterministic
        diff = _diff_cv_deterministic(CV_DIFF_ANTIGO, CV_DIFF_NOVO)
        # "PostgreSQL" só aparece (2+) na nova → adicionado
        assert "postgresql" in diff["termos_adicionados"]
        # "Excel" se repetia na antiga e saiu na nova → removido
        assert "excel" in diff["termos_removidos"]

    def test_identical_texts_yield_no_delta(self):
        from main import _diff_cv_deterministic
        diff = _diff_cv_deterministic(CV_DIFF_ANTIGO, CV_DIFF_ANTIGO)
        assert diff["bullets_experiencia"]["anterior"] == diff["bullets_experiencia"]["novo"]
        assert diff["metricas_numericas"]["anterior"] == diff["metricas_numericas"]["novo"]
        assert diff["termos_adicionados"] == []
        assert diff["termos_removidos"] == []


class TestCVDiffValidation:
    """Pós-processo anti-alucinação do diff (pós-processo), testável
    diretamente: zera evidências que não existem na versão citada."""

    def test_hallucinated_evidence_is_zeroed(self):
        from main import _diff_cv_validate
        antigo = "Experiência: Python e PostgreSQL. Gerenciei pipelines com Docker."
        novo = "Experiência: Python, PostgreSQL e Kubernetes. Gerenciei pipelines com Docker."
        narrativa = {
            "resumo": "Saldo positivo: novas skills e métricas.",
            "melhorias": [
                {"item": "Kubernetes adicionado", "evidencia_antiga": None, "evidencia_nova": "Kubernetes"},
                {"item": "Alucinação", "evidencia_antiga": None, "evidencia_nova": "certificação AWS que não existe no CV"},
                "item solto sem evidência",
            ],
            "piorou": [
                {"item": "Referência sumiu", "evidencia_antiga": "texto inventado fora do CV", "evidencia_nova": None},
            ],
            "recomendacao_proxima": 42,
        }
        out = _diff_cv_validate(narrativa, antigo, novo)
        assert out["melhorias"][0]["evidencia_nova"] == "Kubernetes"
        # Evidência que não existe no texto da nova versão → zerada
        assert out["melhorias"][1]["evidencia_nova"] is None
        # Item string puro é normalizado e fica com evidências null
        assert out["melhorias"][2] == {"item": "item solto sem evidência", "evidencia_antiga": None, "evidencia_nova": None}
        # Evidência que não existe no texto da versão antiga → zerada
        assert out["piorou"][0]["evidencia_antiga"] is None
        # Campos não-string viram ""
        assert out["recomendacao_proxima"] == ""
        assert out["resumo"].startswith("Saldo positivo")

    def test_valid_evidence_is_kept(self):
        from main import _diff_cv_validate
        antigo = "Experiência: Python e PostgreSQL."
        novo = "Experiência: Python, PostgreSQL e Docker."
        narrativa = {
            "resumo": "Docker entrou no CV.",
            "melhorias": [
                {"item": "Docker adicionado", "evidencia_nova": "Docker", "evidencia_antiga": None},
            ],
            "piorou": [],
            "recomendacao_proxima": "Detalhe o uso de Docker.",
        }
        out = _diff_cv_validate(narrativa, antigo, novo)
        assert out["melhorias"][0]["evidencia_nova"] == "Docker"
        assert out["piorou"] == []
        assert out["recomendacao_proxima"] == "Detalhe o uso de Docker."


# ============================================================================
# load_dotenv no topo do main (.env deixa de ser inócuo)
# ============================================================================

class TestLoadDotenv:
    def test_main_wired_to_load_dotenv(self):
        """O main importa load_dotenv (chamado no topo do módulo)."""
        import main
        assert hasattr(main, "load_dotenv")

    def test_load_dotenv_called_before_first_key_read(self):
        """Guarda de regressão: a chamada load_dotenv() deve vir ANTES da
        primeira leitura de os.getenv("OPENAI_API_KEY") do main."""
        from pathlib import Path
        import main
        src = Path(main.__file__).read_text(encoding="utf-8")
        load_idx = src.index("load_dotenv(")
        key_idx = src.index('os.getenv("OPENAI_API_KEY"')
        assert load_idx < key_idx

    def test_load_dotenv_mechanism(self, tmp_path, monkeypatch):
        """python-dotenv carrega .env para o os.environ; variável já definida
        no sistema prevalece (override=False)."""
        from dotenv import load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TRIVOR_TESTE_SENTINELA=valor-do-env\nTRIVOR_TESTE_OVERRIDE=dois\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRIVOR_TESTE_OVERRIDE", "um")
        try:
            load_dotenv(env_file, override=False)
            assert os.environ.get("TRIVOR_TESTE_SENTINELA") == "valor-do-env"
            # variável do sistema prevalece sobre o .env
            assert os.environ.get("TRIVOR_TESTE_OVERRIDE") == "um"
        finally:
            # load_dotenv escreve direto no os.environ (fora do monkeypatch)
            os.environ.pop("TRIVOR_TESTE_SENTINELA", None)
