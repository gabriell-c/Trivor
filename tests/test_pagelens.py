"""Testes da leitura semântica de página (apply/common/pagelens.py).

Driver e LLM fake — nenhum browser nem provedor real entra: o módulo é
duck-typed em `driver.find_element(by=..., value=...)` + `execute_script`,
então o teste simula uma página e confere quando o seletores-conhecidos
cumprem (sem LLM) e quando o resgate semântico precisa do LLM.
"""
import importlib.util
import json
import sys
import types
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
                 iframes: list | None = None, campos: dict | None = None):
        self.mapa = mapa or {}
        self.digest = digest
        self.bloqueio = bloqueio
        # qual botão de fechamento "existe" em cada frame (None = main)
        self.close_map = close_por_frame if close_por_frame is not None \
            else ({None: close_el} if close_el is not None else {})
        self.frame_atual = None
        self.iframes = iframes or []
        self.campos = campos or {}
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
        if js == pagelens.CAMPOS_JS:
            return self.campos
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


# ── Rótulo de campo (layout mudou → LLM infere a pergunta) ──────────────────

def test_rotulo_irresolvido_casos():
    assert pagelens.rotulo_irresolvido("") is True
    assert pagelens.rotulo_irresolvido("   ") is True
    assert pagelens.rotulo_irresolvido("campo") is True
    assert pagelens.rotulo_irresolvido("q_123") is True
    assert pagelens.rotulo_irresolvido("input-q_456") is True
    assert pagelens.rotulo_irresolvido("question_7") is True
    assert pagelens.rotulo_irresolvido("CPF") is False
    assert pagelens.rotulo_irresolvido("Qual seu nível?") is False
    assert pagelens.rotulo_irresolvido(None) is True


def test_resumo_campos_json_com_k_e_opcoes():
    campos = {"passo": "Etapa 2: Dados",
              "campos": [{"k": "q_1", "t": "text", "ph": "", "opt": []},
                         {"k": "q_2", "t": "select", "ph": "",
                          "opt": ["a", "b"]}]}
    d = _DriverFake(campos=campos)
    s = pagelens.resumo_campos(d)
    assert '"q_1"' in s and '"q_2"' in s and '"Etapa 2' in s
    assert '"a"' in s  # opções de select entram no snapshot
    # vazio → '' (não existe resumo pra LLM)
    assert pagelens.resumo_campos(_DriverFake()) == ""
    assert pagelens.resumo_campos(_DriverFake(campos={"passo": "", "campos": []})) == ""


def test_agente_rotulos_resposta_valida():
    desc = json.dumps({"passo": "", "campos": [{"k": "q_9", "t": "text",
                                                  "ph": "", "opt": []}]})
    got = pagelens.agente_rotulos(desc, "vaga de dev jr",
                                  chamar=lambda p, m=500: json.dumps(
                                      {"respostas": {"q_9": "Qual seu CPF?"}}))
    assert got == {"q_9": "Qual seu CPF?"}


def test_agente_rotulos_garbage_e_sem_llm_vira_vazio():
    desc = json.dumps({"passo": "", "campos": [{"k": "q_9", "t": "text",
                                                  "ph": "", "opt": []}]})
    assert pagelens.agente_rotulos(desc, "v",
                                   chamar=lambda p, m=500: "não é json") == {}
    assert pagelens.agente_rotulos(desc, "v") == {}
    assert pagelens.agente_rotulos("", "v",
                                   chamar=lambda p, m=500: "{}") == {}


# ── Deteção de envio semântica (tela de sucesso nova) ───────────────────────

def test_montar_prompt_enviada_avisa_que_revisao_nao_e_envio():
    p = pagelens.montar_prompt_enviada(json.dumps(_SNAPSHOT))
    assert "REVISÃO" in p and '"enviada"' in p


def test_parse_enviada_varias_respostas():
    assert pagelens.parse_enviada(json.dumps({"enviada": True, "motivo": "ok"})) is True
    assert pagelens.parse_enviada(json.dumps({"enviada": "sim"})) is True
    assert pagelens.parse_enviada(json.dumps({"enviada": False})) is False
    assert pagelens.parse_enviada("garbage") is False
    assert pagelens.parse_enviada("") is False


# ── Supervisor de bloqueio (Playwright) ──────────────────────────────────────

class _HandleFake:
    """ElementHandle fake — `click()` do botão de fechamento."""
    def __init__(self):
        self.clicou = False

    def click(self) -> None:
        self.clicou = True


class _LocatorFake:
    def __init__(self, alvo):
        self._alvo = alvo
        self.clicou = False

    @property
    def first(self):
        return self

    def wait_for(self, state, timeout) -> None:
        if self._alvo is None:
            raise RuntimeError("elemento não apareceu")
        self._alvo = None  # consumido

    def click(self) -> None:
        self.clicou = True


class _FrameFake:
    """Frame child (cookie notice) — `evaluate` por script."""
    def __init__(self, por_script: dict):
        self.por_script = por_script

    def evaluate(self, js: str, *args):
        return self.por_script.get(js)


class _PageFake:
    """Page fake do Playwright: locator/evaluate/keyboard/frames duck-typed."""
    def __init__(self, mapa: dict | None = None, digest: dict | None = None,
                 bloqueio: str | None = None, close_el: object | None = None,
                 campos: dict | None = None, esc_fecha: bool = False,
                 frames: list | None = None):
        self.mapa = mapa or {}
        self.digest = digest
        self.bloqueio = bloqueio
        self.close_el = close_el
        self.campos = campos or {}
        self.escapes = 0
        self.esc_fecha = esc_fecha
        self.sel_tentados: list[str] = []
        main = object()
        self.main_frame = main
        self.frames = [main] + (frames or [])
        self.keyboard = self  # `page.keyboard.press(...)` cai em `page.press`

    def evaluate(self, js: str, *args):
        if js == pagelens.DIGEST_JS:
            return self.digest
        if js == pagelens.BLOCKER_JS:
            return self.bloqueio
        if js == pagelens._CLOSE_BTN_JS:
            return self.close_el
        if js == pagelens.CAMPOS_JS:
            return self.campos
        return self.digest

    def locator(self, sel: str) -> _LocatorFake:
        self.sel_tentados.append(sel)
        return _LocatorFake(self.mapa.get(sel))

    def press(self, tecla: str) -> None:
        """page.keyboard.press(...) — `keyboard` aponta pra própria page."""
        if tecla == "Escape":
            self.escapes += 1
            if self.esc_fecha:
                self.bloqueio = None


def test_pw_tela_livre_nao_chama_llm():
    chamadas: list[str] = []
    p = _PageFake(bloqueio=None)
    r = pagelens.tratar_bloqueio_pw(p, chamar=lambda a, b: chamadas.append(a) or "{}")
    assert r["tipo"] == "nada"
    assert not chamadas


def test_pw_captcha_por_keyword_sem_llm():
    p = _PageFake(bloqueio="overlay :: Turnstile: I am not a robot")
    r = pagelens.tratar_bloqueio_pw(p, chamar=None)
    assert r["tipo"] == "captcha"
    assert r["el"] is None


def test_pw_texto_rapido_fecha_sem_llm():
    h = _HandleFake()
    p = _PageFake(bloqueio="modal :: Aviso: candidaturas encerram em breve",
                   close_el=h)
    chamadas: list[str] = []
    r = pagelens.tratar_bloqueio_pw(p, chamar=lambda a, b: chamadas.append(a) or "{}")
    assert r["tipo"] == "fechou"
    assert r["el"] is h
    assert not chamadas


def test_pw_llm_multiplos_candidatos():
    h = _HandleFake()
    p = _PageFake(mapa={"#certo": h}, digest=_SNAPSHOT,
                   bloqueio="modal :: aviso de privacidade")
    resp = json.dumps({"humano": False, "seletores": ["#errado", "#certo"],
                       "texto": "modal de aviso"})
    r = pagelens.tratar_bloqueio_pw(p, chamar=lambda a, b: resp)
    assert r["tipo"] == "fechou"
    assert r["el"] is not None  # locator do '#certo' (o wrapper do fake)
    r["el"].click()
    assert p.sel_tentados.index("#certo") > p.sel_tentados.index("#errado")


def test_pw_esc_pressionado_quando_nada_fecha():
    p = _PageFake(bloqueio="modal :: aviso sem botão", esc_fecha=True)
    r = pagelens.tratar_bloqueio_pw(p, chamar=None)
    assert r["tipo"] == "fechou"
    assert r["el"] is None
    assert p.escapes == 1


def test_pw_indeciso_quando_esc_nao_fecha():
    p = _PageFake(bloqueio="modal :: aviso sem botão")
    r = pagelens.tratar_bloqueio_pw(p, chamar=None)
    assert r["tipo"] == "indeciso"
    assert p.escapes == 1


def test_pw_iframe_cookie_notice():
    h = _HandleFake()
    frame = _FrameFake({pagelens.BLOCKER_JS: "cookie :: use e aceite cookies",
                        pagelens._CLOSE_BTN_JS: h})
    p = _PageFake(bloqueio="modal :: cookie notice", frames=[frame])
    r = pagelens.tratar_bloqueio_pw(p, chamar=None)
    assert r["tipo"] == "fechou"
    assert r["el"] is None


def test_pw_llm_sem_resposta_nao_ignora_overlay():
    # Provedor devolve None/vazio (ex.: `_chamar_llm` da Gupy em falha) —
    # NÃO pode virar "nada" (tela livre): o overlay continua na tela.
    p = _PageFake(mapa={}, digest=_SNAPSHOT, bloqueio="modal :: aviso")
    r = pagelens.tratar_bloqueio_pw(p, chamar=lambda a, b: "")
    assert r["tipo"] == "indeciso"
    assert p.escapes == 1


def test_resumo_campos_pw_via_evaluate():
    campos = {"passo": "p", "campos": [{"k": "q_1", "t": "text", "ph": "",
                                          "opt": []}]}
    p = _PageFake(campos=campos)
    s = pagelens.resumo_campos_pw(p)
    assert '"q_1"' in s
    assert pagelens.resumo_campos_pw(_PageFake()) == ""


# ── Leitor estrutural (crawl4ai via CDP) — seção extra do digest ─────────────
# O `common.leitor` é fake em sys.modules: nenhum crawl4ai/Chrome entra.
# A regra testada: com o leitor ligado, a seção estrutural é ANEXADA ao
# digest clássico; em falha, o digest sai intacto (nunca pior).

def _instalar_leitor_fake(resumo_retorno: str):
    fake_leitor = types.ModuleType("common.leitor")
    fake_leitor.leitura_estruturada = lambda url, cdp, limite=1200: object()
    fake_leitor.resumo_para_llm = lambda leitura, fallback="": resumo_retorno
    fake_common = types.ModuleType("common")
    fake_common.leitor = fake_leitor
    antigo_common = sys.modules.get("common")
    antigo_cdp = pagelens._LEITOR_CDP
    sys.modules["common"] = fake_common
    pagelens.habilitar_leitor("http://127.0.0.1:9333")
    return (antigo_common, antigo_cdp)


def _restaurar_leitor_fake(estado) -> None:
    antigo_common, antigo_cdp = estado
    if antigo_common is None:
        sys.modules.pop("common", None)
    else:
        sys.modules["common"] = antigo_common
    pagelens._LEITOR_CDP = antigo_cdp


def test_leitor_desligado_mantem_fluxo_classico():
    d = _DriverFake(mapa={}, digest=_SNAPSHOT)
    s = pagelens.resumo_pagina(d)
    assert "next-btn" in s
    assert "[estrutura da página" not in s  # sem CDP, digest sai como antes


def test_leitor_ligado_anexa_secao_estrutural():
    estado = _instalar_leitor_fake(resumo_retorno="## seções\n- formulário (12 campos)\n[links]\nhttps://vaga")
    try:
        d = _DriverFake(mapa={}, digest=_SNAPSHOT)
        d.current_url = "https://portal/etapa2"
        s = pagelens.resumo_pagina(d)
        assert "next-btn" in s             # DOM vivo continua a verdade
        assert "[estrutura da página" in s  # seção do c4a anexada
        assert "https://vaga" in s         # estrutura (seções + links) presente
    finally:
        _restaurar_leitor_fake(estado)


def test_leitor_pw_anexa_secao_estrutural():
    estado = _instalar_leitor_fake(resumo_retorno="seções do portal")
    try:
        p = _PageFake(digest=_SNAPSHOT)
        p.url = "https://portal/etapa2"
        s = pagelens.resumo_pagina_pw(p)
        assert "next-btn" in s and "seções do portal" in s
    finally:
        _restaurar_leitor_fake(estado)


def test_leitor_em_falha_devolve_digest_intacto():
    # resumo_para_llm com fallback="" retorna "" → leitor não contribuiu
    estado = _instalar_leitor_fake(resumo_retorno="")
    try:
        d = _DriverFake(mapa={}, digest=_SNAPSHOT)
        s_ligado = pagelens.resumo_pagina(d)
    finally:
        _restaurar_leitor_fake(estado)
    s_desligado = pagelens.resumo_pagina(_DriverFake(mapa={}, digest=_SNAPSHOT))
    assert s_ligado == s_desligado  # falha do c4a nunca muda o resultado


def test_habilitar_leitor_nulo_desliga():
    pagelens.habilitar_leitor("http://127.0.0.1:9333")
    assert pagelens._LEITOR_CDP is not None
    pagelens.habilitar_leitor(None)
    assert pagelens._LEITOR_CDP is None


def test_leitor_sem_url_da_pagina_nao_anexa():
    # Page sem atributo `url` (fakes antigos, página em navegação) →
    # a seção estrutural não entra, digest sai intacto
    estado = _instalar_leitor_fake(resumo_retorno="seções")
    try:
        p = _PageFake(digest=_SNAPSHOT)
        assert not hasattr(p, "url")
        s_ligado = pagelens.resumo_pagina_pw(p)
    finally:
        _restaurar_leitor_fake(estado)
    s_desligado = pagelens.resumo_pagina_pw(_PageFake(digest=_SNAPSHOT))
    assert s_ligado == s_desligado
