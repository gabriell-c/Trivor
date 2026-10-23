"""Testes da leitura semântica de página (apply/common/pagelens.py).

Driver e LLM fake — nenhum browser nem provedor real entra: o módulo é
duck-typed em `driver.find_element(by=..., value=...)` + `execute_script`,
então o teste simula uma página e confere quando o seletores-conhecidos
cumprem (sem LLM) e quando o resgate semântico precisa do LLM.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _carregar_pagelens():
    p = ROOT / 'apply' / 'common' / 'pagelens.py'
    spec = importlib.util.spec_from_file_location('apply_pagelens_teste', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pagelens = _carregar_pagelens()


class _El:
    def __init__(self, visivel: bool = True):
        self.visivel = visivel

    def is_displayed(self) -> bool:
        return self.visivel


class _DriverFake:
    def __init__(self, mapa: dict | None = None, digest: dict | None = None):
        self.mapa = mapa or {}
        self.digest = digest
        self.sel_tentados: list[str] = []

    def find_element(self, by: str, value: str):
        self.sel_tentados.append(value)
        return self.mapa.get(value)

    def execute_script(self, js: str, *args):
        return self.digest


_SNAPSHOT = {"titulo": "Aplicação | Empresa X",
             "passo": "Etapa 2 de 5: Dados pessoais",
             "els": [
                 {"t": "botao", "txt": "Avançar para etapa 3", "id": "next-btn",
                  "tid": "", "aria": "", "n": "", "ty": "button"},
                 {"t": "botao", "txt": "Voltar", "id": "back",
                  "tid": "", "aria": "", "n": "", "ty": "button"},
             ]}


def test_seletor_conhecido_sem_llm():
    el = _El()
    d = _DriverFake(mapa={"[data-testid='next']": el}, digest=_SNAPSHOT)
    chamadas: list[str] = []
    got = pagelens.achar(d, seletores=["[data-testid='next']"], objetivo="avancar",
                         chamar=lambda p, m: chamadas.append(p) or "{}")
    assert got is el
    assert not chamadas  # happy path nunca chama LLM


def test_seletor_nao_visivel_vira_falha():
    d = _DriverFake(mapa={"#antigo": _El(visivel=False)}, digest=_SNAPSHOT)
    assert pagelens.achar(d, seletores=["#antigo"], objetivo="avancar") is None


def test_resgate_llm_acha_botao_de_pagina_nova():
    # Seletores conhecidos falharam (o site redesenhou); o LLM lê o snapshot
    # e propõe o botão certo pelo id — simula redesign do site
    el = _El()
    d = _DriverFake(mapa={"#next-btn": el}, digest=_SNAPSHOT)
    resp = json.dumps({"seletores": ["#next-btn"], "motivo": "botão avança a etapa"})
    got = pagelens.achar(d, seletores=["#inexistente"],
                         objetivo="Avançar para o próximo passo",
                         chamar=lambda p, m: resp)
    assert got is el
    assert "#inexistente" in d.sel_tentados and "#next-btn" in d.sel_tentados


def test_resgate_erro_anterior_entra_na_2a_rodada():
    el = _El()
    prompts: list[str] = []

    def llm(prompt: str, max_tokens: int) -> str:
        prompts.append(prompt)
        return json.dumps({"seletores": ["#certo"], "motivo": "ok"})

    d = _DriverFake(mapa={"#certo": el}, digest=_SNAPSHOT)
    pagelens.achar(d, seletores=[], objetivo="x",
                   chamar=llm, tentativas_llm=1)
    assert len(prompts) == 1

    # candidato errado → a segunda rodada deve mencionar a falha anterior
    d2 = _DriverFake(mapa={"#certo2": _El()}, digest=_SNAPSHOT)
    prompts2: list[str] = []

    def llm2(prompt: str, max_tokens: int) -> str:
        prompts2.append(prompt)
        if len(prompts2) == 1:
            return json.dumps({"seletores": ["#errado"], "motivo": "chute"})
        return json.dumps({"seletores": ["#certo2"], "motivo": "corrigido"})

    pagelens.achar(d2, seletores=[], objetivo="x", chamar=llm2, tentativas_llm=2)
    assert "não achou elemento visível" in prompts2[1]


def test_llm_json_invalido_nao_lanca():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT)
    got = pagelens.achar(d, seletores=[], objetivo="x",
                         chamar=lambda p, m: "isso não é JSON")
    assert got is None


def test_snapshot_vazio_nao_chama_llm():
    d = _DriverFake(mapa={}, digest={"titulo": "", "passo": "", "els": []})
    chamadas: list[str] = []
    got = pagelens.achar(d, seletores=[], objetivo="x",
                         chamar=lambda p, m: chamadas.append(p) or "{}")
    assert got is None
    assert not chamadas


def test_sem_chamar_apenas_seletores():
    el = _El()
    d = _DriverFake(mapa={"//div/botao": el}, digest=_SNAPSHOT)
    assert pagelens.achar(d, seletores=["//div/botao"], objetivo="x") is el
    d2 = _DriverFake(mapa={}, digest=_SNAPSHOT)
    assert pagelens.achar(d2, seletores=[], objetivo="x") is None


def test_prompt_inclui_objetivo_snapshot_e_regras():
    p = pagelens.montar_prompt("Avançar", json.dumps(_SNAPSHOT),
                               regras="pretensão 3000", erro_anterior="falhou #antigo")
    assert "Avançar" in p and "next-btn" in p and "pretensão 3000" in p and "#antigo" in p


def test_parse_seletores_markdown_e_limite():
    r = '```json\n{"seletores": ["#a", "//b"], "motivo": "ok"}\n```'
    assert pagelens.parse_seletores(r) == ["#a", "//b"]
    assert pagelens.parse_seletores(json.dumps({"seletores": ["a", "b", "c", "d", "e"]})) == ["a", "b", "c"]
    assert pagelens.parse_seletores("sem json aqui") == []
    assert pagelens.parse_seletores('{"seletores": []}') == []


def test_digest_js_nao_inclui_value_de_input():
    # PII digitada no formulário (CPF, salário) não pode ir ao LLM
    assert "el.value" not in pagelens.DIGEST_JS
    assert "placeholder" in pagelens.DIGEST_JS


def test_resumo_corta_para_limite():
    grande = {"titulo": "t", "passo": "p",
              "els": [{"t": "botao", "txt": "x" * 40, "id": f"id{i}", "tid": "",
                       "aria": "", "n": "", "ty": ""} for i in range(40)]}
    s = pagelens.resumo_pagina(_DriverFake(mapa={}, digest=grande), limite=500)
    assert len(s) <= 500
    assert '"titulo"' in s  # título/passo sobrevivem ao corte
