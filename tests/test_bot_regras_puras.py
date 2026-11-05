"""Rede de teste das REGRAS PURAS dos bots de apply (split seguro).

Objetivo: proteger a lógica pura (decisão por texto/URL/dict, sem Selenium)
de `indeed.py`, `gupy.py` e `indeed_regras.py` (motor de regras do Indeed) —
antes SEM cobertura. É essa rede que torna o "split seguro" reversível: se
uma refatoração mudar o comportamento de uma regra, um destes testes estoura.

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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


@pytest.fixture(scope="module")
def regras():
    """Motor determinístico extraído do indeed.py (indeed_regras.py).

    Sem Selenium no import — mas lê config.yaml/.env relativos, por isso o
    mesmo contrato de chdir+importlib do _load_bot."""
    return _load_bot("indeed_regras")


# Candidato sintético p/ regras que leem ctx.c — os valores reais do
# config.yaml/.env (PII) NUNCA aparecem em assert; onde uma regra lê o
# .env (_DOC_*/_END_*), o teste monkeypatcheia o atributo do módulo.
CANDIDATO_TESTE = {
    "linkedin": "linkedin.com/in/candidato",
    "github": "github.com/candidato",
    "portfolio": "meuportfolio.com",
    "email": "candidato@exemplo.com",
    "telefone": "(16) 99999-0000",
    "nome": "Candidato Teste",
    "data_nascimento": "01/01/1990",
}


def _ctx(regras, pergunta, tipo="texto", opcoes=None, c=None, div=None,
         contexto_vaga="", **end):
    """_CtxRegras de teste com endereço neutro (evita vazar PII da config)."""
    base = {"pais": "Brasil", "estado_nome": "Rialdo", "estado_uf": "RD",
            "cidade": "Vila Teste", "bairro": "Centro", "logradouro": "Rua Um",
            "numero": "123", "complemento": "", "cep": "14010-000"}
    base.update(end)
    # pergunta é pré-normalizada no contrato real (o resolver faz
    # .lower().strip() antes de montar o ctx) — as regras assumem isso.
    return regras._CtxRegras(
        c=CANDIDATO_TESTE if c is None else c,
        div={} if div is None else div,
        contexto_vaga=contexto_vaga,
        pergunta=pergunta.lower().strip(), tipo=tipo, opcoes=opcoes or [],
        **base,
    )


def _limpar_end(regras, monkeypatch):
    """Desliga os env de endereço sensíveis capturados no import do módulo."""
    for nome in ("_END_BAIRRO", "_END_LOGRADOURO", "_END_NUMERO",
                 "_END_CEP", "_END_COMPLEMENTO"):
        monkeypatch.setattr(regras, nome, "")


# ---------------------------------------------------------------------------
# indeed_regras.py — data de nascimento
# ---------------------------------------------------------------------------
class TestRegraDataNascimento:
    def test_pergunta_nascimento_texto(self, regras):
        assert regras._regra_data_nascimento(_ctx(regras, "data de nascimento")) \
            == (True, "01/01/1990")

    def test_tipo_date_com_pergunta_neutra(self, regras):
        assert regras._regra_data_nascimento(
            _ctx(regras, "informe a data", tipo="date")) == (True, "01/01/1990")

    def test_pergunta_inglesa(self, regras):
        assert regras._regra_data_nascimento(
            _ctx(regras, "what is your date of birth?")) == (True, "01/01/1990")

    @pytest.mark.parametrize("pergunta", [
        "qual a sua comida favorita?", "quantos irmãos você tem?",
    ])
    def test_irrelevante_passa_o_turno(self, regras, pergunta):
        assert regras._regra_data_nascimento(_ctx(regras, pergunta)) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — gênero
# ---------------------------------------------------------------------------
class TestRegraGenero:
    def test_radio_masculino(self, regras):
        ctx = _ctx(regras, "qual o seu gênero?", tipo="radio",
                   opcoes=["Feminino", "Masculino", "Outro"],
                   div={"genero": "Masculino"})
        assert regras._regra_genero(ctx) == (True, 1)

    def test_radio_feminino(self, regras):
        ctx = _ctx(regras, "qual o seu gênero?", tipo="radio",
                   opcoes=["Feminino", "Masculino"],
                   div={"genero": "Feminino"})
        assert regras._regra_genero(ctx) == (True, 0)

    def test_texto_devolve_config(self, regras):
        ctx = _ctx(regras, "gênero", div={"genero": "Prefiro não informar"})
        assert regras._regra_genero(ctx) == (True, "Prefiro não informar")

    def test_opcoes_ilegiveis_assume_indice(self, regras):
        # opções parecem IDs React → convenção Indeed: 0 = masc, 1 = fem
        ctx = _ctx(regras, "gênero", tipo="radio",
                   opcoes=["obj:r1abc:p:0", "obj:r1def:p:1"],
                   div={"genero": "Feminino"})
        assert regras._regra_genero(ctx) == (True, 1)

    def test_pergunta_irrelevante(self, regras):
        assert regras._regra_genero(
            _ctx(regras, "qual seu nome?")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — PCD
# ---------------------------------------------------------------------------
class TestRegraPcd:
    def test_checkbox_sem_pcd_devolve_lista_vazia(self, regras):
        ctx = _ctx(regras, "você é PCD?", tipo="checkbox")
        assert regras._regra_pcd(ctx) == (True, [])

    def test_radio_sem_pcd_marca_nao(self, regras):
        ctx = _ctx(regras, "você tem alguma deficiência?", tipo="radio",
                   opcoes=["Sim", "Não"])
        assert regras._regra_pcd(ctx) == (True, 1)

    def test_texto_sem_pcd(self, regras):
        ctx = _ctx(regras, "descreva sua deficiência")
        assert regras._regra_pcd(ctx) == (True, "Não possuo deficiência")

    def test_pcd_verdadeiro_nao_marca_nada(self, regras):
        ctx = _ctx(regras, "você é PCD?", tipo="checkbox", div={"pcd": True})
        assert regras._regra_pcd(ctx) == (False, None)

    def test_pergunta_irrelevante(self, regras):
        assert regras._regra_pcd(_ctx(regras, "qual seu nome?")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — grupo de diversidade
# ---------------------------------------------------------------------------
class TestRegraGrupoDiversidade:
    def test_radio_marca_opcao_neutra(self, regras):
        ctx = _ctx(regras, "em qual grupo você se enquadra?", tipo="radio",
                   opcoes=["Mulher", "Preta", "Não pertenço a nenhum dos grupos"])
        assert regras._regra_grupo_diversidade(ctx) == (True, 2)

    def test_checkbox_neutra_devolve_lista(self, regras):
        ctx = _ctx(regras, "grupos de diversidade aos quais você pertence",
                   tipo="checkbox",
                   opcoes=["Mulher", "Preta", "Não me identifico"])
        assert regras._regra_grupo_diversidade(ctx) == (True, [2])

    def test_sem_neutra_marca_raca_do_config(self, regras):
        ctx = _ctx(regras, "grupo de diversidade", tipo="radio",
                   opcoes=["Branca", "Parda", "Preta"],
                   div={"raca_cor": "Preta"})
        assert regras._regra_grupo_diversidade(ctx) == (True, 2)

    def test_sem_neutra_nem_raca_cai_no_prefiro_nao(self, regras):
        ctx = _ctx(regras, "grupo de diversidade", tipo="radio",
                   opcoes=["Branca", "Prefiro não responder"],
                   div={"raca_cor": "Parda"})
        assert regras._regra_grupo_diversidade(ctx) == (True, 1)

    def test_tipo_texto_nao_aplica(self, regras):
        assert regras._regra_grupo_diversidade(
            _ctx(regras, "grupo de diversidade")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — raça/cor
# ---------------------------------------------------------------------------
class TestRegraRaca:
    def test_radio_marca_cor_do_config(self, regras):
        ctx = _ctx(regras, "qual a sua cor?", tipo="radio",
                   opcoes=["Parda", "Branca"], div={"raca_cor": "Parda"})
        assert regras._regra_raca(ctx) == (True, 0)

    def test_texto_devolve_cor_do_config(self, regras):
        ctx = _ctx(regras, "qual sua etnia?", div={"raca_cor": "Preta"})
        assert regras._regra_raca(ctx) == (True, "Preta")

    def test_pergunta_irrelevante(self, regras):
        assert regras._regra_raca(_ctx(regras, "qual seu nome?")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — país
# ---------------------------------------------------------------------------
class TestRegraPais:
    def test_radio_por_nome_do_endereco(self, regras):
        ctx = _ctx(regras, "país de residência", tipo="radio",
                   opcoes=["Estados Unidos", "Brasil"])
        assert regras._regra_pais(ctx) == (True, 1)

    def test_alias_brazil(self, regras):
        ctx = _ctx(regras, "nacionalidade", tipo="radio",
                   opcoes=["Brazil", "USA"])
        assert regras._regra_pais(ctx) == (True, 0)

    def test_sem_correspondencia(self, regras):
        ctx = _ctx(regras, "país", tipo="radio", opcoes=["Alemanha"])
        assert regras._regra_pais(ctx) == (False, None)

    def test_tipo_texto_nao_aplica(self, regras):
        assert regras._regra_pais(_ctx(regras, "país")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — estado/UF
# ---------------------------------------------------------------------------
class TestRegraEstado:
    def test_radio_por_nome_do_endereco(self, regras):
        ctx = _ctx(regras, "em qual estado você mora?", tipo="radio",
                   opcoes=["Rio de Janeiro", "Rialdo"])
        assert regras._regra_estado(ctx) == (True, 1)

    def test_uf_sp_padrao(self, regras):
        ctx = _ctx(regras, "qual sua UF?", tipo="radio", opcoes=["SP", "RJ"])
        assert regras._regra_estado(ctx) == (True, 0)

    def test_sem_correspondencia(self, regras):
        ctx = _ctx(regras, "estado", tipo="radio", opcoes=["Acre"])
        assert regras._regra_estado(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — condicionais "Se outra" (outro + outra)
# ---------------------------------------------------------------------------
class TestRegraCondicionalOutro:
    def test_especifique_vira_pular(self, regras):
        assert regras._regra_condicional_outro(
            _ctx(regras, "especifique")) == (True, "PULAR")

    def test_if_yes_vira_pular(self, regras):
        assert regras._regra_condicional_outro(
            _ctx(regras, "if yes, please explain")) == (True, "PULAR")

    def test_tipo_radio_nao_aplica(self, regras):
        assert regras._regra_condicional_outro(
            _ctx(regras, "especifique", tipo="radio")) is None


class TestRegraCondicionalOutra:
    def test_se_marcou_outro_vira_pular(self, regras):
        assert regras._regra_condicional_outra(
            _ctx(regras, "se marcou outro, especifique")) == (True, "PULAR")

    def test_if_other_vira_pular(self, regras):
        assert regras._regra_condicional_outra(
            _ctx(regras, "if other, please specify")) == (True, "PULAR")

    def test_tipo_radio_nao_aplica(self, regras):
        assert regras._regra_condicional_outra(
            _ctx(regras, "if other", tipo="radio")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — segmento / último segmento
# ---------------------------------------------------------------------------
class TestRegraSegmento:
    def test_autonomo_tem_prioridade_sobre_tecnologia(self, regras):
        ctx = _ctx(regras, "qual seu ramo de atuação?", tipo="radio",
                   opcoes=["Tecnologia", "Autônomo", "Varejo"])
        assert regras._regra_segmento(ctx) == (True, 1)

    def test_tecnologia_quando_sem_autonomo(self, regras):
        ctx = _ctx(regras, "qual o segmento?", tipo="radio",
                   opcoes=["Varejo", "Tecnologia"])
        assert regras._regra_segmento(ctx) == (True, 1)

    def test_sem_opcao_reconhecida(self, regras):
        ctx = _ctx(regras, "segmento", tipo="radio", opcoes=["Varejo"])
        assert regras._regra_segmento(ctx) == (False, None)


class TestRegraUltimoSegmento:
    def test_autonomo(self, regras):
        ctx = _ctx(regras, "qual o último segmento trabalhado?", tipo="radio",
                   opcoes=["Varejo", "Autônomo"])
        assert regras._regra_ultimo_segmento(ctx) == (True, 1)

    def test_tecnologia(self, regras):
        ctx = _ctx(regras, "qual o último segmento?", tipo="radio",
                   opcoes=["Tecnologia", "Varejo"])
        assert regras._regra_ultimo_segmento(ctx) == (True, 0)

    def test_so_primeiro_emprego_nao_responde(self, regras):
        ctx = _ctx(regras, "último segmento", tipo="radio",
                   opcoes=["1º Emprego"])
        assert regras._regra_ultimo_segmento(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — origem / fonte da vaga
# ---------------------------------------------------------------------------
class TestRegraOrigem:
    def test_indeed_tem_prioridade(self, regras):
        ctx = _ctx(regras, "como você chegou até nós?", tipo="radio",
                   opcoes=["Google", "Indeed", "LinkedIn"])
        assert regras._regra_origem(ctx) == (True, 1)

    def test_linkedin_ao_sem_indeed(self, regras):
        ctx = _ctx(regras, "como chegou até aqui?", tipo="radio",
                   opcoes=["LinkedIn", "Google"])
        assert regras._regra_origem(ctx) == (True, 0)

    def test_google(self, regras):
        ctx = _ctx(regras, "como ficou sabendo?", tipo="radio",
                   opcoes=["Twitter", "Google"])
        assert regras._regra_origem(ctx) == (True, 1)

    def test_site(self, regras):
        ctx = _ctx(regras, "como conheceu a vaga?", tipo="radio",
                   opcoes=["Site da empresa", "Outro"])
        assert regras._regra_origem(ctx) == (True, 0)

    def test_sem_opcao_reconhecida(self, regras):
        ctx = _ctx(regras, "canal de indicação?", tipo="radio",
                   opcoes=["Amigos"])
        assert regras._regra_origem(ctx) == (False, None)


class TestRegraFonte:
    def test_indeed_primeiro(self, regras):
        ctx = _ctx(regras, "como ficou sabendo desta vaga?", tipo="radio",
                   opcoes=["LinkedIn", "Indeed"])
        assert regras._regra_fonte(ctx) == (True, 1)

    def test_google_antes_do_linkedin(self, regras):
        ctx = _ctx(regras, "fonte da vaga", tipo="radio",
                   opcoes=["Google", "LinkedIn"])
        assert regras._regra_fonte(ctx) == (True, 0)

    def test_fallback_outro(self, regras):
        ctx = _ctx(regras, "como conheceu?", tipo="radio",
                   opcoes=["Facebook", "Outro"])
        assert regras._regra_fonte(ctx) == (True, 1)

    def test_sem_opcao_reconhecida(self, regras):
        ctx = _ctx(regras, "fonte da vaga", tipo="radio",
                   opcoes=["Facebook"])
        assert regras._regra_fonte(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — mapa de texto (links, contato, endereço, disponibilidade)
# ---------------------------------------------------------------------------
class TestRegraMapaTexto:
    def test_linkedin(self, regras):
        assert regras._regra_mapa_texto(_ctx(regras, "qual seu linkedin?")) \
            == (True, "linkedin.com/in/candidato")

    def test_github(self, regras):
        assert regras._regra_mapa_texto(_ctx(regras, "seu github")) \
            == (True, "github.com/candidato")

    def test_email(self, regras):
        assert regras._regra_mapa_texto(_ctx(regras, "qual o seu email?")) \
            == (True, "candidato@exemplo.com")

    def test_nome_completo(self, regras):
        assert regras._regra_mapa_texto(_ctx(regras, "qual seu nome completo?")) \
            == (True, "Candidato Teste")

    def test_cidade_bairro_cep_do_endereco(self, regras):
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual sua cidade?")) == (True, "Vila Teste")
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual seu bairro?")) == (True, "Centro")
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual seu CEP?")) == (True, "14010-000")

    def test_disponibilidade_eh_data_de_hoje(self, regras):
        esperado = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
        assert regras._regra_mapa_texto(
            _ctx(regras, "quando pode começar?")) == (True, esperado)

    def test_empresa_e_cargo_atual(self, regras):
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual sua empresa atual?")) == (True, "Autônomo / Freelancer")
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual seu cargo atual?")) == (True, "Desenvolvedor Web Freelancer")

    def test_cargo_pretendido_eh_contextual_a_vaga(self, regras):
        ctx = _ctx(regras, "cargo pretendido?",
                   contexto_vaga="Vaga de estágio em dados")
        assert regras._regra_mapa_texto(ctx) \
            == (True, "Estagiário em Engenheiro de Dados")

    def test_cpf_vem_do_env_sensivel(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CPF", "123.456.789-09")
        assert regras._regra_mapa_texto(
            _ctx(regras, "informe seu CPF")) == (True, "123.456.789-09")

    def test_cpf_vazio_vira_pular(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CPF", "")
        assert regras._regra_mapa_texto(
            _ctx(regras, "informe seu CPF")) == (True, "PULAR")

    def test_pergunta_irrelevante(self, regras):
        assert regras._regra_mapa_texto(
            _ctx(regras, "qual a sua comida favorita?")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — documentos (tipo + número)
# ---------------------------------------------------------------------------
class TestRegraTipoDoc:
    def test_cpf_tem_prioridade(self, regras):
        ctx = _ctx(regras, "qual o tipo de documento?", tipo="radio",
                   opcoes=["RG", "CPF", "Passaporte"])
        assert regras._regra_tipo_doc(ctx) == (True, 1)

    def test_fallback_rg(self, regras):
        ctx = _ctx(regras, "tipo de documento", tipo="radio",
                   opcoes=["RG", "Passaporte"])
        assert regras._regra_tipo_doc(ctx) == (True, 0)

    def test_sem_doc_reconhecido(self, regras):
        ctx = _ctx(regras, "tipo de documento", tipo="radio",
                   opcoes=["Passaporte", "Título"])
        assert regras._regra_tipo_doc(ctx) == (False, None)


class TestRegraNumDoc:
    def test_cpf(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CPF", "111.222.333-44")
        ctx = _ctx(regras, "qual seu número de CPF?")
        assert regras._regra_num_doc(ctx) == (True, "111.222.333-44")

    def test_cpf_vazio_vira_pular(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CPF", "")
        ctx = _ctx(regras, "qual seu número de CPF?")
        assert regras._regra_num_doc(ctx) == (True, "PULAR")

    def test_cnh(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CNH", "888.777")
        ctx = _ctx(regras, "número da CNH")
        assert regras._regra_num_doc(ctx) == (True, "888.777")

    def test_rg(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_RG", "12.345.678-9")
        ctx = _ctx(regras, "número do RG")
        assert regras._regra_num_doc(ctx) == (True, "12.345.678-9")

    def test_documento_generico_assume_cpf(self, regras, monkeypatch):
        monkeypatch.setattr(regras, "_DOC_CPF", "999.888.777-66")
        ctx = _ctx(regras, "informe o número do documento")
        assert regras._regra_num_doc(ctx) == (True, "999.888.777-66")

    def test_tipo_radio_nao_aplica(self, regras):
        assert regras._regra_num_doc(
            _ctx(regras, "número do RG", tipo="radio")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — condições especiais
# ---------------------------------------------------------------------------
class TestRegraCondicoesEspeciais:
    def test_condicoes_especiais(self, regras):
        ctx = _ctx(regras, "condições especiais para trabalhar?")
        assert regras._regra_condicoes_especiais(ctx) \
            == (True, "Não possuo necessidades especiais.")

    def test_acessibilidade(self, regras):
        ctx = _ctx(regras, "você tem necessidades de acessibilidade?")
        assert regras._regra_condicoes_especiais(ctx) \
            == (True, "Não possuo necessidades especiais.")

    def test_tipo_radio_nao_aplica(self, regras):
        assert regras._regra_condicoes_especiais(
            _ctx(regras, "condições especiais", tipo="radio")) is None


# ---------------------------------------------------------------------------
# indeed_regras.py — nível de experiência
# ---------------------------------------------------------------------------
class TestRegraNivelExperiencia:
    def test_junior_em_vaga_normal(self, regras):
        ctx = _ctx(regras, "qual seu nível de experiência?", tipo="radio",
                   opcoes=["Estágio", "Júnior", "Pleno"])
        assert regras._regra_nivel_experiencia(ctx) == (True, 1)

    def test_estagio_em_vaga_de_estagio(self, regras):
        ctx = _ctx(regras, "qual seu nível?", tipo="radio",
                   opcoes=["Estágio", "Júnior"],
                   contexto_vaga="Vaga de estágio de desenvolvimento")
        assert regras._regra_nivel_experiencia(ctx) == (True, 0)

    def test_estagio_sem_opcao_cai_no_indice_zero(self, regras):
        ctx = _ctx(regras, "nível de experiência", tipo="radio",
                   opcoes=["Júnior", "Pleno"],
                   contexto_vaga="estágio")
        assert regras._regra_nivel_experiencia(ctx) == (True, 0)

    def test_pleno_como_fallback(self, regras):
        ctx = _ctx(regras, "senioridade?", tipo="radio",
                   opcoes=["Pleno", "Sênior"])
        assert regras._regra_nivel_experiencia(ctx) == (True, 0)

    def test_sem_opcao_reconhecida(self, regras):
        ctx = _ctx(regras, "nível de experiência", tipo="radio",
                   opcoes=["Sênior"])
        assert regras._regra_nivel_experiencia(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — área profissional
# ---------------------------------------------------------------------------
class TestRegraAreaProfissional:
    def test_tecnologia(self, regras):
        ctx = _ctx(regras, "qual sua área profissional?", tipo="radio",
                   opcoes=["Comércio", "Tecnologia da Informação", "Vendas"])
        assert regras._regra_area_profissional(ctx) == (True, 1)

    def test_software(self, regras):
        ctx = _ctx(regras, "área de atuação?", tipo="radio",
                   opcoes=["Software", "Varejo"])
        assert regras._regra_area_profissional(ctx) == (True, 0)

    def test_sem_ti_nao_responde(self, regras):
        ctx = _ctx(regras, "área profissional", tipo="radio",
                   opcoes=["Vendas", "Construção Civil"])
        assert regras._regra_area_profissional(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — pretensão salarial
# ---------------------------------------------------------------------------
class TestRegraPretensaoSalarial:
    def test_clt_padrao(self, regras):
        ctx = _ctx(regras, "qual a sua pretensão salarial?")
        assert regras._regra_pretensao_salarial(ctx) == (True, "3500")

    def test_clt_customizada(self, regras):
        ctx = _ctx(regras, "pretensão salarial?", c={"pretensao_clt": "4000"})
        assert regras._regra_pretensao_salarial(ctx) == (True, "4000")

    def test_salario_atual_vira_pular(self, regras):
        ctx = _ctx(regras, "qual a sua pretensão salarial atual?")
        assert regras._regra_pretensao_salarial(ctx) == (True, "PULAR")

    def test_estagio(self, regras):
        ctx = _ctx(regras, "qual a pretensão salarial para o estágio?",
                   c={"pretensao_estagio": "1500"})
        assert regras._regra_pretensao_salarial(ctx) == (True, "1500")

    def test_pj_por_hora(self, regras):
        ctx = _ctx(regras, "pretensão salarial para contrato PJ por hora?",
                   c={"pretensao_pj_hora": "25"})
        assert regras._regra_pretensao_salarial(ctx) == (True, "25")

    def test_pj_mensal(self, regras):
        ctx = _ctx(regras, "pretensão salarial (PJ)?", c={"pretensao_pj_mensal": "5000"})
        assert regras._regra_pretensao_salarial(ctx) == (True, "5000")

    def test_tipo_radio_nao_aplica(self, regras):
        ctx = _ctx(regras, "pretensão salarial?", tipo="radio")
        assert regras._regra_pretensao_salarial(ctx) == (False, None)


# ---------------------------------------------------------------------------
# indeed_regras.py — filiação (aborto da candidatura)
# ---------------------------------------------------------------------------
class TestPerguntaFiliacao:
    def test_portugues(self, regras):
        assert regras._contem_pergunta_filiacao("Qual o nome da sua mãe?") is True

    def test_normaliza_espacos_e_caixa(self, regras):
        assert regras._contem_pergunta_filiacao("  NOME  COMPLETO  DO  PAI ") is True

    def test_ingles(self, regras):
        assert regras._contem_pergunta_filiacao("What is your mother's name?") is True

    def test_negativo(self, regras):
        assert regras._contem_pergunta_filiacao("Qual o seu nome completo?") is False


# ---------------------------------------------------------------------------
# indeed_regras.py — inferência do cargo pretendido (contextual à vaga)
# ---------------------------------------------------------------------------
class TestInferirCargoPretendido:
    def test_estagio_de_dados(self, regras):
        assert regras._inferir_cargo_pretendido("Vaga de estágio em dados") \
            == "Estagiário em Engenheiro de Dados"

    def test_frontend(self, regras):
        assert regras._inferir_cargo_pretendido("Vaga de desenvolvedor React") \
            == "Desenvolvedor Frontend"

    def test_devops(self, regras):
        assert regras._inferir_cargo_pretendido("DevOps com AWS") \
            == "Engenheiro DevOps"

    def test_mobile(self, regras):
        assert regras._inferir_cargo_pretendido("Android developer") \
            == "Desenvolvedor Mobile"

    def test_contexto_vazio_usa_padrao(self, regras):
        assert regras._inferir_cargo_pretendido("") == "Desenvolvedor Web Fullstack"


# ---------------------------------------------------------------------------
# indeed_regras.py — resolver em série (primeira regra que reconhece decide)
# ---------------------------------------------------------------------------
class TestResolverPorRegra:
    def _isolar(self, regras, monkeypatch):
        """Config sintética — config.yaml/.env reais (PII) ficam de fora."""
        monkeypatch.setattr(regras, "CANDIDATO", CANDIDATO_TESTE)
        monkeypatch.setattr(regras, "CONFIG", {
            "candidato": CANDIDATO_TESTE,
            "endereco": {"estado_nome": "Rialdo", "estado_uf": "RD"},
            "diversidade": {},
        })
        _limpar_end(regras, monkeypatch)

    def test_filiacao_levanta_excecao(self, regras):
        with pytest.raises(regras._PerguntaFiliacaoDetectada):
            regras._resolver_por_regra(
                {"pergunta": "Qual o nome da sua mãe?", "tipo": "texto"}, "")

    def test_nao_reconhecido_vai_para_ia(self, regras, monkeypatch):
        self._isolar(regras, monkeypatch)
        res = regras._resolver_por_regra(
            {"pergunta": "Qual a sua comida favorita?", "tipo": "texto"}, "")
        assert res == (False, None)

    def test_pais_do_endereco_config(self, regras, monkeypatch):
        self._isolar(regras, monkeypatch)
        res = regras._resolver_por_regra(
            {"pergunta": "Qual o seu país de residência?", "tipo": "texto"}, "")
        assert res == (True, "Brasil")

    def test_estado_radio_pelo_config(self, regras, monkeypatch):
        self._isolar(regras, monkeypatch)
        res = regras._resolver_por_regra(
            {"pergunta": "Em qual estado você mora?", "tipo": "radio",
             "opcoes": ["Rio de Janeiro", "Rialdo"]}, "")
        assert res == (True, 1)

    def test_cargo_pretendido_contextual(self, regras, monkeypatch):
        self._isolar(regras, monkeypatch)
        res = regras._resolver_por_regra(
            {"pergunta": "Qual é o cargo pretendido?", "tipo": "texto"},
            "Vaga de estágio em dados")
        assert res == (True, "Estagiário em Engenheiro de Dados")


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
