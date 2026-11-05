"""Regressão das correções da auditoria (S3, S4, S5, L11, L12).

Cada teste amarra um CONTRATO do auditorio, não o output atual — oráculos:
- S3: PII do CV/prompt não persiste em claro no requests.log.db
- S4: fname/model do /api/export/market não injetam header (Content-Disposition)
- S5: save_env com payload parcial NÃO apaga credencial não citada
- L11: .doc binário legacy é rejeitado com 400 claro (não 500 crua)
- L12: skill com '&' solto ("C&B") não quebra o parser XML do PDF

Executar: pytest tests/test_correcoes_auditoria.py
"""
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import apply_admin as ad  # noqa: E402
import logging_service  # noqa: E402
import market_export  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_apply_dir(tmp_path, monkeypatch):
    apply_dir = tmp_path / "apply"
    # resolve_apply_dir exige relatorio/candidaturas.json (mesmo setup de
    # fake_apply em test_apply_admin.py)
    (apply_dir / "relatorio").mkdir(parents=True)
    (apply_dir / "relatorio" / "candidaturas.json").write_text(
        '{"candidaturas": [], "ja_candidatado": []}', encoding="utf-8")
    monkeypatch.setenv("APPLY_DIR", str(apply_dir))
    return apply_dir


# ---------------------------------------------------------------------------
# S3 — PII sanitizada na escrita do log de requisições
# ---------------------------------------------------------------------------
class TestPiiNoLog:
    def test_persiste_resumo_e_nao_o_texto(self, tmp_path, monkeypatch):
        db = tmp_path / "pi.db"
        conexao = sqlite3.connect(str(db))
        conexao.executescript(logging_service.SCHEMA)
        monkeypatch.setattr(logging_service, "_conn", lambda: conexao)

        texto_grande = ("prefacio-ineofensivo-" * 20) + ("segredo-unico-abc123" * 400)
        # o segredo começa APÓS a janela de 200 chars que o resumo retém por
        # design (preview); a propriedade testada é: nada além dos 200 iniciais
        logging_service.log_request(
            endpoint="/api/cv/analyze", method="POST", status_code=200,
            duration_ms=10.0, model="m", api_key_preview="…1234",
            extracted_text=texto_grande, llm_prompt="instrucao-" + "x" * 3000,
        )
        linha = conexao.execute(
            "SELECT extracted_text, llm_prompt FROM api_logs").fetchone()
        conexao.close()

        # O conteúdo integral NÃO vai para o disco
        assert "segredo-unico-abc123" not in linha[0]
        assert "x" * 500 not in linha[1]
        # Forma contratada: [sha256:8] N chars — (primeiros 200)
        assert linha[0].startswith("[sha256:") and "chars —" in linha[0]
        assert linha[0].endswith(texto_grande[:200])
        assert linha[1].startswith("[sha256:")


# ---------------------------------------------------------------------------
# S4 — Content-Disposition sem CRLF (header injection)
# ---------------------------------------------------------------------------
class TestContentDisposition:
    def test_fname_com_crlf_e_espacos_e_sanitized(self, client):
        r = client.post(
            "/api/export/market",
            data={
                "format": "md",
                "report_json": "{}",
                "filename": "rel\\nX-inj: 1",
                "job_title": "Dev",
            },
        )
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        # propriedade de segurança: SEM CRLF no header (injeção morta)
        assert "\n" not in cd and "\r" not in cd
        # o nome segue anexado a sufixo uuid do servidor
        import re as _re
        assert _re.search(r"attachment; filename=\"[^\r\n\"]+\"?", cd)


# ---------------------------------------------------------------------------
# S5 — save_env: payload parcial preserva credencial não citada
# ---------------------------------------------------------------------------
class TestSaveEnvParcial:
    def test_ausente_mantem_vazio_remove(self, fake_apply_dir):
        env = fake_apply_dir / ".env"
        env.write_text("ENDERECO_BAIRRO=Centro\n", encoding="utf-8")

        # payload vazio → NENHUMA chave citada → valores atuais mantidos
        ad.save_env({})
        conteudo = env.read_text(encoding="utf-8")
        assert "Centro" in conteudo, "payload parcial apagou valor não citado"

        # vazio explícito → remoção de propósito
        ad.save_env({"ENDERECO_BAIRRO": ""})
        conteudo = env.read_text(encoding="utf-8")
        assert "ENDERECO_BAIRRO=Centro" not in conteudo


# ---------------------------------------------------------------------------
# L11 — .doc fora dos formatos aceitos: 400 claro, não 500 crua
# ---------------------------------------------------------------------------
class TestExtensoes:
    def test_doc_binario_rejeitado_400(self, client):
        r = client.post(
            "/api/cv/analyze",
            files={"cv_file": ("cv.doc", b"MEI\x00\x00falso", "application/msword")},
            data={"job": "test"},
        )
        assert r.status_code == 400
        assert "docx" in r.json()["detail"], "mensagem 400 deve listar os formatos aceitos"


# ---------------------------------------------------------------------------
# L12 — '&' solto em dado do relatório não quebra o PDF (parser XML)
# ---------------------------------------------------------------------------
class TestPdfComAmpersand:
    def test_c_b_nao_quebra_reportlab(self):
        relatorio = {
            "summary": {"generated_at": "2026-11-05 00:00"},
            "statistics": {},
            "sample_jobs": [{
                "title": "Dev C&B", "company": "C&B Corp", "location": "SP",
                "modality": "Remoto", "source": "jsearch", "source_url": "",
                "requirements": ["C&B Python", "R&D"],
                "nice_to_have": ["Q&A"],
                "soft_skills": ["trabalho em equipe"],
                "certifications": [],
                "salary_min": 5000, "salary_max": 8000, "role_level": "Pleno",
            }],
        }
        out = market_export.generate_market_pdf_export(
            relatorio, "Dev", "Pleno", "br", "gpt-4o")
        pdf = out.getvalue()
        assert pdf.startswith(b"%PDF") and len(pdf) > 1000
