"""
Testes de fronteira de palavra de perfil.titulo_excluido (comum/perfil.py) —
o helper que os 5 bots usam para filtrar vagas pela lista negativa:
"java" precisa excluir "Analista Java" SEM excluir "Analista Javascript".
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _carregar_perfil():
    p = ROOT / 'apply' / 'common' / 'perfil.py'
    spec = importlib.util.spec_from_file_location('apply_perfil_exclusao', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


perfil = _carregar_perfil()
T = perfil.titulo_excluido


def test_palavra_simples_exclui():
    assert T('Analista Java', ['java']) == 'java'


def test_fronteira_nao_exclui_superstring():
    # o bug que motivou o helper: "java" dentro de "Javascript"
    assert T('Analista Javascript', ['java']) is None


def test_caixa_ignorada():
    assert T('DEV JAVA SÊNIOR', ['java']) == 'java'


def test_acentuacao_conta_palavra_diferente():
    # "senior" (sem acento) não pega "Sênior" — chars acentuados são \w
    assert T('Dev Sênior', ['senior']) is None
    assert T('Dev Sênior', ['sênior']) == 'sênior'


def test_multipalavra_com_espaço():
    assert T('Analista de Backend de Pagas Pleno', ['backend de pagas']) == 'backend de pagas'
    assert T('Analista de Backend de Pagamentos', ['backend de pagas']) is None


def test_prefixo_dentro_de_palavra_nao_exclui():
    assert T('Python Developer', ['py']) is None


def test_c_com_simbolo_exclui():
    assert T('Programador C#', ['c']) == 'c'


def test_pontuacao_termina_a_palavra():
    assert T('Jr. Developer', ['jr.']) == 'jr.'


def test_titulo_vazio_ou_lista_vazia():
    assert T('', ['java']) is None
    assert T('Analista Java', []) is None
    assert T('Analista Java', None) is None


def test_whitespaces_do_titulo_sao_normalizados():
    assert T('Analista   Java', ['java']) == 'java'
