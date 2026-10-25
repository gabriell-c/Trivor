"""Testes do status de sessão dos 5 bots (apply/common/status_sessoes.py).

Módulo carregado por path (ele é independente de propósito — não puxa a
camada de browser). Fixtures em tmp_path: perfis de sessão em vários
estados, .env com/sem credenciais.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

APPLY_PATH = Path(__file__).parent.parent / "apply"


def _carregar():
    spec = importlib.util.spec_from_file_location(
        "status_sessoes", APPLY_PATH / "common" / "status_sessoes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["status_sessoes"] = mod
    return mod


@pytest.fixture()
def ss():
    return _carregar()


def _estado_de(ss, base: Path, bot: str) -> dict:
    return next(e for e in ss.estados(base) if e["bot"] == bot)


def test_vazio_sem_nada(ss, tmp_path):
    for bot in ss.BOTS:
        e = _estado_de(ss, tmp_path, bot)
        assert e["tem_sessao"] is False
        assert e["ultima_atualizacao"] is None
        assert "sem" in e["detalhe"] or "ausente" in e["detalhe"]


def test_gupy_perfil_persistente(ss, tmp_path):
    base = tmp_path / "sessions" / "gupy" / "chromium"
    base.mkdir(parents=True)
    (base / "marker").write_text("x")
    e = _estado_de(ss, tmp_path, "gupy")
    assert e["tem_sessao"] is True
    assert "chromium" in e["detalhe"]
    assert e["ultima_atualizacao"]


def test_gupy_pasta_vazia_nao_conta(ss, tmp_path):
    (tmp_path / "sessions" / "gupy" / "chromium").mkdir(parents=True)
    assert _estado_de(ss, tmp_path, "gupy")["tem_sessao"] is False


def test_indeed_precisa_dos_dois_pickles(ss, tmp_path):
    (tmp_path / "indeed_session.pkl").write_bytes(b"\x80")
    parcial = _estado_de(ss, tmp_path, "indeed")
    assert parcial["tem_sessao"] is False
    assert "parcial" in parcial["detalhe"]
    (tmp_path / "google_session.pkl").write_bytes(b"\x80")
    completo = _estado_de(ss, tmp_path, "indeed")
    assert completo["tem_sessao"] is True
    assert completo["ultima_atualizacao"]


def test_solides_json(ss, tmp_path):
    e0 = _estado_de(ss, tmp_path, "solides")
    assert e0["tem_sessao"] is False
    (tmp_path / "solides_session.json").write_text("[]")
    e1 = _estado_de(ss, tmp_path, "solides")
    assert e1["tem_sessao"] is True
    assert "storage_state" in e1["detalhe"]


@pytest.mark.parametrize("bot,chaves", [
    ("infojobs", ["INFOJOBS_EMAIL", "INFOJOBS_SENHA"]),
    ("nerdin", ["NERDIN_EMAIL", "NERDIN_SENHA"]),
])
def test_credenciais_env(ss, tmp_path, bot, chaves):
    e = _estado_de(ss, tmp_path, bot)
    assert e["tem_sessao"] is False
    assert all(c in e["detalhe"] for c in chaves)
    env = tmp_path / ".env"
    env.write_text("\n".join(f"{c}=valor-fake" for c in chaves), encoding="utf-8")
    e2 = _estado_de(ss, tmp_path, bot)
    assert e2["tem_sessao"] is True
    # valor do .env nunca vaza para a resposta
    assert "valor-fake" not in str(e2)


def test_env_parcial_nao_basta(ss, tmp_path):
    (tmp_path / ".env").write_text("INFOJOBS_EMAIL=a@b.c\n", encoding="utf-8")
    assert _estado_de(ss, tmp_path, "infojobs")["tem_sessao"] is False


# ═══ deslogar (apaga só a sessão local; .env nunca é tocado) ═══

def test_estados_marca_deslogavel_por_bot(ss, tmp_path):
    for bot in ss.BOTS:
        e = _estado_de(ss, tmp_path, bot)
        assert e["deslogavel"] is (bot in ss.COM_SESSAO_LOCAL)


def test_deslogar_gupy_apaga_os_perfis(ss, tmp_path):
    for engine in ("chromium", "firefox"):
        d = tmp_path / "sessions" / "gupy" / engine
        d.mkdir(parents=True)
        (d / "marker").write_text("x")
    removidos = ss.deslogar(tmp_path, "gupy")
    assert len(removidos) == 2
    assert not any((tmp_path / "sessions" / "gupy").iterdir())
    assert _estado_de(ss, tmp_path, "gupy")["tem_sessao"] is False


def test_deslogar_indeed_apaga_pickles(ss, tmp_path):
    (tmp_path / "indeed_session.pkl").write_bytes(b"\x80")
    (tmp_path / "google_session.pkl").write_bytes(b"\x80")
    removidos = ss.deslogar(tmp_path, "indeed")
    assert removidos == ["indeed_session.pkl", "google_session.pkl"]
    assert not (tmp_path / "indeed_session.pkl").exists()
    assert not (tmp_path / "google_session.pkl").exists()


def test_deslogar_indeem_parcial_so_apaga_o_que_existe(ss, tmp_path):
    (tmp_path / "indeed_session.pkl").write_bytes(b"\x80")
    removidos = ss.deslogar(tmp_path, "indeed")
    assert removidos == ["indeed_session.pkl"]


def test_deslogar_solides_apaga_storage_state(ss, tmp_path):
    (tmp_path / "solides_session.json").write_text("[]")
    removidos = ss.deslogar(tmp_path, "solides")
    assert removidos == ["solides_session.json"]
    assert not (tmp_path / "solides_session.json").exists()


@pytest.mark.parametrize("bot", ["nerdin", "infojobs"])
def test_deslogar_sem_sessao_local_recusa(ss, tmp_path, bot):
    env = tmp_path / ".env"
    chaves = ss._ENV_CREDENCIAIS[bot]
    env.write_text("\n".join(f"{c}=segredo-fake" for c in chaves), encoding="utf-8")
    with pytest.raises(ValueError, match=r"credenciais no \.env"):
        ss.deslogar(tmp_path, bot)
    # .env nunca é tocado pelo deslogar
    assert "segredo-fake" in env.read_text(encoding="utf-8")


def test_deslogar_bot_desconhecido_recusa(ss, tmp_path):
    with pytest.raises(ValueError, match="desconhecido"):
        ss.deslogar(tmp_path, "xpto")


def test_deslogar_idempotente_sem_nada_para_apagar(ss, tmp_path):
    assert ss.deslogar(tmp_path, "gupy") == []
    assert ss.deslogar(tmp_path, "indeed") == []
    assert ss.deslogar(tmp_path, "solides") == []
