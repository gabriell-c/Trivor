"""Rede de teste das REGRAS PURAS dos bots de apply (split seguro).

Objetivo: proteger a lógica pura (decisão por texto/URL/dict, sem Selenium)
de `indeed.py` e `gupy.py` — hoje SEM cobertura. É essa rede que torna o
futuro "split seguro" (extração de regras p/ módulos) reversível: se uma
refatoração mudar o comportamento de uma regra, um destes testes estoura.

Nada aqui toca a orquestração Selenium (`driver`); só as funções puras.

Como os módulos são pesados (selenium/groq/config.yaml com path relativo),
carregamos cada um UMA vez por módulo de teste via importlib (mesmo
contrato do fixture de test_indeed_login.py), isolando CWD/sys.path e
restaurando ao fim.

Executar: pytest tests/test_bot_regras_puras.py
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
APPLY_DIR = REPO / "apply"

_BOT_CACHE: dict[str, object] = {}


def _load_bot(nome: str):
    """Importa `nome.py` de apply/ UMA vez (cache), sem rodar o bot.

    Faz chdir p/ apply/ (config.yaml é relativo) + sys.path, executa o
    módulo e RESTAURA CWD/sys.path ao fim — não polui o resto da suíte."""
    if nome in _BOT_CACHE:
        return _BOT_CACHE[nome]

    old_cwd = os.getcwd()
    old_path = list(sys.path)
    old_env = {k: os.environ.get(k) for k in ("TRIVOR_LOGIN_ONLY", "TRIVOR_LOGIN_POLL")}
    try:
        os.chdir(APPLY_DIR)
        sys.path.insert(0, str(APPLY_DIR))
        os.environ.setdefault("TRIVOR_LOGIN_ONLY", "1")
        os.environ.setdefault("TRIVOR_LOGIN_POLL", "1")
        for mod in sys.modules.copy():
            if mod in ("indeed", "gupy") or mod.startswith(("indeed_", "gupy_")):
                sys.modules.pop(mod, None)
        spec = importlib.util.spec_from_file_location(nome, APPLY_DIR / f"{nome}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[nome] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old_path
        os.chdir(old_cwd)
        for k, v in old_env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    _BOT_CACHE[nome] = mod
    return mod


@pytest.fixture(scope="module")
def indeed():
    return _load_bot("indeed")


@pytest.fixture(scope="module")
def gupy():
    return _load_bot("gupy")


@pytest.fixture(scope="module")
def solides():
    return _load_bot("solides")


# ---------------------------------------------------------------------------
# solides.py — filtragem de vaga (título + badges)
# ---------------------------------------------------------------------------
class TestFiltrarVagaSolides:
    def test_senior_no_titulo_sem_nivel_baixo_eh_excluido(self, solides):
        # "Sênior" é token de senioridade no título + sem júnior/jr/estágio → sai
        assert solides._filtrar_vaga("Analista de Sênior", None) is False

    def test_titulo_neutro_sem_senioridade_eh_mantido(self, solides):
        assert solides._filtrar_vaga("Analista de Dados", None) is True

    def test_nivel_baixo_no_titulo_nao_eh_excluido(self, solides):
        # "Júnior" não é token de senioridade (é nível baixo) → não cai no loop de título
        assert solides._filtrar_vaga("Analista Júnior", None) is True


# ---------------------------------------------------------------------------
# indeed.py — detecção de campos de data (label)
# ---------------------------------------------------------------------------
class TestLabelDataIndeed:
    @pytest.mark.parametrize("label", [
        "Data de Nascimento", "Qual a sua data nasc.", "BIRTHDAY", "aniversário",
    ])
    def test_nascimento_positivo(self, indeed, label):
        assert indeed._label_eh_nascimento(label) is True

    @pytest.mark.parametrize("label", ["Qual seu nome", "Salário esperado", "E-mail", "Telhado"])
    def test_nascimento_negativo(self, indeed, label):
        assert indeed._label_eh_nascimento(label) is False

    @pytest.mark.parametrize("label", [
        "Quando pode começar?", "Data de início", "Início do contrato", "start date",
    ])
    def test_data_inicio_positivo(self, indeed, label):
        assert indeed._label_eh_data_inicio(label) is True

    @pytest.mark.parametrize("label", ["Salário", "Nome", "Endereço", "Telhado"])
    def test_data_inicio_negativo(self, indeed, label):
        assert indeed._label_eh_data_inicio(label) is False


# ---------------------------------------------------------------------------
# indeed.py — identificação de etapa pela URL
# ---------------------------------------------------------------------------
class TestIdentificarEtapa:
    def test_mapeia_fragmentos(self, indeed):
        assert indeed._identificar_etapa("https://x/portal/apply/resume?id=1") == "curriculo"
        assert indeed._identificar_etapa("https://x/portal/question?i=2") == "perguntas"
        assert indeed._identificar_etapa("https://x/portal/submit?i=3") == "revisao"
        assert indeed._identificar_etapa("https://x/portal/cover-letter?i=4") == "revisao"

    def test_desconhecida_quando_nao_ha_fragmento(self, indeed):
        assert indeed._identificar_etapa("https://x/portal/outra-tela?i=5") == "desconhecida"

    def test_case_insensitive(self, indeed):
        assert indeed._identificar_etapa("https://X/RESUME?i=6") == "curriculo"


# ---------------------------------------------------------------------------
# indeed.py — filtragem de vaga por título
# ---------------------------------------------------------------------------
class TestFiltrarVagaIndeed:
    def test_aceita_termo_relevante(self, indeed):
        assert indeed.filtrar_vaga("Desenvolvedor Python Pleno") is True
        assert indeed.filtrar_vaga("Júnior React Developer") is True
        assert indeed.filtrar_vaga("Estágio em Web") is True

    def test_rejeita_sem_termo_relevante(self, indeed):
        assert indeed.filtrar_vaga("Gerente de Contas Bancárias") is False


# ---------------------------------------------------------------------------
# gupy.py — formatação de respostas (puro)
# ---------------------------------------------------------------------------
class TestFormatarRespostasGupy:
    def test_vazio_vira_placeholder(self, gupy):
        assert gupy._formatar_respostas_txt({}) == "    (sem perguntas respondidas)\n"

    def test_apresentacao_pessoal_quebra_linha_a_linha(self, gupy):
        saida = gupy._formatar_respostas_txt({"Apresentação pessoal": "linha1\nlinha2"})
        assert "Apresentação pessoal:" in saida
        assert "       linha1" in saida and "       linha2" in saida

    def test_valor_curto_vai_na_mesma_linha(self, gupy):
        saida = gupy._formatar_respostas_txt({"Idioma": "Inglês"})
        assert "📌 Idioma: Inglês" in saida

    def test_valor_longo_quebra_linha(self, gupy):
        longo = "x" * 90
        saida = gupy._formatar_respostas_txt({"Currículo": longo})
        # chave sozinha numa linha, valor na seguinte (len > 80)
        assert f"📌 Currículo:\n       {longo}" in saida


# ---------------------------------------------------------------------------
# gupy.py — filtragem por palavras de exclusão (fronteira de palavra)
# ---------------------------------------------------------------------------
class TestFiltrarVagaGupy:
    def test_titulo_livre_eh_mantido(self, gupy):
        cfg = {"busca": {"palavras_excluir": []}}
        assert gupy.filtrar_vaga("Analista de Suporte", cfg) is True

    def test_titulo_excluido_caai(self, gupy):
        cfg = {"busca": {"palavras_excluir": ["gerente"]}}
        assert gupy.filtrar_vaga("Gerente Comercial", cfg) is False

    def test_exclusao_respeita_fronteira_de_palavra(self, gupy):
        # "java" (negativa) NÃO pode derrubar "Javascript": fronteira de palavra
        cfg = {"busca": {"palavras_excluir": ["java"]}}
        assert gupy.filtrar_vaga("Desenvolvedor Javascript", cfg) is True
