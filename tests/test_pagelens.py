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


class _Corpo:
    """body fake — grava quantas vezes a tecla ESC foi 'pressionada'."""
    def __init__(self):
        self.escapes = 0

    def send_keys(self, tecla: str) -> None:
        self.escapes += 1


class _Switch:
    """switch_to fake — grava a trilha de frames e mantém frame_atual no driver."""
    def __init__(self, fake: "_DriverFake"):
        self._fake = fake
        self.log: list[str] = []

    def frame(self, target) -> None:
        self.log.append(f'frame:{target}')
        self._fake.frame_atual = target

    def default_content(self) -> None:
        self.log.append('default')
        self._fake.frame_atual = None


class _DriverFake:
    def __init__(self, mapa: dict | None = None, digest: dict | None = None,
                 bloqueio: str | None = None, close_el: object | None = None,
                 close_por_frame: dict | None = None,
                 iframes: list | None = None):
        self.mapa = mapa or {}
        self.digest = digest
        self.bloqueio = bloqueio
        # qual botão de fechamento "existe" em cada frame (None = main)
        self.close_map = close_por_frame if close_por_frame is not None \
            else ({None: close_el} if close_el is not None else {})
        self.frame_atual = None
        self.iframes = iframes or []
        self.switch_to = _Switch(self)
        self.sel_tentados: list[str] = []

    def find_element(self, by: str, value: str):
        self.sel_tentados.append(value)
        return self.mapa.get(value)

    def find_elements(self, by: str, value: str) -> list:
        if value == 'iframe':
            return self.iframes
        return []

    def execute_script(self, js: str, *args):
        if js == pagelens.DIGEST_JS:
            return self.digest
        if js == pagelens.BLOCKER_JS:
            return self.bloqueio
        if js == pagelens._CLOSE_BTN_JS:
            return self.close_map.get(self.frame_atual)
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


# ── Supervisor de bloqueios (modal/overlay/captcha) ─────────────────────────

def test_bloqueio_tela_livre_nao_chama_llm():
    chamadas: list[str] = []
    d = _DriverFake(mapa={}, digest=_SNAPSHOT, bloqueio=None)  # sem overlay
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: chamadas.append(p) or "{}")
    assert r["tipo"] == "nada"
    assert not chamadas  # checar é barato; LLM só com overlay de fato


def test_bloqueio_llm_fecha_modal():
    el = _El()
    d = _DriverFake(mapa={"#fechar-modal": el}, digest=_SNAPSHOT,
                    bloqueio="modal :: Aviso: as candidaturas encerram em breve. [Fechar]")
    resp = json.dumps({"acao": "clicar", "seletor": "#fechar-modal",
                       "texto": "modal informativo com botão fechar"})
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: resp)
    assert r["tipo"] == "fechou"
    assert r["el"] is el
    assert "#fechar-modal" in d.sel_tentados


def test_bloqueio_llm_captcha_sinaliza_humano():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT,
                    bloqueio="overlay :: I am not a robot — Verificação de segurança")
    resp = json.dumps({"acao": "humano", "seletor": "", "texto": "reCAPTCHA"})
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: resp)
    assert r["tipo"] == "captcha"
    assert r["el"] is None


def test_bloqueio_llm_ignora_inofensivo():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT, bloqueio="overlay :: texto de rodapé")
    resp = json.dumps({"acao": "nada", "seletor": "", "texto": "só é rodapé, não bloqueia"})
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: resp)
    assert r["tipo"] == "nada"


def test_bloqueio_sem_llm_nao_quebra():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT, bloqueio="modal :: algo apareceu")
    r = pagelens.tratar_bloqueio(d, chamar=None)
    assert r["tipo"] == "indeciso"
    assert "algo apareceu" in r["detalhe"]


def test_bloqueio_texto_rapido_fecha_sem_llm():
    # Camada 1: overlay com botão "OK" visível → fecha SEM LLM (o caso que
    # travava antes, mesmo com provedor fora do ar)
    el = _El()
    d = _DriverFake(mapa={}, digest=_SNAPSHOT,
                    bloqueio="modal :: Aviso: candidaturas encerram em breve",
                    close_el=el)
    chamadas: list[str] = []
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: chamadas.append(p) or "{}")
    assert r["tipo"] == "fechou"
    assert r["el"] is el
    assert not chamadas  # nem LLM nem segunda camada precisou


def test_bloqueio_captcha_por_keyword_sem_llm():
    # Gate determinístico: palavra-chave já sinaliza humano, sem LLM
    d = _DriverFake(mapa={}, digest=_SNAPSHOT,
                    bloqueio="overlay :: Turnstile: I am not a robot")
    r = pagelens.tratar_bloqueio(d, chamar=None)
    assert r["tipo"] == "captcha"


def test_bloqueio_llm_miltiplos_candidatos_no_erro():
    # Camada 3: 1º seletor falha, 2º acerta — na mesma rodada
    el = _El()
    d = _DriverFake(mapa={"#certo": el}, digest=_SNAPSHOT,
                    bloqueio="modal :: aviso de privacidade")
    resp = json.dumps({"humano": False, "seletores": ["#errado", "#certo"],
                       "texto": "modal de aviso"})
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: resp)
    assert r["tipo"] == "fechou"
    assert r["el"] is el
    # _encontrar faz polling (3 verif./seletor) — confira ordem, não contagem
    assert d.sel_tentados.index("#certo") > d.sel_tentados.index("#errado")


def test_parse_bloqueio_aceita_formatos_antigo_e_novo():
    novo = json.dumps({"humano": False, "seletores": ["#a", "#b"], "texto": "x"})
    p = pagelens.parse_bloqueio(novo)
    assert p["seletores"] == ["#a", "#b"] and not p["humano"]
    antigo = json.dumps({"acao": "clicar", "seletor": "#fechar", "texto": "y"})
    p2 = pagelens.parse_bloqueio(antigo)
    assert p2["seletores"] == ["#fechar"] and not p2["humano"]
    p3 = pagelens.parse_bloqueio(json.dumps({"acao": "humano", "texto": "recaptcha"}))
    assert p3["humano"] and p3["seletores"] == []
    p4 = pagelens.parse_bloqueio("garbage")
    assert p4 == {"humano": False, "seletores": [], "texto": ""}


def test_bloqueio_esc_pressionado_quando_nada_fecha():
    corpo = _Corpo()
    d = _DriverFake(mapa={"body": corpo}, digest=_SNAPSHOT,
                    bloqueio="modal :: aviso sem botão conhecido")
    r = pagelens.tratar_bloqueio(d, chamar=None)
    assert r["tipo"] == "indeciso"
    assert corpo.escapes == 1  # último recurso determinístico


def test_bloqueio_iframe_fecha_modal_dentro_de_frame():
    # O botão "OK" existe SÓ dentro do iframe (cookie notice de fornecedor
    # externo) — a camada de texto do frame principal não o vê.
    el = _El()
    d = _DriverFake(mapa={}, digest=_SNAPSHOT,
                    bloqueio="modal :: cookie notice",
                    close_por_frame={"cookie-frame": el},
                    iframes=["cookie-frame"])
    r = pagelens.tratar_bloqueio(d, chamar=None)
    assert r["tipo"] == "fechou"
    assert r["el"] is None  # fechado no próprio frame, nada pra _click fora
    assert "frame:cookie-frame" in d.switch_to.log
    assert "default" in d.switch_to.log


def test_bloqueio_llm_julga_inofensivo_retorna_nada():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT,
                    bloqueio="overlay :: erro de campo: preencha o email")
    resp = json.dumps({"humano": False, "seletores": [],
                       "texto": "só erro de validação, some sozinho"})
    r = pagelens.tratar_bloqueio(d, chamar=lambda p, m: resp)
    assert r["tipo"] == "nada"
    assert "erro de validação" in r["detalhe"]


def test_bloqueio_llm_excecao_nao_lanca():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT, bloqueio="modal :: x")

    def boom(p, m):
        raise RuntimeError("provedor fora do ar")

    r = pagelens.tratar_bloqueio(d, chamar=boom)
    assert r["tipo"] == "indeciso"


def test_parse_acao_invalido_vira_nada():
    assert pagelens.parse_acao('{"acao": "pular-mundo"}')["acao"] == "nada"
    assert pagelens.parse_acao("garbage") == {"acao": "nada", "seletor": "", "texto": ""}


# ── Agente de passo (todos os campos em 1 chamada de LLM) ──────────────────

_CAMPOS = [
    {"id": "r_0", "tipo": "radio", "pergunta": "Qual seu nível?",
     "opcoes": ["Estágio", "Júnior", "Pleno", "Sênior"]},
    {"id": "t_1", "tipo": "texto", "pergunta": "Quantos anos de experiência?",
     "opcoes": []},
    {"id": "cb_2", "tipo": "checkbox", "pergunta": "Quais tecnologias você domina?",
     "opcoes": ["Python", "Java", "React", "Go"]},
]


def test_montar_prompt_agente_inclui_todos_campos():
    p = pagelens.montar_prompt_agente(_CAMPOS, "Cargo: Dev Jr | Empresa: X")
    for esperado in ["r_0", "t_1", "cb_2", "1:Júnior", "Dev Jr", "PULAR", '"respostas"']:
        assert esperado in p, f'falta no prompt: {esperado!r}'


def test_parse_batch_coercao_por_tipo():
    resp = json.dumps({"respostas": {"r_0": 1, "t_1": "2 a 3 anos", "cb_2": [0, 2]}})
    got = pagelens.parse_batch(_CAMPOS, resp)
    assert got == {"r_0": 1, "t_1": "2 a 3 anos", "cb_2": [0, 2]}
    assert isinstance(got["r_0"], int)


def test_parse_batch_indice_fora_de_faixa_e_omite():
    resp = json.dumps({"respostas": {"r_0": 99, "t_1": "ok"}})
    assert pagelens.parse_batch(_CAMPOS, resp) == {"t_1": "ok"}


def test_parse_batch_checkbox_aceita_string_de_numeros():
    resp = json.dumps({"respostas": {"cb_2": "0, 2"}})
    assert pagelens.parse_batch(_CAMPOS, resp)["cb_2"] == [0, 2]
    # checkbox com "nenhuma se aplica" vira lista vazia (resposta válida)
    resp2 = json.dumps({"respostas": {"cb_2": "não se aplica"}})
    assert pagelens.parse_batch(_CAMPOS, resp2)["cb_2"] == []


def test_parse_batch_json_invalido_vira_vazio():
    assert pagelens.parse_batch(_CAMPOS, "isso não é JSON") == {}
    assert pagelens.parse_batch(_CAMPOS, '{"respostas": [1,2]}') == {}


def test_agente_campos_faz_uma_sola_chamada():
    chamadas: list[str] = []
    def llm(prompt: str, max_tokens: int) -> str:
        chamadas.append(prompt)
        return json.dumps({"respostas": {"r_0": 1, "t_1": "PULAR", "cb_2": [0]}})
    got = pagelens.agente_campos(_CAMPOS, "cargo x",
                                 chamar=llm)
    assert len(chamadas) == 1
    assert got == {"r_0": 1, "t_1": "PULAR", "cb_2": [0]}


def test_agente_campos_sem_llm_nao_chama():
    assert pagelens.agente_campos(_CAMPOS, "cargo x") == {}
    assert pagelens.agente_campos([], "cargo x",
                                   chamar=lambda p, m: "{}") == {}


def test_agente_campos_llm_falha_retorna_vazio():
    def boom(p, m):
        raise RuntimeError("provedor fora do ar")
    assert pagelens.agente_campos(_CAMPOS, "cargo x", chamar=boom) == {}
