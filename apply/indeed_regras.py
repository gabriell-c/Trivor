"""Engine de regras determinísticas do formulário do Indeed.

Bloco extraído de indeed.py (zero mudança de comportamento): cópia exata das
regras + _CtxRegras + _REGRAS_DETERMINISTICAS + _resolver_por_regra.

O módulo re-lê config.yaml e o .env sensível no import (mesmo processo →
mesmos valores); o bot consome o bloco via `from indeed_regras import *`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

load_dotenv()

with open("config.yaml", encoding="utf-8") as _f:
    CONFIG: dict = yaml.safe_load(_f)
CANDIDATO = CONFIG["candidato"]
TZ = ZoneInfo("America/Sao_Paulo")

# Dados sensíveis — lidos exclusivamente do .env, nunca do config.yaml
_DOC_CPF = os.getenv("CANDIDATO_CPF", "")
_DOC_RG  = os.getenv("CANDIDATO_RG",  "")
_DOC_CNH = os.getenv("CANDIDATO_CNH", "")

_END_LOGRADOURO  = os.getenv("ENDERECO_LOGRADOURO",  "")
_END_NUMERO      = os.getenv("ENDERECO_NUMERO",      "")
_END_BAIRRO      = os.getenv("ENDERECO_BAIRRO",      "")
_END_CEP         = os.getenv("ENDERECO_CEP",         "")
_END_COMPLEMENTO = os.getenv("ENDERECO_COMPLEMENTO", "")


# ---------------------------------------------------------------------------
# Depurações da engine (cópias exatas do bot — o bot re-importa via star)
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO") -> None:
    print(f"[{_now_str()}] [{level}] {msg}")

def log_warn(msg: str) -> None:
    log(msg, "⚠️ ")

class _PerguntaFiliacaoDetectada(Exception):
    """Aborta a candidatura quando detecta campo de nome da mãe/pai."""


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
__all__ = [
    "_REGRAS_DETERMINISTICAS",
    "_TERMOS_FILIACAO",
    "_CtxRegras",
    "_PerguntaFiliacaoDetectada",
    "_contem_pergunta_filiacao",
    "_inferir_cargo_pretendido",
    "_now_str",
    "_regra_area_profissional",
    "_regra_condicional_outra",
    "_regra_condicional_outro",
    "_regra_condicoes_especiais",
    "_regra_data_nascimento",
    "_regra_estado",
    "_regra_fonte",
    "_regra_genero",
    "_regra_grupo_diversidade",
    "_regra_mapa_texto",
    "_regra_nivel_experiencia",
    "_regra_num_doc",
    "_regra_origem",
    "_regra_pais",
    "_regra_pcd",
    "_regra_pretensao_salarial",
    "_regra_raca",
    "_regra_segmento",
    "_regra_tipo_doc",
    "_regra_ultimo_segmento",
    "_resolver_por_regra",
    "log",
    "log_warn",
]




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
