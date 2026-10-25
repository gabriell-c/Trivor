"""
Testes dos helpers compartilhados de crash recovery (common/browser.py):
aba_morta e reabrir_aba — o anti-bot do GUPY/Sólides derruba a aba
("Target crashed") e o bot reabre uma nova no MESMO context (a sessão
persiste). Sem browser real: páginas fake cobrem os três estados.
"""
import sys
from pathlib import Path

APPLY_DIR = Path(__file__).parent.parent / "apply"
sys.path.insert(0, str(APPLY_DIR))

from common import browser as bmod


class ContextoFalso:
    def __init__(self):
        self.criadas: list = []

    def new_page(self):
        p = PaginaViva(self)
        self.criadas.append(p)
        return p


class PaginaViva:
    def __init__(self, context):
        self.context = context
        self.fechada = False
        self.crashada = False
        self.timeouts: list = []

    def is_closed(self):
        return self.fechada

    def evaluate(self, _expr):
        if self.crashada:
            raise RuntimeError("Target closed")
        return 1

    def close(self):
        self.fechada = True

    def set_default_timeout(self, ms):
        self.timeouts.append(ms)


def _pagina(**atributos):
    p = PaginaViva(ContextoFalso())
    for chave, valor in atributos.items():
        setattr(p, chave, valor)
    return p


def test_aba_saudavel_nao_e_morta():
    assert bmod.aba_morta(_pagina()) is False


def test_aba_crashada_e_morta():
    assert bmod.aba_morta(_pagina(crashada=True)) is True


def test_aba_fechada_e_morta():
    assert bmod.aba_morta(_pagina(fechada=True)) is True


def test_reabrir_cria_aba_nova_e_fecha_a_original():
    context = ContextoFalso()
    original = PaginaViva(context)
    original.crashada = True

    nova = bmod.reabrir_aba(original)

    assert nova in context.criadas
    assert original.fechada is True
    assert nova.timeouts[-1] == 30000


def test_reabrir_com_contexto_que_falha_nao_quebra_a_original_nao_criada():
    # new_page pode estourar no anti-bot — a original é fechada por
    # contextlib.suppress e a exceção do new_page propaga
    class ContextoFalsoQuebrado:
        def new_page(self):
            raise RuntimeError("anti-bot bloqueou")

    original = PaginaViva(None)
    original.context = ContextoFalsoQuebrado()
    try:
        bmod.reabrir_aba(original)
    except RuntimeError:
        pass
    else:
        raise AssertionError("deveria propagar a falha do new_page")
