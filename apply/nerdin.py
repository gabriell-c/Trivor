"""
nerdin.py — Automação completa do Nerdin
Fluxo: Login → Buscar vagas → Candidatura (3 etapas) → Enviar

VERSÃO v1.2:
  - LLM router Groq → Gemini → Mistral → fallback local
    · Groq rate limit curto (< 5min): aguarda e retenta automaticamente
    · Groq rate limit diário: troca para Gemini até meia-noite
    · Gemini 2.5 Flash-Lite: 1.000 req/dia, 15 RPM, com retry automático
    · Mistral Small: ~1 bilhão tokens/mês, praticamente ilimitado
    · Fallback local como último recurso (zero API)
  - Salvamento de respostas no relatório:
    · Função detectada, níveis de tech, pretensão, PJ, currículo
    · JSON e .txt diário com dados completos por candidatura
  - Variáveis de ambiente necessárias:
    · GROQ_API_KEY    — console.groq.com
    · GEMINI_API_KEY  — aistudio.google.com
    · MISTRAL_API_KEY — console.mistral.ai

VERSÃO v1.1:
  - Salvamento de respostas no relatório (função, tecnologias, pretensão)

VERSÃO v1.0:
  - Resolução de função do cargo via CARGO_MAP estático + LLM fallback
  - Resolução de nível de tecnologia via config.yaml + LLM fallback
"""

import os
import re
import time
import json
import yaml
import threading
import datetime as _dt
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, Page
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Cache em memória: evita chamar LLM duas vezes pro mesmo cargo/tech
_cache_nivel_tech: dict[str, str] = {}
_cache_funcao:     dict[str, str] = {}

# ══════════════════════════════════════════════════════════════════════════════
#  MAPA ESTÁTICO DE CARGOS
# ══════════════════════════════════════════════════════════════════════════════

CARGO_MAP: list[tuple[str, str]] = [
    # ── Dados ────────────────────────────────────────────────────────────
    (r"engenheiro?\s*de\s*dados",       "Engenheiro de Dados"),
    (r"cientista\s*de\s*dados",         "Cientista de Dados"),
    (r"analista\s*de\s*dados",          "Analista de Dados"),
    (r"data\s*engineer",                "Engenheiro de Dados"),
    (r"data\s*scientist",               "Cientista de Dados"),
    (r"data\s*analyst",                 "Analista de Dados"),
    (r"analista\s*bi\b",                "Analista de BI"),
    (r"analista\s*de\s*bi\b",           "Analista de BI"),
    (r"business\s*analyst",             "Analista de Negócios"),
    (r"business\s*intelligence",        "Analista de BI"),
    (r"power\s*bi",                     "Analista de BI"),
    # ── Desenvolvimento ───────────────────────────────────────────────────
    (r"desenvolvedora?\s*full.?stack",  "Desenvolvedor Fullstack"),
    (r"desenvolvedora?\s*frontend",     "Desenvolvedor Frontend"),
    (r"desenvolvedora?\s*front.?end",   "Desenvolvedor Frontend"),
    (r"desenvolvedora?\s*backend",      "Desenvolvedor Backend"),
    (r"desenvolvedora?\s*back.?end",    "Desenvolvedor Backend"),
    (r"desenvolvedora?\s*python",       "Desenvolvedor Python"),
    (r"desenvolvedora?\s*django",       "Desenvolvedor Python"),
    (r"desenvolvedora?\s*flask",        "Desenvolvedor Python"),
    (r"desenvolvedora?\s*php",          "Desenvolvedor PHP"),
    (r"desenvolvedora?\s*laravel",      "Desenvolvedor PHP"),
    (r"desenvolvedora?\s*react\b",      "Desenvolvedor React"),
    (r"desenvolvedora?\s*vue",          "Desenvolvedor Vue.js"),
    (r"desenvolvedora?\s*angular",      "Desenvolvedor Angular"),
    (r"desenvolvedora?\s*node",         "Desenvolvedor Node.js"),
    (r"desenvolvedora?\s*javascript",   "Desenvolvedor JavaScript"),
    (r"desenvolvedora?\s*typescript",   "Desenvolvedor TypeScript"),
    (r"desenvolvedora?\s*java\b",       "Desenvolvedor Java"),
    (r"desenvolvedora?\s*\.net",        "Desenvolvedor .NET"),
    (r"desenvolvedora?\s*dynamics",     "Desenvolvedor Dynamics"),
    (r"desenvolvedora?\s*mobile",       "Desenvolvedor Mobile"),
    (r"desenvolvedora?\s*web",          "Desenvolvedor Web"),
    (r"desenvolvedora?\s*de\s*sistemas","Desenvolvedor de Sistemas"),
    (r"desenvolvedora?\s*de\s*software","Desenvolvedor de Software"),
    (r"desenvolvedora?\b",              "Desenvolvedor de Software"),
    (r"programadora?\s*python",         "Desenvolvedor Python"),
    (r"programadora?\s*php",            "Desenvolvedor PHP"),
    (r"programadora?\s*web",            "Desenvolvedor Web"),
    (r"programadora?\b",                "Desenvolvedor de Software"),
    (r"front.?end\b",                   "Desenvolvedor Frontend"),
    (r"back.?end\b",                    "Desenvolvedor Backend"),
    (r"full.?stack\b",                  "Desenvolvedor Fullstack"),
    (r"engenheiro?\s*de\s*software",    "Engenheiro de Software"),
    (r"software\s*engineer",            "Engenheiro de Software"),
    # ── DevOps / Cloud / Infra ────────────────────────────────────────────
    (r"devops",                         "Engenheiro DevOps"),
    (r"site\s*reliability",             "Engenheiro SRE"),
    (r"\bsre\b",                        "Engenheiro SRE"),
    (r"cloud\s*computing",              "Especialista em Cloud"),
    (r"engenheiro?\s*cloud",            "Engenheiro Cloud"),
    (r"analista\s*cloud",               "Analista Cloud"),
    (r"analista\s*de\s*infraestrutura", "Analista de Infraestrutura"),
    (r"analista\s*de\s*redes",          "Analista de Redes"),
    (r"administrador\s*de\s*redes",     "Administrador de Redes"),
    (r"administrador\s*de\s*sistemas",  "Administrador de Sistemas"),
    (r"sysadmin",                       "Administrador de Sistemas"),
    (r"infraestrutura",                 "Analista de Infraestrutura"),
    # ── Suporte ───────────────────────────────────────────────────────────
    (r"service\s*desk",                 "Analista de Service Desk"),
    (r"help\s*desk",                    "Analista de Help Desk"),
    (r"helpdesk",                       "Analista de Help Desk"),
    (r"suporte\s*n[123]",               "Analista de Suporte"),
    (r"analista\s*de\s*suporte",        "Analista de Suporte"),
    (r"técnico\s*de\s*suporte",         "Técnico de Suporte"),
    (r"auxiliar\s*de\s*suporte",        "Auxiliar de Suporte"),
    (r"suporte\s*técnico",              "Analista de Suporte"),
    (r"suporte\s*de\s*ti",              "Analista de Suporte TI"),
    (r"it\s*support",                   "Analista de Suporte TI"),
    (r"it\s*supporter",                 "Analista de Suporte TI"),
    (r"field\s*service",                "Técnico de Field Service"),
    (r"\bnoc\b",                        "Analista NOC"),
    # ── Segurança ─────────────────────────────────────────────────────────
    (r"segurança\s*da\s*informação",    "Analista de Segurança da Informação"),
    (r"cyber\s*security",               "Analista de Segurança da Informação"),
    (r"cybersecurity",                  "Analista de Segurança da Informação"),
    (r"pentest",                        "Analista de Pentest"),
    (r"\bsoc\b",                        "Analista SOC"),
    # ── QA / Testes ───────────────────────────────────────────────────────
    (r"analista\s*de\s*testes",         "Analista de Testes"),
    (r"analista\s*de\s*qualidade",      "Analista de Qualidade"),
    (r"analista\s*qa",                  "Analista de QA"),
    (r"quality\s*assurance",            "Analista de QA"),
    # ── Banco de Dados ────────────────────────────────────────────────────
    (r"\bdba\b",                        "Administrador de Banco de Dados"),
    (r"banco\s*de\s*dados",             "Administrador de Banco de Dados"),
    (r"analista\s*de\s*banco",          "Analista de Banco de Dados"),
    # ── ERP / SAP ─────────────────────────────────────────────────────────
    (r"sap\s*fi\s*co",                  "Consultor SAP FI/CO"),
    (r"sap\s*fi\b",                     "Consultor SAP FI"),
    (r"sap\s*co\b",                     "Consultor SAP CO"),
    (r"sap\s*abap",                     "Desenvolvedor SAP ABAP"),
    (r"consultor\s*sap",                "Consultor SAP"),
    (r"l[ií]der\s*sap",                 "Líder SAP"),
    (r"\bsap\b",                        "Consultor SAP"),
    (r"consultor\s*erp",                "Consultor ERP"),
    (r"analista\s*erp",                 "Analista ERP"),
    (r"analista\s*totvs",               "Analista TOTVS"),
    (r"implantador",                    "Consultor de Implantação"),
    (r"analista\s*de\s*implanta",       "Analista de Implantação"),
    # ── UX / Design ───────────────────────────────────────────────────────
    (r"ux\s*designer",                  "UX Designer"),
    (r"ui\s*designer",                  "UI Designer"),
    (r"analista\s*de\s*ux",             "Analista de UX"),
    (r"analista\s*de\s*ui",             "Analista de UI"),
    (r"analista\s*ux\b",                "Analista de UX"),
    (r"analista\s*ui\b",                "Analista de UI"),
    (r"ux[/\s]*ui",                     "UX/UI Designer"),
    (r"product\s*designer",             "Product Designer"),
    (r"web\s*designer",                 "Web Designer"),
    (r"motion\s*designer",              "Motion Designer"),
    (r"graphic\s*designer",             "Designer Gráfico"),
    (r"designer\s*gr[áa]fico",          "Designer Gráfico"),
    (r"\bdesigner\b",                   "Designer"),
    # ── Produto / Gestão ──────────────────────────────────────────────────
    (r"product\s*owner",                "Product Owner"),
    (r"scrum\s*master",                 "Scrum Master"),
    (r"analista\s*de\s*produto",        "Analista de Produto"),
    (r"gerente\s*de\s*projetos",        "Gerente de Projetos TI"),
    (r"gerente\s*de\s*inova",           "Gerente de Inovação"),
    (r"analista\s*de\s*processos",      "Analista de Processos"),
    (r"analista\s*de\s*opera",          "Analista de Operações"),
    (r"analista\s*de\s*monitoramento",  "Analista de Monitoramento"),
    (r"supervisor\s*de\s*ti",           "Supervisor de TI"),
    (r"supervisor\s*de\s*sistemas",     "Supervisor de Sistemas"),
    (r"consultor\s*de\s*ti",            "Consultor de TI"),
    (r"l[ií]der\s*de\s*delivery",       "Líder de Delivery"),
    (r"l[ií]der\s*t[eé]cnico",          "Líder Técnico"),
    # ── Estágio ───────────────────────────────────────────────────────────
    (r"est[aá]gi[oá].+suporte",         "Estagiário de Suporte TI"),
    (r"est[aá]gi[oá].+infra",           "Estagiário de Infraestrutura"),
    (r"est[aá]gi[oá].+dados",           "Estagiário de Dados"),
    (r"est[aá]gi[oá].+ti\b",            "Estagiário de TI"),
    (r"est[aá]gi[oá].+tecnologia",      "Estagiário de TI"),
    (r"est[aá]gi[oá].+admin",           "Estagiário Administrativo"),
    (r"est[aá]gi[oá]",                  "Estagiário de TI"),
    # ── Geral TI ─────────────────────────────────────────────────────────
    (r"analista\s*de\s*ti\b",           "Analista de TI"),
    (r"técnico\s*de\s*ti\b",            "Técnico de TI"),
    (r"assistente\s*de\s*ti\b",         "Assistente de TI"),
    # ── Marketing / Conteúdo ─────────────────────────────────────────────
    (r"marketing\s*digital",            "Analista de Marketing Digital"),
    (r"analista\s*de\s*marketing",      "Analista de Marketing"),
    (r"social\s*media",                 "Analista de Social Media"),
    (r"analista\s*de\s*m[ií]dia",       "Analista de Mídia"),
    (r"gestor\s*de\s*tr[áa]fego",       "Gestor de Tráfego"),
    (r"traffic\s*manager",              "Gestor de Tráfego"),
    (r"copywriter",                     "Copywriter"),
    (r"redator",                        "Redator"),
    # ── Outros ───────────────────────────────────────────────────────────
    (r"implanta[çc][aã]o",              "Consultor de Implantação"),
    (r"onboarding",                     "Analista de Onboarding"),
    (r"customer\s*success",             "Customer Success"),
    (r"\bcs\s*analyst",                 "Analista de Customer Success"),
    (r"technical\s*writer",             "Technical Writer"),
    (r"redator\s*t[eé]cnico",           "Redator Técnico"),
    (r"power\s*center",                 "Desenvolvedor Power Center"),
    (r"\bfield\b",                      "Técnico de Field Service"),
    (r"atendimento\s*t[eé]cnico",       "Técnico de Atendimento"),
]

NIVEIS_VALIDOS = [
    "Nenhum",
    "Acadêmico",
    "Até 6 meses",
    "De 6 meses a 1 ano",
    "De 1 ano até 2 anos",
    "De 2 anos até 3 anos",
    "De 3 anos até 4 anos",
    "De 4 anos até 5 anos",
    "Acima de 5 anos",
    "Possuo Certificação",
]

MAPA_NIVEL_VALUE = {
    "Nenhum":               "1",
    "Acadêmico":            "2",
    "Até 6 meses":          "3",
    "De 6 meses a 1 ano":   "4",
    "De 1 ano até 2 anos":  "5",
    "De 2 anos até 3 anos": "6",
    "De 3 anos até 4 anos": "7",
    "De 4 anos até 5 anos": "8",
    "Acima de 5 anos":      "9",
    "Possuo Certificação":  "10",
}


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def carregar_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def log(msg: str):
    print(f"  {msg}")

def esperar(page: Page, segundos: float = None):
    config = carregar_config()
    s = segundos or config["automacao"]["delay_entre_acoes"]
    page.wait_for_timeout(int(s * 1000))

def nivel_ingles_value(nivel_texto: str) -> str:
    mapa = {
        "Nenhum": "1", "nenhum": "1",
        "Basic": "2", "basic": "2",
        "Intermediate": "3", "intermediate": "3",
        "Advanced": "4", "advanced": "4",
        "Fluent": "5", "fluent": "5",
    }
    return mapa.get(nivel_texto, "2")

def calcular_pj_hora(pretensao_clt: int) -> str:
    hora = int((pretensao_clt * 1.3) / 160)
    return f"{hora},00"

def formatar_valor_br(valor: str) -> str:
    if "," not in valor:
        return f"{valor},00"
    return valor


# ══════════════════════════════════════════════════════════════════════════════
#  LLM ROUTER — Groq → Gemini → Mistral → None (fallback local)
#
#  Cascata:
#    1. Groq          — primário, rápido, sem crédito mensal (só rate limit diário)
#       · Rate limit curto (< 5min) → aguarda e retenta automaticamente (até 4x)
#       · Rate limit diário         → passa para Gemini até meia-noite UTC
#    2. Gemini 2.5 Flash-Lite — 1.000 req/dia, 15 RPM, com retry automático de RPM
#    3. Mistral Small — ~1 bilhão tokens/mês no free tier
#    4. None          — fallback local (zero API)
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
#    [LLM] ⚡       → rate limit curto, aguardando e retentando
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


class _GroqLimiteDiario(Exception):
    pass


def _calcular_reset_groq() -> "_dt.datetime":
    agora = _dt.datetime.now(_dt.timezone.utc)
    reset = agora.replace(hour=0, minute=0, second=10, microsecond=0)
    if reset <= agora:
        reset += _dt.timedelta(days=1)
    return reset


def _agendar_retorno_groq(reset_utc: "_dt.datetime") -> None:
    def _voltar():
        agora  = _dt.datetime.now(_dt.timezone.utc)
        espera = max(0, (reset_utc - agora).total_seconds()) + 15
        log(f"    [LLM] Groq volta em {int(espera / 60)}min "
            f"({reset_utc.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M')} local)")
        time.sleep(espera)
        with _llm_state["lock"]:
            _llm_state["provedor"]      = "groq"
            _llm_state["groq_reset_em"] = None
        log("    [LLM] ✅ Groq reativado automaticamente!")
    threading.Thread(target=_voltar, daemon=True).start()


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _chamar_groq(prompt: str, config: dict, temperatura: float = 0.1,
                 tentativas: int = 4) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada")

    client      = Groq(api_key=GROQ_API_KEY)
    ultimo_erro = None

    for tentativa in range(tentativas):
        try:
            resp = client.chat.completions.create(
                model=config["groq"]["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=temperatura,
            )
            return resp.choices[0].message.content.strip()

        except Exception as exc:
            ultimo_erro = exc
            msg = str(exc)

            if "429" in msg or "rate_limit" in msg.lower():
                m    = re.search(r"try again in\s+(?:(\d+)m)?(\d+(?:\.\d+)?)s", msg)
                wait = int(m.group(1) or 0) * 60 + float(m.group(2) or 0) + 5 if m else 90
                if wait > 300:
                    raise _GroqLimiteDiario(str(exc))
                log(f"    [LLM] ⚡ Groq rate limit curto: aguardando {int(wait)}s "
                    f"(tentativa {tentativa + 1}/{tentativas})")
                time.sleep(wait)
                continue

            import random as _random
            backoff = 2 ** tentativa + _random.uniform(0, 1)
            log(f"    [LLM] ⚠️  Groq erro (tentativa {tentativa + 1}/{tentativas}): {exc} "
                f"— retry em {backoff:.1f}s")
            time.sleep(backoff)

    raise RuntimeError(f"Groq falhou após {tentativas} tentativas: {ultimo_erro}")


def _chamar_gemini(prompt: str, temperatura: float = 0.1,
                   tentativas: int = 4) -> str:
    """
    Gemini 2.5 Flash-Lite via REST.
    Plano free: 1.000 req/dia, 15 RPM.

    Trata dois tipos de 429:
      - RPM excedido  → espera 4s * tentativa e retenta
      - Cota diária   → levanta RuntimeError imediatamente
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-lite-preview-06-17:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     max(0.0, temperatura),
            "maxOutputTokens": 600,
        },
    }

    for tentativa in range(tentativas):
        try:
            data  = _post_json(url, {"Content-Type": "application/json"}, payload)
            texto = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            log(f"    [LLM Gemini] ✅ ({len(texto)} chars)")
            return texto

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")

            if e.code == 429:
                if "daily" in body.lower() or ("quota" in body.lower() and "day" in body.lower()):
                    raise RuntimeError(f"Gemini cota diária esgotada: {body[:200]}") from e
                wait = 4 * (tentativa + 1)
                log(f"    [LLM] ⚡ Gemini RPM: aguardando {wait}s "
                    f"(tentativa {tentativa + 1}/{tentativas})")
                time.sleep(wait)
                continue

            raise RuntimeError(f"Gemini HTTP {e.code}: {body[:300]}") from e

    raise RuntimeError(f"Gemini falhou após {tentativas} tentativas (RPM)")


def _chamar_mistral(prompt: str, temperatura: float = 0.1) -> str:
    """
    Mistral Small via API oficial.
    Plano free: ~1 bilhão de tokens/mês.
    """
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY não configurada")

    url     = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       "mistral-small-latest",
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  600,
        "temperature": max(0.0, temperatura),
    }
    try:
        data  = _post_json(url, headers, payload)
        texto = data["choices"][0]["message"]["content"].strip()
        log(f"    [LLM Mistral] ✅ (resposta: {texto!r})")
        return texto
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Mistral HTTP {e.code}: {body[:300]}") from e


def _chamar_llm(prompt: str, config: dict, contexto: str = "",
                temperatura: float = 0.1) -> str | None:
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
#  RESOLUÇÃO DE NÍVEL DE TECNOLOGIA
# ══════════════════════════════════════════════════════════════════════════════

def resolver_nivel_tech(nome_tech: str, titulo_vaga: str, config: dict) -> str:
    tecnologias = config.get("tecnologias", {})
    chave = nome_tech.lower().strip()

    # 1. Match exato
    for nome, nivel in tecnologias.items():
        if nome.lower() == chave:
            return nivel

    # 2. Match parcial
    for nome, nivel in tecnologias.items():
        nome_lower = nome.lower()
        if nome_lower in chave or chave in nome_lower:
            return nivel

    # 3. Cache + LLM
    if chave in _cache_nivel_tech:
        return _cache_nivel_tech[chave]

    log(f"    🤖 LLM consultado para tech desconhecida: '{nome_tech}'")
    nivel = _llm_avaliar_tech(nome_tech, titulo_vaga, config)
    _cache_nivel_tech[chave] = nivel
    return nivel


def _llm_avaliar_tech(tech: str, titulo_vaga: str, config: dict) -> str:
    tecnologias      = config.get("tecnologias", {})
    tech_lista       = "\n".join(f"- {n}: {v}" for n, v in tecnologias.items())
    niveis_sem_nenhum = [n for n in NIVEIS_VALIDOS if n != "Nenhum"]

    prompt = (
        f'Você está preenchendo um formulário de candidatura de emprego.\n\n'
        f'Vaga: "{titulo_vaga}"\nTecnologia perguntada: "{tech}"\n\n'
        f'O candidato tem experiência nas seguintes tecnologias:\n{tech_lista}\n\n'
        f'Com base no perfil do candidato, qual o nível de experiência mais adequado para "{tech}"?\n\n'
        f'Regras:\n'
        f'- Se for tecnologia que o candidato claramente domina, use o nível correspondente\n'
        f'- Se for algo relacionado à área mas sem experiência listada, use "Acadêmico" ou "Até 6 meses"\n'
        f'- NUNCA responda "Nenhum" — use "Acadêmico" como mínimo\n'
        f'- Responda SOMENTE com uma das opções abaixo, sem mais nada:\n\n'
        + "\n".join(niveis_sem_nenhum)
    )

    resposta = _chamar_llm(prompt, config, contexto=tech)
    if resposta:
        nivel = resposta.splitlines()[0].strip()
        if nivel in NIVEIS_VALIDOS and nivel != "Nenhum":
            return nivel
    return "Acadêmico"


# ══════════════════════════════════════════════════════════════════════════════
#  DETECÇÃO DE FUNÇÃO/CARGO
# ══════════════════════════════════════════════════════════════════════════════

def detectar_funcao_vaga(titulo: str, descricao: str, config: dict) -> str:
    titulo_lower = titulo.lower().strip()

    if titulo_lower in _cache_funcao:
        return _cache_funcao[titulo_lower]

    for padrao, cargo in CARGO_MAP:
        if re.search(padrao, titulo_lower):
            _cache_funcao[titulo_lower] = cargo
            return cargo

    log(f"    🤖 LLM consultado para cargo desconhecido: '{titulo}'")
    cargo = _llm_detectar_funcao(titulo, descricao, config)
    _cache_funcao[titulo_lower] = cargo
    return cargo


def _llm_detectar_funcao(titulo: str, descricao: str, config: dict) -> str:
    prompt = (
        f'Dado o título de uma vaga de TI, retorne APENAS o nome da função para preencher um formulário.\n'
        f'Exemplos: "Desenvolvedor Python", "Desenvolvedor Frontend", "Estagiário de TI", "Analista de Suporte TI".\n'
        f'Título: {titulo}\nDescrição (trecho): {descricao[:200]}\n'
        f'Responda SOMENTE com a função, sem pontuação extra, sem explicação.'
    )
    resposta = _chamar_llm(prompt, config, contexto=titulo)
    if resposta:
        return resposta.splitlines()[0].strip()
    return titulo.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def fazer_login(page: Page, config: dict) -> bool:
    log("🔐 Fazendo login no Nerdin...")
    email = os.environ.get("NERDIN_EMAIL")
    senha = os.environ.get("NERDIN_SENHA")

    if not email or not senha:
        log("❌ NERDIN_EMAIL ou NERDIN_SENHA não encontrados no .env!")
        return False

    try:
        page.goto(config["nerdin"]["url_login"], timeout=15000)
        esperar(page, 2)
        page.fill('input[type="email"], input[name*="email" i]', email)
        esperar(page, 0.5)
        page.fill('input[type="password"]', senha)
        esperar(page, 0.5)
        page.click('button[type="submit"], button:has-text("Entrar"), button:has-text("Login")')
        esperar(page, 3)
        if "login" in page.url.lower() and "menu" not in page.url.lower():
            log("❌ Falha no login. Verifique NERDIN_EMAIL e NERDIN_SENHA no .env")
            return False
        log("✅ Login realizado!")
        return True
    except Exception as e:
        log(f"❌ Erro no login: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  BUSCAR VAGAS
# ══════════════════════════════════════════════════════════════════════════════

def buscar_vagas_nerdin(page: Page, config: dict) -> list:
    palavras          = config["busca"]["palavras_chave"]
    excluir           = [p.lower() for p in config["busca"]["palavras_excluir"]]
    vagas_encontradas = []
    links_vistos      = set()

    log("🔍 Buscando vagas no Nerdin...\n")

    for palavra in palavras:
        try:
            url = f"{config['nerdin']['url_busca']}?busca={palavra.replace(' ', '+')}"
            page.goto(url, timeout=15000)
            esperar(page, 2)

            cards = page.query_selector_all("div.vaga-card")
            log(f"  [{palavra}] {len(cards)} vagas encontradas")

            for card in cards:
                try:
                    if card.query_selector(".badge-inscrito"):
                        continue

                    texto_card = (card.inner_text() or "").lower()
                    if any(ex in texto_card for ex in excluir):
                        continue

                    btn = card.query_selector("a.btn-ver-vaga")
                    if not btn:
                        continue
                    href = btn.get_attribute("href") or ""
                    if not href:
                        continue

                    if href.startswith("http"):
                        link = href
                    elif href.startswith("/"):
                        link = "https://nerdin.com.br" + href
                    else:
                        link = "https://nerdin.com.br/" + href

                    if link in links_vistos:
                        continue
                    links_vistos.add(link)

                    titulo_el = card.query_selector("h3.vaga-titulo")
                    titulo    = titulo_el.inner_text().strip().split("\n")[0].strip() if titulo_el else palavra
                    local_el  = card.query_selector(".vaga-local")
                    local     = local_el.inner_text().strip() if local_el else ""

                    vagas_encontradas.append({
                        "titulo": titulo, "link": link,
                        "local": local, "palavra_chave": palavra, "descricao": "",
                    })
                    log(f"    ✅ {titulo} | {local}")

                except Exception as e:
                    log(f"    ⚠️  Erro num card: {e}")

        except Exception as e:
            log(f"⚠️  Erro buscando '{palavra}': {e}")

    log(f"\n📋 Total de vagas novas: {len(vagas_encontradas)}")
    return vagas_encontradas


# ══════════════════════════════════════════════════════════════════════════════
#  ESCOLHER CURRÍCULO
# ══════════════════════════════════════════════════════════════════════════════

def escolher_curriculo(titulo: str, descricao: str, config: dict) -> str:
    mapeamento = config["resumes"]["mapeamento"]
    curriculos = config["resumes"]
    texto      = (titulo + " " + descricao).lower()
    for keyword, tipo in mapeamento.items():
        if keyword == "default":
            continue
        if keyword in texto:
            arquivo = curriculos.get(tipo, curriculos["fullstack"])
            if os.path.exists(arquivo):
                return arquivo
    return curriculos["fullstack"]


# ══════════════════════════════════════════════════════════════════════════════
#  OBTER URL DO FORMULÁRIO
# ══════════════════════════════════════════════════════════════════════════════

def obter_url_formulario(page: Page) -> tuple:
    descricao = ""
    try:
        desc_el = page.query_selector("#sobre-pane, .tab-pane.active")
        if desc_el:
            descricao = desc_el.inner_text().strip()[:800]
    except Exception:
        pass
    try:
        btn = page.query_selector("a.btn-candidatar-vaga")
        if btn:
            href = btn.get_attribute("href") or ""
            if href:
                url_form = href if href.startswith("http") else "https://nerdin.com.br/" + href.lstrip("./")
                return url_form, descricao
    except Exception:
        pass
    return None, descricao


# ══════════════════════════════════════════════════════════════════════════════
#  ETAPA 1 — Dados Básicos
# ══════════════════════════════════════════════════════════════════════════════

def preencher_etapa1(page: Page, config: dict):
    log("📝 Etapa 1: Dados básicos")
    c = config["candidato"]
    esperar(page, 1)

    for field_id, valor in {
        "nome_candidato":     c["nome"],
        "telefone_candidato": c["telefone"],
        "email_candidato":    c["email"],
        "cidade_candidato":   c["cidade_uf"],
    }.items():
        try:
            el = page.query_selector(f"#{field_id}")
            if el:
                el.click(click_count=3)
                el.fill(valor)
                log(f"    ✓ {field_id}: {valor}")
        except Exception as e:
            log(f"    ⚠️  Erro em {field_id}: {e}")

    esperar(page, 0.8)
    page.click("#btn-proximo")
    log("  ➡️  Próxima etapa")
    esperar(page, 1.5)


# ══════════════════════════════════════════════════════════════════════════════
#  ETAPA 2 — Profissional
# ══════════════════════════════════════════════════════════════════════════════

def preencher_etapa2(page: Page, titulo_vaga: str, descricao: str,
                     config: dict, respostas: dict):
    log("📝 Etapa 2: Profissional")
    c = config["candidato"]
    esperar(page, 1)

    funcao = detectar_funcao_vaga(titulo_vaga, descricao, config)
    log(f"    🤖 Função detectada: {funcao}")
    respostas["Função detectada"] = funcao
    try:
        el = page.query_selector("#funcao_candidato")
        if el:
            el.click(click_count=3)
            el.fill(funcao)
    except Exception as e:
        log(f"    ⚠️  Erro em funcao_candidato: {e}")

    ingles_value = nivel_ingles_value(c["nivel_ingles"])
    respostas["Nível de inglês"] = c["nivel_ingles"]
    try:
        page.select_option("#nivel_ingles", value=ingles_value)
        log(f"    ✓ nivel_ingles: {c['nivel_ingles']} (value={ingles_value})")
    except Exception as e:
        log(f"    ⚠️  Erro em nivel_ingles: {e}")

    respostas["Disponibilidade (dias)"] = c["disponibilidade_dias"]
    try:
        el = page.query_selector("#disponibilidade_inicio_dias")
        if el:
            el.click(click_count=3)
            el.fill(c["disponibilidade_dias"])
            log(f"    ✓ disponibilidade: {c['disponibilidade_dias']} dias")
    except Exception as e:
        log(f"    ⚠️  Erro em disponibilidade_inicio_dias: {e}")

    pj_value = "1" if c["possui_pj"] else "0"
    respostas["Possui empresa aberta (PJ)"] = "Sim" if c["possui_pj"] else "Não"
    try:
        page.select_option("#possui_empresa_aberta", value=pj_value)
        log(f"    ✓ possui_empresa_aberta: {'Sim' if c['possui_pj'] else 'Não'}")
    except Exception as e:
        log(f"    ⚠️  Erro em possui_empresa_aberta: {e}")

    esperar(page, 0.8)
    page.click("#btn-proximo")
    log("  ➡️  Próxima etapa")
    esperar(page, 1.5)


# ══════════════════════════════════════════════════════════════════════════════
#  ETAPA 3 — Complementares
# ══════════════════════════════════════════════════════════════════════════════

def preencher_etapa3(page: Page, titulo_vaga: str, descricao: str,
                     arquivo_curriculo: str, config: dict, respostas: dict):
    log("📝 Etapa 3: Complementares")
    c = config["candidato"]
    esperar(page, 1)

    valor_clt = formatar_valor_br(c["pretensao_clt"])
    respostas["Pretensão CLT"] = f"R$ {valor_clt}"
    try:
        el = page.query_selector("#pretensao_salarial")
        if el:
            el.click(click_count=3)
            el.fill(valor_clt)
            log(f"    ✓ pretensao_salarial CLT: R${valor_clt}")
    except Exception as e:
        log(f"    ⚠️  Erro em pretensao_salarial: {e}")

    valor_pj = calcular_pj_hora(int(c["pretensao_clt"]))
    respostas["Pretensão PJ/hora"] = f"R$ {valor_pj}"
    try:
        el = page.query_selector("#pretensao_salarial_pj")
        if el:
            el.click(click_count=3)
            el.fill(valor_pj)
            log(f"    ✓ pretensao_salarial PJ/hora: R${valor_pj}")
    except Exception as e:
        log(f"    ⚠️  Erro em pretensao_salarial_pj: {e}")

    esperar(page, 0.5)

    tecnologias_respondidas: dict[str, str] = {}
    for sel_el in page.query_selector_all("select[id^='palavra_chave_']"):
        try:
            sel_id    = sel_el.get_attribute("id")
            label     = page.query_selector(f"label[for='{sel_id}']")
            nome_tech = label.inner_text().strip() if label else ""
            if not nome_tech:
                continue
            nivel = resolver_nivel_tech(nome_tech, titulo_vaga, config)
            value = MAPA_NIVEL_VALUE.get(nivel, "1")
            sel_el.select_option(value=value)
            tecnologias_respondidas[nome_tech] = nivel
            log(f"    ✓ {nome_tech}: {nivel}")
        except Exception as e:
            log(f"    ⚠️  Erro em tecnologia: {e}")

    if tecnologias_respondidas:
        respostas["Tecnologias"] = tecnologias_respondidas

    esperar(page, 0.5)

    respostas["Currículo enviado"] = arquivo_curriculo
    if os.path.exists(arquivo_curriculo):
        try:
            page.set_input_files("#curriculo", arquivo_curriculo)
            log(f"    ✓ Currículo: {arquivo_curriculo}")
            esperar(page, 1)
        except Exception as e:
            log(f"    ⚠️  Erro no upload do currículo: {e}")
    else:
        log(f"    ⚠️  Arquivo não encontrado: {arquivo_curriculo}")

    esperar(page, 0.8)


# ══════════════════════════════════════════════════════════════════════════════
#  FLUXO COMPLETO DE CANDIDATURA
# ══════════════════════════════════════════════════════════════════════════════

def candidatar_vaga_nerdin(page: Page, vaga: dict, config: dict) -> dict:
    resultado = {
        "vaga":      vaga["titulo"],
        "link":      vaga["link"],
        "local":     vaga.get("local", ""),
        "site":      "Nerdin",
        "status":    "erro",
        "data":      datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"),
        "horario":   datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M:%S"),
        "curriculo": "",
        "respostas": {},
        "carta":     "",   # Nerdin não tem carta — mantido para consistência com o JSON
    }

    respostas: dict = {}

    try:
        log(f"\n🚀 Abrindo vaga: {vaga['titulo']}")
        page.goto(vaga["link"], timeout=15000)
        esperar(page, 2)

        url_form, descricao = obter_url_formulario(page)
        if not url_form:
            log("  ❌ Botão 'Quero me Candidatar' não encontrado")
            resultado["status"] = "botao_nao_encontrado"
            return resultado

        arquivo_curriculo    = escolher_curriculo(vaga["titulo"], descricao, config)
        resultado["curriculo"] = arquivo_curriculo
        log(f"  📄 Currículo: {arquivo_curriculo}")

        log(f"  📋 Abrindo formulário: {url_form}")
        page.goto(url_form, timeout=15000)
        esperar(page, 2)

        preencher_etapa1(page, config)
        preencher_etapa2(page, vaga["titulo"], descricao, config, respostas)
        preencher_etapa3(page, vaga["titulo"], descricao, arquivo_curriculo, config, respostas)

        resultado["respostas"] = respostas

        esperar(page, 0.5)
        try:
            btn_enviar = page.query_selector("#btn-enviar-candidatura")
            if btn_enviar:
                btn_enviar.click()
                esperar(page, 3)
                log("  ✅ Candidatura enviada!")
                resultado["status"] = "enviado"
            else:
                log("  ⚠️  Botão de envio não encontrado")
                resultado["status"] = "preenchido_sem_envio"
        except Exception as e:
            log(f"  ⚠️  Erro ao enviar: {e}")
            resultado["status"] = f"erro_envio: {e}"

    except Exception as e:
        log(f"  ❌ Erro: {e}")
        resultado["status"] = f"erro: {str(e)}"

    return resultado


# ══════════════════════════════════════════════════════════════════════════════
#  LOG / RELATÓRIO
# ══════════════════════════════════════════════════════════════════════════════

def _ler_json_candidaturas() -> tuple[list, list]:
    arquivo = "relatorio/candidaturas.json"
    if not os.path.exists(arquivo):
        return [], []
    with open(arquivo, "r", encoding="utf-8") as f:
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
    """Formata respostas do Nerdin para o .txt — suporta sub-dicts (Tecnologias)."""
    if not respostas:
        return "    (sem respostas registradas)\n"
    linhas = []
    for chave, valor in respostas.items():
        if isinstance(valor, dict):
            linhas.append(f"    📌 {chave}:")
            for sub_k, sub_v in valor.items():
                linhas.append(f"       • {sub_k}: {sub_v}")
        else:
            linhas.append(f"    📌 {chave}: {valor}")
    return "\n".join(linhas) + "\n"


def salvar_log(candidaturas_novas: list):
    os.makedirs("relatorio", exist_ok=True)
    hoje         = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    arquivo_json = "relatorio/candidaturas.json"

    candidaturas_existentes, ja_candidatado_existente = _ler_json_candidaturas()
    todas_candidaturas = candidaturas_existentes + candidaturas_novas

    links_novos = {
        c["link"] for c in candidaturas_novas
        if isinstance(c, dict) and c.get("status") == "enviado" and "link" in c
    }
    ja_candidatado_atualizado = sorted(set(ja_candidatado_existente) | links_novos)

    # ── JSON: persiste tudo incluindo respostas ───────────────────────────────
    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(
            {"candidaturas": todas_candidaturas,
             "ja_candidatado": ja_candidatado_atualizado},
            f, ensure_ascii=False, indent=2,
        )

    # ── TXT diário ────────────────────────────────────────────────────────────
    resumo   = f"relatorio/nerdin_{hoje}.txt"
    enviadas = [c for c in candidaturas_novas if c["status"] == "enviado"]

    with open(resumo, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write(f"📊 NERDIN — {hoje}\n{'='*50}\n\n")
            f.write(f"✅ Enviadas: {len(enviadas)}/{len(candidaturas_novas)}\n\n")

        for c in candidaturas_novas:
            f.write(f"[{c['status'].upper()}] {c['vaga']} | {c.get('local','')}\n")
            f.write(f"  🔗 {c['link']}\n")
            f.write(f"  🕐 {c.get('data','')} {c.get('horario','')}\n")
            f.write(f"  📄 Currículo: {c.get('curriculo','')}\n\n")
            f.write("  📋 Dados preenchidos:\n")
            f.write(_formatar_respostas_txt(c.get("respostas", {})))
            f.write("\n  ✉️  Carta: (não aplicável no Nerdin)\n")
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
║       🤖 JOB HUNTER — NERDIN  v1.2      ║
╚══════════════════════════════════════════╝
    """)

    config = carregar_config()

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY não configurada no .env!")
        return
    if not os.environ.get("NERDIN_SENHA"):
        print("❌ NERDIN_SENHA não configurada no .env!")
        return
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY não configurada — Gemini desativado como fallback")
    if not MISTRAL_API_KEY:
        print("⚠️  MISTRAL_API_KEY não configurada — Mistral desativado como fallback")

    curriculo_principal = config["resumes"]["fullstack"]
    if not os.path.exists(curriculo_principal):
        print(f"❌ Currículo não encontrado: {curriculo_principal}")
        return

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

        vagas       = buscar_vagas_nerdin(page, config)
        vagas_novas = [v for v in vagas if v["link"] not in ja_candidatados]
        vagas_novas = vagas_novas[:config["automacao"]["max_candidaturas_por_dia"]]

        print(f"\n🎯 Vagas para candidatar: {len(vagas_novas)}")
        print("=" * 50)

        candidaturas = []
        try:
            for i, vaga in enumerate(vagas_novas, 1):
                print(f"\n[{i}/{len(vagas_novas)}]")
                resultado = candidatar_vaga_nerdin(page, vaga, config)
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