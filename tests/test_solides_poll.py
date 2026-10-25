"""
Testes do polling de login manual do Sólides (apply/solides.py →
_aguardar_login_manual) — o fallback do botão "Logar" da UI quando o
login automático (SOLIDES_EMAIL/SENHA) falha: o bot pola a janela aberta
até o usuário logar, sem depender de TTY ("ENTER" não existe no runner).

O módulo é pesado (playwright, groq, config.yaml com path relativo), então
o fixture faz chdir para apply/ e carrega por spec. O login em si é
fingado: page fake + sessao_valida patcheada + relógio fake no timeout.
"""
import importlib.util
import sys
import time
from pathlib import Path

import pytest

APPLY_DIR = Path(__file__).parent.parent / "apply"


@pytest.fixture
def solides_mod(monkeypatch):
    monkeypatch.chdir(APPLY_DIR)
    monkeypatch.syspath_prepend(str(APPLY_DIR))
    sys.modules.pop("solides", None)
    spec = importlib.util.spec_from_file_location(
        "trivor_solides_teste", APPLY_DIR / "solides.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class PageFalso:
    """Imita o Page do Playwright só no que o polling toca: .url e
    wait_for_timeout (no-op — o tempo real é controlado pelo relógio fake)."""

    def __init__(self, url: str, flip_apos: int = 0):
        self.url = url
        self.polls = 0
        self._flip_apos = flip_apos

    def wait_for_timeout(self, _ms: int):
        self.polls += 1
        if self._flip_apos and self.polls >= self._flip_apos:
            self.url = "https://vagas.solides.com.br/"


class RelogioFake:
    def __init__(self, passo: float = 40.0):
        self._t = 0.0
        self._passo = passo

    def monotonic(self):
        self._t += self._passo
        return self._t


URL_SIGN_IN = "https://auth.vagas.solides.com.br/sign-in"


def test_poll_detecta_o_login_e_encerra(solides_mod, monkeypatch):
    monkeypatch.setattr(
        solides_mod, "sessao_valida",
        lambda p: "sign-in" not in p.url.lower())
    page = PageFalso(URL_SIGN_IN, flip_apos=2)
    assert solides_mod._aguardar_login_manual(page, 50) is True
    assert page.polls >= 2


def test_poll_estoura_no_prazo_se_ninguem_loga(solides_mod, monkeypatch):
    monkeypatch.setattr(time, "monotonic", RelogioFake().monotonic)
    monkeypatch.setattr(solides_mod, "sessao_valida", lambda p: False)
    page = PageFalso(URL_SIGN_IN)
    assert solides_mod._aguardar_login_manual(page, 50) is False
    # 50 min simulados (40s por tick do relógio fake) — o loop manteve o
    # polling vivo; o número exato depende da estrutura interna, só precisa
    # de muitos giros
    assert page.polls >= 30
