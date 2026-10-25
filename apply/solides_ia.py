"""Camada de IA do bot Sólides — LLM Groq (fallback HF) + perfil do candidato.

Extraído de solides.py sem mudança de comportamento:
  • Roteador chamar_llm (Groq) + _chamar_huggingface (fallback)
  • PERFIL_COMPLETO (perfil comum + extras Sólides)
  • Nível de habilidade (NIVEL_HABILIDADE + ia_nivel_habilidade)
  • Killer questions (radio/texto)

Módulo autossuficiente: re-lê config.yaml/.env no import (mesmo processo →
mesmos valores). O bot re-importa tudo via star import — os nomes no escopo
de solides.py seguem iguais para os call sites.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from common import perfil
from dotenv import load_dotenv
from groq import Groq

# ── Bootstrap autossuficiente (mesmo processo → mesmos valores do bot) ──
load_dotenv()

with open("config.yaml", encoding="utf-8") as _f:
    CONFIG: dict = yaml.safe_load(_f)

TZ               = ZoneInfo("America/Sao_Paulo")
CANDIDATO        = CONFIG["candidato"]
DIVERSIDADE      = CONFIG.get("diversidade", {})
LOCALIZACAO      = CONFIG.get("localizacao", {})
GROQ_MODEL       = CONFIG["groq"]["model"]
PALAVRAS_EXCLUIR = [p.lower() for p in CONFIG["busca"].get("palavras_excluir", [])]

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------------------------------------------------------
# Logging (cópias exatas do bot — o bot re-importa via star)
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO") -> None:
    print(f"[{_now()}] [{level}] {msg}")

def log_ok(msg: str)   -> None: log(msg, "✅")
def log_err(msg: str)  -> None: log(msg, "❌")
def log_skip(msg: str) -> None: log(msg, "⏭️ ")
def log_info(msg: str) -> None: log(msg, "ℹ️ ")
def log_warn(msg: str) -> None: log(msg, "⚠️ ")

__all__ = [
    "GROQ_MODEL",
    "NIVEL_HABILIDADE",
    "PERFIL_COMPLETO",
    "_chamar_huggingface",
    "_nivel_para_texto",
    "_now",
    "_perfil_extras_solides",
    "chamar_llm",
    "groq_client",
    "ia_nivel_habilidade",
    "ia_responder_killer_question_radio",
    "ia_responder_killer_question_texto",
    "log",
    "log_err",
    "log_info",
    "log_ok",
    "log_skip",
    "log_warn",
]

# ═══════════════════════════════════════════════════════════════
#  GROQ — LLM
# ═══════════════════════════════════════════════════════════════

def chamar_llm(prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> str:
    """Chama o Groq com fallback para HuggingFace."""
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log_warn(f"  [Groq] erro: {exc} — tentando HuggingFace")
        return _chamar_huggingface(prompt, max_tokens, temperature)


def _chamar_huggingface(prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> str:
    import urllib.error
    import urllib.request
    hf_key = os.getenv("HF_API_KEY", "")
    if not hf_key:
        raise RuntimeError("HF_API_KEY não configurada")

    hf_model = CONFIG.get("huggingface", {}).get("model", "Qwen/Qwen2.5-72B-Instruct")
    url = "https://router.huggingface.co/v1/chat/completions"
    payload = json.dumps({
        "model": hf_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": max(0.01, temperature),
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bearer {hf_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


# ═══════════════════════════════════════════════════════════════
#  PERFIL COMPLETO DO CANDIDATO (para o LLM)
# ═══════════════════════════════════════════════════════════════

def _perfil_extras_solides() -> str:
    """O que o contexto comum não cobre: valores dos select do site Sólides.
    O resto (identidade, formação, experiências, exclusões, pretensões) vem
    do perfil completo — common/perfil.py — editado na aba Perfil do Trivor."""
    pcd = DIVERSIDADE.get("pcd")
    ind = str(DIVERSIDADE.get("indicacao") or "").lower()
    return (
        "── EXTRAS SÓLIDES (valores dos select do site) ──\n"
        f"Gênero: {DIVERSIDADE.get('genero', 'Homem cisgênero')} → valor select: cisgenero\n"
        f"Orientação sexual: {DIVERSIDADE.get('orientacao_sexual', 'Heterossexual')} → valor: heterossexual\n"
        "Sexo: Masculino → valor select: male\n"
        f"PCD: {'SIM' if pcd else 'NÃO'}\n"
        f"Indicado: {'SIM' if ind and 'espont' not in ind else 'NÃO'}\n"
        "Instagram: https://www.instagram.com/gabri3l.cardoso"
    )


PERFIL_COMPLETO = (
    perfil.contexto_perfil(CONFIG)
    + "\n\n" + _perfil_extras_solides()
)


# ═══════════════════════════════════════════════════════════════
#  IA — NÍVEL DE HABILIDADE
# ═══════════════════════════════════════════════════════════════

NIVEL_HABILIDADE: dict[str, int] = {
    # Avançado
    "python": 3, "php": 3, "javascript": 3, "js": 3, "html": 3, "html5": 3,
    "css": 3, "css3": 3, "mysql": 3, "bootstrap": 3, "tailwind": 3, "tailwind css": 3,
    "api rest": 3, "api restful": 3, "rest": 3, "git": 3, "github": 3,
    "windows": 3, "programação php": 3, "performance de sites": 3,
    "segurança de sites": 2, "segurança de sites e sistemas": 2,
    # Intermediário
    "react": 2, "postgresql": 2, "django": 2, "django rest": 2, "django rest framework": 2,
    "drf": 2, "flask": 2, "typescript": 2,
    "programação de temas wordpress": 2, "programação de plugins wordpress": 2,
    "wordpress": 2,
    # Básico
    "docker": 1, "numpy": 1, "pandas": 1, "redis": 1,
    "espanhol": 1, "inglês": 2,
    # Nenhum
    ".net": 0, "c#": 0, "java": 0, "spring": 0, "c++": 0, "kotlin": 0,
    "swift": 0, "flutter": 0, "angular": 0, "vue": 0,
}


def _nivel_para_texto(nivel: int) -> str:
    return {0: "Nenhum", 1: "Básico", 2: "Intermediário", 3: "Avançado"}.get(nivel, "Nenhum")


def ia_nivel_habilidade(nome_habilidade: str, contexto_vaga: str = "") -> int:
    nome_lower = nome_habilidade.lower().strip()

    # Lista negativa: determinístico, não depende da IA — item excluído → Nenhum.
    if perfil.tech_excluida(nome_habilidade, PALAVRAS_EXCLUIR):
        log_info(f"    [HABILIDADE EXCLUÍDA] '{nome_habilidade}' → Nenhum (lista negativa)")
        return 0

    for chave, nivel in NIVEL_HABILIDADE.items():
        if chave in nome_lower or nome_lower in chave:
            log_info(f"    [HABILIDADE DIRETA] '{nome_habilidade}' → {_nivel_para_texto(nivel)}")
            return nivel

    prompt = (
        f"Você é um assistente que avalia o nível de habilidade de um candidato.\n\n"
        f"PERFIL DO CANDIDATO:\n{PERFIL_COMPLETO}\n\n"
        f"HABILIDADE A AVALIAR: '{nome_habilidade}'\n"
        f"CONTEXTO DA VAGA: {contexto_vaga[:200]}\n\n"
        f"Avalie o nível do candidato nessa habilidade.\n"
        f"Considere conhecimentos implícitos: se é algo relacionado ao que ele já sabe,\n"
        f"como 'Performance de Sites' para um dev web, pode ser avançado.\n"
        f"A LISTA DE EXCLUSÕES do perfil vale: qualquer item dela → responda 0.\n\n"
        f"Responda APENAS com um número:\n"
        f"0 = Nenhum\n"
        f"1 = Básico\n"
        f"2 = Intermediário\n"
        f"3 = Avançado\n\n"
        f"RESPOSTA (apenas o número 0, 1, 2 ou 3):"
    )
    try:
        resposta = chamar_llm(prompt, max_tokens=5, temperature=0.0).strip()
        m = re.search(r"\b([0-3])\b", resposta)
        if m:
            nivel = int(m.group(1))
            log_info(f"    [HABILIDADE IA] '{nome_habilidade}' → {_nivel_para_texto(nivel)}")
            return nivel
    except Exception as exc:
        log_warn(f"    [HABILIDADE IA] erro: {exc} — assumindo Básico")

    return 1


def ia_responder_killer_question_radio(pergunta: str) -> str:
    pergunta_lower = pergunta.lower()

    CONFIRMAR_SIM = [
        "compreende", "está ciente", "está de acordo", "concorda",
        "aceita", "tem ciência", "você sabe que", "confirma",
        "tem disponibilidade", "disponibilidade para",
        "aceita trabalhar", "disposto a",
    ]
    if any(p in pergunta_lower for p in CONFIRMAR_SIM):
        log_info("    [killer] Pergunta de confirmação → Sim")
        return "Sim"

    loc = LOCALIZACAO
    if any(p in pergunta_lower for p in ["remoto", "home office", "trabalho remoto"]):
        return "Sim" if loc.get("aceita_remoto") else "Não"
    if "híbrido" in pergunta_lower or "hibrido" in pergunta_lower:
        return "Sim" if loc.get("aceita_hibrido") else "Não"
    if "presencial" in pergunta_lower:
        return "Sim" if loc.get("aceita_presencial") else "Não"

    prompt = (
        f"Responda APENAS com 'Sim' ou 'Não' (sem mais nada).\n\n"
        f"PERFIL DO CANDIDATO:\n{PERFIL_COMPLETO}\n\n"
        f"PERGUNTA: {pergunta}\n\n"
        f"REGRAS:\n"
        f"- Responda SOMENTE com base no perfil acima (identidade, formação, exclusões)\n"
        f"- Se a pergunta pede experiência/habilidade que o candidato TEM → Sim\n"
        f"- Item da LISTA DE EXCLUSÕES do perfil → Não (nunca se apresente com ele)\n"
        f"- Se pede experiência que NÃO TEM → Não\n"
        f"- Em caso de dúvida (sem tocar em exclusão) → Sim (melhor tentar do que desistir)\n\n"
        f"RESPOSTA (apenas Sim ou Não):"
    )
    try:
        r = chamar_llm(prompt, max_tokens=5, temperature=0.0).strip()
        if "sim" in r.lower() or r.lower().startswith("s"):
            return "Sim"
        return "Não"
    except Exception:
        return "Sim"


def ia_responder_killer_question_texto(pergunta: str, contexto_vaga: str = "") -> str:
    pergunta_lower = pergunta.lower()

    if any(p in pergunta_lower for p in ["pretens", "salarial", "remuner", "expectativa", "salário"]):
        eh_pj = any(p in pergunta_lower for p in ["pj", "pessoa jurídica", "mei"])
        eh_hora = "hora" in pergunta_lower
        if eh_pj and eh_hora:
            return f"R$ {CANDIDATO.get('pretensao_pj_hora', '22')}/hora"
        elif eh_pj:
            return f"R$ {CANDIDATO.get('pretensao_pj_mensal', '4500')}/mês"
        return f"R$ {CANDIDATO.get('pretensao_clt', '3000')}"

    if any(p in pergunta_lower for p in ["indicad", "recomendad"]):
        return "Não fui indicado, candidatura espontânea."

    if any(p in pergunta_lower for p in ["deficiência", "pcd", "deficiente"]):
        return "Não possuo deficiência."

    prompt = (
        f"Responda a pergunta abaixo de forma direta e profissional em nome do candidato.\n\n"
        f"PERFIL DO CANDIDATO:\n{PERFIL_COMPLETO}\n\n"
        f"CONTEXTO DA VAGA: {contexto_vaga[:300]}\n\n"
        f"PERGUNTA: {pergunta}\n\n"
        f"REGRAS:\n"
        f"- Tom natural, profissional, direto\n"
        f"- Máximo 3 frases\n"
        f"- NÃO use frases de IA genéricas\n"
        f"- Se não tem experiência com algo, seja honesto\n"
        f"- Se pede experiência em algo que tem, mencione brevemente\n\n"
        f"RESPOSTA:"
    )
    try:
        return chamar_llm(prompt, max_tokens=200, temperature=0.4)
    except Exception:
        return "Tenho disponibilidade imediata e interesse na vaga."

