"""
Simulação do login-só do Indeed SEM browser real — cobre exatamente o bug
da sessão anterior ("o navegador fechava antes de eu logar"): o runner sobe
o bot com TRIVOR_LOGIN_POLL=1 e stdin em DEVNULL, e o bot PRECISA cair no
ramo de polling (não em input(), que vira EOFError sem TTY).

O módulo é pesado (selenium/groq/config.yaml com path relativo), então o
fixture faz chdir para apply/ e carrega por spec com o env do runner.
"""
import importlib.util
import sys
import time
from pathlib import Path

import pytest

APPLY_DIR = Path(__file__).parent.parent / "apply"


@pytest.fixture
def indeed_mod(monkeypatch):
    # O MESMO env que o start_login define — é esse contrato que o teste
    # garante (flag de polling vence o isatty() mentiroso do Git-Bash)
    monkeypatch.setenv("TRIVOR_LOGIN_ONLY", "1")
    monkeypatch.setenv("TRIVOR_LOGIN_POLL", "1")
    monkeypatch.chdir(APPLY_DIR)
    monkeypatch.syspath_prepend(str(APPLY_DIR))
    sys.modules.pop("indeed", None)
    spec = importlib.util.spec_from_file_location(
        "trivor_indeed_teste", APPLY_DIR / "indeed.py")
    mod = importlib.util.module_from_spec(spec)
    # registra com o nome do spec: o módulo tem dataclass com InitVar, e o
    # dataclasses resolve cls.__module__ por sys.modules (None → crash)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class RelogioFake:
    def __init__(self, passo: float = 1.0):
        self._t = 0.0
        self._passo = passo

    def time(self):
        self._t += self._passo
        return self._t


def _relolgio_fake(monkeypatch, passo: float):
    relogio = RelogioFake(passo)
    monkeypatch.setattr(time, "time", relogio.time)
    monkeypatch.setattr(time, "sleep", lambda _ms: None)
    return relogio


def test_contrato_do_runner_garante_modo_polling(indeed_mod):
    # Regressão do bug: sem a flag, isatty() podia mentir e o bot ia para
    # input() → EOFError no DEVNULL → browser fechado sem chance de login
    assert indeed_mod._INTERATIVO is False


def test_polling_detecta_o_login_do_google(indeed_mod, monkeypatch):
    _relolgio_fake(monkeypatch, passo=1.0)
    chamadas = {"n": 0}

    def detectar():
        chamadas["n"] += 1
        return chamadas["n"] >= 3

    assert indeed_mod._aguardar_login("ENTER", detectar, timeout_min=50) is True
    assert chamadas["n"] >= 3


def test_polling_estoura_no_prazo_se_ninguem_loga(indeed_mod, monkeypatch):
    # passo de 6s por tick: 50 min simulados em ~500 giros rápidos
    _relolgio_fake(monkeypatch, passo=6.0)
    assert indeed_mod._aguardar_login("ENTER", lambda: False, timeout_min=50) is False


def test_ramo_interativo_mantem_o_input_original(indeed_mod, monkeypatch):
    """Comum a terminais: o ramo original (ENTER) continua intacto."""
    monkeypatch.setattr(indeed_mod, "_INTERATIVO", True)
    entradas = []
    monkeypatch.setattr("builtins.input", lambda msg: entradas.append(msg) or "x")
    assert indeed_mod._aguardar_login("pressione ENTER", lambda: None) is True
    assert entradas == ["pressione ENTER"]


class _DriverFalso:
    def quit(self):
        pass


def test_solo_login_nao_pula_por_hora_ou_limite(indeed_mod, monkeypatch):
    """Regressão (indeed-login.log 01:41): o botão "Logar" fora do horário
    permitido encerrava com exit 0 SEM fazer o login, e a UI mostrava
    "login concluído — sessão atualizada" sem sessão nenhuma. No modo
    login-só, os guards de negócio (horário/limite diário) não valem: o
    login acontece de qualquer forma; exit 0 só com sessão salva."""
    chamadas = {"fazer_login": 0}

    def _fazer_login_falso():
        chamadas["fazer_login"] += 1
        return _DriverFalso()

    monkeypatch.setattr(indeed_mod, "fazer_login", _fazer_login_falso)
    monkeypatch.setattr(indeed_mod, "horario_ok", lambda: False)
    monkeypatch.setattr(indeed_mod, "carregar_relatorio", lambda: {"ja_candidatado": []})
    monkeypatch.setattr(indeed_mod, "candidaturas_hoje",
                       lambda _rel: indeed_mod.MAX_POR_DIA)

    indeed_mod.main()  # exit 0 com o login executado
    assert chamadas["fazer_login"] == 1


def test_hora_e_limite_valem_ainda_no_fluxo_normal(indeed_mod, monkeypatch):
    """O guard de horário/limite segue valendo para o fluxo de
    candidatura (sem TRIVOR_LOGIN_ONLY): fora do horário, não loga, não
    busca — encerra quieto."""
    monkeypatch.delenv("TRIVOR_LOGIN_ONLY")
    chamadas = {"fazer_login": 0}

    def _fazer_login_falso():
        chamadas["fazer_login"] += 1
        return _DriverFalso()

    monkeypatch.setattr(indeed_mod, "fazer_login", _fazer_login_falso)
    monkeypatch.setattr(indeed_mod, "horario_ok", lambda: False)

    indeed_mod.main()
    assert chamadas["fazer_login"] == 0
