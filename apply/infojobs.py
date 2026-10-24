"""
infojobs.py — Automação completa do InfoJobs
Fluxo: Login → Buscar vagas → Fechar modal → Responder killer questions → Candidatar

VERSÃO v1.5:
  - LLM router Groq → Gemini → Mistral → fallback local
    · Groq rate limit curto (< 5min): aguarda e retenta automaticamente
    · Groq rate limit diário: troca para Gemini até meia-noite
    · Gemini 2.0 Flash: 1.000 req/dia, sem crédito mensal expirável
    · Mistral Small: ~1 bilhão tokens/mês, praticamente ilimitado
    · Fallback local como último recurso (zero API)
  - Variáveis de ambiente necessárias:
    · GROQ_API_KEY    — console.groq.com
    · GEMINI_API_KEY  — aistudio.google.com
    · MISTRAL_API_KEY — console.mistral.ai

VERSÃO v1.4:
  - Salvamento de respostas e carta de apresentação no relatório
  - _fallback_local_carta inteligente por categoria de vaga

VERSÃO v1.3:
  - Fallback local inteligente para perguntas abertas

VERSÃO v1.1/1.2:
  - Killer questions de múltipla escolha corrigidas
  - Fallback local para múltipla escolha
"""

import contextlib
import datetime as _dt
import json
import os
import re
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from common import llm as _llm_lib
from common import pagelens, perfil
from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  PERFIL DO CANDIDATO
# ══════════════════════════════════════════════════════════════════════════════

def _perfil_ctx(config: dict) -> str:
    """Contexto completo do candidato (common/perfil.py) — substitui o bloco
    estático antigo: a IA vê tudo que o usuário mantém na aba Perfil do Trivor
    (config.yaml + .env), com a lista de exclusões e regras de resposta."""
    return perfil.contexto_perfil(config)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def carregar_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

def log(msg: str):
    print(f"  {msg}")

def esperar(page: Page, segundos: float | None = None):
    config = carregar_config()
    s = segundos or config["automacao"]["delay_entre_acoes"]
    page.wait_for_timeout(int(s * 1000))


# ══════════════════════════════════════════════════════════════════════════════
#  LLM ROUTER — Groq → Gemini → Mistral → fallback local
#
#  Cascata:
#    1. Groq          — primário, rápido, sem crédito mensal (só rate limit diário)
#       · Rate limit curto (< 5min) → aguarda e retenta automaticamente (até 4x)
#       · Rate limit diário         → passa para Gemini até meia-noite UTC
#    2. Gemini Flash  — 1.000 req/dia, sem crédito expirável
#    3. Mistral Small — ~1 bilhão tokens/mês no free tier
#    4. Fallback local — zero API, regras estáticas
#
#  Variáveis de ambiente (.env):
#    GROQ_API_KEY    — console.groq.com
#    GEMINI_API_KEY  — aistudio.google.com
#    MISTRAL_API_KEY — console.mistral.ai
#
#  Log de diagnóstico:
#    [LLM Groq]    ✅ → Groq respondeu OK
#    [LLM Gemini]  ✅ → Gemini respondeu OK
#    [LLM Mistral] ✅ → Mistral respondeu OK
#    [LLM] ⚡       → rate limit curto Groq, aguardando e retentando
#    [LLM] 🔴       → limite diário Groq, trocando para Gemini
#    [LLM] ❌       → provedor falhou, tentando próximo
# ══════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

_llm_state = {
    "provedor":      "groq",   # "groq" | "gemini" | "mistral"
    "groq_reset_em": None,
    "lock":          threading.Lock(),
}


_GroqLimiteDiario = _llm_lib.GroqLimiteDiario
_calcular_reset_groq = _llm_lib.calcular_reset_groq


def _agendar_retorno_groq(reset_utc: "_dt.datetime") -> None:
    def _voltar():
        agora  = _dt.datetime.now(_dt.UTC)
        espera = max(0, (reset_utc - agora).total_seconds()) + 15
        log(f"    [LLM] Groq volta em {int(espera / 60)}min "
            f"({reset_utc.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M')} local)")
        time.sleep(espera)
        with _llm_state["lock"]:
            _llm_state["provedor"]      = "groq"
            _llm_state["groq_reset_em"] = None
        log("    [LLM] ✅ Groq reativado automaticamente!")
    threading.Thread(target=_voltar, daemon=True).start()


def _chamar_groq(prompt: str, config: dict, temperatura: float, tentativas: int = 4) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada")
    return _llm_lib.chamar_groq(
        [{"role": "user", "content": prompt}],
        model=config["groq"]["model"],
        api_key=GROQ_API_KEY,
        log_info=lambda m: log(f"    [LLM] ⚡ {m}"),
        max_tokens=None,
        temperature=temperatura,
        tentativas=tentativas,
    )


def _chamar_gemini(prompt: str, temperatura: float, tentativas: int = 4) -> str:
    """
    Gemini 2.5 Flash-Lite via REST.
    Plano free: 1.000 req/dia, 15 RPM.

    Trata dois tipos de 429:
      - RPM excedido : espera 4s * tentativa e retenta (ate `tentativas` vezes)
      - Cota diaria  : levanta RuntimeError imediatamente, sem retry
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nao configurada")

    texto = _llm_lib.chamar_gemini(
        prompt,
        api_key=GEMINI_API_KEY,
        log_info=lambda m: log(f"    [LLM] ⚡ {m}"),
        temperatura=temperatura,
        tentativas=tentativas,
    )
    log(f"    [LLM Gemini] ✅ ({len(texto)} chars)")
    return texto


def _chamar_mistral(prompt: str, temperatura: float) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY não configurada")

    texto = _llm_lib.chamar_mistral(
        prompt,
        api_key=MISTRAL_API_KEY,
        temperatura=temperatura,
        max_tokens=600,
    )
    log(f"    [LLM Mistral] ✅ (resposta: {texto!r})")
    return texto


def _chamar_llm(prompt: str, config: dict, contexto: str = "", temperatura: float = 0.4) -> str | None:
    """Roteador LLM: Groq → Gemini → Mistral → None (fallback local)."""
    sufixo = f" ({contexto})" if contexto else ""

    with _llm_state["lock"]:
        provedor = _llm_state["provedor"]

    # ── 1. Groq ───────────────────────────────────────────────────────────────
    if provedor == "groq":
        try:
            resultado = _chamar_groq(prompt, config, temperatura)
            log(f"    [LLM Groq] ✅{sufixo} ({len(resultado)} chars)")
            return resultado
        except _GroqLimiteDiario:
            reset_utc = _calcular_reset_groq()
            with _llm_state["lock"]:
                _llm_state["provedor"]      = "gemini"
                _llm_state["groq_reset_em"] = reset_utc
            log(f"    [LLM] 🔴 Groq limite diário{sufixo} → trocando para Gemini")
            _agendar_retorno_groq(reset_utc)
        except Exception as exc:
            log(f"    [LLM] ❌ Groq erro{sufixo}: {exc} → tentando Gemini")

    # ── 2. Gemini ─────────────────────────────────────────────────────────────
    try:
        return _chamar_gemini(prompt, temperatura)
    except Exception as exc:
        log(f"    [LLM] ❌ Gemini falhou{sufixo}: {exc} → tentando Mistral")

    # ── 3. Mistral ────────────────────────────────────────────────────────────
    try:
        return _chamar_mistral(prompt, temperatura)
    except Exception as exc:
        log(f"    [LLM] ❌ Mistral falhou{sufixo}: {exc} → usando fallback local")

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  KILLER QUESTIONS
# ══════════════════════════════════════════════════════════════════════════════

_ATALHOS_RADIO: list[tuple[str, str]] = [
    (r"disponib",                                      "Sim"),
    (r"imediata",                                      "Sim"),
    (r"home\s*office|remoto|trabalhar\s*(de\s*)?casa", "Sim"),
    (r"híbrido|hibrido",                               "Sim"),
    (r"presencial",                                    "Sim"),
    (r"superior|gradua|faculdade|universidade",         "Sim"),
    (r"engenharia\s*de\s*software",                    "Sim"),
    (r"python",                                        "Sim"),
    (r"javascript|js\b",                               "Sim"),
    (r"react\b",                                       "Sim"),
    (r"php\b",                                         "Sim"),
    (r"django",                                        "Sim"),
    (r"sql\b|mysql|banco\s*de\s*dados",                "Sim"),
    (r"git\b|github",                                  "Sim"),
    (r"html|css\b",                                    "Sim"),
    (r"api\s*rest|restful",                            "Sim"),
    (r"docker",                                        "Sim"),
    (r"freelanc",                                      "Sim"),
    (r"portfólio|portfolio",                           "Sim"),
    (r"deficiência|deficiente|pcd",                    "Não"),
    (r"\b(5|seis|6|sete|7|oito|8|dez|10)\s*anos",     "Não"),
    (r"sênior|senior\b",                               "Não"),
    (r"java\b(?!script)",                              "Não"),
    (r"\bc#\b|\.net\b",                                "Não"),
    (r"kotlin|swift\b|flutter",                        "Não"),
    (r"sap\b|totvs|protheus",                          "Não"),
]


def _eh_pergunta_sim_nao(opcoes: list[dict]) -> bool:
    valores = {o["value"].strip().lower() for o in opcoes}
    return valores <= {"sim", "não", "nao", "yes", "no", "s", "n"}


def _escolher_opcao_multipla_escolha(pergunta: str, opcoes: list[dict], config: dict) -> dict | None:
    lista_opcoes = "\n".join(
        f"{i+1}. {o['label'] or o['value']}" for i, o in enumerate(opcoes)
    )
    prompt = f"""Você está respondendo uma pergunta de processo seletivo em nome de um candidato.

PERFIL DO CANDIDATO (responda SOMENTE com base nele; a lista de exclusões vale):
{_perfil_ctx(config)}

PERGUNTA:
{pergunta}

OPÇÕES DISPONÍVEIS:
{lista_opcoes}

INSTRUÇÕES:
- Escolha a opção que melhor representa o candidato com base no perfil acima
- Responda APENAS com o número da opção (ex: "3")
- Não escreva mais nada além do número
- Formação, experiência, CNH, habilitação, senioridade → use SOMENTE o perfil acima
  (itens da lista de exclusões → escolha a opção que nega experiência: "Nenhum", "Não", "0 anos")
- Se pedir se já trabalhou na empresa, escolha "Não"
- Se pedir confirmação/concordância (ex: "li e concordo"), escolha essa opção

Número da opção escolhida:"""

    resposta = _chamar_llm(prompt, config, contexto="multipla_escolha", temperatura=0.0)
    if resposta:
        m = re.search(r"\b(\d+)\b", resposta.strip())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(opcoes):
                log(f"    ✓ LLM escolheu opção {idx+1}: '{opcoes[idx]['label'] or opcoes[idx]['value']}'")
                return opcoes[idx]
    return None


def _fallback_local_multipla_escolha(pergunta: str, opcoes: list[dict]) -> dict:
    p            = pergunta.lower()
    labels_lower = [o["label"].lower() for o in opcoes]

    def achar(termo: str) -> dict | None:
        for i, lbl in enumerate(labels_lower):
            if termo in lbl:
                return opcoes[i]
        return None

    if any(x in p for x in ["formação", "escolaridade", "grau de instrução", "nível de escolaridade"]):
        for t in ["superior cursando", "ensino superior cursando", "graduação cursando",
                  "superior incompleto", "cursando"]:
            r = achar(t)
            if r:
                return r
        for t in ["superior completo", "ensino superior completo", "graduação completa"]:
            r = achar(t)
            if r:
                return r

    if any(x in p for x in ["experiência", "tempo de experiência", "anos de experiência",
                             "experiência requisitada", "tempo na área"]):
        for t in ["mais de 01 ano", "mais de 1 ano", "acima de 1 ano", "acima de um ano",
                  "mais de 2 anos", "mais de 3 anos"]:
            r = achar(t)
            if r:
                return r
        for t in ["06 meses", "6 meses a", "6 meses"]:
            r = achar(t)
            if r:
                return r

    if any(x in p for x in ["cnh", "habilitação", "habilitacao", "carteira de motorista"]):
        for t in ["não possuo habilitação", "não possuo cnh", "não possuo", "não tenho"]:
            r = achar(t)
            if r:
                return r

    if any(x in p for x in ["inglês", "ingles", "english", "idioma", "língua"]):
        for t in ["básico", "basico"]:
            r = achar(t)
            if r:
                return r

    if any(x in p for x in ["já trabalhou", "trabalhou na empresa", "já foi colaborador",
                             "ex-funcionário", "ex-colaborador", "sistema fiesc",
                             "trabalhou no grupo", "faz parte do grupo"]):
        r = achar("não")
        if r:
            return r

    if any(x in p for x in ["declaro", "concordo", "li e concordo", "estou ciente",
                             "aceito", "confirmo", "compreendo", "ciência"]):
        for t in ["li e concordo", "concordo", "aceito", "estou ciente", "sim"]:
            r = achar(t)
            if r:
                return r

    if any(x in p for x in ["bolsista", "bolsa", "cnpq", "ipt", "fapesp",
                             "deficiência", "deficiente", "pcd", "reabilitado"]):
        r = achar("não")
        if r:
            return r

    if any(x in p for x in ["disponibilidade", "disponível", "início imediato"]):
        for t in ["sim", "imediata", "disponível"]:
            r = achar(t)
            if r:
                return r

    melhor = max(opcoes, key=lambda o: o.get("score", 0))
    if melhor.get("score", 0) > 0:
        return melhor

    log(f"    ⚠️  Fallback local sem regra para: '{pergunta[:60]}' — usando 1ª opção")
    return opcoes[0]


def pegar_texto_pergunta_infojobs(page: Page, id_killerquestion: str) -> str:
    try:
        texto = page.evaluate(f"""
            (() => {{
                const el = document.querySelector("[data-idkillerquestion='{id_killerquestion}']");
                if (!el) return '';
                let node = el;
                for (let i = 0; i < 8; i++) {{
                    node = node.parentElement;
                    if (!node) break;
                    if (node.classList && node.classList.contains('mb-32')) {{
                        const prev = node.previousElementSibling;
                        if (prev) return prev.innerText.trim();
                    }}
                }}
                return '';
            }})()
        """)
        return (texto or "").strip()
    except Exception:
        return ""


def _coletar_opcoes_grupo(page: Page, radios: list) -> list[dict]:
    opcoes = []
    for radio in radios:
        try:
            answer_id  = radio.get_attribute("id") or ""
            value      = radio.get_attribute("value") or ""
            score      = int(radio.get_attribute("data-score") or "0")
            max_score  = int(radio.get_attribute("data-maxscore") or "0")
            label_text = ""
            if answer_id:
                try:
                    lbl = page.query_selector(f"label[for='{answer_id}']")
                    if lbl:
                        label_text = lbl.inner_text().strip()
                except Exception:
                    pass
            opcoes.append({
                "answer_id": answer_id,
                "value":     value,
                "label":     label_text or value,
                "score":     score,
                "max_score": max_score,
                "element":   radio,
            })
        except Exception:
            continue
    return opcoes


def _clicar_opcao(page: Page, opcao: dict) -> bool:
    answer_id = opcao.get("answer_id", "")
    if answer_id:
        try:
            label = page.query_selector(f"label[for='{answer_id}']")
            if label:
                label.click()
                return True
        except Exception:
            pass
        try:
            opcao["element"].click(force=True)
            return True
        except Exception:
            pass
    return False


def responder_killer_questions(page: Page, config: dict) -> tuple[bool, dict]:
    """Retorna (encontrou: bool, respostas: dict[pergunta → resposta])."""
    respostas_salvas: dict[str, str] = {}

    try:
        form = page.query_selector("#KillerQuestionsForm")
        if not form:
            return False, respostas_salvas

        log("  📝 Killer questions detectadas, respondendo...")

        radios_grupos: dict[str, list] = {}
        for radio in page.query_selector_all("input[type='radio'][data-idkillerquestiontype]"):
            name = radio.get_attribute("name") or ""
            radios_grupos.setdefault(name, []).append(radio)

        for name, radio_els in radios_grupos.items():
            try:
                opcoes   = _coletar_opcoes_grupo(page, radio_els)
                if not opcoes:
                    continue

                id_kq    = radio_els[0].get_attribute("data-idkillerquestion") or ""
                pergunta = pegar_texto_pergunta_infojobs(page, id_kq) or name

                log(f"    ❓ {pergunta[:90]}")
                log(f"       Opções: {[o['label'][:30] for o in opcoes]}")

                if _eh_pergunta_sim_nao(opcoes):
                    resposta_str = None
                    for padrao, resp in _ATALHOS_RADIO:
                        if re.search(padrao, pergunta.lower()):
                            resposta_str = resp
                            break

                    if not resposta_str:
                        prompt = f"""Responda APENAS com "Sim" ou "Não" (sem aspas, sem mais nada).

PERFIL DO CANDIDATO (responda SOMENTE com base nele; a lista de exclusões vale):
{_perfil_ctx(config)}

PERGUNTA: {pergunta}

Regras:
- "Sim" se o candidato genuinamente tem a habilidade/experiência/característica pedida
- "Não" se não tem
- Em caso de dúvida sobre concordância com termos, responda "Sim"

Resposta:"""
                        resp_llm     = _chamar_llm(prompt, config, contexto="sim_nao", temperatura=0.0)
                        resposta_str = "Sim" if resp_llm and "sim" in resp_llm.lower() else "Não"

                    log(f"       → {resposta_str}")
                    respostas_salvas[pergunta] = resposta_str

                    clicou = False
                    for opcao in opcoes:
                        if opcao["value"].strip().lower() == resposta_str.lower():
                            _clicar_opcao(page, opcao)
                            clicou = True
                            break
                    if not clicou and opcoes:
                        _clicar_opcao(page, opcoes[-1])

                else:
                    opcao_escolhida = _escolher_opcao_multipla_escolha(pergunta, opcoes, config)
                    if not opcao_escolhida:
                        opcao_escolhida = _fallback_local_multipla_escolha(pergunta, opcoes)
                        log(f"       → Fallback local: '{opcao_escolhida['label'][:50]}'")
                    respostas_salvas[pergunta] = opcao_escolhida["label"] or opcao_escolhida["value"]
                    _clicar_opcao(page, opcao_escolhida)

                esperar(page, 0.4)

            except Exception as e:
                log(f"    ⚠️  Erro ao responder grupo '{name}': {e}")
                try:
                    fb = _coletar_opcoes_grupo(page, radio_els)
                    if fb:
                        _clicar_opcao(page, fb[-1])
                except Exception:
                    pass

        for textarea in page.query_selector_all("textarea[data-idkillerquestiontype]"):
            try:
                id_kq    = textarea.get_attribute("data-idkillerquestion") or ""
                pergunta = pegar_texto_pergunta_infojobs(page, id_kq)
                if not pergunta:
                    pergunta = textarea.get_attribute("placeholder") or "Descreva sua experiência"

                log(f"    📝 Respondendo aberta: {pergunta[:80]}...")
                resposta = responder_pergunta_aberta(pergunta, config)
                textarea.click(force=True)
                textarea.fill(resposta)
                respostas_salvas[pergunta] = resposta
                log(f"       → {resposta[:80]}...")
                esperar(page, 0.5)

            except Exception as e:
                log(f"    ⚠️  Erro ao responder textarea: {e}")

        return True, respostas_salvas

    except Exception as e:
        log(f"  ⚠️  Erro ao processar killer questions: {e}")
        return False, respostas_salvas


# ══════════════════════════════════════════════════════════════════════════════
#  PERGUNTAS ABERTAS
# ══════════════════════════════════════════════════════════════════════════════

def _fallback_local_pergunta_aberta(pergunta: str) -> str:
    p = pergunta.lower()

    if any(x in p for x in ["conhecimento", "habilidade", "skill", "experiência técnica",
                             "principais conhecimentos", "conhece", "domina", "sabe"]):
        return ("Tenho experiência sólida com Python, Django e React para desenvolvimento "
                "full stack, além de PHP, JavaScript, MySQL e APIs RESTful. Trabalho com "
                "Git, Docker e autenticação JWT em projetos reais desde 2022.")
    if any(x in p for x in ["por que", "porque", "motivação", "motivo", "interesse na vaga",
                             "por qual razão", "o que te atrai", "o que te motivou"]):
        return ("Busco minha primeira experiência CLT para crescer como desenvolvedor em "
                "ambiente colaborativo. A vaga se alinha com meu stack atual e quero "
                "contribuir com o que já desenvolvi como freelancer.")
    if any(x in p for x in ["experiência profissional", "trajetória", "carreira",
                             "histórico profissional", "fale sobre você",
                             "conte sobre você", "se apresente", "apresentação"]):
        return ("Atuo como desenvolvedor web freelancer desde novembro de 2022, com foco "
                "em Python/Django, PHP e React. Desenvolvi sistemas de e-commerce, APIs "
                "RESTful, chatbots com IA e aplicações financeiras. Atualmente cursando "
                "Engenharia de Software na Estácio.")
    if any(x in p for x in ["formação", "escolaridade", "curso", "graduação",
                             "faculdade", "universidade", "estuda"]):
        return "Engenharia de Software (cursando, 1º semestre) — Estácio de Sá, EAD."
    if any(x in p for x in ["pretensão", "salário", "remuneração", "expectativa salarial"]):
        return "R$ 3000"
    if any(x in p for x in ["horário", "turno", "período", "manhã", "tarde", "noite",
                             "disponibilidade de horário", "qual horário"]):
        return "Tenho disponibilidade integral — manhã, tarde e noite."
    if any(x in p for x in ["cidade", "local", "deslocamento", "distância", "mora",
                             "reside", "onde mora", "localização"]):
        return "Moro em Ribeirão Preto/SP e aceito remoto, híbrido ou presencial."
    if any(x in p for x in ["diferencial", "ponto forte", "destaque", "qualidade",
                             "o que te diferencia", "por que te contratar"]):
        return ("Meu diferencial é a capacidade de entregar soluções completas de forma "
                "autônoma — do banco de dados à interface — com código limpo e foco em "
                "resultado. Tenho experiência real com IA, automação e APIs escaláveis.")
    if any(x in p for x in ["projeto", "portfólio", "portfolio", "o que já fez",
                             "o que desenvolveu", "trabalhos anteriores"]):
        return ("Desenvolvi um chatbot com IA (Python/Django) que automatizou 80% do "
                "atendimento, um sistema financeiro completo (React/PHP/Docker) e uma "
                "API RESTful de e-commerce com autenticação JWT. Portfólio: "
                "portfolio--gabriel.vercel.app")
    if any(x in p for x in ["ferramenta", "tecnologia", "linguagem", "framework",
                             "stack", "qual linguagem", "qual tecnologia"]):
        return ("Trabalho com Python, Django, PHP, Laravel, JavaScript, React, MySQL, "
                "PostgreSQL, Docker, Git e APIs RESTful. Tenho certificações em HTML5, "
                "CSS3, JS, PHP e Django.")
    if any(x in p for x in ["inglês", "ingles", "idioma", "língua", "english"]):
        return "Inglês básico — consigo ler documentação técnica sem dificuldade."
    if any(x in p for x in ["equipe", "time", "colaboração", "trabalho em grupo",
                             "colegas", "comunicação"]):
        return ("Como freelancer trabalhei diretamente com clientes, alinhando expectativas "
                "e entregando dentro do prazo. Estou acostumado a comunicação clara e "
                "gestão de prioridades de forma autônoma.")
    if any(x in p for x in ["desafio", "dificuldade", "obstáculo", "problema que resolveu",
                             "situação difícil"]):
        return ("Um dos maiores desafios foi integrar NLP e LLMs num chatbot para atender "
                "automaticamente clientes de e-commerce. Resolvi com pesquisa, testes "
                "iterativos e documentação constante, chegando a 80% de automação.")
    if any(x in p for x in ["objetivo", "plano", "meta", "onde quer chegar",
                             "onde se vê", "futuro profissional"]):
        return ("Quero crescer como desenvolvedor full stack em ambiente colaborativo, "
                "aprofundar conhecimentos em arquitetura de software e contribuir com "
                "projetos que gerem impacto real.")
    if any(x in p for x in ["quando pode começar", "início", "disponibilidade",
                             "quando estaria disponível"]):
        return "Tenho disponibilidade imediata para início."

    return ("Tenho ~3 anos de experiência como desenvolvedor freelancer, com foco em "
            "Python, Django, React e PHP. Desenvolvo APIs, automações e interfaces "
            "completas, e busco minha primeira oportunidade CLT para crescer em equipe.")


def responder_pergunta_aberta(pergunta: str, config: dict) -> str:
    pergunta_lower = pergunta.lower()
    div       = config.get("diversidade", {})
    candidato = config.get("candidato", {})

    if any(p in pergunta_lower for p in ["salari", "pretens", "remuner", "valor", "expectativa"]):
        eh_pj = any(p in pergunta_lower for p in ["pj", "pessoa jurídica", "pessoa juridica", "mei"])
        return (f"R$ {candidato.get('pretensao_pj_mensal', '4500')}/mês"
                if eh_pj else f"R$ {candidato.get('pretensao_clt', '3000')}")
    if any(p in pergunta_lower for p in ["indicad", "matrícula", "recomendad"]):
        return "Não"
    if any(p in pergunta_lower for p in ["deficiência", "deficiente", "pcd", "acessibilidade"]):
        return "Não possuo deficiência" if not div.get("pcd") else "Sim, possuo deficiência"
    if any(p in pergunta_lower for p in ["raça", "cor", "étnico", "etnia"]):
        return div.get("raca_cor", "Pardo")
    if any(p in pergunta_lower for p in ["gênero", "genero", "identidade de gênero"]):
        return div.get("genero", "Homem cisgênero")
    if any(p in pergunta_lower for p in ["orientação sexual", "orientacao sexual"]):
        return div.get("orientacao_sexual", "Heterossexual")
    if any(p in pergunta_lower for p in ["cnh", "carteira de habilitação", "habilitação"]):
        return "Não possuo CNH"
    if any(p in pergunta_lower for p in ["disponibilidade", "início", "quando pode começar"]):
        return "Disponibilidade imediata"
    if any(p in pergunta_lower for p in ["inglês", "ingles", "english"]):
        return "Nível básico, com boa capacidade de leitura técnica"

    prompt = f"""Você vai responder uma pergunta de processo seletivo em nome de um candidato de TI júnior.

PERFIL DO CANDIDATO (responda SOMENTE com base nele; a lista de exclusões vale):
{_perfil_ctx(config)}

PERGUNTA:
{pergunta}

REGRAS DE ESCRITA (MUITO IMPORTANTES):
- Escreva em português, tom profissional mas natural — como uma pessoa real escreveria
- NÃO use frases que pareçam geradas por IA como: "Certamente", "Com prazer", "Excelente pergunta"
- NÃO comece com "Sim" ou "Não" direto — desenvolva a resposta
- Seja honesto sobre o nível (júnior), mas mostre entusiasmo e disposição para aprender
- Entre 3 e 6 frases, máximo 400 caracteres
- Use linguagem direta, sem exageros, sem adjetivos desnecessários
- Não mencione o nome do candidato

Resposta:"""

    resposta = _chamar_llm(prompt, config, contexto="aberta", temperatura=0.6)
    return resposta or _fallback_local_pergunta_aberta(pergunta)


# ══════════════════════════════════════════════════════════════════════════════
#  CARTA DE APRESENTAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

def _fallback_local_carta(titulo: str, descricao: str) -> str:
    """Carta personalizada por categoria quando todas as APIs falham."""
    t = (titulo + " " + descricao).lower()

    if any(x in t for x in ["suporte", "help desk", "helpdesk", "service desk",
                             "field service", "assistente de ti", "atendimento técnico",
                             "sustentação", "noc"]):
        return ("Tenho ~3 anos de experiência em desenvolvimento web com Python e React, "
                "o que me deu base sólida para atuar em suporte técnico: diagnostico "
                "problemas de sistemas, APIs e banco de dados com agilidade. Desenvolvi "
                "um chatbot que automatizou 80% do atendimento. Disponibilidade imediata.")
    if any(x in t for x in ["infraestrutura", "redes", "cloud", "devops", "sre",
                             "sysadmin", "linux", "aws", "azure", "kubernetes"]):
        return ("Trabalho com Docker e containerização desde 2023, apliquei em produção "
                "no projeto GoMoney. Tenho familiaridade com Linux, Git e automação de "
                "processos. Busco aprofundar minha atuação em infraestrutura e cloud. "
                "Disponibilidade imediata.")
    if any(x in t for x in ["dados", "data", "bi", "business intelligence", "analytics",
                             "power bi", "tableau", "etl", "pandas", "numpy",
                             "cientista", "analista de dados"]):
        return ("Utilizo Python com Pandas e NumPy em projetos de processamento de dados "
                "e já desenvolvi dashboards com Chart.js integrados a MySQL. Tenho "
                "experiência com modelagem relacional e consultas complexas. "
                "Disponibilidade imediata.")
    if any(x in t for x in ["python", "django", "flask", "fastapi"]):
        return ("Desenvolvedor Python desde 2022 com projetos em produção usando Django "
                "e DRF. Construí API RESTful de e-commerce com JWT e chatbot com LLMs "
                "que automatizou 80% do atendimento. Disponibilidade imediata.")
    if any(x in t for x in ["php", "laravel", "wordpress", "codeigniter"]):
        return ("Trabalho com PHP desde 2022, desenvolvendo sistemas web e APIs RESTful. "
                "No GoMoney construí o backend com JWT, CRUD completo e MySQL. Tenho "
                "certificação PHP avançado (B7Web). Disponibilidade imediata.")
    if any(x in t for x in ["frontend", "front-end", "front end", "react", "vue",
                             "angular", "next", "typescript", "javascript"]):
        return ("Desenvolvedor frontend com foco em React e TypeScript desde 2022. "
                "Construí e-commerce completo com Tailwind CSS e JWT, além de dashboards "
                "com Chart.js no GoMoney. Código limpo e componentizado. "
                "Disponibilidade imediata.")
    if any(x in t for x in ["full stack", "fullstack", "full-stack"]):
        return ("Desenvolvedor Full Stack com ~3 anos em Python/Django e React. Construí "
                "APIs RESTful, chatbot com IA (80% de automação) e sistema financeiro "
                "completo com Docker e JWT. Do banco de dados à interface. "
                "Disponibilidade imediata.")
    if any(x in t for x in ["mobile", "android", "ios", "flutter", "react native"]):
        return ("Minha base em React e APIs RESTful me permite evoluir rapidamente para "
                "React Native. Tenho experiência com JWT e consumo de APIs que são "
                "fundamentais no mobile. Disponibilidade imediata.")
    if any(x in t for x in ["qa", "qualidade", "testes", "quality assurance",
                             "selenium", "cypress"]):
        return ("Minha experiência full stack me deu visão clara sobre pontos de falha "
                "em APIs, banco de dados e interfaces. Já apliquei validação manual e "
                "automatizada nos meus projetos. Disponibilidade imediata.")
    if any(x in t for x in ["sap", "totvs", "erp", "protheus", "dynamics"]):
        return ("Tenho experiência em sistemas empresariais com Python, PHP e MySQL — "
                "modelagem de dados, integrações e automação de processos. Aprendo "
                "stacks específicas com rapidez. Disponibilidade imediata.")
    if any(x in t for x in ["estágio", "estagio", "trainee", "jovem aprendiz"]):
        return ("Estou cursando Engenharia de Software (1º semestre, Estácio) e tenho "
                "~3 anos de experiência prática como freelancer em Python, React e PHP. "
                "Busco minha primeira experiência formal. Disponibilidade imediata.")
    if any(x in t for x in ["administrativo", "governança", "gestão", "processos",
                             "compliance", "business"]):
        return ("Tenho experiência em automação de processos que reduziu erros em 30% "
                "e automatizou 80% de tarefas manuais. Visão técnica e de negócios "
                "combinadas. Disponibilidade imediata.")

    return ("Desenvolvedor Full Stack com ~3 anos em Python, Django, React e PHP. "
            "Desenvolvi APIs RESTful, chatbot com IA (80% automação) e sistema "
            "financeiro completo com Docker e JWT. Busco primeira experiência CLT. "
            "Disponibilidade imediata.")


def gerar_carta_apresentacao(titulo: str, descricao: str, config: dict) -> str:
    prompt = f"""Escreva uma carta de apresentação para uma candidatura de emprego.

PERFIL DO CANDIDATO (responda SOMENTE com base nele; a lista de exclusões vale):
{_perfil_ctx(config)}

VAGA:
Título: {titulo}
Descrição: {descricao[:600]}

REGRAS (MUITO IMPORTANTES):
- Máximo 800 caracteres (o campo aceita até 1000)
- Tom profissional, direto e natural — como uma pessoa real escreveria
- NÃO use frases genéricas de IA: "Venho por meio desta", "Prezado(a)", "Atenciosamente"
- NÃO use saudações formais de carta — vai direto ao ponto
- Destaque 1 ou 2 experiências/projetos relevantes para ESSA vaga específica
- Mencione disponibilidade e motivação de forma breve
- Seja honesto com o nível júnior, mas mostre resultado concreto
- Não mencione o nome do candidato

Carta:"""

    resposta = _chamar_llm(prompt, config, contexto="carta", temperatura=0.6)
    return resposta or _fallback_local_carta(titulo, descricao)


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def fazer_login(page: Page, config: dict) -> bool:
    log("🔐 Fazendo login no InfoJobs...")
    email = os.environ.get("INFOJOBS_EMAIL")
    senha = os.environ.get("INFOJOBS_SENHA")
    if not email or not senha:
        log("❌ INFOJOBS_EMAIL ou INFOJOBS_SENHA não encontrados no .env!")
        return False
    try:
        page.goto(config["infojobs"]["url_login"], timeout=15000, wait_until="domcontentloaded")
        esperar(page, 2)
        for seletor in ["#onetrust-accept-btn-handler", "button:has-text('Aceitar todos')",
                         "button:has-text('Aceitar')", ".js_cookiesAccept"]:
            try:
                btn = page.query_selector(seletor)
                if btn and btn.is_visible():
                    btn.click()
                    log("  ✓ Popup de cookies fechado")
                    esperar(page, 1)
                    break
            except Exception:
                pass
        page.fill("#Email", email)
        esperar(page, 0.5)
        page.click(".js_loginButton")
        esperar(page, 2)
        campo_senha = page.query_selector("#Password")
        if campo_senha:
            campo_senha.fill(senha)
            esperar(page, 0.5)
            page.click(".js_loginButton")
            esperar(page, 3)
        if "login" in page.url.lower() or "account" in page.url.lower():
            log("❌ Falha no login. Verifique INFOJOBS_EMAIL e INFOJOBS_SENHA no .env")
            return False
        log("✅ Login realizado!")
        return True
    except Exception as e:
        log(f"❌ Erro no login: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  BUSCAR VAGAS
# ══════════════════════════════════════════════════════════════════════════════

def buscar_vagas_infojobs(page: Page, config: dict) -> list:
    palavras          = config["busca"]["palavras_chave"]
    excluir           = [p.lower() for p in config["busca"]["palavras_excluir"]]
    vagas_encontradas = []
    links_vistos      = set()
    log("🔍 Buscando vagas no InfoJobs...\n")

    for palavra in palavras:
        try:
            url = f"{config['infojobs']['url_busca']}?palabra={palavra.replace(' ', '+')}"
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            esperar(page, 2)
            cards = page.query_selector_all(".js_rowCard")
            log(f"  [{palavra}] {len(cards)} vagas encontradas")
            for card in cards:
                try:
                    texto_card = (card.inner_text() or "").lower()
                    if any(ex in texto_card for ex in excluir):
                        continue
                    link_el = card.query_selector(".js_cardLink") or card.query_selector("a[href*='vaga-de']")
                    if not link_el:
                        continue
                    href = link_el.get_attribute("data-href") or link_el.get_attribute("href") or ""
                    if not href:
                        continue
                    if href.startswith("/"):
                        link = "https://www.infojobs.com.br" + href
                    elif href.startswith("http"):
                        link = href
                    else:
                        link = "https://www.infojobs.com.br/" + href
                    if link in links_vistos:
                        continue
                    links_vistos.add(link)
                    titulo_el = card.query_selector("h2")
                    titulo    = titulo_el.inner_text().strip() if titulo_el else palavra
                    local     = ""
                    for linha in texto_card.split("\n"):
                        if " - " in linha and any(
                            uf in linha.upper()
                            for uf in ["SP","RJ","MG","PR","SC","RS","GO","BA","CE","PE"]
                        ):
                            local = linha.strip()
                            break
                    vagas_encontradas.append({"titulo": titulo, "link": link,
                                              "local": local, "palavra_chave": palavra})
                    log(f"    ✅ {titulo} | {local}")
                except Exception as e:
                    log(f"    ⚠️  Erro num card: {e}")
        except Exception as e:
            log(f"⚠️  Erro buscando '{palavra}': {e}")

    log(f"\n📋 Total de vagas novas: {len(vagas_encontradas)}")
    return vagas_encontradas


# ══════════════════════════════════════════════════════════════════════════════
#  FECHAR MODAL
# ══════════════════════════════════════════════════════════════════════════════

def fechar_modal_se_existir(page: Page):
    for seletor in ["#modalCreateAlert [data-dismiss='modal']",
                     ".modal.show [data-dismiss='modal']",
                     ".modal.show [data-bs-dismiss='modal']",
                     ".modal.show .modal-header .btn",
                     ".toast.show .js_toastClose"]:
        try:
            el = page.query_selector(seletor)
            if el and el.is_visible():
                el.click()
                log("  ✓ Modal/popup fechado")
                esperar(page, 0.8)
                break
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  CARTA — helper de envio
# ══════════════════════════════════════════════════════════════════════════════

def tentar_enviar_carta(page: Page, titulo: str, descricao: str, config: dict) -> str:
    carta_gerada = ""
    try:
        btn_carta = page.query_selector("#btnLetterToCompany")
        if not btn_carta or not btn_carta.is_visible():
            return carta_gerada
        log("  ✉️  Carta de apresentação disponível, anexando...")
        btn_carta.click()
        esperar(page, 1.5)
        textarea_carta = page.query_selector("#LetterToCompany")
        if not textarea_carta:
            return carta_gerada
        carta_gerada = gerar_carta_apresentacao(titulo, descricao, config)
        textarea_carta.click(force=True)
        textarea_carta.fill(carta_gerada)
        log(f"  ✓ Carta gerada: {carta_gerada[:80]}...")
        esperar(page, 0.5)
        btn_anexar = page.query_selector("#btnSendLetterToCompanyModal")
        if btn_anexar and btn_anexar.is_visible():
            btn_anexar.click()
            esperar(page, 2)
            log("  ✅ Carta anexada!")
    except Exception as e:
        log(f"  ⚠️  Erro ao enviar carta: {e}")
    return carta_gerada


# ══════════════════════════════════════════════════════════════════════════════
#  FLUXO DE CANDIDATURA
# ══════════════════════════════════════════════════════════════════════════════

def candidatar_vaga_infojobs(page: Page, vaga: dict, config: dict) -> dict:
    resultado = {
        "vaga":      vaga["titulo"],
        "link":      vaga["link"],
        "local":     vaga.get("local", ""),
        "site":      "InfoJobs",
        "status":    "erro",
        "data":      datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"),
        "horario":   datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M:%S"),
        "curriculo": "perfil InfoJobs",
        "respostas": {},
        "carta":     "",
    }
    try:
        log(f"\n🚀 Abrindo vaga: {vaga['titulo']}")
        page.goto(vaga["link"], timeout=15000, wait_until="domcontentloaded")
        esperar(page, 2)
        fechar_modal_se_existir(page)

        btn_candidatar = None
        for seletor in ["a.js_btApplyVacancy", "a[data-iv]",
                         "a:has-text('CANDIDATAR-ME')", "a:has-text('Candidatar-me')",
                         "button:has-text('CANDIDATAR-ME')"]:
            try:
                el = page.query_selector(seletor)
                if el and el.is_visible():
                    btn_candidatar = el
                    break
            except Exception:
                pass

        if not btn_candidatar:
            log("  ❌ Botão 'Candidatar-me' não encontrado")
            resultado["status"] = "botao_nao_encontrado"
            return resultado

        btn_candidatar.click()
        esperar(page, 2)

        aviso = page.query_selector("#WarningVacancyToast")
        if aviso and aviso.is_visible():
            log("  ⏭️  Já candidatado anteriormente, pulando...")
            resultado["status"] = "ja_candidatado"
            return resultado

        fechar_modal_se_existir(page)
        esperar(page, 1)

        descricao = ""
        try:
            desc_el = page.query_selector(".js_vacancyDataPanels p")
            if desc_el:
                descricao = desc_el.inner_text().strip()[:800]
        except Exception:
            pass

        _, respostas_kq      = responder_killer_questions(page, config)
        resultado["respostas"] = respostas_kq

        # Supervisor de tela: overlay que o flow clássico não conhece (layout
        # mudou, modal novo apareceu entre KQ e submit). Camada de texto e
        # captcha correm SEM LLM; só overlay "estranho" chama o LLM.
        def _chamar_resgate(prompt: str, max_tokens: int = 300) -> str:
            return _chamar_llm(prompt, config,
                               contexto=vaga.get("titulo", ""),
                               temperatura=0.4) or ""

        bloqueio = pagelens.tratar_bloqueio_pw(page, chamar=_chamar_resgate, log=log)
        if bloqueio["tipo"] == "fechou":
            if bloqueio["el"] is not None:
                with contextlib.suppress(Exception):
                    bloqueio["el"].click()
            log(f"  [bloqueio] modal fechado antes do submit: {bloqueio['detalhe'][:80]}")
            esperar(page, 1.5)
        elif bloqueio["tipo"] == "captcha":
            log(f"  [bloqueio] desafio humano no meio do flow — aguardando: "
                f"{bloqueio['detalhe'][:80]}")
            esperar(page, 10)

        btn_concluir = page.query_selector("#btnKillerQuestionsAccept")
        if btn_concluir and btn_concluir.is_visible():
            btn_concluir.click()
            esperar(page, 3)

        confirmacao = None
        for seletor in ["div.text-success h3", "h3:has-text('Você se candidatou')"]:
            try:
                confirmacao = page.query_selector(seletor)
                if confirmacao:
                    break
            except Exception:
                pass

        if confirmacao or btn_concluir:
            log("  ✅ Candidatura enviada!")
            resultado["status"] = "enviado"
            esperar(page, 1)
            fechar_modal_se_existir(page)
            resultado["carta"] = tentar_enviar_carta(page, vaga["titulo"], descricao, config)
        else:
            # Parada "invisível": sem confirmação e sem botão — tenta o
            # supervisor de novo (overlay pode estar escondendo a tela de ok).
            bloqueio2 = pagelens.tratar_bloqueio_pw(page, chamar=_chamar_resgate, log=log)
            if bloqueio2["tipo"] == "fechou":
                if bloqueio2["el"] is not None:
                    with contextlib.suppress(Exception):
                        bloqueio2["el"].click()
                esperar(page, 3)
                for seletor in ["div.text-success h3", "h3:has-text('Você se candidatou')"]:
                    with contextlib.suppress(Exception):
                        if page.query_selector(seletor):
                            log("  ✅ Candidatura enviada (após resgate do overlay)!")
                            resultado["status"] = "enviado"
                            break
            else:
                log(f"  [bloqueio] sem confirmação após resgate: "
                    f"{bloqueio2['detalhe'][:80] or 'tela livre (mudou o layout?)'}")
            if resultado["status"] != "enviado":
                if bloqueio2["tipo"] in ("indeciso", "captcha"):
                    resultado["status"] = ("modal_nao_resolvido"
                                            if bloqueio2["tipo"] == "indeciso"
                                            else "captcha_nao_resolvido")
                else:
                    log("  ⚠️  Candidatura pode ter sido enviada — sem confirmação clara")
                    resultado["status"] = "preenchido_sem_confirmacao"
            fechar_modal_se_existir(page)

    except Exception as e:
        log(f"  ❌ Erro: {e}")
        resultado["status"] = f"erro: {e!s}"

    return resultado


# ══════════════════════════════════════════════════════════════════════════════
#  LOG / RELATÓRIO
# ══════════════════════════════════════════════════════════════════════════════

def _ler_json_candidaturas() -> tuple[list, list]:
    arquivo = "relatorio/candidaturas.json"
    if not os.path.exists(arquivo):
        return [], []
    with open(arquivo, encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError:
            return [], []
    if isinstance(dados, dict):
        c  = dados.get("candidaturas", [])
        jc = dados.get("ja_candidatado", [])
        return (c if isinstance(c, list) else [], jc if isinstance(jc, list) else [])
    if isinstance(dados, list):
        c  = [x for x in dados if isinstance(x, dict)]
        jc = [x["link"] for x in c if x.get("status") == "enviado" and "link" in x]
        return c, jc
    return [], []


def links_ja_candidatados() -> set:
    candidaturas, ja_candidatado = _ler_json_candidaturas()
    links = set(ja_candidatado)
    for c in candidaturas:
        if isinstance(c, dict) and c.get("status") == "enviado" and "link" in c:
            links.add(c["link"])
    return links


def _formatar_respostas_txt(respostas: dict) -> str:
    if not respostas:
        return "    (sem killer questions)\n"
    linhas = []
    for pergunta, resposta in respostas.items():
        linhas.append(f"    ❓ {pergunta}")
        for linha in str(resposta).splitlines():
            linhas.append(f"       → {linha}")
    return "\n".join(linhas) + "\n"


def _formatar_carta_txt(carta: str) -> str:
    if not carta:
        return "    (sem carta de apresentação)\n"
    linhas      = ["    ✉️  Carta de Apresentação:"]
    palavras    = carta.split()
    linha_atual = "    "
    for palavra in palavras:
        if len(linha_atual) + len(palavra) + 1 > 84:
            linhas.append(linha_atual.rstrip())
            linha_atual = "    " + palavra + " "
        else:
            linha_atual += palavra + " "
    if linha_atual.strip():
        linhas.append(linha_atual.rstrip())
    return "\n".join(linhas) + "\n"


def salvar_log(candidaturas_novas: list):
    os.makedirs("relatorio", exist_ok=True)
    hoje         = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    arquivo_json = "relatorio/candidaturas.json"

    candidaturas_existentes, ja_candidatado_existente = _ler_json_candidaturas()
    todas_candidaturas = candidaturas_existentes + candidaturas_novas

    links_novos = {c["link"] for c in candidaturas_novas
                   if isinstance(c, dict) and c.get("status") == "enviado" and "link" in c}
    ja_candidatado_atualizado = sorted(set(ja_candidatado_existente) | links_novos)

    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump({"candidaturas": todas_candidaturas,
                   "ja_candidatado": ja_candidatado_atualizado},
                  f, ensure_ascii=False, indent=2)

    resumo   = f"relatorio/infojobs_{hoje}.txt"
    enviadas = [c for c in candidaturas_novas if c["status"] == "enviado"]

    with open(resumo, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write(f"📊 INFOJOBS — {hoje}\n{'='*50}\n\n")
            f.write(f"✅ Enviadas: {len(enviadas)}/{len(candidaturas_novas)}\n\n")
        for c in candidaturas_novas:
            f.write(f"[{c['status'].upper()}] {c['vaga']} | {c.get('local','')}\n")
            f.write(f"  🔗 {c['link']}\n")
            f.write(f"  🕐 {c.get('data','')} {c.get('horario','')}\n\n")
            f.write("  📋 Respostas das Killer Questions:\n")
            f.write(_formatar_respostas_txt(c.get("respostas", {})))
            f.write("\n")
            f.write(_formatar_carta_txt(c.get("carta", "")))
            f.write("\n" + "-"*50 + "\n\n")

    print(f"\n  📄 Relatório salvo: {resumo}")
    print(f"  📝 Total histórico: {len(todas_candidaturas)} candidaturas | "
          f"{len(ja_candidatado_atualizado)} links na blacklist")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════╗
║       🤖 JOB HUNTER — INFOJOBS  v1.5    ║
╚══════════════════════════════════════════╝
    """)

    config = carregar_config()

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY não configurada no .env!")
        return
    if not os.environ.get("INFOJOBS_SENHA"):
        print("❌ INFOJOBS_SENHA não configurada no .env!")
        return
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY não configurada — Gemini desativado como fallback")
    if not MISTRAL_API_KEY:
        print("⚠️  MISTRAL_API_KEY não configurada — Mistral desativado como fallback")

    ja_candidatados = links_ja_candidatados()
    print(f"  📋 Links já candidatados na blacklist: {len(ja_candidatados)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["automacao"]["headless"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"
        )
        page = context.new_page()

        if not fazer_login(page, config):
            browser.close()
            return

        vagas       = buscar_vagas_infojobs(page, config)
        vagas_novas = [v for v in vagas if v["link"] not in ja_candidatados]
        vagas_novas = vagas_novas[:config["automacao"]["max_candidaturas_por_dia"]]

        print(f"\n🎯 Vagas para candidatar: {len(vagas_novas)}")
        print("=" * 50)

        candidaturas = []
        try:
            for i, vaga in enumerate(vagas_novas, 1):
                print(f"\n[{i}/{len(vagas_novas)}]")
                resultado = candidatar_vaga_infojobs(page, vaga, config)
                candidaturas.append(resultado)
                salvar_log([resultado])
                time.sleep(config["automacao"]["delay_entre_vagas"])
        finally:
            browser.close()

    print("\n" + "=" * 50)
    enviadas = [c for c in candidaturas if c["status"] == "enviado"]
    print(f"✅ Enviadas: {len(enviadas)}/{len(candidaturas)}")
    print("\n🏁 Finalizado!")


if __name__ == "__main__":
    main()
