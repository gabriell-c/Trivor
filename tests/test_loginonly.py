"""
Testes do modo login-só (apply/common/loginonly.py) — a chave do botão
"Logar" da UI: o runner define TRIVOR_LOGIN_ONLY=1 e os 5 bots cortam o
fluxo após garantir a sessão.
"""
import importlib.util
from pathlib import Path

APPLY_DIR = Path(__file__).parent.parent / "apply"


def _carregar():
    spec = importlib.util.spec_from_file_location(
        "trivor_loginonly_teste", APPLY_DIR / "common" / "loginonly.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_inativo_por_padrao(monkeypatch):
    monkeypatch.delenv("TRIVOR_LOGIN_ONLY", raising=False)
    assert _carregar().ativo() is False


def test_ativo_com_1(monkeypatch):
    monkeypatch.setenv("TRIVOR_LOGIN_ONLY", "1")
    assert _carregar().ativo() is True


def test_ativo_tolera_espacos(monkeypatch):
    monkeypatch.setenv("TRIVOR_LOGIN_ONLY", " 1 ")
    assert _carregar().ativo() is True


def test_inativo_com_zero(monkeypatch):
    monkeypatch.setenv("TRIVOR_LOGIN_ONLY", "0")
    assert _carregar().ativo() is False
