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


class _ObjetoComClose:
    def close(self):
        pass


class _PlaywrightFake:
    """Context manager que finge sync_playwright() — devolve um p qualquer."""
    def __enter__(self):
        return object()

    def __exit__(self, *_):
        return False


def test_solo_login_nao_pula_por_hora_ou_limite(solides_mod, monkeypatch):
    """Regressão (mesmo caso do Indeed): o botão "Logar" fora do horário
    (06h–23h) encerrava com exit 0 SEM garantir a sessão — a UI mostrava
    "concluído" inventado. No modo login-só os guards de negócio não valem:
    fazer_login roda de qualquer forma; exit 0 só com sessão salva."""
    chamadas = {"fazer_login": 0}

    def _fazer_login_falso(_p):
        chamadas["fazer_login"] += 1
        return _ObjetoComClose(), _ObjetoComClose(), _ObjetoComClose()

    monkeypatch.setattr(solides_mod.loginonly, "ativo", lambda: True)
    monkeypatch.setattr(solides_mod, "sync_playwright", _PlaywrightFake)
    monkeypatch.setattr(solides_mod, "fazer_login", _fazer_login_falso)
    monkeypatch.setattr(solides_mod, "horario_ok", lambda: False)
    monkeypatch.setattr(solides_mod, "carregar_relatorio", lambda: {"ja_candidatado": []})
    monkeypatch.setattr(solides_mod, "candidaturas_hoje",
                        lambda _rel: solides_mod.MAX_POR_DIA)

    solides_mod.main()
    assert chamadas["fazer_login"] == 1


def test_hora_e_limite_valem_ainda_no_fluxo_normal(solides_mod, monkeypatch):
    """Sem login-only, fora do horário permitido main() encerra ANTES do
    browser abrir — o guard segue valendo para o fluxo de candidatura."""
    chamadas = {"fazer_login": 0}

    def _fazer_login_falso(_p):
        chamadas["fazer_login"] += 1
        return _ObjetoComClose(), _ObjetoComClose(), _ObjetoComClose()

    monkeypatch.setattr(solides_mod, "fazer_login", _fazer_login_falso)
    monkeypatch.setattr(solides_mod, "horario_ok", lambda: False)

    solides_mod.main()
    assert chamadas["fazer_login"] == 0
