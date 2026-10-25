"""Camada de IA do bot Indeed — roteador LLM + prompts + detecção de inglês.

Extraído de indeed.py (v2.8) sem mudança de comportamento:
  • Roteador LLM (chamar_llm): somente provedores cadastrados na UI
    (config.yaml → ia, ativo em 1º, demais em ordem de cadastro)
  • Processamento de formulário (regras → agente → IA campo a campo)
  • Prompts do sistema + perfil resumido (PERFIL_RESUMIDO)
  • Detecção de descrição/formulário em inglês via IA (v2.7/v2.8)
  • Carta de apresentação

Módulo autossuficiente: re-lê config.yaml/.env no import (mesmo processo →
mesmos valores). O bot re-importa tudo via star import — os nomes no escopo
de indeed.py seguem iguais para os call sites (mesmo padrão de indeed_regras).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from common import llm as _llm_lib
from common import pagelens, perfil
from dotenv import load_dotenv

# ── Bootstrap autossuficiente (mesmo processo → mesmos valores do bot) ──
load_dotenv()

with open("config.yaml", encoding="utf-8") as _f:
    CONFIG: dict = yaml.safe_load(_f)

TZ           = ZoneInfo("America/Sao_Paulo")
CANDIDATO    = CONFIG["candidato"]
DIVERSIDADE  = CONFIG["diversidade"]
LOCALIZACAO  = CONFIG["localizacao"]

# Engine de regras determinísticas (módulo extraído anterior)
from indeed_regras import (
    _contem_pergunta_filiacao,
    _PerguntaFiliacaoDetectada,
    _resolver_por_regra,
)

# ---------------------------------------------------------------------------
# Logging (cópias exatas do bot — o bot re-importa via star)
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO") -> None:
    print(f"[{_now_str()}] [{level}] {msg}")

def log_ok(msg: str)   -> None: log(msg, "✅")
def log_err(msg: str)  -> None: log(msg, "❌")
def log_skip(msg: str) -> None: log(msg, "⏭️ ")
def log_info(msg: str) -> None: log(msg, "ℹ️ ")
def log_warn(msg: str) -> None: log(msg, "⚠️ ")

class _FormularioEmIngles(Exception):
    """Aborta a candidatura quando o formulário está predominantemente em inglês."""

__all__ = [
    "PERFIL_RESUMIDO",
    "_SYSTEM_FORM_TEMPLATE",
    "_FormularioEmIngles",
    "_build_perfil_resumido",
    "_descricao_em_ingles",
    "_esta_em_ingles",
    "_formulario_em_ingles",
    "_get_system_form",
    "_ia_resolver_campo",
    "_now_str",
    "chamar_llm",
    "ia_gerar_carta",
    "ia_processar_formulario",
    "log",
    "log_err",
    "log_info",
    "log_ok",
    "log_skip",
    "log_warn",
]

# ═══════════════════════════════════════════════════════════════
#  DETECÇÃO DE DESCRIÇÃO EM INGLÊS VIA IA  (v2.7)
# ═══════════════════════════════════════════════════════════════

def _descricao_em_ingles(descricao: str) -> bool:
    """
    Usa o LLM (provedores da UI via chamar_llm) para detectar se a
    descrição da vaga está predominantemente em inglês.

    O modelo recebe os primeiros 800 caracteres da descrição e deve
    responder apenas SIM ou NÃO. Qualquer falha no LLM é tratada como
    NÃO (não pular a vaga por precaução).
    """
    if not descricao or len(descricao.strip()) < 30:
        return False

    trecho = descricao.strip()[:800]

    prompt = (
        "Analise o trecho de descrição de vaga abaixo e responda APENAS com "
        "SIM ou NÃO, sem mais nada.\n\n"
        "PERGUNTA: O texto está predominantemente em inglês?\n\n"
        "Considere SIM se a maior parte do conteúdo estiver em inglês, "
        "mesmo que haja algumas palavras em português.\n"
        "Considere NÃO se o texto estiver em português, mesmo com termos "
        "técnicos em inglês (ex: 'React', 'backend', 'deploy').\n\n"
        f"TRECHO:\n{trecho}\n\n"
        "RESPOSTA (apenas SIM ou NÃO):"
    )

    try:
        resposta = chamar_llm(
            prompt,
            max_tokens=5,
            temperature=0.0,
        ).strip().upper()

        log_info(f"  [IA idioma descrição] resposta bruta: {resposta[:20]!r}")
        return resposta.startswith("S") or resposta.startswith("Y")

    except Exception as exc:
        log_warn(f"  [IA idioma descrição] falha na detecção — assumindo português: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════
#  DETECÇÃO DE FORMULÁRIO EM INGLÊS VIA IA  (v2.8)
# ═══════════════════════════════════════════════════════════════

def _formulario_em_ingles(labels: list[str]) -> bool:
    """
    Detecta se o formulário está predominantemente em inglês.
    Usa duas heurísticas em cascata:
    1. Frases gramaticais de pergunta em inglês
    2. Densidade de palavras funcionais inglesas (the, your, and, by...)
    Se qualquer heurística ultrapassar o threshold, confirma via IA.
    """
    labels_validos = [rot.strip() for rot in labels if rot and len(rot.strip()) > 5]
    if len(labels_validos) < 2:
        return False

    _PREFIXO = re.compile(r"^\[(EN|ES|FR|DE|PT)\]\s*", re.IGNORECASE)

    # ── Heurística 1: frases de pergunta em inglês ──
    _FRASES_EN = [
        r"\bdo you\b", r"\bare you\b", r"\bhave you\b", r"\bcan you\b",
        r"\bwill you\b", r"\bwould you\b", r"\bhow many\b", r"\bhow long\b",
        r"\bwhat is\b", r"\bwhat are\b", r"\bwhich of\b", r"\bwhere do\b",
        r"\bplease (select|choose|describe|provide|indicate)\b",
        r"\byears of experience\b", r"\bauthorized to work\b",
        r"\bcurrent (company|employer|salary)\b", r"\bsalary expectation\b",
        r"\bexpected salary\b", r"\bconfirm (the|your)\b",
        r"\bby clicking\b", r"\bpersonal data\b", r"\bprivacy notice\b",
        r"\bdata subject\b", r"\byour application\b", r"\bapplicable law\b",
    ]
    contagem_frases = sum(
        1 for rot in labels_validos
        if any(re.search(p, _PREFIXO.sub("", rot).lower()) for p in _FRASES_EN)
    )
    pct_frases = contagem_frases / len(labels_validos)

    # ── Heurística 2: palavras funcionais inglesas no texto completo ──
    # Palavras que aparecem MUITO em inglês mas raramente em português
    _PALAVRAS_EN = [
        r"\bthe\b", r"\byour\b", r"\band\b", r"\bof\b", r"\bby\b",
        r"\bfor\b", r"\bwith\b", r"\bthis\b", r"\bthat\b", r"\byou\b",
        r"\bour\b", r"\bwe\b", r"\bto\b", r"\bin\b", r"\bis\b",
        r"\bare\b", r"\bhas\b", r"\bhave\b", r"\bnot\b", r"\ball\b",
    ]
    texto_total = " ".join(_PREFIXO.sub("", rot).lower() for rot in labels_validos)
    palavras_total = len(texto_total.split())
    if palavras_total > 0:
        hits_en = sum(len(re.findall(p, texto_total)) for p in _PALAVRAS_EN)
        # Ratio de palavras funcionais inglesas sobre total de palavras
        # Em texto inglês normal fica acima de 15%, em português fica abaixo de 5%
        ratio_en = hits_en / palavras_total
    else:
        ratio_en = 0

    log_info(f"  [idioma formulário] frases={pct_frases:.0%} palavras_en={ratio_en:.0%}")

    # Se nenhuma heurística indica inglês, descarta sem chamar IA
    if pct_frases < 0.30 and ratio_en < 0.12:
        return False

    # ── Confirmação via IA ──
    texto_labels = "\n".join(f"- {rot}" for rot in labels_validos[:25])
    prompt = (
        "Você vai analisar o conteúdo de um formulário de candidatura de emprego.\n"
        "Responda APENAS com a palavra SIM ou NÃO — nenhuma outra palavra.\n\n"
        "PERGUNTA: O conteúdo abaixo está predominantemente em inglês?\n\n"
        "IMPORTANTE:\n"
        "- Responda SIM se a maioria do texto estiver em inglês\n"
        "- Isso inclui avisos de privacidade, termos, perguntas ou qualquer texto em inglês\n"
        "- Prefixos como [EN] ou termos técnicos isolados NÃO contam\n"
        "- Ex SIM: 'By clicking the button you confirm...' ou 'Do you have experience...'\n"
        "- Ex NÃO: 'Você tem experiência com React?' ou '[EN] Qual seu nível de inglês?'\n\n"
        f"CONTEÚDO:\n{texto_labels}\n\n"
        "RESPOSTA (apenas SIM ou NÃO):"
    )

    try:
        resposta = chamar_llm(
            prompt,
            max_tokens=5,
            temperature=0.0,
        ).strip().upper()
        log_info(f"  [idioma formulário] IA respondeu: {resposta[:10]!r}")
        return resposta.startswith("S") or resposta.startswith("Y")

    except Exception as exc:
        log_warn(f"  [idioma formulário] IA falhou — usando heurística: {exc}")
        return pct_frases > 0.60 or ratio_en > 0.20


# ═══════════════════════════════════════════════════════════════
#  PERFIL DO CANDIDATO — RICO E EXPLÍCITO
# ═══════════════════════════════════════════════════════════════

def _build_perfil_resumido() -> str:
    """Contexto do LLM no Indeed: perfil completo (common/perfil.py — tudo
    que o usuário mantém na aba Perfil do Trivor, com a lista de exclusões)
    + regras específicas do site. Bloco estático antigo foi cortado:
    formação, experiência e tecnologias agora vêm do config.yaml."""
    c    = CANDIDATO
    div  = DIVERSIDADE
    loc  = LOCALIZACAO
    hoje = datetime.now(TZ).strftime("%d/%m/%Y")

    fmt_remoto     = "SIM" if loc.get("aceita_remoto", False)     else "NÃO"
    fmt_hibrido    = "SIM" if loc.get("aceita_hibrido", False)    else "NÃO"
    fmt_presencial = "SIM" if loc.get("aceita_presencial", False) else "NÃO"
    fmt_mudanca    = "SIM" if loc.get("aceita_mudanca", False)    else "NÃO"

    regra_pcd = ('"Qual sua deficiência?" → responda conforme a seção Diversidade do perfil (é PCD)'
                 if div.get("pcd")
                 else '"Qual sua deficiência?" → responder PULAR (não é PCD; não necessita de acessibilidade)')

    bloco_indeed = f"""
════ INDEED — REGRAS ESPECÍFICAS DO SITE (somam-se ao contexto acima) ════
SITUAÇÃO:
  - Empresa aberta (CNPJ): {'SIM' if c.get('possui_pj') else 'NÃO'}
  - Não foi indicado por ninguém; não tem familiares ou conhecidos trabalhando em nenhuma empresa; não é ex-funcionário
  - Início: imediato (hoje é {hoje})

REGRAS CRÍTICAS DESTE FORMULÁRIO:
  • "Salário atual" / "último salário" → PULAR (NUNCA revelar)
  • {regra_pcd}
  • "Nome do indicador/familiar" → PULAR (candidatura espontânea)
  • "Caso a resposta anterior seja Sim..." / subperguntas / campo opcional que não se aplica → PULAR
  • Expectativa pedindo APENAS dígitos (sem "R$" nem "mês") → {c['pretensao_clt']}
  • Formato de trabalho: remoto → {fmt_remoto} | híbrido → {fmt_hibrido} | presencial → {fmt_presencial} | mudança → {fmt_mudanca}
  • Idiomas: use SOMENTE a seção IDIOMAS do perfil; idioma não listado → "Nenhum"
"""
    return perfil.contexto_perfil(CONFIG) + bloco_indeed


PERFIL_RESUMIDO = _build_perfil_resumido()


# ═══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT DA IA
# ═══════════════════════════════════════════════════════════════

_SYSTEM_FORM_TEMPLATE = """Você é um assistente especializado em preencher formulários de candidatura de emprego.
Responde EXCLUSIVAMENTE com base no perfil do candidato abaixo. NUNCA inventa informações.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERFIL DO CANDIDATO:
{perfil}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

════════════════════════════════════════════════════════════
REGRAS CRÍTICAS — LEIA ANTES DE QUALQUER RESPOSTA
════════════════════════════════════════════════════════════

⚠️  REGRA ABSOLUTA — CAMPOS DE TEXTO:
    Se o campo for do tipo TEXTO (não radio, não select),
    a resposta NUNCA pode ser um número sozinho (ex: "3", "1", "0").
    Campos de texto exigem texto descritivo.
    - "Cargo pretendido" → "Desenvolvedor Web Fullstack"   NÃO → "3"
    - "Pretensão salarial" → "3500"  (número de salário é OK, mas não índice)
    - "Descreva..." → frase completa                       NÃO → "1"

⚠️  REGRA ABSOLUTA — NÍVEL / SENIORIDADE:
    O candidato é DESENVOLVEDOR JÚNIOR / PLENO — trabalhando como freelancer.
    Ele NÃO é estagiário. NUNCA selecione "Estágio", "Estagiário" ou "Trainee".
    Ordem de preferência: Júnior > Pleno > Sênior (último recurso) > qualquer coisa exceto Estágio.

⚠️  REGRA ABSOLUTA — ÁREA / CATEGORIA PROFISSIONAL:
    O candidato atua em TI / Tecnologia / Desenvolvimento de Software.
    NUNCA selecione "Engenharia" como área profissional, mesmo que o título da vaga
    contenha palavras como "engenheiro" ou "engineer".
    O candidato NÃO é engenheiro de formação — é desenvolvedor de software.
    Ordem de preferência para área: TI > Tecnologia > Informática > Software > Desenvolvimento.

⚠️  REGRA ABSOLUTA — PRETENSÃO SALARIAL:
    Valor padrão (CLT, não especificado): {pretensao_clt}
    Valor PJ mensal: {pretensao_pj_mensal}
    Valor PJ hora:   {pretensao_pj_hora}
    Valor estágio:   {pretensao_estagio}
    Salário ATUAL/ÚLTIMO: sempre PULAR — nunca revelar.
    ATENÇÃO: Use valor de estágio (1600) APENAS se a pergunta mencionar
    explicitamente "estágio", "estagiário" ou "intern". Para qualquer
    outra vaga de desenvolvedor, use o valor CLT ({pretensao_clt}).

⚠️  REGRA ABSOLUTA — ÚLTIMO SEGMENTO / SETOR TRABALHADO:
    O candidato é AUTÔNOMO / FREELANCER desde 2022.
    Se perguntarem sobre último segmento, setor ou área trabalhada:
    - Priorize SEMPRE: "Autônomo" > "Freelancer" > "Tecnologia" > qualquer outra
    - NUNCA selecione "1° emprego", "Sem experiência" ou similar — ele TEM experiência
    - Se não houver opção de autônomo, escolha Tecnologia/TI

⚠️  REGRA ABSOLUTA — CAMPOS CONDICIONAIS "SE OUTRA/OUTRO":
    Campos como "Se outra, informar abaixo", "Caso outro, especifique",
    "If other, please specify" são condicionais — só devem ser preenchidos
    se a pergunta ANTERIOR selecionou "Outro/Outra/Other".
    Se a opção anterior NÃO foi "Outro", responda: FINAL: PULAR
    Em caso de dúvida, SEMPRE responda: FINAL: PULAR


    Se perguntarem "cargo pretendido", "posição desejada" ou similar,
    responda SEMPRE: "Desenvolvedor Web Fullstack"
    NUNCA responda com um número.

════════════════════════════════════════════════════════════
REGRAS GERAIS DE RESPOSTA
════════════════════════════════════════════════════════════

1. CAMPOS DE SELEÇÃO ÚNICA (radio/select):
   - Responda APENAS com o número do índice da opção (0, 1, 2, 3...)
   - Analise cuidadosamente o texto de cada opção antes de escolher
   - Última linha SEMPRE: FINAL: <número>

2. CAMPOS DE MÚLTIPLA ESCOLHA (checkbox):
   - Selecione TODAS as opções corretas/verdadeiras
   - Responda com os índices separados por vírgula: FINAL: 0,2,3
   - Se apenas uma opção for correta: FINAL: 0
   - NUNCA responda com texto descritivo — sempre números separados por vírgula
   - Exemplo correto: FINAL: 0,1   Exemplo ERRADO: "A primeira e a segunda opção"

3. CAMPOS DE TEXTO:
   - Responda com texto descritivo — NUNCA com um número sozinho
   - Seja direto e conciso com base no perfil
   - Última linha SEMPRE: FINAL: <resposta textual>

4. CAMPOS CONDICIONAIS (ex: "Caso a resposta anterior seja Sim..."):
   - Se a condição não se aplica ao candidato → FINAL: PULAR
   - "PULAR" = campo deve ficar em branco

5. CAMPOS DE CONSENTIMENTO / LGPD / TERMOS:
   - SEMPRE aceitar → FINAL: <índice da opção de aceite>

6. CAMPOS DE SALÁRIO ATUAL/ÚLTIMO:
   - SEMPRE → FINAL: PULAR

7. CAMPOS DE PRETENSÃO SALARIAL:
   - Leia com atenção se menciona CLT, PJ, hora, mensal ou estágio
   - Use o valor correto conforme as REGRAS CRÍTICAS acima
   - Se não especificado, use o valor CLT: {pretensao_clt}
   - Se pedir só número (sem R$ ou /mês), responda só o número

7. CAMPOS SOBRE DISPONIBILIDADE DE FORMATO:
   - Remoto / home office → consulte "Trabalho REMOTO" no perfil
   - Híbrido → consulte "Trabalho HÍBRIDO" no perfil
   - Presencial → consulte "Trabalho PRESENCIAL" no perfil

8. CAMPOS SOBRE OUTROS IDIOMAS além de português e inglês:
   - O candidato NÃO possui outros idiomas
   - Texto → FINAL: Não possuo outros idiomas além do inglês básico
   - Radio/select → escolher opção "não" ou nível mais baixo disponível

9. EXPERIÊNCIA TÉCNICA:
   - Se TEM: descreva brevemente o tempo e uso real
   - Se NÃO TEM: "Não tenho experiência com X, mas tenho base em Y"
   - NUNCA invente projetos, empresas ou certificações

10. DISPONIBILIDADE PARA OUTRAS CIDADES:
    - Candidato aceita mudança — responda que tem interesse

FORMATO OBRIGATÓRIO — última linha SEMPRE:
  FINAL: <resposta>
"""


def _get_system_form() -> str:
    c = CANDIDATO
    return _SYSTEM_FORM_TEMPLATE.format(
        perfil=PERFIL_RESUMIDO,
        pretensao_clt=c.get("pretensao_clt", "3500"),
        pretensao_pj_mensal=c.get("pretensao_pj_mensal", "4500"),
        pretensao_pj_hora=c.get("pretensao_pj_hora", "22"),
        pretensao_estagio=c.get("pretensao_estagio", "1600"),
    )


# ═══════════════════════════════════════════════════════════════
#  PROCESSAMENTO DE FORMULÁRIO
# ═══════════════════════════════════════════════════════════════

def ia_processar_formulario(campos: list[dict], contexto_vaga: str) -> dict[str, Any]:
    """
    Camada 1 — Regras: dados mecânicos fixos
    Camada 2 — IA: tudo que precisa de interpretação
    Levanta _PerguntaFiliacaoDetectada se detectar campo de mãe/pai.
    Levanta _FormularioEmIngles se o formulário estiver em inglês.
    """
    if not campos:
        return {}

    # ── VERIFICAÇÃO DE IDIOMA DO FORMULÁRIO (v2.8) ──────────────
    # Coleta todos os labels para análise antes de processar
    todos_labels = [c["pergunta"] for c in campos if c.get("pergunta")]
    log_info("  🌐 Verificando idioma do formulário via IA...")
    if _formulario_em_ingles(todos_labels):
        raise _FormularioEmIngles(
            f"Formulário em inglês detectado ({len(todos_labels)} campo(s) analisado(s))"
        )
    log_info("  ✅ Formulário em português — prosseguindo")

    resultado:      dict[str, Any] = {}
    campos_para_ia: list[dict]     = []

    for i, campo in enumerate(campos):
        log_info(f"  [CAMPO {i}] tipo={campo['tipo']} | label='{campo['pergunta'][:80]}'")

        if _contem_pergunta_filiacao(campo["pergunta"]):
            raise _PerguntaFiliacaoDetectada(
                f"Campo de filiação detectado: '{campo['pergunta'][:80]}'"
            )

        resolveu, valor = _resolver_por_regra(campo, contexto_vaga)
        if resolveu:
            resultado[campo["id"]] = valor
            log_ok(f"    [REGRA] '{campo['pergunta'][:55]}' → {repr(valor)[:50]}")
        else:
            campos_para_ia.append(campo)
            log_info(f"    [→IA]  '{campo['pergunta'][:55]}'  (sem regra, vai pra IA)")

    log_info(f"  Regras: {len(resultado)}/{len(campos)} resolvidos | IA: {len(campos_para_ia)} restantes")

    if not campos_para_ia:
        return resultado

    # ── AGENTE DE PASSO: o LLM lê TODOS os campos restantes de uma vez ──
    # (1 chamada no lugar de N; respostas consistentes + perguntas que a
    #  tabela de regras não conhece). Falhou → fallback per-field clássico,
    #  que nunca fica pior que hoje.
    agente = pagelens.agente_campos(
        campos_para_ia, contexto_vaga,
        regras=_get_system_form(),
        chamar=lambda prompt, max_tokens=900: chamar_llm(
            prompt,
            max_tokens=max_tokens, temperature=0.1),
    )
    if agente:
        for campo in campos_para_ia:
            cid = campo["id"]
            if cid not in agente:
                continue
            val = agente[cid]
            if campo["tipo"] in ("radio", "select"):
                resultado[cid] = val
                ops = campo.get("opcoes") or []
                log_ok(f"    [AGENTE] '{campo['pergunta'][:50]}' → {val}: "
                       f"'{ops[val][:40] if val < len(ops) else ''}'")
            elif campo["tipo"] == "checkbox":
                resultado[cid] = val
                log_ok(f"    [AGENTE] '{campo['pergunta'][:50]}' → índices {val}")
            else:
                v = "" if isinstance(val, str) and val.strip().upper() == "PULAR" else val
                resultado[cid] = v
                log_ok(f"    [AGENTE] '{campo['pergunta'][:50]}' → {repr(v)[:50] if v else '[PULADO]'}")

        restantes = [c for c in campos_para_ia if c["id"] not in resultado]
        if restantes:
            log_info(f"  [AGENTE] {len(campos_para_ia) - len(restantes)} campo(s) em 1 chamada; "
                     f"{len(restantes)} sem resposta → fallback campo a campo")
            campos_para_ia = restantes
        else:
            log_ok(f"  🤖 [AGENTE] {len(campos_para_ia)} campo(s) resolvido(s) em 1 chamada de LLM")
            return resultado

    for campo in campos_para_ia:
        try:
            val = _ia_resolver_campo(campo, contexto_vaga)

            if isinstance(val, str) and val.strip().upper() == "PULAR":
                log_info(f"    [IA] '{campo['pergunta'][:55]}' → [PULADO]")
                resultado[campo["id"]] = ""
                continue

            if val is not None:
                resultado[campo["id"]] = val
                log_ok(f"    [IA] '{campo['pergunta'][:55]}' → {repr(val)[:50]}")
                continue

            log_warn(f"    [IA] sem resposta — tentando modo forçado para '{campo['pergunta'][:55]}'")
            val2 = _ia_resolver_campo(campo, contexto_vaga, modo_forcado=True)

            if val2 is not None and not (isinstance(val2, str) and val2.upper() == "PULAR"):
                resultado[campo["id"]] = val2
                log_ok(f"    [IA*] '{campo['pergunta'][:55]}' → {repr(val2)[:50]} (modo forçado)")
                continue

            if campo["tipo"] in ("radio", "select") and campo.get("opcoes"):
                resultado[campo["id"]] = 0
                log_warn(f"    [FALLBACK] '{campo['pergunta'][:55]}' → índice 0 '{campo['opcoes'][0][:40]}'")
            else:
                log_warn(f"    [IA] '{campo['pergunta'][:55]}' → sem resposta após todas as tentativas")

        except _PerguntaFiliacaoDetectada:
            raise
        except _FormularioEmIngles:
            raise
        except Exception as exc:
            log_err(f"    [IA erro] '{campo['pergunta'][:40]}': {exc}")
            if campo["tipo"] in ("radio", "select") and campo.get("opcoes"):
                resultado[campo["id"]] = 0
                log_warn(f"    [FALLBACK erro] '{campo['pergunta'][:40]}' → índice 0")

    log_ok(f"  Total final: {len(resultado)}/{len(campos)} campos resolvidos")
    return resultado


def _esta_em_ingles(texto: str) -> bool:
    if not texto:
        return False
    palavras_en = [
        "do you", "are you", "have you", "can you", "will you",
        "how many", "how long", "what is", "which of", "please",
        "select", "choose", "indicate", "describe", "explain",
        "years of", "experience with", "willing to", "authorized to",
        "currently", "currently working", "salary expectation",
        "cover letter", "upload", "attach", "provide",
    ]
    texto_lower = texto.lower()
    return any(p in texto_lower for p in palavras_en)


def _ia_resolver_campo(campo: dict, contexto_vaga: str, modo_forcado: bool = False) -> Any:
    pergunta = campo["pergunta"]
    tipo     = campo["tipo"]
    opcoes   = campo.get("opcoes", [])

    if not pergunta or pergunta.strip() in ("", "q_"):
        return None

    texto_completo = pergunta + " " + " ".join(opcoes)
    aviso_ingles = (
        "\nATENÇÃO: A pergunta acima está em inglês. "
        "Entenda-a e responda normalmente.\n"
    ) if _esta_em_ingles(texto_completo) else ""

    if tipo in ("radio", "select"):
        opts_str = "\n".join(f"  [{j}] {o}" for j, o in enumerate(opcoes))

        # Aviso contextual baseado no tipo de pergunta
        aviso_nivel = ""
        aviso_area  = ""
        _p_lower = pergunta.lower()
        if any(t in _p_lower for t in ["nível", "nivel", "senioridade", "experiência", "seniority"]):
            aviso_nivel = (
                "\n⚠️  ATENÇÃO NÍVEL: O candidato é JÚNIOR/PLENO — NÃO é estagiário.\n"
                "NUNCA escolha opções como 'Estágio', 'Estagiário', 'Trainee' ou 'Intern'.\n"
                "Prefira sempre: Júnior > Pleno > qualquer coisa > Estágio (PROIBIDO).\n"
            )
        if any(t in _p_lower for t in ["área", "area", "categoria", "departamento", "setor"]):
            aviso_area = (
                "\n⚠️  ATENÇÃO ÁREA: O candidato é desenvolvedor de SOFTWARE/TI.\n"
                "NUNCA selecione 'Engenharia' como área — mesmo que a vaga tenha 'engenheiro' no título.\n"
                "Prefira: TI > Tecnologia > Informática > Software > Desenvolvimento.\n"
            )

        if not modo_forcado:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DO FORMULÁRIO:\n\"{pergunta}\"\n"
                f"{aviso_ingles}{aviso_nivel}{aviso_area}\n"
                f"OPÇÕES DISPONÍVEIS:\n{opts_str}\n\n"
                f"Analise a pergunta, considere o perfil e escolha a opção correta.\n"
                f"Se for campo condicional que não se aplica: FINAL: PULAR\n"
                f"Última linha obrigatória: FINAL: <número da opção>"
            )
        else:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DO FORMULÁRIO:\n\"{pergunta}\"\n"
                f"{aviso_ingles}{aviso_nivel}{aviso_area}\n"
                f"OPÇÕES DISPONÍVEIS:\n{opts_str}\n\n"
                f"Esta é uma pergunta de conhecimento técnico ou quiz da vaga.\n"
                f"Use seu conhecimento geral para identificar a melhor resposta.\n"
                f"Você DEVE escolher uma opção — NUNCA retorne PULAR ou vazio.\n"
                f"Raciocine brevemente sobre cada opção e escolha a mais correta.\n"
                f"Última linha obrigatória: FINAL: <número da opção>"
            )

    elif tipo == "checkbox":
        opts_str = "\n".join(f"  [{j}] {o}" for j, o in enumerate(opcoes))

        if not modo_forcado:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DE MÚLTIPLA ESCOLHA (checkbox):\n\"{pergunta}\"\n"
                f"{aviso_ingles}\n"
                f"OPÇÕES DISPONÍVEIS:\n{opts_str}\n\n"
                f"Selecione TODAS as opções corretas/verdadeiras para esta pergunta.\n"
                f"Responda com os números das opções corretas separados por vírgula.\n"
                f"⚠️  FORMATO OBRIGATÓRIO: apenas números separados por vírgula.\n"
                f"Exemplos: FINAL: 0   ou   FINAL: 0,2   ou   FINAL: 1,2,3\n"
                f"NUNCA responda com texto — apenas números.\n"
                f"Última linha obrigatória: FINAL: <números separados por vírgula>"
            )
        else:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DE MÚLTIPLA ESCOLHA (checkbox):\n\"{pergunta}\"\n"
                f"{aviso_ingles}\n"
                f"OPÇÕES DISPONÍVEIS:\n{opts_str}\n\n"
                f"Use seu conhecimento técnico para identificar as opções corretas.\n"
                f"Você DEVE escolher pelo menos uma opção.\n"
                f"Responda SOMENTE com números separados por vírgula — NADA mais.\n"
                f"Última linha obrigatória: FINAL: <números separados por vírgula>"
            )
    else:
        if not modo_forcado:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DO FORMULÁRIO:\n\"{pergunta}\"\n"
                f"{aviso_ingles}\n"
                f"Este é um campo de TEXTO LIVRE — responda com palavras descritivas, NÃO com um número sozinho.\n"
                f"Responda de forma direta e concisa com base no perfil.\n"
                f"Se for campo condicional que não se aplica: FINAL: PULAR\n"
                f"Se pedir salário atual/último: FINAL: PULAR\n"
                f"Última linha obrigatória: FINAL: <resposta textual>"
            )
        else:
            prompt = (
                f"VAGA: {contexto_vaga[:150]}\n\n"
                f"PERGUNTA DO FORMULÁRIO:\n\"{pergunta}\"\n"
                f"{aviso_ingles}\n"
                f"ATENÇÃO: Este é um campo de TEXTO LIVRE. Responda com palavras, NÃO com números.\n"
                f"Responda com base no perfil do candidato.\n"
                f"Você DEVE fornecer uma resposta textual — NUNCA retorne vazio ou só um número.\n"
                f"Exemplos corretos: 'Desenvolvedor Web Fullstack', '3500', 'Sim, tenho experiência com React'\n"
                f"Última linha obrigatória: FINAL: <resposta textual>"
            )

    raw = chamar_llm(
        messages=[
            {"role": "system", "content": _get_system_form()},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=500,
        temperature=0.0 if not modo_forcado else 0.2,
    ).strip()

    log_info(f"      [IA RAW{'*' if modo_forcado else ''}] {raw[-200:]!r}")

    resposta_str = ""
    for linha in reversed(raw.split("\n")):
        linha = linha.strip()
        if re.match(r"^FINAL\s*:", linha, re.IGNORECASE):
            resposta_str = re.sub(r"^FINAL\s*:\s*", "", linha, flags=re.IGNORECASE).strip()
            resposta_str = resposta_str.strip("\"' <>")
            placeholders = {"numero", "número", "numero da opcao", "número da opção",
                            "resposta", "texto", "valor", "<número>", "<resposta>"}
            if resposta_str.lower() in placeholders:
                resposta_str = ""
            break

    if not resposta_str:
        for linha in reversed(raw.split("\n")):
            if linha.strip():
                resposta_str = linha.strip().strip("\"' ")
                log_warn(f"      [IA] Sem FINAL:, usando última linha: {resposta_str[:50]!r}")
                break

    if not resposta_str:
        return None

    # ── Checkbox: retorna lista de índices ──────────────────────────
    if tipo == "checkbox":
        if resposta_str.upper() == "PULAR":
            return []
        # Extrai todos os números da resposta
        nums = re.findall(r"\b(\d+)\b", resposta_str)
        indices = [int(n) for n in nums if 0 <= int(n) < len(opcoes)]
        if indices:
            return indices
        # Nenhum índice válido — tenta match por texto
        resp_lower = resposta_str.lower()
        matches = [
            j for j, opt in enumerate(opcoes)
            if (opt["texto"].lower() if isinstance(opt, dict) else opt.lower()) in resp_lower
        ]
        return matches if matches else None

    # ── Texto/textarea ───────────────────────────────────────────────
    if tipo not in ("radio", "select"):
        if resposta_str.upper() == "PULAR":
            return "PULAR"
        # Valida: campo texto NÃO deve retornar apenas um número (seria índice de select)
        if re.match(r"^\d+$", resposta_str.strip()) and not modo_forcado:
            log_warn(f"      [IA] Campo TEXTO retornou número puro '{resposta_str}' — suspeito, rejeitando")
            return None
        return resposta_str

    # ── Radio / Select ───────────────────────────────────────────────
    if resposta_str.upper() == "PULAR":
        if modo_forcado:
            return None
        return "PULAR"

    m = re.search(r"\b(\d+)\b", resposta_str)
    if m:
        idx = int(m.group(1))
        if 0 <= idx < len(opcoes):
            return idx
        log_warn(f"      [IA] idx={idx} fora do range 0-{len(opcoes)-1}")

    r_lower = resposta_str.lower().strip()
    for j, opt in enumerate(opcoes):
        if r_lower == opt.lower().strip():
            return j
    for j, opt in enumerate(opcoes):
        if r_lower in opt.lower() or opt.lower().strip() in r_lower:
            return j

    log_warn(f"      [IA] Não mapeou '{resposta_str[:50]}' para nenhuma opção")
    return None


def ia_gerar_carta(titulo: str, empresa: str, descricao: str) -> str:
    lang = "em inglês" if any(
        w in descricao.lower()
        for w in ["required", "experience", "skills", "must", "responsibilities"]
    ) else "em português"

    prompt = (
        f"Escreva uma carta de apresentação {lang} para a candidatura abaixo.\n\n"
        f"VAGA:\nCargo: {titulo}\nEmpresa: {empresa}\n"
        f"Descrição: {descricao[:800] or 'Não informada'}\n\n"
        f"CANDIDATO:\n{PERFIL_RESUMIDO}\n\n"
        "OBJETIVO DA CARTA:\n"
        "Uma apresentação técnica curta — estilo resumo do LinkedIn adaptado à vaga.\n"
        "Mostra quem o candidato é tecnicamente e por que o perfil se encaixa nesta vaga.\n"
        "NÃO é um relato de projetos. NÃO são promessas. É um perfil direcionado.\n\n"
        "ESTRUTURA OBRIGATÓRIA — 3 parágrafos curtos (máx. 3 linhas cada):\n"
        "1º: Quem é o candidato tecnicamente — destaque as stacks e habilidades\n"
        "    que a vaga pede E o candidato realmente tem. Adapte ao contexto da vaga.\n"
        "2º: Como o perfil se encaixa no que esta empresa/vaga precisa.\n"
        "3º: Disponibilidade imediata + encerramento em 1 linha.\n\n"
        "REGRAS:\n"
        "- Tom: direto, confiante, profissional\n"
        "- PROIBIDO: citar projetos pessoais, mencionar anos de experiência,\n"
        "  prometer métricas, usar linguagem bajuladora\n"
        "- PROIBIDO: 'ansioso', 'não hesite', 'motivado', 'comprometido',\n"
        "  'entusiasmo', 'tenho o prazer', 'seria uma honra', 'prezado(a)', 'oportunidade'\n"
        "- NÃO começar com 'Prezado' ou 'A quem'\n"
        "- NÃO mencionar salário\n"
        "- Assinar com o nome completo do candidato ao final\n"
    )

    try:
        carta = chamar_llm(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.4,
        )
        log_ok(f"  Carta gerada ({len(carta)} chars)")
        return carta
    except Exception as exc:
        log_err(f"  Carta falhou: {exc} — usando fallback")
        techs = [
            t.capitalize()
            for t in ["python", "django", "react", "php", "javascript", "typescript", "docker", "node"]
            if t in descricao.lower() and t in " ".join(CONFIG.get("tecnologias", {}).keys()).lower()
        ][:4] or ["Python", "Django", "React"]
        return (
            f"Atuo como desenvolvedor full stack com foco em {', '.join(techs[:2])} no backend "
            f"e {', '.join(techs[2:] or ['React'])} no frontend, desenvolvendo APIs RESTful, "
            f"autenticação, integração de sistemas e interfaces responsivas.\n\n"
            f"O perfil que a vaga de {titulo} descreve se encaixa diretamente com o que trabalho: "
            f"código organizado, boas práticas, capacidade de atuar de forma autônoma e entregar "
            f"soluções completas, do banco de dados à interface.\n\n"
            f"Disponibilidade imediata. Fico à disposição para conversa.\n\n"
            f"{CANDIDATO.get('nome', '')}"
        )


# ═══════════════════════════════════════════════════════════════
#  LLM ROUTER — somente provedores cadastrados na UI (config.yaml → ia)
#
#  Roteador único: common.llm.chamar_ia (ativo em 1º, demais em ordem de
#  cadastro). Sem cadastro, ou todos falharem → LLMError (subclasse de
#  RuntimeError) — os chamadores mantêm seus fallbacks.
# ═══════════════════════════════════════════════════════════════


def chamar_llm(prompt: str, max_tokens: int = 400, temperature: float = 0.1) -> str:
    """LLM do Indeed: somente provedores cadastrados na UI (config.yaml → ia).

    O roteador (common.llm.chamar_ia) tenta o provedor ativo e os demais em
    ordem de cadastro; sem cadastro, ou todos falharem, levanta LLMError."""
    return _llm_lib.chamar_ia(
        CONFIG, prompt,
        temperatura=temperature,
        max_tokens=max_tokens,
        log_info=lambda m: log_info(m),
    )

