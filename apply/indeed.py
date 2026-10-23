"""
╔══════════════════════════════════════════════════════════════╗
║              🤖 JOB HUNTER — INDEED  v2.8                   ║
║  Engenharia profissional: robusto, limpo, sem travamentos    ║
╚══════════════════════════════════════════════════════════════╝

Mudanças v2.8:
  • Regra de skip por formulário em inglês via IA:
    - Após abrir o formulário de candidatura (Indeed Apply),
      ANTES de preencher qualquer campo, todos os labels/perguntas
      detectados são concatenados e enviados ao LLM.
    - Prompt direto: "A maioria dessas perguntas está em inglês? SIM ou NÃO"
    - Se a IA responder SIM → candidatura abortada imediatamente
    - Status registrado como "formulario_ingles"
    - Aproveita chamar_llm() — mesmo roteador Groq/HuggingFace
    - Distingue inglês real de termos técnicos (React, API, deploy)
      que aparecem normalmente em formulários PT-BR

Mudanças v2.7:
  • Regra de skip por descrição em inglês via IA:
    - A descrição da vaga é enviada ao LLM (Groq/HuggingFace)
      com um prompt direto: "Esta descrição está em inglês? SIM ou NÃO"
    - Se a IA responder SIM → candidatura abortada imediatamente
    - Status registrado como "descricao_ingles"

Mudanças v2.6:
  • Regra de skip por perguntas de filiação:
    - Se qualquer etapa do formulário contiver pergunta sobre
      nome/dados da mãe ou do pai → candidatura abortada imediatamente
    - Status registrado como "pergunta_filiacao"

Mudanças v2.5:
  • LLM Router: Groq primário / HuggingFace fallback automático
  • _ia_resolver_campo() com 3 camadas
  • Carta de apresentação reescrita estilo resumo LinkedIn

Mudanças v2.4:
  • _inserir_carta_na_revisao() reescrito com 3 estratégias em cascata

Mudanças v2.3:
  • Fix disponibilidade remoto/híbrido/presencial
  • Fix pretensão salarial CLT vs PJ
"""

from __future__ import annotations

import json
import os
import pickle
import random
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from common import llm as _llm_lib
from common import pagelens, perfil
from dotenv import load_dotenv
from groq import Groq
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from seleniumbase import Driver

# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

load_dotenv()

with open("config.yaml", encoding="utf-8") as _f:
    CONFIG: dict = yaml.safe_load(_f)

TZ                = ZoneInfo("America/Sao_Paulo")
CANDIDATO         = CONFIG["candidato"]
DIVERSIDADE       = CONFIG["diversidade"]
LOCALIZACAO       = CONFIG["localizacao"]
GROQ_MODEL        = CONFIG["groq"]["model"]
MAX_POR_DIA       = CONFIG["automacao"]["max_candidaturas_por_dia"]
DELAY_VAGAS       = CONFIG["automacao"]["delay_entre_vagas"]
CURRICULO_PDF     = str(Path(CONFIG["resumes"]["fullstack"]).resolve())
PALAVRAS_CHAVE    = CONFIG["busca"]["palavras_chave"]
PALAVRAS_EXCLUIR  = [p.lower() for p in CONFIG["busca"]["palavras_excluir"]]
SESSION_FILE      = Path("indeed_session.pkl")
RELATORIO_DIR     = Path("relatorio")
RELATORIO_DIR.mkdir(exist_ok=True)
RELATORIO_FILE    = RELATORIO_DIR / "candidaturas.json"

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Dados sensíveis — lidos exclusivamente do .env, nunca do config.yaml
_DOC_CPF = os.getenv("CANDIDATO_CPF", "")
_DOC_RG  = os.getenv("CANDIDATO_RG",  "")
_DOC_CNH = os.getenv("CANDIDATO_CNH", "")

_END_LOGRADOURO  = os.getenv("ENDERECO_LOGRADOURO",  "")
_END_NUMERO      = os.getenv("ENDERECO_NUMERO",      "")
_END_BAIRRO      = os.getenv("ENDERECO_BAIRRO",      "")
_END_CEP         = os.getenv("ENDERECO_CEP",         "")
_END_COMPLEMENTO = os.getenv("ENDERECO_COMPLEMENTO", "")


# ═══════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════

def _now_str() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO") -> None:
    print(f"[{_now_str()}] [{level}] {msg}")

def log_ok(msg: str)   -> None: log(msg, "✅")
def log_err(msg: str)  -> None: log(msg, "❌")
def log_skip(msg: str) -> None: log(msg, "⏭️ ")
def log_info(msg: str) -> None: log(msg, "ℹ️ ")
def log_warn(msg: str) -> None: log(msg, "⚠️ ")


# ═══════════════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════════════

def esperar(seconds: float, jitter: float = 0.3) -> None:
    time.sleep(max(0.2, seconds + random.uniform(-jitter * 0.5, jitter)))


def horario_ok() -> bool:
    return 3 <= datetime.now(TZ).hour <= 22

# ═══════════════════════════════════════════════════════════════
#  EXCEÇÕES CUSTOMIZADAS
# ═══════════════════════════════════════════════════════════════

class _PerguntaFiliacaoDetectada(Exception):
    """Aborta a candidatura quando detecta campo de nome da mãe/pai."""


class _FormularioEmIngles(Exception):
    """Aborta a candidatura quando o formulário está predominantemente em inglês."""


# ═══════════════════════════════════════════════════════════════
#  DETECÇÃO DE DESCRIÇÃO EM INGLÊS VIA IA  (v2.7)
# ═══════════════════════════════════════════════════════════════

def _descricao_em_ingles(descricao: str) -> bool:
    """
    Usa o LLM (Groq/HuggingFace via chamar_llm) para detectar se a
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
            messages=[{"role": "user", "content": prompt}],
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
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0,
        ).strip().upper()
        log_info(f"  [idioma formulário] IA respondeu: {resposta[:10]!r}")
        return resposta.startswith("S") or resposta.startswith("Y")

    except Exception as exc:
        log_warn(f"  [idioma formulário] IA falhou — usando heurística: {exc}")
        return pct_frases > 0.60 or ratio_en > 0.20


# ═══════════════════════════════════════════════════════════════
#  DETECÇÃO DE PERGUNTAS DE FILIAÇÃO  (v2.6)
# ═══════════════════════════════════════════════════════════════

_TERMOS_FILIACAO = [
    # Português
    "nome da mãe", "nome da mae", "nome completo da mãe", "nome completo da mae",
    "nome da genitora", "nome da progenitora",
    "nome do pai", "nome completo do pai",
    "nome do genitor", "nome do progenitor",
    "filiação", "filiacao",
    "nome da sua mãe", "nome da sua mae",
    "nome do seu pai",
    "dados da mãe", "dados da mae",
    "dados do pai",
    "mãe e pai", "mae e pai",
    "pai e mãe", "pai e mae",
    # Inglês
    "mother's name", "mothers name", "mother name",
    "full name of mother", "full name of your mother",
    "father's name", "fathers name", "father name",
    "full name of father", "full name of your father",
    "parent name", "parents name", "parent's name",
    "name of mother", "name of father",
    "maternal name", "paternal name",
]


def _contem_pergunta_filiacao(texto: str) -> bool:
    t = " ".join(texto.lower().split())
    return any(termo in t for termo in _TERMOS_FILIACAO)


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


def _inferir_cargo_pretendido(contexto_vaga: str) -> str:
    """
    Infere o cargo pretendido adequado com base no contexto da vaga.
    Analisa o título e descrição para retornar algo coerente com o que foi pedido,
    mantendo o candidato como desenvolvedor/engenheiro de software.
    """
    ctx = contexto_vaga.lower()

    # Detecta modalidade
    eh_estagio = any(t in ctx for t in ["estágio", "estagio", "estagiário", "intern", "trainee", "aprendiz"])

    # Detecta stack/especialidade mencionada
    if any(t in ctx for t in ["data", "dados", "analytics", "pyspark", "spark", "etl", "pipeline"]):
        base = "Engenheiro de Dados"
    elif any(t in ctx for t in ["devops", "sre", "infra", "cloud", "aws", "azure", "gcp", "terraform"]):
        base = "Engenheiro DevOps"
    elif any(t in ctx for t in ["mobile", "ios", "android", "react native", "flutter", "kotlin", "swift"]):
        base = "Desenvolvedor Mobile"
    elif any(t in ctx for t in ["frontend", "front-end", "react", "vue", "angular", "ui", "css", "html"]):
        base = "Desenvolvedor Frontend"
    elif any(t in ctx for t in ["backend", "back-end", "api", "django", "fastapi", "node", "java", "spring"]):
        base = "Desenvolvedor Backend"
    elif any(t in ctx for t in ["fullstack", "full stack", "full-stack"]):
        base = "Desenvolvedor Fullstack"
    elif any(t in ctx for t in ["engenharia de software", "software engineer", "engenheiro de software"]):
        base = "Engenheiro de Software"
    else:
        base = "Desenvolvedor Web Fullstack"

    if eh_estagio:
        return f"Estagiário de {base}" if "Engenheiro" not in base else f"Estagiário em {base}"

    return base


# ═══════════════════════════════════════════════════════════════
#  REGRAS DETERMINÍSTICAS — APENAS DADOS 100% MECÂNICOS
# ═══════════════════════════════════════════════════════════════

@dataclass
class _CtxRegras:
    """Contexto compartilhado pelas regras determinísticas do formulário.

    Cada regra recebe este contexto e devolve (resolvido, valor) quando
    reconhece a pergunta, ou None para passar o turno à próxima regra.

    `c` (candidato) e `div` (diversidade) são referências vivas da config —
    lidos em tempo de chamada, como na versão monolítica. Os campos de
    endereço chegam pré-resolvidos (env tem prioridade sobre o config;
    vazio cai para o default do campo).
    """
    c: dict                    # CONFIG["candidato"]
    div: dict                  # CONFIG.get("diversidade", {})
    contexto_vaga: str
    pergunta: str              # label da pergunta, normalizado (lower/strip)
    tipo: str                  # "radio" | "select" | "checkbox" | "texto" | ...
    opcoes: list[str]          # textos das opções (radio/select)
    # endereço — env tem prioridade; vazio cai para o config
    pais: str
    estado_nome: str
    estado_uf: str
    cidade: str
    bairro: str
    logradouro: str
    numero: str
    complemento: str
    cep: str


def _regra_data_nascimento(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """Data de nascimento — fixa do candidato."""
    termos = [
        "nascimento", "data de nascimento", "nasc.", "birth date", "date of birth",
        "birthday", "born", "birth", "aniversário", "aniversario",
    ]
    if ctx.tipo == "date" or any(t in ctx.pergunta for t in termos):
        return True, ctx.c.get("data_nascimento", "")
    return None

def _regra_genero(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """Gênero/sexo — segue a config de diversidade do candidato."""
    if not any(t in ctx.pergunta for t in ["gênero", "genero", "gender", "sexo", "sex"]):
        return None

    genero_cfg = ctx.div.get("genero", "").lower()
    if ctx.tipo in ("radio", "select"):
        masculino_keys = ["masculino", "male", "homem", "masc", "man", "men"]
        feminino_keys  = ["feminino", "female", "mulher", "fem", "woman", "women"]
        outro_keys     = ["outro", "other", "não-binário", "nao-binario", "nonbinary"]
        pns_keys       = ["prefiro não", "prefer not", "não informar", "not say", "não declarar"]

        if any(k in genero_cfg for k in ["masculino", "homem", "male"]):
            alvo = masculino_keys
        elif any(k in genero_cfg for k in ["feminino", "mulher", "female"]):
            alvo = feminino_keys
        elif any(k in genero_cfg for k in ["outro", "other", "não-bin"]):
            alvo = outro_keys
        else:
            alvo = pns_keys

        # Tenta match por texto da opção
        for j, opt in enumerate(ctx.opcoes):
            if any(k in opt.lower() for k in alvo):
                return True, j

        # Fallback: opções com IDs React ilegíveis — tenta match pelo value
        # (campo["opcoes"] só tem texto; o value fica em elementos[] que não
        # chegamos aqui, mas podemos checar se todas as opções parecem IDs React)
        todas_ilegíveis = all(
            re.search(r":r[0-9a-z]+[p]?:", opt) or len(opt) > 40
            for opt in ctx.opcoes
        )
        if todas_ilegíveis and ctx.opcoes:
            # Convenção típica do Indeed: índice 0 = Masculino, 1 = Feminino, 2 = Outro
            if any(k in genero_cfg for k in ["masculino", "homem", "male"]):
                log_warn("    [GÊNERO] Opções ilegíveis — assumindo índice 0 = Masculino")
                return True, 0
            elif any(k in genero_cfg for k in ["feminino", "mulher", "female"]):
                log_warn("    [GÊNERO] Opções ilegíveis — assumindo índice 1 = Feminino")
                return True, 1

    elif ctx.tipo in ("texto", "textarea"):
        return True, ctx.div.get("genero", "")
    return False, None


def _regra_pcd(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """PCD — segue a flag de deficiência da config de diversidade."""
    termos = [
        "pcd", "deficiência", "deficiencia", "disability",
        "pessoa com deficiência", "portador",
    ]
    if not any(t in ctx.pergunta for t in termos):
        return None

    if not ctx.div.get("pcd", False):
        if ctx.tipo == "checkbox":
            return True, []
        elif ctx.tipo in ("radio", "select"):
            nao_keys = ["não", "nao", "no", "nenhum", "nenhuma", "não possuo"]
            for j, opt in enumerate(ctx.opcoes):
                if any(k in opt.lower() for k in nao_keys):
                    return True, j
            return True, None
        elif ctx.tipo in ("texto", "textarea"):
            return True, "Não possuo deficiência"
    return False, None

def _regra_grupo_diversidade(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Grupo de diversidade / inclusão.
    Perguntas como "Você pertence a algum grupo abaixo?" com opções de
    minorias (PCD, LGBTI+, Mulher, Preta, Parda...).
    Lógica: se tiver opção que representa homem cis sem grupo → escolhe.
    Se não tiver → marca cor/raça real (parda/preta conforme config).
    Nunca marca LGBTI+, PCD, Mulher se não for o caso."""
    termos = [
        "pertence a", "faz parte de", "grupo", "diversidade", "inclusão", "inclusao",
        "grupos minorizados", "grupo minoritário", "grupo minoritario",
        "grupo de diversidade", "grupo social",
    ]
    if not (ctx.tipo in ("radio", "select", "checkbox")
            and any(t in ctx.pergunta for t in termos)):
        return None

    raca_cfg = ctx.div.get("raca_cor", "").lower()

    # Opções que representam "nenhum grupo" / homem cis sem minoria
    neutro_keys = [
        "não pertenço", "nao pertenco", "nenhum dos grupos", "nenhum grupo",
        "não me identifico", "nao me identifico", "não se aplica",
        "homem cis", "homem cisgênero", "homem cisgenero",
        "cisgênero", "cisgenero", "cis",
    ]
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in neutro_keys):
            if ctx.tipo == "checkbox":
                return True, [j]
            return True, j

    # Sem opção neutra → marca cor/raça real do candidato
    preta_keys = ["preta", "negro", "negra", "black"]
    parda_keys = ["parda", "pardo", "mixed", "morena", "moreno"]
    alvo_raca = preta_keys if any(k in raca_cfg for k in ["pret", "negr"]) else parda_keys  # default: pardo

    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in alvo_raca):
            if ctx.tipo == "checkbox":
                return True, [j]
            return True, j

    # Último recurso: "Prefiro não responder"
    pnr_keys = ["prefiro não", "prefer not", "não informar", "não declarar"]
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in pnr_keys):
            if ctx.tipo == "checkbox":
                return True, [j]
            return True, j

    return False, None

def _regra_raca(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """Raça/cor/etnia — marca a real, conforme a config de diversidade."""
    if not any(t in ctx.pergunta for t in
        ["raça", "raca", "cor", "etnia", "race", "ethnicity"]):
        return None

    raca = ctx.div.get("raca_cor", "")
    if ctx.tipo in ("radio", "select"):
        for j, opt in enumerate(ctx.opcoes):
            if raca.lower() in opt.lower():
                return True, j
    elif ctx.tipo in ("texto", "textarea"):
        return True, raca
    return False, None


def _regra_pais(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """País/nacionalidade — sempre o do endereço do candidato."""
    if ctx.tipo in ("radio", "select") and any(
        t in ctx.pergunta for t in ["país", "pais", "country", "país de residência", "nacionalidade"]
    ):
        for j, opt in enumerate(ctx.opcoes):
            if opt.strip().lower() in (ctx.pais.lower(), "brazil"):
                return True, j
        return False, None
    return None


def _regra_estado(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """Estado/UF — sempre o do endereço do candidato."""
    if ctx.tipo in ("radio", "select") and any(
        t in ctx.pergunta for t in ["estado", "state", "province", "uf"]
    ):
        for j, opt in enumerate(ctx.opcoes):
            opt_l = opt.strip().lower()
            if opt_l in (ctx.estado_nome.lower(), ctx.estado_uf.lower(), "são paulo", "sp"):
                return True, j
        return False, None
    return None

def _regra_condicional_outro(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Campos condicionais "Se outra / If other / Especifique".
    Só devem ser preenchidos se a resposta anterior foi "Outro/Outra".
    Como o bot nunca seleciona "Outro/Outra" (sempre escolhe opção
    específica), esses campos condicionais devem sempre ficar em branco."""
    termos = [
        "se outra", "se outro", "if other", "if yes", "caso outro", "caso outra",
        "caso sim", "caso positivo", "especifique", "qual outro", "qual outra",
        "informar abaixo", "informe abaixo", "descreva abaixo", "especifique abaixo",
        "se marcou outro", "se selecionou outro",
    ]
    if ctx.tipo in ("texto", "textarea") and any(t in ctx.pergunta for t in termos):
        return True, "PULAR"
    return None


def _regra_segmento(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Segmento / ramo / setor de atuação — o candidato é
    autônomo/freelancer em TI."""
    termos = [
        "segmento", "ramo", "setor", "área de atuação", "area de atuacao",
        "último segmento", "ultimo segmento", "segmento trabalhado",
        "ramo de atuação", "ramo de atividade",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    autonomo_keys   = ["autônomo", "autonomo", "freelance", "freelancer", "autônoma"]
    tecnologia_keys = ["tecnologia", "ti", "t.i", "software", "informática", "informatica"]

    # Prioridade: Autônomo > Tecnologia > (nunca 1° emprego para freelancer)
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in autonomo_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in tecnologia_keys):
            return True, j
    return False, None


def _regra_origem(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Como conheceu a vaga / origem da candidatura."""
    termos = [
        "como você chegou", "como chegou", "como ficou sabendo",
        "onde viu", "como soube", "fonte da candidatura",
        "como nos encontrou", "how did you find", "how did you hear",
        "where did you find", "source", "referral", "indicação",
        "como conheceu", "canal", "como chegou até",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    linkedin_keys = ["linkedin"]
    google_keys   = ["google"]
    indeed_keys   = ["indeed"]
    site_keys     = ["site", "website", "portal"]

    # Prioridade: Indeed (já que veio do Indeed) > LinkedIn > Google > Site
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in indeed_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in linkedin_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in google_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in site_keys):
            return True, j
    return False, None

def _regra_mapa_texto(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """Campos de texto com correspondência direta: links, e-mail,
    endereço, disponibilidade, empresa/cargo atual e cargo pretendido
    (contextual à vaga)."""
    if ctx.tipo not in ("texto", "textarea"):
        return None

    c = ctx.c
    MAPA: list[tuple[list[str], str]] = [
        (["linkedin"],                                          c["linkedin"]),
        (["github"],                                            c["github"]),
        (["portfólio", "portfolio"],                            c.get("portfolio", "")),
        (["seu email", "seu e-mail", "your email",
          "endereço de e-mail", "endereço de email"],           c["email"]),
        (["telefone", "celular", "whatsapp", "phone number"],   c["telefone"]),
        (["cpf"],                                               _DOC_CPF or "PULAR"),
        (["nome completo", "full name", "your full name",
          "seu nome completo"],                                  c["nome"]),
        (["país", "pais", "country", "nationality",
          "nacionalidade"],                                      ctx.pais),
        (["estado", "state", "province", "uf",
          "province/state"],                                     ctx.estado_nome),
        (["cidade", "city", "município", "municipio"],           ctx.cidade),
        (["bairro", "neighborhood", "distrito"],                 ctx.bairro),
        (["logradouro", "rua", "endereço", "endereco",
          "address", "street"],                                  ctx.logradouro),
        (["número", "numero", "nº", "number", "num.",
          "nr.", "house number"],                                ctx.numero),
        (["complemento", "complement", "apto",
          "apartamento", "additional address"],                  ctx.complemento),
        (["cep", "zip", "zip code", "postal code",
          "código postal"],                                      ctx.cep),
        (["quando pode começar", "data de início", "start date",
          "when can you start", "disponibilidade para início"],
         datetime.now(TZ).strftime("%d/%m/%Y")),
        (["empresa atual", "current company",
          "company where you work", "confirme o nome da empresa"],
         "Autônomo / Freelancer"),
        (["cargo atual", "current job title",
          "posição atual", "sua posição"],
         "Desenvolvedor Web Freelancer"),
        # Cargo pretendido / desejado — contextual à vaga
        # Detecta o tipo de vaga pelo contexto e adapta o cargo
        (["cargo pretendido", "cargo desejado", "cargo que deseja",
          "vaga pretendida", "posição pretendida", "função pretendida",
          "desired position", "desired job", "position applying"],
         _inferir_cargo_pretendido(ctx.contexto_vaga)),
    ]

    for termos, valor in MAPA:
        if any(t in ctx.pergunta for t in termos):
            return True, valor
    return None

def _regra_tipo_doc(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Tipo de documento (select) — assume CPF; RG como fallback."""
    termos = [
        "tipo de documento", "tipo documento", "document type",
        "tipo de identificação", "tipo de identificacao",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    cpf_keys = ["cpf"]
    rg_keys  = ["rg", "identidade", "identity"]
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in cpf_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in rg_keys):
            return True, j
    return False, None


def _regra_num_doc(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Número de documento / CPF / RG — campo de texto pedindo o
    número do documento."""
    termos = [
        "cpf", "número do cpf", "numero do cpf",
        "rg", "número do rg", "numero do rg",
        "número de identidade", "numero de identidade",
        "número do documento", "numero do documento",
        "documento", "document number", "id number",
        "número de identificação", "numero de identificacao",
        "cnh", "número da cnh",
    ]
    if not (ctx.tipo in ("texto", "textarea") and any(t in ctx.pergunta for t in termos)):
        return None

    # CPF tem prioridade — é o documento principal
    cpf_termos = ["cpf", "cadastro de pessoa", "taxpayer"]
    rg_termos  = ["rg", "identidade", "identity", "registro geral"]
    cnh_termos = ["cnh", "habilitação", "habilitacao", "driver"]

    if any(t in ctx.pergunta for t in cpf_termos):
        return True, _DOC_CPF or "PULAR"
    if any(t in ctx.pergunta for t in cnh_termos):
        return True, _DOC_CNH or "PULAR"
    if any(t in ctx.pergunta for t in rg_termos):
        return True, _DOC_RG or "PULAR"
    # Label genérico "Documento" — assume CPF
    return True, _DOC_CPF or "PULAR"

def _regra_ultimo_segmento(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Último segmento / setor / área trabalhado.
    Candidato é autônomo/freelancer — nunca "1° emprego"."""
    termos = [
        "último segmento", "ultimo segmento", "segmento trabalhado",
        "setor trabalhado", "último setor", "ultimo setor",
        "ramo de atuação", "ramo de atuacao", "segmento de atuação",
        "área de atuação anterior", "last segment", "industry",
        "último emprego", "ultimo emprego", "último trabalho", "ultimo trabalho",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    autonomo_keys = ["autônomo", "autonomo", "freelance", "freelancer", "autono"]
    tech_keys     = ["tecnologia", "technology", "ti", "t.i", "software", "informática"]

    # Prioridade: autônomo > tecnologia (nunca "1° emprego")
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in autonomo_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in tech_keys):
            return True, j
    # Se só tem "1° emprego" como opção de inexperiência, evita
    # Retorna False para a IA decidir com instrução adequada
    return False, None


def _regra_condicional_outra(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Campos condicionais "Se outra / If other" — só se a opção
    "Outro/Outra" foi selecionada na pergunta anterior; como regra geral,
    pular."""
    termos = [
        "se outra", "se outro", "if other", "if yes", "se sim",
        "caso outro", "caso outra", "qual outra", "qual outro",
        "especifique", "especificar", "informe abaixo", "informar abaixo",
        "detalhe abaixo", "detail below", "please specify",
        "se escolheu outro", "se selecionou outro",
        "se marcou outro", "se marcou outra",
    ]
    if ctx.tipo in ("texto", "textarea") and any(t in ctx.pergunta for t in termos):
        return True, "PULAR"
    return None


def _regra_fonte(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Como conheceu a vaga / fonte de indicação — sempre responde
    "Indeed" (ou "Google"/"Outro" dependendo das opções)."""
    termos = [
        "como chegou", "como conheceu", "como ficou sabendo",
        "como soube", "fonte da vaga", "where did you hear",
        "how did you find", "how did you hear", "referral source",
        "canal de captação", "como você chegou",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    indeed_keys   = ["indeed", "portal de emprego", "job board"]
    linkedin_keys = ["linkedin"]
    google_keys   = ["google"]
    outro_keys    = ["outro", "other", "outra"]

    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in indeed_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in google_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in linkedin_keys):
            return True, j
    # Fallback: "Outro" — mas aí o campo "Se outra" será PULAR
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in outro_keys):
            return True, j
    return False, None

def _regra_condicoes_especiais(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Condições especiais / acessibilidade / PCD descritivo —
    o candidato não tem nenhuma."""
    termos = [
        "condições especiais", "condicoes especiais",
        "condição especial", "condicao especial",
        "necessidade especial", "necessidades especiais",
        "acessibilidade", "adaptação", "adaptacao",
        "transporte especial", "locomoção", "locomocao",
        "descreva sua deficiência", "descreva sua deficiencia",
        "descreva condições", "descreva condicoes",
        "tipo de deficiência", "tipo de deficiencia",
        "qual deficiência", "qual deficiencia",
        "detalhe sua necessidade", "condições de trabalho especiais",
        "special needs", "accessibility needs", "accommodation",
        "workplace accommodation",
    ]
    if ctx.tipo in ("texto", "textarea") and any(t in ctx.pergunta for t in termos):
        return True, "Não possuo necessidades especiais."
    return None


def _regra_nivel_experiencia(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Nível de experiência / senioridade — detecta o nível
    adequado conforme o contexto da vaga. Se a vaga é de estágio,
    seleciona estágio; caso contrário, prioriza júnior > pleno,
    nunca estágio."""
    termos = [
        "nível de experiência", "nivel de experiencia", "senioridade",
        "nível profissional", "nivel profissional", "experience level",
        "seniority", "nível", "nivel", "experiência profissional",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    ctx_lower = ctx.contexto_vaga.lower()
    vaga_eh_estagio = any(t in ctx_lower for t in [
        "estágio", "estagio", "estagiário", "estagiario",
        "intern", "trainee", "aprendiz",
    ])

    junior_keys  = ["júnior", "junior", "jr", "jr.", "entry", "iniciante"]
    pleno_keys   = ["pleno", "mid", "intermediário", "intermediario", "mid-level"]
    estagio_keys = ["estágio", "estagio", "estagiário", "estagiario", "intern", "trainee"]

    if vaga_eh_estagio:
        # Vaga de estágio → seleciona estágio
        for j, opt in enumerate(ctx.opcoes):
            if any(k in opt.lower() for k in estagio_keys):
                return True, j
        # fallback: índice 0 (geralmente o mais baixo)
        return True, 0

    # Vaga normal → júnior primeiro, pleno como fallback
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in junior_keys):
            return True, j
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in pleno_keys):
            return True, j
    return False, None


def _regra_area_profissional(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Área profissional / categoria — o candidato é de TI/
    Tecnologia, nunca "Engenharia" ou outra área."""
    termos = [
        "área profissional", "area profissional", "área de atuação",
        "area de atuacao", "categoria profissional", "área", "area",
        "departamento", "setor", "ramo", "segmento",
        "professional area", "field", "department",
    ]
    if not (ctx.tipo in ("radio", "select") and any(t in ctx.pergunta for t in termos)):
        return None

    ti_keys = [
        "ti", "t.i", "t.i.", "tecnologia", "technology",
        "informática", "informatica", "software", "sistemas",
        "computação", "computacao", "desenvolvimento", "it",
        "tech", "tecnologia da informação", "tecnologia da informacao",
    ]
    for j, opt in enumerate(ctx.opcoes):
        if any(k in opt.lower() for k in ti_keys):
            return True, j
    return False, None


def _regra_pretensao_salarial(ctx: _CtxRegras) -> tuple[bool, Any] | None:
    """REGRA: Pretensão salarial — varia por regime (CLT/PJ/hora),
    estágio e pretensão atual (sempre PULAR)."""
    termos = [
        "pretensão salarial", "pretensao salarial", "pretensão", "pretensao",
        "salário pretendido", "salario pretendido", "salário esperado",
        "salario esperado", "expectativa salarial", "remuneração pretendida",
        "remuneracao pretendida", "salary expectation", "expected salary",
        "desired salary", "salary range",
    ]
    if not any(t in ctx.pergunta for t in termos):
        return None

    ctx_lower = ctx.contexto_vaga.lower()
    eh_pj      = any(t in ctx.pergunta for t in ["pj", "pessoa jurídica", "pessoa juridica", "prestação", "prestacao", "contrato pj"])
    eh_hora    = any(t in ctx.pergunta for t in ["hora", "/h", "por hora", "hourly"])
    eh_atual   = any(t in ctx.pergunta for t in ["atual", "último", "ultimo", "current salary", "last salary"])
    # Detecta estágio tanto pelo texto da pergunta quanto pelo contexto da vaga
    eh_estagio = any(t in ctx.pergunta for t in ["estágio", "estagio", "estagiário", "intern", "trainee"]) or \
                 any(t in ctx_lower for t in ["estágio", "estagio", "estagiário", "estagiario", "intern", "trainee"])

    if eh_atual:
        return True, "PULAR"
    if eh_estagio:
        val = ctx.c.get("pretensao_estagio", "1600")
    elif eh_pj and eh_hora:
        val = ctx.c.get("pretensao_pj_hora", "22")
    elif eh_pj:
        val = ctx.c.get("pretensao_pj_mensal", "4500")
    else:
        val = ctx.c.get("pretensao_clt", "3500")

    if ctx.tipo in ("texto", "textarea"):
        return True, val
    return False, None

def _resolver_por_regra(campo: dict, contexto_vaga: str = "") -> tuple[bool, Any]:
    """
    Resolve dados 100% fixos via regras determinísticas, em série.
    A ordem de _REGRAS_DETERMINISTICAS é o contrato: a primeira regra que
    reconhece a pergunta decide o campo; nenhuma reconhecendo, o campo vai
    para a camada de IA. Levanta _PerguntaFiliacaoDetectada se o campo
    for sobre mãe/pai.
    """
    if _contem_pergunta_filiacao(campo["pergunta"]):
        raise _PerguntaFiliacaoDetectada(
            f"Campo de filiação detectado: '{campo['pergunta'][:80]}'"
        )

    c   = CANDIDATO
    en  = CONFIG.get("endereco", {})
    div = CONFIG.get("diversidade", {})

    ctx = _CtxRegras(
        c=c,
        div=div,
        pergunta=campo["pergunta"].lower().strip(),
        tipo=campo["tipo"],
        opcoes=campo.get("opcoes", []),
        contexto_vaga=contexto_vaga,
        pais=en.get("pais", "Brasil"),
        estado_nome=en.get("estado_nome", "São Paulo"),
        estado_uf=en.get("estado_uf", "SP"),
        cidade=en.get("cidade", "Ribeirão Preto"),
        bairro=_END_BAIRRO or en.get("bairro", ""),
        logradouro=_END_LOGRADOURO or en.get("logradouro", ""),
        numero=_END_NUMERO or en.get("numero", "S/N"),
        complemento=_END_COMPLEMENTO or en.get("complemento", ""),
        cep=_END_CEP or en.get("cep", ""),
    )
    for regra in _REGRAS_DETERMINISTICAS:
        resultado = regra(ctx)
        if resultado is not None:
            return resultado

    return False, None


# Ordem = prioridade: a primeira regra que retorna não-None decide o
# campo. Mantém a ordem exata da versão monolítica anterior à refatoração.
_REGRAS_DETERMINISTICAS: list = [
    _regra_data_nascimento,
    _regra_genero,
    _regra_pcd,
    _regra_grupo_diversidade,
    _regra_raca,
    _regra_pais,
    _regra_estado,
    _regra_condicional_outro,
    _regra_segmento,
    _regra_origem,
    _regra_mapa_texto,
    _regra_tipo_doc,
    _regra_num_doc,
    _regra_ultimo_segmento,
    _regra_condicional_outra,
    _regra_fonte,
    _regra_condicoes_especiais,
    _regra_nivel_experiencia,
    _regra_area_profissional,
    _regra_pretensao_salarial,
]


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
            [{"role": "user", "content": prompt}],
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
#  LLM ROUTER — Groq primário / HuggingFace fallback
# ═══════════════════════════════════════════════════════════════

import datetime as _dt
import threading

_HF_MODEL_LEGADO = "meta-llama/Meta-Llama-3-8B-Instruct"
_hf_model_cfg    = CONFIG.get("huggingface", {}).get("model", "")
HF_MODEL = (
    _hf_model_cfg
    if _hf_model_cfg and _hf_model_cfg != _HF_MODEL_LEGADO
    else "Qwen/Qwen2.5-72B-Instruct"
)
HF_API_KEY = os.getenv("HF_API_KEY", "")

_llm_state = {
    "provedor":      "groq",
    "groq_reset_em": None,
    "lock":          threading.Lock(),
}


def _agendar_retorno_groq(reset_utc: _dt.datetime) -> None:
    def _voltar():
        agora  = _dt.datetime.now(_dt.UTC)
        espera = max(0, (reset_utc - agora).total_seconds()) + 15
        log_info(f"  [LLM] HuggingFace ativo. Groq volta em {int(espera/60)}min "
                 f"({reset_utc.astimezone(TZ).strftime('%H:%M')} horário local)")
        time.sleep(espera)
        with _llm_state["lock"]:
            _llm_state["provedor"]      = "groq"
            _llm_state["groq_reset_em"] = None
        log_ok("  [LLM] Groq reativado automaticamente!")

    t = threading.Thread(target=_voltar, daemon=True)
    t.start()


_calcular_reset_groq = _llm_lib.calcular_reset_groq


def _normalizar_messages_para_hf(messages: list[dict]) -> list[dict]:
    """
    O HuggingFace Inference API frequentemente ignora mensagens com role='system'.
    Esta função mescla qualquer system prompt no início da primeira mensagem user,
    garantindo que o contexto seja sempre respeitado.
    """
    if not messages:
        return messages

    system_parts: list[str] = []
    user_messages: list[dict] = []

    for msg in messages:
        if msg.get("role") == "system":
            system_parts.append(msg["content"])
        else:
            user_messages.append(msg)

    if not system_parts:
        return messages  # sem system, nada a fazer

    system_text = "\n\n".join(system_parts)

    if not user_messages:
        # Só tinha system — converte para user
        return [{"role": "user", "content": system_text}]

    # Injeta o system no início da primeira mensagem user
    resultado = []
    primeiro_user_injetado = False
    for msg in user_messages:
        if msg.get("role") == "user" and not primeiro_user_injetado:
            conteudo_combinado = (
                f"[INSTRUÇÕES DO SISTEMA — SIGA RIGOROSAMENTE]\n"
                f"{system_text}\n"
                f"[FIM DAS INSTRUÇÕES DO SISTEMA]\n\n"
                f"{msg['content']}"
            )
            resultado.append({"role": "user", "content": conteudo_combinado})
            primeiro_user_injetado = True
        else:
            resultado.append(msg)

    return resultado


def _chamar_huggingface(
    messages: list[dict],
    max_tokens: int = 400,
    temperature: float = 0.1,
) -> str:
    import urllib.error
    import urllib.request

    if not HF_API_KEY:
        raise RuntimeError("HF_API_KEY não configurada no .env")

    url = "https://router.huggingface.co/v1/chat/completions"

    # HuggingFace ignora role='system' — mescla no user para garantir obediência
    messages_hf = _normalizar_messages_para_hf(messages)

    payload = json.dumps({
        "model":       HF_MODEL,
        "messages":    messages_hf,
        "max_tokens":  max_tokens,
        "temperature": max(0.01, temperature),
        "stream":      False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HuggingFace HTTP {e.code}: {body[:300]}") from e


def _chamar_groq(
    messages: list[dict],
    max_tokens: int = 400,
    temperature: float = 0.1,
    tentativas: int = 4,
) -> str:
    def _log(msg: str) -> None:
        log_info(f"  [Groq] {msg}")

    return _llm_lib.chamar_groq(
        messages,
        model=GROQ_MODEL,
        api_key=groq_client.api_key,
        log_info=_log,
        max_tokens=max_tokens,
        temperature=temperature,
        tentativas=tentativas,
    )


_GroqLimiteDiario = _llm_lib.GroqLimiteDiario


def chamar_llm(
    messages: list[dict],
    max_tokens: int = 400,
    temperature: float = 0.1,
) -> str:
    with _llm_state["lock"]:
        provedor = _llm_state["provedor"]

    if provedor == "groq":
        try:
            return _chamar_groq(messages, max_tokens, temperature)
        except _GroqLimiteDiario:
            reset_utc = _calcular_reset_groq()
            with _llm_state["lock"]:
                _llm_state["provedor"]      = "huggingface"
                _llm_state["groq_reset_em"] = reset_utc
            log_err("  [LLM] Groq: limite diário atingido → trocando para HuggingFace")
            _agendar_retorno_groq(reset_utc)

    try:
        resultado = _chamar_huggingface(messages, max_tokens, temperature)
        log_info(f"  [LLM] HuggingFace respondeu ({len(resultado)} chars)")
        return resultado
    except Exception as exc:
        raise RuntimeError(f"HuggingFace também falhou: {exc}") from exc


# ═══════════════════════════════════════════════════════════════
#  RELATÓRIO
# ═══════════════════════════════════════════════════════════════

def carregar_relatorio() -> dict:
    with suppress(Exception):
        if RELATORIO_FILE.exists():
            data = json.loads(RELATORIO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {
                    "candidaturas": data,
                    "ja_candidatado": [c.get("link", "") for c in data if c.get("status") == "enviado"],
                }
            return data
    return {"candidaturas": [], "ja_candidatado": []}


def salvar_relatorio(rel: dict) -> None:
    RELATORIO_FILE.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_candidatura(entry: dict) -> None:
    rel = carregar_relatorio()
    rel["candidaturas"].append(entry)
    if entry.get("status") == "enviado":
        link = entry.get("link", "")
        if link and link not in rel["ja_candidatado"]:
            rel["ja_candidatado"].append(link)
    salvar_relatorio(rel)


def candidaturas_hoje(rel: dict) -> int:
    hoje = datetime.now(TZ).strftime("%d/%m/%Y")
    return sum(
        1 for c in rel["candidaturas"]
        if c.get("site") == "Indeed" and c.get("status") == "enviado" and c.get("data") == hoje
    )


# ═══════════════════════════════════════════════════════════════
#  DRIVER E SESSÃO
# ═══════════════════════════════════════════════════════════════

def _encontrar_brave() -> str | None:
    """Encontra o executável do Brave no sistema."""
    import platform
    sistema = platform.system()
    candidatos = []

    if sistema == "Windows":
        candidatos = [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
    elif sistema == "Darwin":
        candidatos = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    else:
        candidatos = ["/usr/bin/brave-browser", "/usr/bin/brave"]

    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    return None


def _novo_driver() -> Driver:
    brave = _encontrar_brave()
    if brave:
        log_info(f"  🦁 Usando Brave: {brave}")
        driver = Driver(uc=True, binary_location=brave)
    else:
        log_warn("  Brave não encontrado — usando Chrome")
        driver = Driver(uc=True)
    driver.maximize_window()
    return driver


# Arquivo separado para cookies do Google (anti-captcha)
GOOGLE_SESSION_FILE = Path("google_session.pkl")


def salvar_sessao(driver: Driver) -> None:
    """Salva cookies do Indeed E do Google em arquivos separados."""
    # Cookies do Indeed
    with suppress(Exception):
        cookies_indeed = driver.get_cookies()
        SESSION_FILE.write_bytes(pickle.dumps(cookies_indeed))
        log_ok(f"  {len(cookies_indeed)} cookies Indeed salvos")

    # Cookies do Google (navega lá, coleta e volta)
    with suppress(Exception):
        url_atual = _url(driver)
        driver.uc_open_with_reconnect("https://accounts.google.com/", reconnect_time=2)
        esperar(2)
        cookies_google = driver.get_cookies()
        GOOGLE_SESSION_FILE.write_bytes(pickle.dumps(cookies_google))
        log_ok(f"  {len(cookies_google)} cookies Google salvos")
        # Volta pra onde estava
        with suppress(Exception):
            driver.uc_open_with_reconnect(url_atual, reconnect_time=2)


def _injetar_cookies(driver: Driver, url: str, cookies: list) -> None:
    """Navega para o domínio e injeta os cookies."""
    with suppress(Exception):
        driver.uc_open_with_reconnect(url, reconnect_time=2)
        esperar(1.5)
        for c in cookies:
            c.pop("sameSite", None)
            with suppress(Exception):
                driver.add_cookie(c)
        # Recarrega para aplicar
        driver.uc_open_with_reconnect(url, reconnect_time=2)
        esperar(1.5)


def _carregar_sessao_completa(driver: Driver) -> bool:
    """
    Carrega cookies do Google primeiro (para o reCAPTCHA reconhecer a conta),
    depois cookies do Indeed. Essa ordem é crítica.
    """
    sucesso = False

    # 1. Injeta cookies do Google
    if GOOGLE_SESSION_FILE.exists():
        with suppress(Exception):
            cookies_google = pickle.loads(GOOGLE_SESSION_FILE.read_bytes())
            if cookies_google:
                log_info("  Injetando cookies Google...")
                _injetar_cookies(driver, "https://accounts.google.com/", cookies_google)
                sucesso = True
                log_ok(f"  {len(cookies_google)} cookies Google injetados")

    # 2. Injeta cookies do Indeed
    if SESSION_FILE.exists():
        with suppress(Exception):
            cookies_indeed = pickle.loads(SESSION_FILE.read_bytes())
            if cookies_indeed:
                log_info("  Injetando cookies Indeed...")
                _injetar_cookies(driver, "https://br.indeed.com/", cookies_indeed)
                sucesso = True
                log_ok(f"  {len(cookies_indeed)} cookies Indeed injetados")

    return sucesso


def _esta_bloqueado(driver: Driver) -> bool:
    with suppress(Exception):
        src = driver.page_source.lower()
        return any(x in src for x in [
            "ray id", "cf-browser-verification", "challenge-form",
            "verificação de segurança", "just a moment", "enable javascript and cookies",
        ])
    return False


def _esta_logado_indeed(driver: Driver) -> bool:
    """Verifica se está logado no Indeed."""
    with suppress(Exception):
        src = driver.page_source.lower()
        url = _url(driver)
        return (
            "signin" not in url
            and "login" not in url
            and not _esta_bloqueado(driver)
            and any(x in src for x in [
                "minha conta", "my account", "perfil", "sair", "sign out",
                "upload-resume", "dashboard", "candidaturas",
            ])
        )
    return False


def fazer_login() -> Driver:
    driver = _novo_driver()

    # Tenta carregar sessão salva (Google + Indeed)
    if SESSION_FILE.exists() or GOOGLE_SESSION_FILE.exists():
        log_info("Carregando sessão salva...")
        if _carregar_sessao_completa(driver):
            # Verifica se o Indeed reconheceu o login
            driver.uc_open_with_reconnect("https://br.indeed.com/", reconnect_time=3)
            esperar(random.uniform(2, 3))
            if _esta_logado_indeed(driver):
                log_ok("Sessão carregada com sucesso!")
                return driver
            log_info("Sessão expirou — refazendo login...")

        SESSION_FILE.unlink(missing_ok=True)
        GOOGLE_SESSION_FILE.unlink(missing_ok=True)

    # Primeiro login: Google → Indeed
    print("\n" + "═" * 55)
    print("👆 PRIMEIRO LOGIN — FAÇA UMA VEZ SÓ:")
    print("   1. A página do Google vai abrir")
    print("   2. Faça login com sua conta Google")
    print("   3. Quando logado no Google, pressione ENTER")
    print("═" * 55)

    driver.uc_open_with_reconnect("https://accounts.google.com/", reconnect_time=3)
    esperar(2)
    input("   Pressione ENTER após logar no Google... ")
    esperar(1)

    # Salva cookies do Google imediatamente
    with suppress(Exception):
        cookies_google = driver.get_cookies()
        GOOGLE_SESSION_FILE.write_bytes(pickle.dumps(cookies_google))
        log_ok(f"  {len(cookies_google)} cookies Google salvos")

    # Agora abre Indeed e faz login com Google
    print("\n" + "═" * 55)
    print("   4. Agora clique em 'Entrar' no Indeed")
    print("   5. Clique em 'Continuar com o Google'")
    print("   6. Selecione sua conta (já deve aparecer logada)")
    print("   7. Quando logado no Indeed, pressione ENTER")
    print("═" * 55)

    driver.uc_open_with_reconnect("https://br.indeed.com/", reconnect_time=4)
    esperar(2)
    with suppress(Exception):
        driver.uc_gui_click_captcha()
    esperar(2)

    input("   Pressione ENTER após logar no Indeed... ")
    esperar(2)

    # Salva tudo
    salvar_sessao(driver)
    log_ok("Login concluído! Próximas execuções serão automáticas.")
    return driver


# ═══════════════════════════════════════════════════════════════
#  HELPERS SELENIUM
# ═══════════════════════════════════════════════════════════════

def _js(driver: Driver, script: str, *args: Any) -> Any:
    with suppress(WebDriverException):
        return driver.execute_script(script, *args)
    return None


def _find(driver: Driver, css: str, timeout: float = 5) -> Any | None:
    with suppress(TimeoutException, WebDriverException):
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css))
        )
    return None


def _find_visible(driver: Driver, css: str, timeout: float = 5) -> Any | None:
    with suppress(TimeoutException, WebDriverException):
        return WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css))
        )
    return None


def _all(driver: Driver, css: str) -> list:
    with suppress(WebDriverException):
        return driver.find_elements(By.CSS_SELECTOR, css)
    return []


def _click(driver: Driver, el: Any) -> bool:
    with suppress(Exception):
        _js(driver, "arguments[0].scrollIntoView({block:'center',behavior:'smooth'});", el)
        esperar(0.2)
    for attempt in [el.click, lambda: _js(driver, "arguments[0].click();", el)]:
        with suppress(ElementClickInterceptedException, ElementNotInteractableException,
                      StaleElementReferenceException, WebDriverException):
            attempt()
            return True
    return False


def _fill(driver: Driver, el: Any, text: str) -> bool:
    with suppress(Exception):
        _js(driver, "arguments[0].scrollIntoView({block:'center'});", el)

    with suppress(Exception):
        if el.get_attribute("disabled") is not None:
            _js(driver, "arguments[0].removeAttribute('disabled');", el)
            esperar(0.1)

    with suppress(Exception):
        _js(driver, """
            var el = arguments[0];
            var proto = el.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            if (setter) { setter.call(el, ''); }
            else { el.value = ''; }
            el.dispatchEvent(new Event('input',  {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, el)
        esperar(0.1)

    with suppress(Exception):
        el.click()
        esperar(0.1)
        el.send_keys(Keys.CONTROL + "a")
        el.send_keys(Keys.DELETE)
        esperar(0.1)

    if text == "":
        return True

    with suppress(Exception):
        _js(driver, """
            var el = arguments[0], val = arguments[1];
            var proto = el.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            if (setter) { setter.call(el, val); }
            else { el.value = val; }
            el.dispatchEvent(new Event('focus',  {bubbles:true}));
            el.dispatchEvent(new Event('input',  {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            el.dispatchEvent(new Event('blur',   {bubbles:true}));
        """, el, text)
        esperar(0.2)
        val = (el.get_attribute("value") or "").strip()
        if val == text.strip():
            return True

    with suppress(Exception):
        current = (el.get_attribute("value") or "").strip()
        if current:
            el.click()
            el.send_keys(Keys.CONTROL + "a")
            el.send_keys(Keys.DELETE)
            esperar(0.1)
        el.send_keys(text)
        return True

    return False


def _txt(el: Any) -> str:
    with suppress(Exception):
        return el.text.strip()
    return ""


def _url(driver: Driver) -> str:
    with suppress(Exception):
        return driver.current_url
    return ""


def _src(driver: Driver) -> str:
    with suppress(Exception):
        return driver.page_source
    return ""


def _scroll_suave(driver: Driver) -> None:
    _js(driver, f"window.scrollBy({{top:{random.randint(200,500)},behavior:'smooth'}})")
    esperar(0.5)


# ═══════════════════════════════════════════════════════════════
#  LABEL DE CAMPO
# ═══════════════════════════════════════════════════════════════

def _campo_visivel(driver: Driver, el: Any) -> bool:
    try:
        visivel = _js(driver, """
            (function(el) {
                if (!el) return false;
                var node = el;
                while (node && node !== document.body) {
                    var s = window.getComputedStyle(node);
                    if (s.display === 'none') return false;
                    if (s.visibility === 'hidden') return false;
                    node = node.parentElement;
                }
                return true;
            })(arguments[0])
        """, el)
        if visivel is None:
            return True
        return bool(visivel)
    except Exception:
        return True


_LABEL_SCRIPT = r"""
(function(el) {
    function limpar(t) {
        return (t || '').replace(/\s*\*\s*$/, '').replace(/\s+/g, ' ').trim();
    }
    var container = el.closest('.ia-Questions-item')
                  || el.closest('[data-testid^="input-q_"]')
                  || el.closest('[data-testid]');

    if (container) {
        var sms = container.querySelectorAll('span[data-testid="safe-markup"]');
        for (var i = 0; i < sms.length; i++) {
            var t = limpar(sms[i].innerText);
            if (t && t.length > 3) return t;
        }
        var leg = container.querySelector('legend');
        if (leg) {
            var t = limpar(leg.innerText);
            if (t && t.length > 3) return t;
        }
        var lbls = container.querySelectorAll('label');
        for (var i = 0; i < lbls.length; i++) {
            var clone = lbls[i].cloneNode(true);
            clone.querySelectorAll('[id*="error"],[id*="helper"],input,textarea,select').forEach(function(e){e.remove();});
            var t = limpar(clone.innerText);
            if (t && t.length > 3) return t;
        }
    }

    var lby = el.getAttribute('aria-labelledby');
    if (lby) {
        var parts = lby.split(' ').map(function(id) {
            var e = document.getElementById(id);
            return e ? limpar(e.innerText) : '';
        }).filter(function(t){ return t && t.length > 2 && !t.match(/^[\s*]+$/); });
        if (parts.length) return parts.join(' ');
    }

    if (el.id) {
        var lb = document.querySelector('label[for="' + el.id + '"]');
        if (lb) {
            var sm = lb.querySelector('span[data-testid="safe-markup"]');
            if (sm) return limpar(sm.innerText);
            return limpar(lb.innerText);
        }
    }

    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
})(arguments[0])
"""

_LABEL_RADIO_GROUP_SCRIPT = r"""
(function(name) {
    function limpar(t) {
        return (t || '').replace(/\s*\*\s*$/, '').replace(/\s+/g, ' ').trim();
    }
    var r = document.querySelector('input[type="radio"][name="' + name + '"]');
    if (!r) return '';

    var container = r.closest('.ia-Questions-item')
                  || r.closest('[data-testid^="input-q_"]')
                  || r.closest('[data-testid]');

    if (container) {
        var sms = container.querySelectorAll('span[data-testid="safe-markup"]');
        for (var i = 0; i < sms.length; i++) {
            var t = limpar(sms[i].innerText);
            if (t && t.length > 3) return t;
        }
        var leg = container.querySelector('legend');
        if (leg) {
            var t = limpar(leg.innerText);
            if (t && t.length > 3) return t;
        }
        var lbl = container.querySelector('label[id*="label"]');
        if (lbl) {
            var sm2 = lbl.querySelector('span[data-testid="safe-markup"]');
            if (sm2) return limpar(sm2.innerText);
            return limpar(lbl.innerText);
        }
        var anyLbl = container.querySelector('label');
        if (anyLbl) {
            var clone = anyLbl.cloneNode(true);
            clone.querySelectorAll('input,textarea,[id*="error"]').forEach(function(e){e.remove();});
            var t = limpar(clone.innerText);
            if (t && t.length > 3) return t;
        }
    }
    return '';
})(arguments[0])
"""

_LABEL_RADIO_OPTION_SCRIPT = r"""
(function(inputId) {
    function limpar(t) {
        return (t || '').replace(/\s+/g, ' ').trim();
    }
    var l = document.querySelector('label[for="' + inputId + '"]');
    if (!l) {
        var inp = document.getElementById(inputId);
        if (inp) {
            var p = inp.parentElement;
            if (p && p.tagName === 'LABEL') {
                var clone = p.cloneNode(true);
                clone.querySelectorAll('input').forEach(function(e){e.remove();});
                return limpar(clone.innerText);
            }
        }
        return inputId;
    }
    var spans = l.querySelectorAll('span');
    for (var i = spans.length - 1; i >= 0; i--) {
        var t = limpar(spans[i].innerText);
        if (t && t.length > 0 && !t.match(/^\s*$/)) return t;
    }
    var clone = l.cloneNode(true);
    clone.querySelectorAll('input').forEach(function(e){e.remove();});
    return limpar(clone.innerText);
})(arguments[0])
"""

def obter_label(driver: Driver, el: Any) -> str:
    result = _js(driver, _LABEL_SCRIPT, el)
    return (result or "").strip()


# ═══════════════════════════════════════════════════════════════
#  CAPTCHA
# ═══════════════════════════════════════════════════════════════

_CAPTCHA_IFRAME_SCRIPT = """
(function() {
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = (iframes[i].src || iframes[i].getAttribute('src') || '').toLowerCase();
        if (src.indexOf('recaptcha') !== -1 || src.indexOf('hcaptcha') !== -1
            || src.indexOf('captcha') !== -1) {
            return 'iframe:' + src.substring(0, 80);
        }
    }
    var selectors = [
        'div.g-recaptcha', 'div[data-sitekey]',
        'div.h-captcha', '[data-recaptcha]',
        '#recaptcha', '.recaptcha-container',
        'iframe[title*="reCAPTCHA"]', 'iframe[title*="recaptcha"]',
    ];
    for (var j = 0; j < selectors.length; j++) {
        if (document.querySelector(selectors[j])) {
            return 'div:' + selectors[j];
        }
    }
    var scripts = document.querySelectorAll('script[src]');
    for (var k = 0; k < scripts.length; k++) {
        var s = (scripts[k].src || '').toLowerCase();
        if (s.indexOf('recaptcha') !== -1 || s.indexOf('hcaptcha') !== -1) {
            return 'script:' + s.substring(0, 80);
        }
    }
    return null;
})()
"""

_CAPTCHA_RESOLVED_SCRIPT = """
(function() {
    var token = document.querySelector('textarea#g-recaptcha-response');
    if (token && token.value && token.value.length > 20) {
        return 'token:ok';
    }
    var iframes = document.querySelectorAll('iframe');
    var captchaIframe = false;
    for (var i = 0; i < iframes.length; i++) {
        var src = (iframes[i].src || '').toLowerCase();
        if (src.indexOf('recaptcha') !== -1 || src.indexOf('hcaptcha') !== -1) {
            captchaIframe = true;
            break;
        }
    }
    if (!captchaIframe) {
        var hasDiv = document.querySelector('div.g-recaptcha, div[data-sitekey], div.h-captcha');
        if (!hasDiv) return 'iframe_gone:ok';
    }
    var submitBtns = document.querySelectorAll('button[type="submit"], button[data-testid*="submit"]');
    for (var j = 0; j < submitBtns.length; j++) {
        if (!submitBtns[j].disabled && submitBtns[j].offsetParent !== null) {
            return 'submit_enabled:ok';
        }
    }
    return null;
})()
"""

def tem_captcha(driver: Driver) -> bool:
    with suppress(Exception):
        resultado = _js(driver, _CAPTCHA_IFRAME_SCRIPT)
        if resultado:
            log_info(f"  🔒 Captcha detectado via JS: {resultado[:60]}")
            return True
    with suppress(Exception):
        src = driver.page_source.lower()
        if any(m in src for m in ["i'm not a robot", "não sou um robô", "data-sitekey"]):
            return True
    return False


def _captcha_foi_resolvido(driver: Driver) -> bool:
    with suppress(Exception):
        sinal = _js(driver, _CAPTCHA_RESOLVED_SCRIPT)
        if sinal:
            return True
    return False


def aguardar_resolucao_captcha(driver: Driver, timeout: int = 240) -> bool:
    url_inicial = _url(driver)

    # Tenta resolver automaticamente com SeleniumBase
    with suppress(Exception):
        driver.uc_gui_click_captcha()
        esperar(3)
        if _captcha_foi_resolvido(driver) or verificar_enviada(driver):
            log_ok("  ✅ Captcha resolvido automaticamente pelo SeleniumBase!")
            return True

    # Se não resolveu, aguarda intervenção manual
    print("\n" + "═" * 60)
    print("🔒 CAPTCHA DETECTADO — INTERVENÇÃO NECESSÁRIA")
    print("─" * 60)
    print("   1. Resolva o captcha no navegador")
    print("   2. O bot continuará AUTOMATICAMENTE após detecção")
    print(f"   ⏳ Aguardando até {timeout}s...")
    print("═" * 60)

    for elapsed in range(timeout):
        time.sleep(1)
        with suppress(Exception):
            url_atual = _url(driver)
            if url_atual != url_inicial and "review" not in url_atual.lower():
                log_ok(f"  ✅ Captcha: URL mudou → {url_atual[:60]}")
                esperar(1.5)
                return True
            if _captcha_foi_resolvido(driver):
                log_ok(f"  ✅ Captcha resolvido em {elapsed+1}s")
                esperar(1.5)
                return True
            if verificar_enviada(driver):
                log_ok("  ✅ Candidatura enviada automaticamente após captcha!")
                return True
        if elapsed % 20 == 19:
            log_warn(f"  ⏳ Aguardando resolução... ({elapsed+1}/{timeout}s)")

    log_err(f"  ❌ Timeout: captcha não resolvido em {timeout}s — abortando vaga")
    return False


# ═══════════════════════════════════════════════════════════════
#  POPUPS E MODAIS
# ═══════════════════════════════════════════════════════════════

_TEXTOS_DESCARTAR = ["descartar", "discard", "leave", "sair sem salvar", "exit without saving"]

def fechar_popup_saida(driver: Driver) -> bool:
    for btn in _all(driver, "button"):
        with suppress(Exception):
            txt = _txt(btn).lower()
            if any(t in txt for t in _TEXTOS_DESCARTAR):
                _click(driver, btn)
                esperar(0.5)
                return True
    return False


def fechar_modais(driver: Driver) -> None:
    seletores = [
        "button[aria-label='fechar']",
        "button[aria-label='close']",
        "button[aria-label='Close']",
        "[data-testid='modal-close-button']",
    ]
    for sel in seletores:
        el = _find(driver, sel, timeout=1)
        if el:
            _click(driver, el)
            esperar(0.3)


# ═══════════════════════════════════════════════════════════════
#  DETECÇÃO TIPO CANDIDATURA
# ═══════════════════════════════════════════════════════════════

_INDEED_APPLY_SELECTORS = [
    "[data-testid='indeedApply']",
    "[data-indeed-apply-widget]",
    "[data-indeed-apply-jk]",
    "#indeedApplyButton",
    "[data-testid='indeedApplyButton-test']",
    ".ia-IndeedApplyButton",
]

def detectar_tipo_candidatura(driver: Driver) -> str:
    for sel in _INDEED_APPLY_SELECTORS:
        if _find(driver, sel, timeout=2):
            return "indeed_apply"
    src = _src(driver)
    if any(x in src for x in [
        "Candidate-se facilmente", "indeedApply",
        "ia-IndeedApplyButton", "data-indeed-apply-widget",
    ]):
        return "indeed_apply"
    if "site da empresa" in src.lower():
        return "site_empresa"
    return "nenhum"


# ═══════════════════════════════════════════════════════════════
#  BUSCA DE VAGAS
# ═══════════════════════════════════════════════════════════════

def extrair_vagas(driver: Driver, url: str) -> list[dict]:
    vagas: list[dict] = []
    with suppress(Exception):
        driver.get(url)
        esperar(random.uniform(3, 5))
        fechar_modais(driver)
        _scroll_suave(driver)

        cards = []
        for sel in [
            "[data-testid='slider_item']",
            ".job_seen_beacon",
            "td.resultContent",
            ".resultContent",
        ]:
            cards = _all(driver, sel)
            if cards:
                break

        if not cards:
            log_info("  Nenhum card de vaga encontrado nesta página")
            return []

        log_info(f"  {len(cards)} cards encontrados")

        for card in cards:
            try:
                jk = ""
                for link in card.find_elements(By.CSS_SELECTOR, "a[href*='jk=']"):
                    m = re.search(r"jk=([a-zA-Z0-9]+)", link.get_attribute("href") or "")
                    if m:
                        jk = m.group(1)
                        break
                if not jk:
                    els = card.find_elements(By.CSS_SELECTOR, "[data-jk]")
                    if els:
                        jk = els[0].get_attribute("data-jk") or ""
                if not jk:
                    continue

                titulo = ""
                for sel in [
                    f"span[id='jobTitle-{jk}']",
                    "span[id*='jobTitle']",
                    "h2 a span[title]",
                    "h2 span[title]",
                    "h2 a span",
                    "h2",
                ]:
                    els = card.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        t = els[0].get_attribute("title") or _txt(els[0])
                        if t.strip():
                            titulo = t.strip()
                            break
                if not titulo:
                    continue

                empresa = "Empresa não informada"
                for sel in [
                    "[data-testid='company-name']",
                    ".companyName",
                    "[class*='companyName']",
                ]:
                    els = card.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        t = _txt(els[0])
                        if t:
                            empresa = t
                            break

                local = ""
                for sel in [
                    "[data-testid='text-location']",
                    ".companyLocation",
                    "[class*='companyLocation']",
                ]:
                    els = card.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        local = _txt(els[0])
                        break

                html_card = card.get_attribute("innerHTML") or ""
                interna = any(x in html_card for x in [
                    "Candidate-se facilmente", "indeedApply", "iaIcon",
                ])

                vagas.append({
                    "titulo": titulo,
                    "empresa": empresa,
                    "local": local,
                    "url": f"https://br.indeed.com/viewjob?jk={jk}",
                    "job_key": jk,
                    "candidatura_interna": interna,
                    "data_coleta": datetime.now().isoformat(),
                })

            except (StaleElementReferenceException, WebDriverException):
                continue
            except Exception:
                continue

    return vagas


def filtrar_vaga(titulo: str) -> bool:
    t = titulo.lower()
    for excluir in PALAVRAS_EXCLUIR:
        if excluir in t:
            log_skip(f"Excluída (palavra bloqueada): {titulo}")
            return False
    termos_aceitos = [
        "desenvolvedor", "developer", "programador", "python", "react",
        "django", "php", "javascript", "frontend", "backend", "fullstack",
        "full stack", "web", "software", "sistemas", "júnior", "junior",
        "dev", "estagiário", "estágio",
    ]
    if any(x in t for x in termos_aceitos):
        return True
    log_skip(f"Sem termo relevante: {titulo}")
    return False


# ═══════════════════════════════════════════════════════════════
#  PREENCHIMENTO DE FORMULÁRIO
# ═══════════════════════════════════════════════════════════════

def _clicar_radio_react(driver: Driver, el: Any) -> bool:
    _js(driver, "arguments[0].scrollIntoView({block:'center'});", el)
    esperar(0.2)
    with suppress(Exception):
        if el.get_attribute("disabled") is not None:
            _js(driver, "arguments[0].removeAttribute('disabled');", el)
    with suppress(Exception):
        rid = el.get_attribute("id") or ""
        if rid:
            label = _js(driver, f'return document.querySelector(\'label[for="{rid}"]\');')
            if label:
                _js(driver, "arguments[0].click();", label)
                esperar(0.3)
                if el.is_selected():
                    return True
    with suppress(Exception):
        _js(driver, """
            var el = arguments[0];
            var ev = new MouseEvent('click', {bubbles:true, cancelable:true, view:window});
            el.dispatchEvent(ev);
        """, el)
        esperar(0.3)
        if el.is_selected():
            return True
    with suppress(Exception):
        el.click()
        esperar(0.3)
        if el.is_selected():
            return True
    with suppress(Exception):
        ActionChains(driver).move_to_element(el).click().perform()
        esperar(0.3)
        return True
    return False


_TERMOS_NASCIMENTO = [
    "nascimento", "data de nascimento", "data nasc", "nasc.",
    "birth", "date of birth", "birthday", "born", "birth date",
    "aniversário", "aniversario",
]

_TERMOS_DATA_INICIO = [
    "quando pode começar", "data de início", "início", "inicio",
    "start date", "when can you start", "disponibilidade para início",
    "disponibilidade de início", "data início",
]


def _is_date_field(el: Any, label_hint: str = "") -> bool:
    with suppress(Exception):
        tipo = (el.get_attribute("type") or "").lower()
        ph   = (el.get_attribute("placeholder") or "").upper()
        eid  = (el.get_attribute("id") or "").lower()
        return (
            tipo == "date"
            or "DD/MM" in ph
            or "AAAA" in ph
            or "YYYY" in ph
            or "date-question" in eid
            or _label_eh_nascimento(label_hint)
            or _label_eh_data_inicio(label_hint)
        )
    return False


def _label_eh_nascimento(label: str) -> bool:
    """Retorna True se o label se refere a data de nascimento."""
    texto = label.lower()
    return any(t in texto for t in _TERMOS_NASCIMENTO)


def _label_eh_data_inicio(label: str) -> bool:
    """Retorna True se o label se refere a data de início/disponibilidade."""
    texto = label.lower()
    return any(t in texto for t in _TERMOS_DATA_INICIO)


def _formatar_data_para_input(driver: Driver, el: Any, valor_ddmmaaaa: str) -> bool:
    """
    Preenche um input de data com o valor fornecido no formato DD/MM/AAAA.
    Tenta múltiplas estratégias para cobrir type=date e type=text.
    """
    _js(driver, "arguments[0].scrollIntoView({block:'center'});", el)
    esperar(0.3)

    tipo = (el.get_attribute("type") or "").lower()

    # Para input[type='date'], o valor aceito pelo setter é AAAA-MM-DD
    if tipo == "date":
        partes = valor_ddmmaaaa.split("/")
        valor_iso = f"{partes[2]}-{partes[1]}-{partes[0]}" if len(partes) == 3 else valor_ddmmaaaa

        # Estratégia 1: setter nativo React-friendly
        with suppress(Exception):
            _js(driver, """
                var el=arguments[0], v=arguments[1];
                el.scrollIntoView({block:'center'}); el.focus();
                var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                s.call(el, v);
                ['input','change','blur'].forEach(function(t){
                    el.dispatchEvent(new Event(t,{bubbles:true}));
                });
            """, el, valor_iso)
            esperar(0.4)
            if (el.get_attribute("value") or "").strip():
                return True

        # Estratégia 2: ActionChains com o valor ISO
        with suppress(Exception):
            ac = ActionChains(driver)
            ac.click(el).perform()
            esperar(0.15)
            ac.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
            esperar(0.1)
            ac.send_keys(Keys.DELETE).perform()
            esperar(0.1)
            for ch in valor_iso:
                ac.send_keys(ch).perform()
                esperar(0.03)
            ac.send_keys(Keys.TAB).perform()
            esperar(0.4)
            if (el.get_attribute("value") or "").strip():
                return True

        # Estratégia 3: send_keys com formato DD/MM/AAAA (alguns browsers aceitam)
        with suppress(Exception):
            el.click()
            el.send_keys(Keys.CONTROL + "a")
            el.send_keys(Keys.DELETE)
            esperar(0.1)
            el.send_keys(valor_ddmmaaaa)
            el.send_keys(Keys.TAB)
            esperar(0.4)
            if (el.get_attribute("value") or "").strip():
                return True

        return False

    else:
        # Campo de texto comum com máscara de data
        # Estratégia 1: setter
        with suppress(Exception):
            _js(driver, """
                var el=arguments[0], v=arguments[1];
                el.scrollIntoView({block:'center'}); el.focus();
                var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                s.call(el, v);
                ['input','change','blur'].forEach(function(t){
                    el.dispatchEvent(new Event(t,{bubbles:true}));
                });
            """, el, valor_ddmmaaaa)
            esperar(0.4)
            if (el.get_attribute("value") or "").strip():
                return True

        # Estratégia 2: ActionChains dígito a dígito
        with suppress(Exception):
            ac = ActionChains(driver)
            ac.click(el).perform()
            esperar(0.15)
            ac.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
            esperar(0.1)
            ac.send_keys(Keys.DELETE).perform()
            esperar(0.1)
            for ch in valor_ddmmaaaa:
                ac.send_keys(ch).perform()
                esperar(0.04)
            ac.send_keys(Keys.TAB).perform()
            esperar(0.4)
            if (el.get_attribute("value") or "").strip():
                return True

        return False


def _preencher_data(driver: Driver, el: Any, label: str) -> bool:
    """
    Preenche campo de data detectando automaticamente se é nascimento ou data de início.
    - Nascimento → usa data_nascimento do CANDIDATO
    - Qualquer outra data → usa a data de hoje
    """
    if _label_eh_nascimento(label):
        val = CANDIDATO.get("data_nascimento", "")
        log_info(f"    Data NASCIMENTO '{label[:50]}' → '{val}'")
    else:
        val = datetime.now(TZ).strftime("%d/%m/%Y")
        log_info(f"    Data INÍCIO/OUTRO '{label[:50]}' → '{val}'")

    if not val:
        log_err(f"    Data: valor vazio para '{label[:50]}'")
        return False

    ok = _formatar_data_para_input(driver, el, val)
    if ok:
        log_ok(f"    Data preenchida '{label[:50]}' → '{val}'")
    else:
        log_err(f"    Data FALHOU '{label[:50]}'")
    return ok


def preencher_campos(
    driver: Driver,
    titulo: str,
    empresa: str,
    descricao: str,
) -> None:
    """
    Extrai todos os campos e resolve via regras + IA.
    Levanta _PerguntaFiliacaoDetectada se detectar campo de mãe/pai.
    Levanta _FormularioEmIngles se o formulário estiver predominantemente em inglês.
    """
    ctx = f"Cargo: {titulo} | Empresa: {empresa} | {descricao[:200]}"

    campos_ia:     list[dict]       = []
    elementos:     dict[str, tuple] = {}
    nomes_vistos:  set[str]         = set()
    campos_vistos: set[str]         = set()

    _habilitado = False
    for _t in range(30):
        esperar(0.5)
        try:
            els = driver.find_elements(By.CSS_SELECTOR,
                ".ia-Questions-item input:not([disabled]), "
                ".ia-Questions-item textarea:not([disabled])"
            )
            if els:
                _habilitado = True
                break
        except Exception:
            pass
    if not _habilitado:
        log_warn("  ⚠️ Campos ainda desabilitados após 15s — tentando mesmo assim")

    esperar(0.5)

    containers = _all(driver, ".ia-Questions-item")
    if not containers:
        containers = _all(driver, "[data-testid^='input-q_']")
    if not containers:
        containers = [driver.find_element(By.TAG_NAME, "main")] if _find(driver, "main", timeout=2) else []

    log_info(f"  {len(containers)} container(s) de pergunta encontrados")

    with suppress(Exception):
        _js(driver, "window.scrollTo(0, document.body.scrollHeight);")
        esperar(0.5)
        _js(driver, "window.scrollTo(0, 0);")
        esperar(0.3)

    for container in containers:
        lbl_container = ""

        try:
            for sm in container.find_elements(By.CSS_SELECTOR, 'span[data-testid="safe-markup"]'):
                t = " ".join((sm.get_attribute("textContent") or "").split()).rstrip("*").strip()
                if t and len(t) > 2:
                    lbl_container = t
                    break

            if not lbl_container:
                with suppress(Exception):
                    wrapper = container.find_element(By.CSS_SELECTOR, '[data-testid^="input-q_"]')
                    testid = wrapper.get_attribute("data-testid") or ""
                    if testid:
                        lbl_span = container.find_element(By.CSS_SELECTOR, f'[data-testid="{testid}-label"]')
                        t = " ".join((lbl_span.get_attribute("textContent") or "").split()).rstrip("*").strip()
                        if t and len(t) > 2:
                            lbl_container = t

            if not lbl_container:
                with suppress(Exception):
                    legend = container.find_element(By.TAG_NAME, "legend")
                    t = " ".join((legend.get_attribute("textContent") or "").split()).rstrip("*").strip()
                    if t and len(t) > 2:
                        lbl_container = t

            if lbl_container and _contem_pergunta_filiacao(lbl_container):
                raise _PerguntaFiliacaoDetectada(
                    f"Label de container com filiação: '{lbl_container[:80]}'"
                )

            log_info(f"  [lbl]: {repr(lbl_container[:80]) if lbl_container else '(VAZIO)'}")

            # ── FALLBACK ESPECIAL: label de data sem input convencional ──
            # Se o container tem label de data (nascimento, início, etc.) mas
            # nenhum input será capturado pelos seletores normais,
            # tenta encontrar e preencher qualquer input diretamente agora.
            if lbl_container and (_label_eh_nascimento(lbl_container) or _label_eh_data_inicio(lbl_container)):
                todos_inputs_container = container.find_elements(By.CSS_SELECTOR, "input")
                for inp in todos_inputs_container:
                    with suppress(Exception):
                        inp_name = inp.get_attribute("name") or ""
                        inp_type = (inp.get_attribute("type") or "text").lower()
                        if inp_type in ("radio", "checkbox", "submit", "button", "hidden"):
                            continue
                        if not _campo_visivel(driver, inp):
                            continue
                        log_info(f"    [DATA-FALLBACK] label='{lbl_container[:50]}' type={inp_type}")
                        _preencher_data(driver, inp, lbl_container)
                        if inp_name:
                            campos_vistos.add(inp_name)
                        break  # apenas o primeiro input útil do container

            for el in container.find_elements(By.CSS_SELECTOR,
                "input[type='text'],input[type='email'],input[type='tel'],"
                "input[type='number'],input[type='url'],input[type='date']"
            ):
                with suppress(Exception):
                    name = el.get_attribute("name") or ""
                    if not name or name in campos_vistos:
                        continue
                    if not _campo_visivel(driver, el):
                        continue

                    if _is_date_field(el, lbl_container):
                        campos_vistos.add(name)
                        lbl = lbl_container or obter_label(driver, el) or "Data de início"
                        log_info(f"    [DATA] '{lbl[:60]}'")
                        _preencher_data(driver, el, lbl)
                        continue

                    lbl = lbl_container or obter_label(driver, el) or name

                    if _contem_pergunta_filiacao(lbl):
                        raise _PerguntaFiliacaoDetectada(
                            f"Campo de texto com filiação: '{lbl[:80]}'"
                        )

                    campos_vistos.add(name)
                    log_info(f"    [TEXTO] '{lbl[:70]}'")
                    cid = f"t_{len(campos_ia)}"
                    campos_ia.append({"id": cid, "tipo": "texto", "pergunta": lbl, "opcoes": []})
                    elementos[cid] = ("texto", el, name)

            for el in container.find_elements(By.CSS_SELECTOR, "textarea"):
                with suppress(Exception):
                    name = el.get_attribute("name") or el.get_attribute("id") or ""
                    if name in campos_vistos:
                        continue
                    if not _campo_visivel(driver, el):
                        continue
                    lbl = lbl_container or obter_label(driver, el) or name

                    if _contem_pergunta_filiacao(lbl):
                        raise _PerguntaFiliacaoDetectada(
                            f"Textarea com filiação: '{lbl[:80]}'"
                        )

                    if name:
                        campos_vistos.add(name)
                    log_info(f"    [TEXTAREA] '{lbl[:70]}'")
                    cid = f"ta_{len(campos_ia)}"
                    campos_ia.append({"id": cid, "tipo": "texto", "pergunta": lbl, "opcoes": []})
                    elementos[cid] = ("textarea", el, name)

            for radio in container.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
                with suppress(Exception):
                    name = radio.get_attribute("name") or ""
                    if not name or name in nomes_vistos:
                        continue
                    if not _campo_visivel(driver, radio):
                        continue
                    nomes_vistos.add(name)

                    lbl_grupo = lbl_container or (_js(driver, _LABEL_RADIO_GROUP_SCRIPT, name) or "").strip() or name

                    if _contem_pergunta_filiacao(lbl_grupo):
                        raise _PerguntaFiliacaoDetectada(
                            f"Radio group com filiação: '{lbl_grupo[:80]}'"
                        )

                    log_info(f"    [RADIO] '{lbl_grupo[:70]}'")

                    opcoes: list[dict] = []
                    for r in container.find_elements(
                        By.CSS_SELECTOR, f"input[type='radio'][name='{name}']"
                    ):
                        with suppress(Exception):
                            rid = r.get_attribute("id") or ""
                            val = r.get_attribute("value") or ""

                            # Tenta extrair label visível via script JS
                            txt = (_js(driver, _LABEL_RADIO_OPTION_SCRIPT, rid) or "").strip()

                            # Se o script retornou o próprio ID (React garbage) ou vazio,
                            # tenta estratégias alternativas
                            if not txt or txt == rid or re.search(r":r[0-9a-z]+[p]?:", txt):
                                # Estratégia 2: aria-label no próprio input
                                txt = (r.get_attribute("aria-label") or "").strip()

                            if not txt or re.search(r":r[0-9a-z]+[p]?:", txt):
                                # Estratégia 3: label[for=rid] via Selenium direto
                                with suppress(Exception):
                                    lbl_el = container.find_element(
                                        By.CSS_SELECTOR, f"label[for='{rid}']"
                                    )
                                    # Clona sem inputs para pegar só o texto
                                    t = _js(driver, """
                                        var l = arguments[0].cloneNode(true);
                                        l.querySelectorAll('input,svg,span[class*="icon"]').forEach(function(e){e.remove();});
                                        return (l.innerText || l.textContent || '').replace(/\\s+/g,' ').trim();
                                    """, lbl_el)
                                    if t and not re.search(r":r[0-9a-z]+[p]?:", t):
                                        txt = t.strip()

                            if not txt or re.search(r":r[0-9a-z]+[p]?:", txt):
                                # Estratégia 4: usar o value do input como label (limpo)
                                # Ex: value="Masculino" → texto "Masculino"
                                txt = val.strip()

                            if not txt or re.search(r":r[0-9a-z]+[p]?:", txt):
                                # Último recurso: pula essa opção
                                log_warn(f"      [RADIO OPT] ID={rid} — label ilegível, pulando opção")
                                continue

                            opcoes.append({"el": r, "texto": txt, "value": val})

                    if not opcoes:
                        continue

                    cid = f"r_{len(campos_ia)}"
                    campos_ia.append({
                        "id": cid,
                        "tipo": "radio",
                        "pergunta": lbl_grupo,
                        "opcoes": [o["texto"] for o in opcoes],
                    })
                    elementos[cid] = ("radio", opcoes, name)

            for sel_el in container.find_elements(By.CSS_SELECTOR, "select"):
                with suppress(Exception):
                    name = sel_el.get_attribute("name") or ""
                    if name in campos_vistos:
                        continue
                    if not _campo_visivel(driver, sel_el):
                        continue
                    if name:
                        campos_vistos.add(name)

                    lbl = lbl_container or obter_label(driver, sel_el) or name

                    if _contem_pergunta_filiacao(lbl):
                        raise _PerguntaFiliacaoDetectada(
                            f"Select com filiação: '{lbl[:80]}'"
                        )

                    opts = sel_el.find_elements(By.TAG_NAME, "option")
                    validas = [
                        {"value": o.get_attribute("value"), "texto": _txt(o)}
                        for o in opts
                        if (o.get_attribute("value") or "")
                        and _txt(o).lower() not in [
                            "selecione uma opção", "select an option",
                            "selecione", "select", "",
                        ]
                    ]
                    if not validas:
                        continue
                    log_info(f"    [SELECT] '{lbl[:70]}'")
                    cid = f"s_{len(campos_ia)}"
                    campos_ia.append({
                        "id": cid,
                        "tipo": "select",
                        "pergunta": lbl,
                        "opcoes": [o["texto"] for o in validas],
                    })
                    elementos[cid] = ("select", sel_el, validas)

            for cb in container.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
                with suppress(Exception):
                    name = cb.get_attribute("name") or ""
                    if not name or name in nomes_vistos:
                        continue
                    if not _campo_visivel(driver, cb):
                        continue
                    nomes_vistos.add(name)

                    lbl_grupo = lbl_container or ""
                    if not lbl_grupo:
                        try:
                            fieldset = cb.find_element(By.XPATH, "ancestor::fieldset[1]")
                            legend = fieldset.find_element(By.TAG_NAME, "legend")
                            lbl_grupo = _txt(legend).strip()
                        except Exception:
                            lbl_grupo = name

                    if _contem_pergunta_filiacao(lbl_grupo):
                        raise _PerguntaFiliacaoDetectada(
                            f"Checkbox com filiação: '{lbl_grupo[:80]}'"
                        )

                    log_info(f"    [CHECKBOX] '{lbl_grupo[:70]}'")

                    opcoes_cb: list[dict] = []
                    for c_el in container.find_elements(
                        By.CSS_SELECTOR, f"input[type='checkbox'][name='{name}']"
                    ):
                        with suppress(Exception):
                            cid_el = c_el.get_attribute("id") or ""
                            val_cb = c_el.get_attribute("value") or ""

                            # Estratégia 1: script JS
                            txt_cb = (_js(driver, _LABEL_RADIO_OPTION_SCRIPT, cid_el) or "").strip()

                            # Estratégia 2: aria-label
                            if not txt_cb or re.search(r":r[0-9a-z]+[p]?:", txt_cb):
                                txt_cb = (c_el.get_attribute("aria-label") or "").strip()

                            # Estratégia 3: label[for=id] via Selenium
                            if not txt_cb or re.search(r":r[0-9a-z]+[p]?:", txt_cb):
                                with suppress(Exception):
                                    lbl_el = container.find_element(
                                        By.CSS_SELECTOR, f"label[for='{cid_el}']"
                                    )
                                    t = _js(driver, """
                                        var l = arguments[0].cloneNode(true);
                                        l.querySelectorAll('input,svg,span[class*="icon"]').forEach(function(e){e.remove();});
                                        return (l.innerText || l.textContent || '').replace(/\\s+/g,' ').trim();
                                    """, lbl_el)
                                    if t and not re.search(r":r[0-9a-z]+[p]?:", t):
                                        txt_cb = t.strip()

                            # Estratégia 4: value como fallback
                            if not txt_cb or re.search(r":r[0-9a-z]+[p]?:", txt_cb):
                                txt_cb = val_cb.strip()

                            if not txt_cb or re.search(r":r[0-9a-z]+[p]?:", txt_cb):
                                continue

                            opcoes_cb.append({"el": c_el, "texto": txt_cb, "value": val_cb})

                    if not opcoes_cb:
                        continue

                    cid = f"cb_{len(campos_ia)}"
                    campos_ia.append({
                        "id":      cid,
                        "tipo":    "checkbox",
                        "pergunta": lbl_grupo,
                        "opcoes":  [o["texto"] for o in opcoes_cb],
                    })
                    elementos[cid] = ("checkbox", opcoes_cb, name)

        except (_PerguntaFiliacaoDetectada, _FormularioEmIngles):
            raise

        except Exception:
            continue

    if not campos_ia:
        log_info("  Nenhum campo dinâmico detectado")
        return

    log_info(f"  {len(campos_ia)} campo(s) → chamando IA...")

    # ia_processar_formulario já faz a checagem de idioma internamente
    respostas = ia_processar_formulario(campos_ia, ctx)

    if not respostas:
        log_warn("  IA retornou vazio")
        return

    for campo in campos_ia:
        cid  = campo["id"]
        resp = respostas.get(cid)

        if resp is None:
            log_warn(f"    Sem resposta para '{campo['pergunta'][:50]}'")
            continue

        info = elementos.get(cid)
        if not info:
            continue

        tipo_el = info[0]

        with suppress(StaleElementReferenceException, WebDriverException, Exception):

            if tipo_el in ("texto", "textarea"):
                el  = info[1]
                val = str(resp).strip()

                if not val or val.upper() == "PULAR":
                    log_info(f"    ⬜ '{campo['pergunta'][:50]}' → [pulado]")
                    continue

                if not el.is_displayed():
                    continue

                _fill(driver, el, val)
                log_ok(f"    ✍ '{campo['pergunta'][:50]}' → '{val[:60]}'")
                esperar(0.2)

            elif tipo_el == "radio":
                opcoes = info[1]
                try:
                    idx = int(resp)
                    if 0 <= idx < len(opcoes):
                        opt_el = opcoes[idx]["el"]
                        _clicar_radio_react(driver, opt_el)
                        log_ok(f"    🔘 '{campo['pergunta'][:50]}' → {idx}: '{opcoes[idx]['texto'][:40]}'")
                except (ValueError, TypeError) as exc:
                    log_warn(f"    Radio erro: {exc} | resp={resp!r}")

            elif tipo_el == "select":
                sel_el  = info[1]
                validas = info[2]
                try:
                    idx = int(resp)
                    if 0 <= idx < len(validas):
                        _js(driver, "arguments[0].scrollIntoView({block:'center'});", sel_el)
                        Select(sel_el).select_by_value(validas[idx]["value"])
                        log_ok(f"    📋 '{campo['pergunta'][:50]}' → {idx}: '{validas[idx]['texto'][:40]}'")
                        esperar(0.25)
                except (ValueError, TypeError) as exc:
                    log_warn(f"    Select erro: {exc} | resp={resp!r}")

            elif tipo_el == "checkbox":
                opcoes_cb = info[1]
                if resp is None or resp == [] or (isinstance(resp, list) and len(resp) == 0):
                    log_info(f"    ☐ '{campo['pergunta'][:50]}' → [nenhum marcado]")
                    continue

                indices_a_marcar: list[int] = []

                if isinstance(resp, list):
                    for item in resp:
                        with suppress(Exception):
                            indices_a_marcar.append(int(item))
                elif isinstance(resp, str) and resp.strip().upper() != "PULAR":
                    # IA pode ter retornado texto livre descrevendo as opções corretas
                    # Tenta mapear por número primeiro
                    nums = re.findall(r"\b(\d+)\b", resp)
                    for n in nums:
                        idx = int(n)
                        if 0 <= idx < len(opcoes_cb):
                            indices_a_marcar.append(idx)
                    # Se não achou números válidos, tenta match por texto
                    if not indices_a_marcar:
                        resp_lower = resp.lower()
                        for j, opt in enumerate(opcoes_cb):
                            if opt["texto"].lower() in resp_lower or resp_lower in opt["texto"].lower():
                                indices_a_marcar.append(j)
                elif isinstance(resp, (int, float)):
                    idx = int(resp)
                    if 0 <= idx < len(opcoes_cb):
                        indices_a_marcar.append(idx)

                if not indices_a_marcar:
                    log_info(f"    ☐ '{campo['pergunta'][:50]}' → [sem índices válidos]")
                    continue

                for idx in indices_a_marcar:
                    with suppress(Exception):
                        if 0 <= idx < len(opcoes_cb):
                            _click(driver, opcoes_cb[idx]["el"])
                            log_ok(f"    ☑ '{campo['pergunta'][:50]}' → [{idx}] '{opcoes_cb[idx]['texto'][:40]}'")
                            esperar(0.2)


# ═══════════════════════════════════════════════════════════════
#  NAVEGAÇÃO POR ETAPAS
# ═══════════════════════════════════════════════════════════════

def _clicar_botao_texto(driver: Driver, *textos: str, excluir: list[str] | None = None) -> bool:
    excluir = excluir or []
    for btn in _all(driver, "button"):
        with suppress(Exception):
            txt = _txt(btn).lower()
            if not txt:
                continue
            if any(e in txt for e in excluir):
                continue
            if any(t.lower() in txt for t in textos):
                if _click(driver, btn):
                    esperar(random.uniform(1.5, 2.5))
                    return True
    return False


_CONTINUAR_TEXTOS  = ["continuar", "continue", "próximo", "next",
                      "salvar e continuar", "save and continue", "avançar", "advance",
                      "verificar candidatura", "verificar sua candidatura",
                      "review your application", "review application"]
_CONTINUAR_EXCLUIR = ["fechar", "close", "exit", "sair", "salvar e fechar",
                      "save and close", "voltar", "back", "cancelar", "cancel",
                      "ver descrição", "ver menos", "ver mais", "descrição completa",
                      "show more", "show less", "see more", "see less",
                      "denunciar", "report", "compartilhar", "share"]


def clicar_continuar(driver: Driver) -> bool:
    """
    Tenta clicar no botão de continuar/próximo com múltiplas estratégias.
    Garante estar fora de qualquer iframe antes de buscar.
    """
    # Sempre volta ao contexto principal primeiro
    with suppress(Exception):
        driver.switch_to.default_content()

    # Estratégia 1: botão por texto visível
    if _clicar_botao_texto(driver, *_CONTINUAR_TEXTOS, excluir=_CONTINUAR_EXCLUIR):
        return True

    # Estratégia 2: data-testid conhecido do Indeed
    for testid in [
        "[data-testid='continue-button']",
        "[data-testid='submit-button']",
        "[data-testid='NextButton']",
        "[data-testid='continueButton']",
        "[data-testid='questions-next-button']",
        "[data-testid='ia-continueButton']",
        "button[type='submit']",
    ]:
        el = _find(driver, testid, timeout=1)
        if el and el.is_displayed():
            txt = _txt(el).lower()
            if any(e in txt for e in _CONTINUAR_EXCLUIR):
                continue
            if _click(driver, el):
                log_info("  [continuar] clicou via data-testid")
                esperar(random.uniform(1.5, 2.5))
                return True

    # Estratégia 3: último botão visível e habilitado da página
    with suppress(Exception):
        _EXCLUIR_JS = ["fechar", "close", "voltar", "back", "cancelar", "cancel",
                       "ver descrição", "ver menos", "ver mais", "descrição completa",
                       "show more", "show less", "see more", "see less",
                       "denunciar", "report", "compartilhar", "share", "sair", "exit"]
        botoes = [
            b for b in _all(driver, "button")
            if b.is_displayed()
            and b.is_enabled()
            and not any(e in (_txt(b) or "").lower() for e in _EXCLUIR_JS)
            and (_txt(b) or "").strip() != ""
        ]
        if botoes:
            ultimo = botoes[-1]
            txt_ultimo = (_txt(ultimo) or "").lower()
            palavras_acao = ["continuar", "continue", "próximo", "next",
                             "avançar", "enviar", "submit", "salvar", "save",
                             "verificar candidatura", "verificar sua candidatura",
                             "review"]
            if any(p in txt_ultimo for p in palavras_acao):
                if _click(driver, ultimo):
                    log_info(f"  [continuar] clicou último botão: '{txt_ultimo[:40]}'")
                    esperar(random.uniform(1.5, 2.5))
                    return True

    # Estratégia 4: JS — clica no primeiro button[type=submit] ou último button válido
    clicou = _js(driver, """
        var EXCLUIR = ['fechar','close','voltar','back','cancelar','cancel',
                       'ver descrição','ver menos','ver mais','descrição completa',
                       'show more','show less','see more','see less',
                       'denunciar','report','compartilhar','share','sair','exit'];
        function deveExcluir(txt) {
            for (var i = 0; i < EXCLUIR.length; i++) {
                if (txt.indexOf(EXCLUIR[i]) >= 0) return true;
            }
            return false;
        }
        // Tenta button[type=submit] primeiro
        var btns = document.querySelectorAll('button[type="submit"]');
        for (var i = 0; i < btns.length; i++) {
            var b = btns[i];
            var txt = (b.innerText || b.textContent || '').toLowerCase().trim();
            if (b.offsetParent !== null && !deveExcluir(txt)) {
                b.click();
                return 'submit:' + txt;
            }
        }
        // Último button visível não excluído
        var all = document.querySelectorAll('button');
        var visible = [];
        for (var i = 0; i < all.length; i++) {
            var b = all[i];
            var txt = (b.innerText || b.textContent || '').toLowerCase().trim();
            if (b.offsetParent !== null && txt && !deveExcluir(txt)) {
                visible.push({el: b, txt: txt});
            }
        }
        if (visible.length > 0) {
            var last = visible[visible.length - 1];
            last.el.click();
            return 'last:' + last.txt;
        }
        return null;
    """)

    if clicou:
        log_info(f"  [continuar] clicou via JS: '{clicou}'")
        esperar(random.uniform(1.5, 2.5))
        return True

    # Estratégia 5: resgate semântico — o LLM lê a página viva (snapshot
    # compacto) e escolhe o botão que avança. Só roda se 1–4 falharam, então
    # o happy path não ganha latência; em página redesenhada, ganha resiliência.
    el = pagelens.achar(
        driver,
        seletores=[],  # estratégias 1–4 já testaram os conhecidos
        objetivo=("o botão que AVANÇA para o próximo passo do formulário de "
                  "candidatura (ex.: 'Continuar', 'Next', 'Apply', 'Review application'). "
                  "NUNCA 'Voltar', 'Back', 'Fechar', 'Cancel', 'Salvar e fechar' ou 'Ver mais'."),
        regras=perfil.perfil_compacta(CONFIG, limite=220),
        chamar=lambda prompt, max_tokens=260: chamar_llm(
            [{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.05),
        log=log_info,
    )
    if el is not None and _click(driver, el):
        log_info("  [continuar] clicou via resgate semântico (o LLM leu a página)")
        esperar(random.uniform(1.5, 2.5))
        return True

    return False


def etapa_curriculo(driver: Driver) -> None:
    log_info("  📄 Etapa: Currículo")
    for sel in [
        "label[for*='upload']",
        "label[for*='file']",
        "input[type='radio'][value*='upload']",
    ]:
        el = _find(driver, sel, timeout=2)
        if el:
            _click(driver, el)
            esperar(0.5)
            break
    fi = _find(driver, "input[type='file']", timeout=3)
    if fi:
        with suppress(Exception):
            fi.send_keys(CURRICULO_PDF)
            esperar(3)
            log_ok("    PDF enviado")
    else:
        log_warn("    input[type='file'] não encontrado")
    clicar_continuar(driver)


def etapa_perguntas(driver: Driver, titulo: str, empresa: str, descricao: str) -> None:
    log_info("  ❓ Etapa: Perguntas")
    esperar(1.5)
    preencher_campos(driver, titulo, empresa, descricao)
    esperar(1.5)
    fechar_popup_saida(driver)
    clicar_continuar(driver)


def etapa_carta(driver: Driver, carta: str) -> None:
    log_info("  ✍️  Etapa: Carta de apresentação (additional-documents)")
    esperar(1.0)

    for sel in [
        "[data-testid='cover-letter-radio-card']",
        "label[for*='cover-letter']",
        "input[value*='cover-letter']",
        "input[value*='coverLetter']",
    ]:
        el = _find(driver, sel, timeout=2)
        if el:
            _click(driver, el)
            esperar(0.8)
            break
    else:
        _clicar_botao_texto(driver, "escrever uma carta", "write a cover letter", "carta de apresentação")
        esperar(0.8)

    ta = _find(driver, "textarea[data-testid='cover-letter-radio-card-text-area']", timeout=4)
    if not ta:
        ta = _find(driver, "textarea[aria-label*='carta']", timeout=2)
    if not ta:
        ta = _find(driver, "textarea", timeout=3)

    if ta:
        _js(driver, "arguments[0].scrollIntoView({block:'center'});", ta)
        esperar(0.3)
        _fill(driver, ta, carta)
        log_ok(f"    Carta inserida ({len(carta)} chars)")
    else:
        log_warn("    textarea de carta não encontrado")

    clicar_continuar(driver)
    esperar(1.5)


def _switch_to_apply_iframe(driver: Driver) -> bool:
    with suppress(Exception):
        driver.switch_to.default_content()
    for sel in [
        "iframe[title*='candidatura']",
        "iframe[title*='application']",
        "iframe[data-testid='application-preview']",
        "iframe[name*='indeed']",
        "iframe[src*='smartapply']",
        "iframe[src*='indeedapply']",
        "iframe",
    ]:
        iframes = _all(driver, sel)
        for iframe in iframes:
            with suppress(Exception):
                if "srcdoc" in (iframe.get_attribute("outerHTML") or "").lower():
                    continue
                driver.switch_to.frame(iframe)
                if _find(driver, "[data-testid]", timeout=1):
                    return True
                driver.switch_to.default_content()
    return False


def _inserir_carta_na_revisao(driver: Driver, carta: str) -> bool:
    log_info("  📎 Tentando inserir carta via 'Documentos de apoio'...")

    with suppress(Exception):
        driver.switch_to.default_content()

    clicou = _js(driver, """
        var secao = document.querySelector("[data-testid='supportingDocumentsSection']");
        if (secao) {
            var conteudo = (secao.getAttribute("data-contents") || "").toLowerCase();
            if (conteudo !== "empty" && conteudo !== "") return "ja_preenchido:" + conteudo;
            var btn = secao.querySelector("a[aria-label='Adicionar documentos de apoio']")
                   || secao.querySelector("a[aria-label*='Adicionar']")
                   || secao.querySelector("a[role='button']");
            if (btn) { btn.click(); return "clicou_dom_principal"; }
        }
        return null;
    """)

    if clicou == "clicou_dom_principal":
        log_ok("    Clicou 'Adicionar' no DOM principal — aguardando...")
        esperar(2.5)
        url_now = _url(driver)
        if any(x in url_now for x in ["additional-documents", "cover-letter", "resume-module"]):
            log_ok("    Navegou para additional-documents")
            etapa_carta(driver, carta)
            esperar(2.0)
            return True

    if clicou and str(clicou).startswith("ja_preenchido:"):
        log_info("    Documentos de apoio já preenchidos — pulando")
        return True

    log_info("    DOM principal sem seção — tentando via contentDocument do iframe srcdoc...")

    clicou2 = _js(driver, """
        var iframes = document.querySelectorAll('iframe[data-testid="application-preview"]');
        for (var i = 0; i < iframes.length; i++) {
            try {
                var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                if (!doc) continue;
                var secao = doc.querySelector("[data-testid='supportingDocumentsSection']");
                if (!secao) continue;
                var conteudo = (secao.getAttribute("data-contents") || "").toLowerCase();
                if (conteudo !== "empty" && conteudo !== "") return "ja_preenchido:" + conteudo;
                var btn = secao.querySelector("a[aria-label='Adicionar documentos de apoio']")
                       || secao.querySelector("a[aria-label*='Adicionar']")
                       || secao.querySelector("a[role='button']");
                if (btn) { btn.click(); return "clicou_srcdoc"; }
            } catch(e) { continue; }
        }
        return null;
    """)

    if clicou2 == "clicou_srcdoc":
        log_ok("    Clicou 'Adicionar' via contentDocument do srcdoc — aguardando...")
        esperar(2.5)
        url_now = _url(driver)
        if any(x in url_now for x in ["additional-documents", "cover-letter", "resume-module"]):
            log_ok("    Navegou para additional-documents")
            etapa_carta(driver, carta)
            esperar(2.0)
            return True
        ta = _find(driver, "textarea", timeout=3)
        if ta:
            log_ok("    Textarea detectado após clique srcdoc — preenchendo carta")
            etapa_carta(driver, carta)
            esperar(2.0)
            return True

    if clicou2 and str(clicou2).startswith("ja_preenchido:"):
        log_info("    Documentos de apoio já preenchidos (srcdoc) — pulando")
        return True

    log_info("    Tentando switch_to.frame no application-preview...")
    iframe_el = _find(driver, "iframe[data-testid='application-preview']", timeout=3)
    if iframe_el:
        with suppress(Exception):
            driver.switch_to.frame(iframe_el)
            esperar(0.5)

            secao_el = _find(driver, "[data-testid='supportingDocumentsSection']", timeout=3)
            if secao_el:
                conteudo = secao_el.get_attribute("data-contents") or ""
                if conteudo.lower() not in ("empty", ""):
                    log_info("    Documentos já preenchidos (frame) — pulando")
                    driver.switch_to.default_content()
                    return True

                for sel in [
                    "a[aria-label='Adicionar documentos de apoio']",
                    "a[aria-label*='Adicionar']",
                    "a[role='button']",
                ]:
                    btn_el = _find(driver, sel, timeout=2)
                    if btn_el:
                        _click(driver, btn_el)
                        driver.switch_to.default_content()
                        log_ok("    Clicou 'Adicionar' via switch_to.frame — aguardando...")
                        esperar(2.5)
                        url_now = _url(driver)
                        if any(x in url_now for x in ["additional-documents", "cover-letter", "resume-module"]):
                            log_ok("    Navegou para additional-documents")
                            etapa_carta(driver, carta)
                            esperar(2.0)
                            return True
                        ta = _find(driver, "textarea", timeout=3)
                        if ta:
                            etapa_carta(driver, carta)
                            esperar(2.0)
                            return True
                        break

            driver.switch_to.default_content()

    log_warn("    Todas as estratégias falharam — carta não inserida nesta vaga")
    return False


def _encontrar_btn_submit(driver: Driver) -> Any | None:
    with suppress(Exception):
        btns = _all(driver, "button[data-testid]")
        for btn in btns:
            testid = btn.get_attribute("data-testid") or ""
            txt = _txt(btn).lower()
            if len(testid) > 30 and txt in ("continuar", "enviar", "submit", "continue"):
                if btn.is_displayed() and btn.is_enabled():
                    return btn

    _ENVIAR  = ["enviar sua candidatura", "enviar candidatura",
                "submit application", "submit your application",
                "enviar", "submit"]
    _EXCLUIR = ["fechar", "close", "sair", "salvar e fechar", "save and close", "voltar", "back"]

    for btn in _all(driver, "button"):
        with suppress(Exception):
            txt = _txt(btn).lower()
            if not txt or not btn.is_displayed():
                continue
            if any(e in txt for e in _EXCLUIR):
                continue
            if any(t in txt for t in _ENVIAR):
                return btn

    with suppress(Exception):
        btns_visiveis = [
            b for b in _all(driver, "button")
            if b.is_displayed() and b.is_enabled()
            and _txt(b).strip()
            and not any(e in _txt(b).lower() for e in _EXCLUIR)
        ]
        if btns_visiveis:
            return btns_visiveis[-1]

    return None


def _clicar_submit_com_retry(driver: Driver, tentativas: int = 3) -> bool:
    url_antes = _url(driver)

    for t in range(tentativas):
        btn = _encontrar_btn_submit(driver)
        if not btn:
            log_warn(f"  Submit: botão não encontrado (tentativa {t+1})")
            esperar(1.5)
            continue

        txt_btn = _txt(btn)
        log_info(f"  Submit: tentando clicar '{txt_btn}' (tentativa {t+1})")

        _js(driver, "arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", btn)
        esperar(0.5)

        clicou = False
        with suppress(Exception):
            btn.click()
            clicou = True
        if not clicou:
            with suppress(Exception):
                _js(driver, "arguments[0].click();", btn)
                clicou = True
        if not clicou:
            with suppress(Exception):
                ActionChains(driver).move_to_element(btn).click().perform()
                clicou = True

        if not clicou:
            log_warn("  Submit: nenhuma estratégia de clique funcionou")
            continue

        esperar(3)

        if verificar_enviada(driver):
            return True

        url_depois = _url(driver)
        if url_depois != url_antes:
            log_info(f"  Submit: URL mudou → {url_depois[:60]}")
            return True

        log_warn(f"  Submit: clicou mas página não mudou (tentativa {t+1})")
        esperar(2)

    return False


def _comportamento_humano_pre_submit(driver: Driver) -> None:
    """
    Simula comportamento humano antes de clicar em enviar:
    scroll lento pela página, pequenas pausas, movimento de mouse.
    Reduz chance de trigger do reCAPTCHA.
    """
    with suppress(Exception):
        # Scroll suave até o topo
        _js(driver, "window.scrollTo({top: 0, behavior: 'smooth'});")
        esperar(random.uniform(0.8, 1.5))

        # Scroll lento até o meio
        _js(driver, "window.scrollTo({top: document.body.scrollHeight/2, behavior: 'smooth'});")
        esperar(random.uniform(1.0, 2.0))

        # Scroll até o final (onde fica o botão enviar)
        _js(driver, "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
        esperar(random.uniform(0.8, 1.5))

    # Movimento de mouse aleatório via ActionChains
    with suppress(Exception):
        ac = ActionChains(driver)
        # Move para pontos aleatórios da tela
        for _ in range(3):
            x = random.randint(200, 800)
            y = random.randint(200, 500)
            ac.move_by_offset(x // 10, y // 10).perform()
            esperar(random.uniform(0.2, 0.5))


def _aguardar_submit_habilitado(driver: Driver, timeout: int = 15) -> bool:
    """
    Aguarda o botão de submit ficar habilitado (disabled removido).
    O reCAPTCHA do Indeed desabilita o botão até ser resolvido.
    Retorna True se habilitou dentro do timeout.
    """
    for _ in range(timeout):
        time.sleep(1)
        with suppress(Exception):
            habilitado = _js(driver, """
                var btn = document.querySelector('[data-testid="submit-application-button"]')
                       || document.querySelector('button[name="submit-application"]')
                       || document.querySelector('button[type="submit"]');
                if (!btn) return null;
                return !btn.disabled && btn.offsetParent !== null;
            """)
            if habilitado:
                return True
    return False


def etapa_revisao(driver: Driver, carta: str = "") -> bool:
    log_info("  📋 Etapa: Revisão / Envio")
    esperar(2)
    fechar_popup_saida(driver)

    if carta:
        _inserir_carta_na_revisao(driver, carta)
        esperar(2.0)
        fechar_popup_saida(driver)

    # Comportamento humano antes de tentar enviar
    _comportamento_humano_pre_submit(driver)

    # Tenta resolver captcha automaticamente via SeleniumBase UC
    with suppress(Exception):
        driver.uc_gui_click_captcha()
        esperar(2)

    # Verifica se o botão está desabilitado (captcha pendente)
    btn_desabilitado = _js(driver, """
        var btn = document.querySelector('[data-testid="submit-application-button"]')
               || document.querySelector('button[name="submit-application"]');
        return btn ? btn.disabled : false;
    """)

    if btn_desabilitado:
        log_warn("  🔒 Botão submit desabilitado — tentando resolver captcha...")
        # Tenta novamente com SeleniumBase
        with suppress(Exception):
            driver.uc_gui_click_captcha()
            esperar(3)
        habilitou = _aguardar_submit_habilitado(driver, timeout=15)
        if not habilitou:
            resolveu = aguardar_resolucao_captcha(driver)
            if not resolveu:
                return False
        else:
            log_ok("  ✅ Botão submit habilitado — prosseguindo")
            esperar(0.5)

    elif tem_captcha(driver):
        log_warn("  🔒 Captcha detectado antes do envio")
        with suppress(Exception):
            driver.uc_gui_click_captcha()
            esperar(3)
        if not _captcha_foi_resolvido(driver):
            resolveu = aguardar_resolucao_captcha(driver)
            if not resolveu:
                return False
        if verificar_enviada(driver):
            log_ok("  ✅ Enviado automaticamente após captcha!")
            return True
        esperar(1)

    enviou = _clicar_submit_com_retry(driver)

    if not enviou and tem_captcha(driver):
        log_warn("  🔒 Captcha apareceu após clicar submit")
        with suppress(Exception):
            driver.uc_gui_click_captcha()
            esperar(3)
        if verificar_enviada(driver):
            log_ok("  ✅ Enviado automaticamente após captcha pós-submit!")
            return True
        resolveu = aguardar_resolucao_captcha(driver)
        if resolveu:
            if verificar_enviada(driver):
                return True
            enviou = _clicar_submit_com_retry(driver)

    return enviou


def verificar_enviada(driver: Driver) -> bool:
    with suppress(Exception):
        url = _url(driver)
        if any(x in url for x in ["post-apply", "success", "application-submitted", "applied"]):
            return True
    with suppress(Exception):
        src = driver.page_source.lower()
        sinais = [
            "inscrição foi enviada", "candidatura foi enviada",
            "application submitted", "sua candidatura foi enviada",
            "successfully applied", "application was submitted",
            "you've applied", "você se candidatou",
            "candidatura enviada", "your application has been",
        ]
        if any(x in src for x in sinais):
            return True
    with suppress(Exception):
        confirmacao = _js(driver, """
            var selectors = [
                '[data-testid*="post-apply"]', '[data-testid*="success"]',
                '[data-testid*="applied"]', '[class*="post-apply"]',
                '[class*="application-submitted"]', '.ia-PostApply',
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = document.querySelector(selectors[i]);
                if (el && el.offsetParent !== null) return selectors[i];
            }
            return null;
        """)
        if confirmacao:
            return True
    return False


# ═══════════════════════════════════════════════════════════════
#  CANDIDATURA COMPLETA
# ═══════════════════════════════════════════════════════════════

_URL_ETAPA: dict[str, str] = {
    "resume":               "curriculo",
    "question":             "perguntas",
    "review":               "revisao",
    "submit":               "revisao",
    "additional-documents": "revisao",
    "cover-letter":         "revisao",
}


def _identificar_etapa(url: str) -> str:
    url_lower = url.lower()
    for fragmento, etapa in _URL_ETAPA.items():
        if fragmento in url_lower:
            return etapa
    return "desconhecida"


def candidatar_vaga(driver: Driver, vaga: dict) -> dict:
    now = datetime.now(TZ)
    resultado: dict = {
        "vaga":      vaga["titulo"],
        "empresa":   vaga.get("empresa", ""),
        "link":      vaga["url"],
        "local":     vaga.get("local", ""),
        "site":      "Indeed",
        "status":    "erro",
        "data":      now.strftime("%d/%m/%Y"),
        "horario":   now.strftime("%H:%M:%S"),
        "curriculo": CONFIG["resumes"]["fullstack"],
    }

    log(f"\n🎯 {vaga['titulo']} — {vaga.get('empresa','')}")

    try:
        driver.uc_open_with_reconnect(vaga["url"], reconnect_time=4)
        esperar(random.uniform(2, 3))
        # Resolve qualquer captcha que apareça ao carregar a vaga
        with suppress(Exception):
            driver.uc_gui_click_captcha()

        descricao = ""
        for sel in [
            "#jobDescriptionText",
            "[data-testid='jobDescription']",
            ".jobsearch-JobComponent-description",
        ]:
            el = _find(driver, sel, timeout=3)
            if el:
                descricao = _txt(el)[:2000]
                break

        # ── REGRA v2.7: Descrição em inglês via IA → pular vaga ──
        log_info("  🌐 Verificando idioma da descrição via IA...")
        if _descricao_em_ingles(descricao):
            log_skip("  ⏭️  Descrição em inglês detectada pela IA — vaga ignorada")
            resultado["status"] = "descricao_ingles"
            return resultado

        tipo = detectar_tipo_candidatura(driver)
        if tipo == "site_empresa":
            log_skip("  Candidatura via site da empresa — pulando")
            resultado["status"] = "site_empresa"
            return resultado
        if tipo == "nenhum":
            log_skip("  Nenhum botão de candidatura encontrado — pulando")
            resultado["status"] = "sem_botao"
            return resultado

        log_info("  ✅ Indeed Apply detectado")

        carta = ia_gerar_carta(vaga["titulo"], vaga.get("empresa", ""), descricao)

        clicou = False
        for sel in [
            "#indeedApplyButton",
            "[data-testid='indeedApplyButton-test']",
            ".ia-IndeedApplyButton button",
            "[data-indeed-apply-widget] button",
        ]:
            btn = _find(driver, sel, timeout=3)
            if btn:
                if _click(driver, btn):
                    esperar(3)
                    clicou = True
                    log_ok("  Botão Indeed Apply clicado")
                    break

        if not clicou:
            clicou = _clicar_botao_texto(
                driver,
                "candidate-se facilmente", "apply now", "candidatar-se",
            )

        if not clicou:
            log_err("  Botão de candidatura não clicável")
            resultado["status"] = "botao_nao_clicavel"
            return resultado

        MAX_ITERACOES    = 20
        MAX_BLOQUEIO     = 3
        MAX_REVISAO      = 3
        revisao_count    = 0
        etapa_anterior   = ""
        repeticoes       = 0
        MAX_REPETICOES   = 4
        bloqueios_seguidos = 0

        for iteracao in range(MAX_ITERACOES):
            esperar(1.5)
            fechar_popup_saida(driver)

            # Supervisor de tela: overlay/modal bloqueando? Escalonamento
            # barato→caro: texto conhecido/captcha (SEM LLM) → LLM propõe até
            # 3 seletores (2 rodadas) → iframe/ESC. É aqui que o bot lê a tela.
            bloqueio = pagelens.tratar_bloqueio(
                driver,
                chamar=lambda prompt, max_tokens=300: chamar_llm(
                    [{"role": "user", "content": prompt}],
                    max_tokens=max_tokens, temperature=0.05),
                log=log_info,
            )
            if bloqueio["tipo"] == "fechou":
                if bloqueio["el"] is not None:
                    if _click(driver, bloqueio["el"]):
                        log_info(f"  [bloqueio] modal fechado: {bloqueio['detalhe'][:80]}")
                        esperar(1.5)
                    else:
                        log_warn(f"  [bloqueio] clique no botão falhou: {bloqueio['detalhe'][:80]}")
                else:
                    log_info(f"  [bloqueio] fechado via iframe/ESC: {bloqueio['detalhe'][:80]}")
                    esperar(1.0)
                continue  # reprocessa a etapa — o modal estava cobrindo a tela
            if bloqueio["tipo"] == "captcha":
                log_warn(f"  [bloqueio] desafio humano — aguardando resolução: {bloqueio['detalhe'][:80]}")
                if not aguardar_resolucao_captcha(driver):
                    resultado["status"] = "captcha_nao_resolvido"
                    break
                continue
            if bloqueio["detalhe"]:
                # "indeciso" ou "nada" com overlay ainda presente: sem progresso
                bloqueios_seguidos += 1
                log_warn(f"  [bloqueio] tela bloqueada ({bloqueios_seguidos} seguidas): "
                         f"{bloqueio['detalhe'][:80]}")
                if bloqueios_seguidos >= MAX_BLOQUEIO:
                    log_err("  [bloqueio] modal sem resolução após 3 tentativas — "
                            "parando a vaga (modal_nao_resolvido)")
                    resultado["status"] = "modal_nao_resolvido"
                    break
                continue
            bloqueios_seguidos = 0

            if verificar_enviada(driver):
                resultado["status"] = "enviado"
                log_ok("  ✅ Candidatura enviada com sucesso!")
                break

            url_atual = _url(driver)
            etapa     = _identificar_etapa(url_atual)

            if etapa == etapa_anterior:
                repeticoes += 1
                if repeticoes >= MAX_REPETICOES:
                    log_err(f"  Anti-loop: etapa '{etapa}' repetida {repeticoes}x — abortando")
                    resultado["status"] = "travado"
                    break
            else:
                repeticoes     = 0
                etapa_anterior = etapa

            log_info(f"  Iteração {iteracao+1}/{MAX_ITERACOES} — etapa: {etapa}")

            try:
                if etapa == "curriculo":
                    etapa_curriculo(driver)
                    if not clicar_continuar(driver):
                        log_warn("  Currículo: botão continuar não encontrado — tentando assim mesmo")
                elif etapa == "perguntas":
                    etapa_perguntas(driver, vaga["titulo"], vaga.get("empresa", ""), descricao)
                    if not clicar_continuar(driver):
                        log_warn("  Perguntas: botão continuar não encontrado — tentando assim mesmo")
                elif etapa == "revisao":
                    revisao_count += 1
                    if revisao_count > MAX_REVISAO:
                        log_err(f"  Revisão tentada {revisao_count}x sem sucesso — abortando")
                        resultado["status"] = "travado_revisao"
                        break
                    if etapa_revisao(driver, carta):
                        esperar(3)
                        if verificar_enviada(driver):
                            resultado["status"] = "enviado"
                            log_ok("  ✅ Candidatura enviada com sucesso!")
                            break
                    else:
                        log_err("  Botão enviar não clicado ou captcha não resolvido")
                        resultado["status"] = "captcha_nao_resolvido"
                        break
                elif etapa == "desconhecida":
                    if not clicar_continuar(driver):
                        log_warn("  Etapa desconhecida e sem botão continuar — abortando")
                        break

            except _PerguntaFiliacaoDetectada as exc:
                log_skip(f"  ⏭️  VAGA PULADA — pergunta de filiação detectada: {exc}")
                fechar_popup_saida(driver)
                resultado["status"] = "pergunta_filiacao"
                return resultado

            # ── REGRA v2.8: Formulário em inglês → pular vaga ──
            except _FormularioEmIngles as exc:
                log_skip(f"  ⏭️  VAGA PULADA — formulário em inglês detectado: {exc}")
                fechar_popup_saida(driver)
                resultado["status"] = "formulario_ingles"
                return resultado

        else:
            if verificar_enviada(driver):
                resultado["status"] = "enviado"
                log_ok("  ✅ Candidatura enviada (confirmação final)!")
            else:
                resultado["status"] = "incompleto"
                log_err("  Atingiu máximo de iterações sem concluir")

    except _PerguntaFiliacaoDetectada as exc:
        log_skip(f"  ⏭️  VAGA PULADA — pergunta de filiação detectada: {exc}")
        fechar_popup_saida(driver)
        resultado["status"] = "pergunta_filiacao"

    # ── REGRA v2.8: captura de topo para _FormularioEmIngles ──
    except _FormularioEmIngles as exc:
        log_skip(f"  ⏭️  VAGA PULADA — formulário em inglês detectado: {exc}")
        fechar_popup_saida(driver)
        resultado["status"] = "formulario_ingles"

    except Exception as exc:
        log_err(f"  Exceção inesperada: {exc}")
        resultado["status"] = "erro"

    return resultado


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║              🤖 JOB HUNTER — INDEED  v2.8                   ║
╚══════════════════════════════════════════════════════════════╝""")

    if not horario_ok():
        log_info("Fora do horário permitido (03h–22h).")
        return

    rel  = carregar_relatorio()
    hoje = candidaturas_hoje(rel)
    log_info(f"Candidaturas hoje: {hoje}/{MAX_POR_DIA}")

    if hoje >= MAX_POR_DIA:
        log_info("Limite diário atingido. Encerrando.")
        return

    driver = fazer_login()

    try:
        ja_candidatado: set[str] = set(rel.get("ja_candidatado", []))
        fila: list[dict]         = []

        log_info("\n🔍 Coletando vagas...")
        meta_fila = MAX_POR_DIA * 3

        for termo in PALAVRAS_CHAVE:
            if len(fila) >= meta_fila:
                break
            log(f"\n🔍 Buscando: '{termo}'")

            for pagina in range(5):
                if len(fila) >= meta_fila:
                    break
                url = (
                    f"https://br.indeed.com/jobs"
                    f"?q={termo.replace(' ','+')}&sort=date&start={pagina*10}"
                )
                vagas_pag = extrair_vagas(driver, url)
                if not vagas_pag:
                    log_info(f"  Pág {pagina+1}: sem vagas — próximo termo")
                    break

                novas = 0
                for v in vagas_pag:
                    if (
                        v["url"] not in ja_candidatado
                        and filtrar_vaga(v["titulo"])
                        and v.get("candidatura_interna", True)
                    ):
                        ja_candidatado.add(v["url"])
                        fila.append(v)
                        novas += 1

                log_info(f"  Pág {pagina+1}: +{novas} | acumulado: {len(fila)}")
                esperar(random.uniform(3, 6))

        log(f"\n📊 {len(fila)} vagas na fila")
        if not fila:
            log_info("Nenhuma vaga nova encontrada.")
            return

        log_info("\n🚀 Iniciando candidaturas...\n")
        contadores = {
            "enviado":           0,
            "site_empresa":      0,
            "sem_botao":         0,
            "pergunta_filiacao": 0,
            "descricao_ingles":  0,
            "formulario_ingles": 0,
            "erro":              0,
        }

        for i, vaga in enumerate(fila, 1):
            if hoje + contadores["enviado"] >= MAX_POR_DIA:
                log_info("Limite diário atingido — parando.")
                break

            log(f"[{i}/{len(fila)}]")
            resultado = candidatar_vaga(driver, vaga)
            registrar_candidatura(resultado)

            status = resultado["status"]
            if status == "enviado":
                contadores["enviado"] += 1
                log_info(f"  📅 Total hoje: {hoje + contadores['enviado']}/{MAX_POR_DIA}")
            elif status == "site_empresa":
                contadores["site_empresa"] += 1
            elif status in ("sem_botao", "botao_nao_clicavel"):
                contadores["sem_botao"] += 1
            elif status == "pergunta_filiacao":
                contadores["pergunta_filiacao"] += 1
            elif status == "descricao_ingles":
                contadores["descricao_ingles"] += 1
            elif status == "formulario_ingles":
                contadores["formulario_ingles"] += 1
            else:
                contadores["erro"] += 1

            if i < len(fila):
                delay = random.uniform(DELAY_VAGAS, DELAY_VAGAS + 10)
                log_info(f"  ⏳ Aguardando {delay:.0f}s antes da próxima vaga...\n")
                esperar(delay)

        total_hoje = hoje + contadores["enviado"]
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 RESUMO FINAL                          ║
╠══════════════════════════════════════════════════════════════╣
║  ✅ Enviadas esta sessão : {contadores['enviado']:<33}║
║  📅 Total hoje           : {total_hoje}/{MAX_POR_DIA:<31}║
║  ⏭️  Site da empresa      : {contadores['site_empresa']:<33}║
║  ⏭️  Sem botão apply      : {contadores['sem_botao']:<33}║
║  ⏭️  Pergunta filiação    : {contadores['pergunta_filiacao']:<33}║
║  ⏭️  Descrição em inglês  : {contadores['descricao_ingles']:<33}║
║  ⏭️  Formulário em inglês : {contadores['formulario_ingles']:<33}║
║  ❌ Erros                : {contadores['erro']:<33}║
╚══════════════════════════════════════════════════════════════╝""")

    finally:
        salvar_sessao(driver)
        with suppress(Exception):
            driver.quit()


if __name__ == "__main__":
    main()
