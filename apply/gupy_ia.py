"""Camada de IA do bot Gupy — roteador LLM + fallbacks locais + geradores.

Extraído de gupy.py sem mudança de comportamento:
  • Roteador Groq → Gemini → Mistral → None (providores da UI vencem a cadeia)
  • Fallbacks locais determinísticos (pergunta aberta / apresentação / habilidades)
  • Geradores LLM (responder_pergunta_aberta, gerar_apresentacao,
    selecionar_habilidades_relevantes)

Design config-driven: as funções recebem `config: dict` (mesmo contrato do
bot) — não há estado global de perfil. carregar_config/log/_perfil_ctx são
cópias exatas para o módulo ser autossuficiente.
O bot re-importa tudo via star import — os call sites do gupy.py seguem intactos.
"""
from __future__ import annotations

import datetime as _dt
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from common import llm as _llm_lib
from common import perfil
from dotenv import load_dotenv

load_dotenv()  # idempotente — garante o .env antes de DADOS_PESSOAIS

__all__ = [
    "DADOS_PESSOAIS",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "_GroqLimiteDiario",
    "_agendar_retorno_groq",
    "_calcular_reset_groq",
    "_chamar_gemini",
    "_chamar_groq",
    "_chamar_llm",
    "_chamar_mistral",
    "_fallback_local_apresentacao",
    "_fallback_local_habilidades",
    "_fallback_local_pergunta_aberta",
    "_limpar_markdown",
    "_llm_state",
    "_perfil_ctx",
    "carregar_config",
    "gerar_apresentacao",
    "log",
    "responder_pergunta_aberta",
    "selecionar_habilidades_relevantes",
]

# ══════════════════════════════════════════════════════════════════════════════
#  DADOS PESSOAIS SENSÍVEIS — lidos do .env, nunca passados à LLM
#
#  Adicione ao .env:
#    CANDIDATO_NOME_PAI=Edson Cardoso
#    CANDIDATO_NOME_MAE=Alenisa Alves da Silva Cardoso
#    CANDIDATO_CPF=00000000000
#    CANDIDATO_RG=000000000
#    ENDERECO_LOGRADOURO=Rua Exemplo
#    ENDERECO_NUMERO=100
#    ENDERECO_BAIRRO=Bairro Exemplo
#    ENDERECO_CEP=00000-000
#    ENDERECO_COMPLEMENTO=
#    ENDERECO_CIDADE=Ribeirão Preto
#    ENDERECO_ESTADO=SP
# ══════════════════════════════════════════════════════════════════════════════

DADOS_PESSOAIS = {
    "cpf":         os.getenv("CANDIDATO_CPF", ""),
    "rg":          os.getenv("CANDIDATO_RG", ""),
    "nome_pai":    os.getenv("CANDIDATO_NOME_PAI", ""),
    "nome_mae":    os.getenv("CANDIDATO_NOME_MAE", ""),
    "logradouro":  os.getenv("ENDERECO_LOGRADOURO", ""),
    "numero":      os.getenv("ENDERECO_NUMERO", ""),
    "bairro":      os.getenv("ENDERECO_BAIRRO", ""),
    "cep":         os.getenv("ENDERECO_CEP", ""),
    "complemento": os.getenv("ENDERECO_COMPLEMENTO", ""),
    "cidade":      os.getenv("ENDERECO_CIDADE", "Ribeirão Preto"),
    "estado":      os.getenv("ENDERECO_ESTADO", "SP"),
}

# ══════════════════════════════════════════════════════════════════════════════
#  PERFIL DO CANDIDATO
# ══════════════════════════════════════════════════════════════════════════════

def _perfil_ctx(config: dict) -> str:
    """Contexto completo do candidato (common/perfil.py) — injetado nos prompts.

    Substitui o bloco estático antigo: agora a IA enxerga TUDO que o usuário
    mantém na aba Perfil do Trivor (config.yaml + .env), incluindo a lista de
    exclusões (busca.palavras_excluir) com regras de resposta obrigatórias.
    """
    return perfil.contexto_perfil(config)



def carregar_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)



def log(msg: str):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M:%S")
    print(f"[{agora}] {msg}")



# ══════════════════════════════════════════════════════════════════════════════
#  LLM ROUTER — Groq → Gemini → Mistral → fallback local
#
#  Cascata:
#    1. Groq          — primário, rápido, sem crédito mensal (só rate limit diário)
#       · Rate limit curto (< 5min) → aguarda e retenta automaticamente (até 4x)
#       · Rate limit diário         → passa para Gemini até meia-noite UTC
#    2. Gemini 2.5 Flash-Lite — 1.000 req/dia, 15 RPM, retry automático de RPM
#    3. Mistral Small — ~1 bilhão tokens/mês no free tier
#    4. None          — fallback local (funções estáticas)
#
#  Variáveis de ambiente (.env):
#    GROQ_API_KEY    — console.groq.com
#    GEMINI_API_KEY  — aistudio.google.com
#    MISTRAL_API_KEY — console.mistral.ai
# ══════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

_llm_state = {
    "provedor":      "groq",
    "groq_reset_em": None,
    "lock":          threading.Lock(),
}


_GroqLimiteDiario = _llm_lib.GroqLimiteDiario
_calcular_reset_groq = _llm_lib.calcular_reset_groq


def _agendar_retorno_groq(reset_utc: _dt.datetime) -> None:
    def _voltar():
        agora  = _dt.datetime.now(_dt.UTC)
        espera = max(0, (reset_utc - agora).total_seconds()) + 15
        log(f"  [LLM] Groq volta em {int(espera / 60)}min "
            f"({reset_utc.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M')} local)")
        time.sleep(espera)
        with _llm_state["lock"]:
            _llm_state["provedor"]      = "groq"
            _llm_state["groq_reset_em"] = None
        log("  [LLM] ✅ Groq reativado automaticamente!")
    threading.Thread(target=_voltar, daemon=True).start()


_limpar_markdown = _llm_lib.limpar_markdown


def _chamar_groq(prompt: str, config: dict, temperatura: float = 0.5,
                 max_tokens: int = 500, tentativas: int = 4) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada")
    return _llm_lib.limpar_markdown(_llm_lib.chamar_groq(
        [{"role": "user", "content": prompt}],
        model=config["groq"]["model"],
        api_key=GROQ_API_KEY,
        log_info=lambda m: log(f"  [LLM] ⚡ {m}"),
        max_tokens=max_tokens,
        temperature=temperatura,
        tentativas=tentativas,
    ))


def _chamar_gemini(prompt: str, temperatura: float = 0.5,
                   max_tokens: int = 500, tentativas: int = 4) -> str:
    """
    Gemini 2.5 Flash-Lite via REST.
    Plano free: 1.000 req/dia, 15 RPM.
    429 RPM → retry progressivo. 429 cota diária → abandona imediatamente.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")

    texto = _llm_lib.limpar_markdown(_llm_lib.chamar_gemini(
        prompt,
        api_key=GEMINI_API_KEY,
        log_info=lambda m: log(f"  [LLM] ⚡ {m}"),
        modelo="gemini-2.0-flash",
        temperatura=temperatura,
        max_output_tokens=max_tokens,
        tentativas=tentativas,
    ))
    log(f"  [LLM Gemini] ✅ ({len(texto)} chars)")
    return texto


def _chamar_mistral(prompt: str, temperatura: float = 0.5,
                    max_tokens: int = 500) -> str:
    """Mistral Small via API oficial. Plano free: ~1 bilhão tokens/mês."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY não configurada")

    texto = _llm_lib.chamar_mistral(
        prompt,
        api_key=MISTRAL_API_KEY,
        temperatura=temperatura,
        max_tokens=max_tokens,
    )
    log(f"  [LLM Mistral] ✅ (resposta: {texto[:60]!r})")
    return texto


def _chamar_llm(prompt: str, config: dict, contexto: str = "",
                temperatura: float = 0.5, max_tokens: int = 500) -> str | None:
    """Roteador LLM: provedores da UI (config → ia) → Groq → Gemini → Mistral → None."""
    sufixo = f" ({contexto})" if contexto else ""

    with _llm_state["lock"]:
        provedor = _llm_state["provedor"]

    # ── 0. Provedores configurados pela UI do Trivor (config.yaml → ia) ─────
    # Vencem a cadeia antiga: quem define base_url + api_key + modelo no
    # painel escolhe o LLM. A cadeia .env abaixo segue como fallback.
    from common import llm as llm_ui
    for prov in llm_ui.providers_ativos(config):
        try:
            resultado = llm_ui.chat(prov, prompt, temperatura, max_tokens)
            log(f"  [LLM {prov.get('nome', prov.get('id'))}] ✅{sufixo} ({len(resultado)} chars)")
            return resultado
        except Exception as exc:
            log(f"  [LLM] ❌ Provedor {prov.get('id')} falhou{sufixo}: {exc}")

    # ── 1. Groq ───────────────────────────────────────────────────────────────
    if provedor == "groq":
        try:
            resultado = _chamar_groq(prompt, config, temperatura, max_tokens)
            log(f"  [LLM Groq] ✅{sufixo} ({len(resultado)} chars)")
            return resultado
        except _GroqLimiteDiario:
            reset_utc = _calcular_reset_groq()
            with _llm_state["lock"]:
                _llm_state["provedor"]      = "gemini"
                _llm_state["groq_reset_em"] = reset_utc
            log(f"  [LLM] 🔴 Groq limite diário{sufixo} → trocando para Gemini")
            _agendar_retorno_groq(reset_utc)
        except Exception as exc:
            log(f"  [LLM] ❌ Groq erro{sufixo}: {exc} → tentando Gemini")

    # ── 2. Gemini ─────────────────────────────────────────────────────────────
    try:
        return _chamar_gemini(prompt, temperatura, max_tokens)
    except Exception as exc:
        log(f"  [LLM] ❌ Gemini falhou{sufixo}: {exc} → tentando Mistral")

    # ── 3. Mistral ────────────────────────────────────────────────────────────
    try:
        return _chamar_mistral(prompt, temperatura, max_tokens)
    except Exception as exc:
        log(f"  [LLM] ❌ Mistral falhou{sufixo}: {exc} → usando fallback local")

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  FALLBACKS LOCAIS
# ══════════════════════════════════════════════════════════════════════════════

def _fallback_local_pergunta_aberta(pergunta: str, contexto_vaga: str = "") -> str:
    """
    Fallback local para perguntas abertas quando todas as APIs falham.
    Analisa keywords da pergunta e retorna resposta baseada no perfil real.
    """
    p = pergunta.lower()
    v = contexto_vaga.lower()

    if any(x in p for x in ["conhecimento", "habilidade", "skill", "tecnologia",
                             "experiência técnica", "domina", "sabe"]):
        return ("Tenho experiência sólida com Python, Django e React para desenvolvimento "
                "full stack, além de PHP, JavaScript, MySQL e APIs RESTful. Trabalho com "
                "Git, Docker e autenticação JWT em projetos reais desde 2022.")

    if any(x in p for x in ["por que", "porque", "motivação", "interesse na vaga",
                             "o que te atrai", "o que te motivou"]):
        return ("Busco minha primeira experiência CLT para crescer como desenvolvedor em "
                "ambiente colaborativo. A vaga se alinha com meu stack atual e quero "
                "contribuir com o que já desenvolvi como freelancer.")

    if any(x in p for x in ["experiência profissional", "trajetória", "carreira",
                             "fale sobre você", "conte sobre você", "se apresente"]):
        return ("Atuo como desenvolvedor web freelancer desde novembro de 2022, com foco "
                "em Python/Django, PHP e React. Desenvolvi sistemas de e-commerce, APIs "
                "RESTful, chatbots com IA e aplicações financeiras. Cursando Engenharia "
                "de Software na Estácio.")

    if any(x in p for x in ["formação", "escolaridade", "curso", "graduação",
                             "faculdade", "universidade"]):
        return "Engenharia de Software (cursando, 1º semestre) — Estácio de Sá, EAD."

    if any(x in p for x in ["pretens", "salari", "remuner", "expectativa salarial"]):
        if any(x in v for x in ["estágio", "estagio", "trainee"]):
            return "R$ 1.600"
        return "R$ 3.000"

    if any(x in p for x in ["horário", "turno", "período", "disponibilidade de horário"]):
        return "Tenho disponibilidade integral — manhã, tarde e noite."

    if any(x in p for x in ["cidade", "local", "deslocamento", "mora", "reside"]):
        return "Moro em Ribeirão Preto/SP e aceito remoto, híbrido ou presencial."

    if any(x in p for x in ["diferencial", "ponto forte", "o que te diferencia",
                             "por que te contratar"]):
        return ("Meu diferencial é entregar soluções completas de forma autônoma — do "
                "banco de dados à interface — com código limpo e foco em resultado. "
                "Tenho experiência real com IA, automação e APIs escaláveis.")

    if any(x in p for x in ["projeto", "portfólio", "o que já fez", "o que desenvolveu"]):
        return ("Desenvolvi um chatbot com IA (Python/Django) que automatizou 80% do "
                "atendimento, um sistema financeiro completo (React/PHP/Docker) e uma "
                "API RESTful de e-commerce com JWT. Portfolio: portfolio--gabriel.vercel.app")

    if any(x in p for x in ["inglês", "ingles", "idioma", "english"]):
        return "Inglês básico — consigo ler documentação técnica sem dificuldade."

    if any(x in p for x in ["equipe", "time", "colaboração", "trabalho em grupo"]):
        return ("Como freelancer trabalhei diretamente com clientes, alinhando expectativas "
                "e entregando dentro do prazo. Estou acostumado a comunicação clara e "
                "gestão de prioridades de forma autônoma.")

    if any(x in p for x in ["desafio", "dificuldade", "obstáculo", "problema que resolveu"]):
        return ("Um dos maiores desafios foi integrar NLP e LLMs num chatbot para atender "
                "automaticamente clientes de e-commerce. Resolvi com pesquisa, testes "
                "iterativos e documentação constante, chegando a 80% de automação.")

    if any(x in p for x in ["objetivo", "plano", "meta", "onde quer chegar"]):
        return ("Quero crescer como desenvolvedor full stack em ambiente colaborativo, "
                "aprofundar conhecimentos em arquitetura de software e contribuir com "
                "projetos que gerem impacto real.")

    if any(x in p for x in ["disponibilidade", "início", "quando pode começar"]):
        return "Tenho disponibilidade imediata para início."

    return ("Tenho ~3 anos de experiência como desenvolvedor freelancer, com foco em "
            "Python, Django, React e PHP. Desenvolvo APIs, automações e interfaces "
            "completas, e busco minha primeira oportunidade CLT para crescer em equipe.")


def _fallback_local_apresentacao(titulo: str, descricao: str) -> str:
    """
    Fallback local para apresentação pessoal quando todas as APIs falham.
    Gera texto personalizado por categoria de vaga.
    """
    t = (titulo + " " + descricao).lower()

    if any(x in t for x in ["suporte", "help desk", "helpdesk", "service desk",
                             "assistente de ti", "sustentação", "noc"]):
        return ("Tenho ~3 anos de experiência em desenvolvimento web com Python e React, "
                "o que me deu base sólida para atuar em suporte técnico: diagnostico "
                "problemas de sistemas, APIs e banco de dados com agilidade. Desenvolvi "
                "um chatbot que automatizou 80% do atendimento. Disponibilidade imediata.")

    if any(x in t for x in ["python", "django", "flask", "fastapi", "backend python"]):
        return ("Desenvolvedor Python desde 2022, com projetos em produção usando Django "
                "e DRF. Construí API RESTful de e-commerce com JWT e chatbot com LLMs "
                "que automatizou 80% do atendimento ao cliente. Disponibilidade imediata.")

    if any(x in t for x in ["php", "laravel", "wordpress"]):
        return ("Trabalho com PHP desde 2022, desenvolvendo sistemas web e APIs RESTful. "
                "No GoMoney construí o backend com JWT, CRUD completo e MySQL. Tenho "
                "certificação PHP avançado (B7Web). Disponibilidade imediata.")

    if any(x in t for x in ["frontend", "front-end", "react", "vue", "angular",
                             "javascript", "typescript"]):
        return ("Desenvolvedor frontend com foco em React e TypeScript desde 2022. "
                "Construí e-commerce completo com Tailwind CSS e JWT, além de dashboards "
                "com Chart.js no GoMoney. Código limpo e componentizado. "
                "Disponibilidade imediata.")

    if any(x in t for x in ["full stack", "fullstack", "full-stack"]):
        return ("Desenvolvedor Full Stack com ~3 anos em Python/Django e React. Construí "
                "APIs RESTful, chatbot com IA (80% de automação) e sistema financeiro "
                "completo com Docker e JWT. Do banco de dados à interface. "
                "Disponibilidade imediata.")

    if any(x in t for x in ["dados", "data", "bi", "analytics", "pandas", "numpy"]):
        return ("Utilizo Python com Pandas e NumPy em projetos de processamento de dados "
                "e desenvolvi dashboards com Chart.js integrados a MySQL. Tenho "
                "experiência com modelagem relacional e consultas complexas. "
                "Disponibilidade imediata.")

    if any(x in t for x in ["estágio", "estagio", "trainee", "jovem aprendiz"]):
        return ("Estou cursando Engenharia de Software (1º semestre, Estácio) e tenho "
                "~3 anos de experiência prática como freelancer em Python, React e PHP. "
                "Busco minha primeira experiência formal. Disponibilidade imediata.")

    return ("Desenvolvedor Full Stack com ~3 anos em Python, Django, React e PHP. "
            "Desenvolvi APIs RESTful, chatbot com IA (80% automação) e sistema "
            "financeiro completo com Docker e JWT. Busco primeira experiência CLT. "
            "Disponibilidade imediata.")


def _fallback_local_habilidades(titulo: str, descricao: str,
                                 habilidades_disponiveis: list) -> list:
    """Seleciona até 3 habilidades por keywords sem LLM."""
    t = (titulo + " " + descricao).lower()
    prioridade = []

    # Monta ordem de prioridade por keywords
    if any(x in t for x in ["python", "django", "flask"]):
        prioridade += ["Python", "Django", "Flask"]
    if any(x in t for x in ["react", "frontend", "javascript"]):
        prioridade += ["React", "JavaScript", "TypeScript"]
    if any(x in t for x in ["php", "laravel"]):
        prioridade += ["PHP"]
    if any(x in t for x in ["mysql", "banco de dados", "sql"]):
        prioridade += ["MySQL"]
    if any(x in t for x in ["docker", "devops"]):
        prioridade += ["Docker"]
    if any(x in t for x in ["git", "github"]):
        prioridade += ["Git", "GitHub"]
    if any(x in t for x in ["html", "css"]):
        prioridade += ["HTML5", "CSS3"]

    # Fallback: usa o próprio perfil
    if not prioridade:
        prioridade = ["Python", "Django", "React", "JavaScript", "MySQL", "Git"]

    selecionadas = []
    disp_lower   = {h.lower(): h for h in habilidades_disponiveis}
    for hab in prioridade:
        if len(selecionadas) >= 3:
            break
        if hab.lower() in disp_lower:
            selecionadas.append(disp_lower[hab.lower()])

    # Se não achou nada, pega as primeiras disponíveis
    if not selecionadas:
        selecionadas = habilidades_disponiveis[:3]

    return selecionadas




# ══════════════════════════════════════════════════════════════════════════════
#  FUNÇÕES LLM (usam o router internamente)
# ══════════════════════════════════════════════════════════════════════════════

def responder_pergunta_aberta(pergunta: str, contexto_vaga: str = "") -> str:
    """Responde perguntas abertas via LLM → fallback local."""
    config = carregar_config()
    pergunta_lower = pergunta.lower()

    # ── Atalhos diretos — zero LLM ───────────────────────────────────────────
    # Salário
    # Colaborador/funcionário da empresa
    if any(p in pergunta_lower for p in [
        "colaborador", "funcionário", "funcionario", "você é colaborador",
        "é colaborador", "empregado da", "trabalha na empresa",
    ]):
        return "Não."

    # Vínculo / serviços prestados
    if any(p in pergunta_lower for p in [
        "vínculo", "vinculo", "prestou serviço", "presta serviço",
        "grupo positivo", "grupo empresarial",
    ]):
        return "Não."

    # Cargo público
    if any(p in pergunta_lower for p in [
        "cargo público", "função pública", "servidor público",
        "administração pública", "poder executivo", "mandato",
    ]):
        return "Não."

    # Parentesco / amizade
    if any(p in pergunta_lower for p in [
        "parente", "parentesco", "familiar", "amigo", "relacionamento",
        "pessoa politicamente exposta",
    ]):
        return "Não."

    # Indicação
    if any(p in pergunta_lower for p in ["indicad", "recomendad"]):
        return "Não fui indicado, candidatura espontânea."

    # Disponibilidade de horário para entrevista
    if any(p in pergunta_lower for p in ["horário para", "agendar", "agendarmos",
                                          "melhor horário", "horário disponível"]):
        return "Segunda a sexta, das 8h às 18h, com disponibilidade imediata."

    # Disponibilidade para início / presencial
    if any(p in pergunta_lower for p in ["disponibilidade", "quando pode começar", "início"]):
        return "Disponibilidade imediata."

    # Cidade
    if any(p in pergunta_lower for p in ["cidade", "onde mora", "onde reside"]):
        return f"Moro em {DADOS_PESSOAIS['cidade']}/{DADOS_PESSOAIS['estado']}."

    # Dados pessoais do .env
    if any(p in pergunta_lower for p in ["cpf", "cadastro de pessoa"]):
        return DADOS_PESSOAIS["cpf"]
    if any(p in pergunta_lower for p in ["rg", "registro geral", "carteira de identidade"]):
        return DADOS_PESSOAIS["rg"]
    if any(p in pergunta_lower for p in ["nome do pai", "nome pai"]):
        return DADOS_PESSOAIS["nome_pai"]
    if any(p in pergunta_lower for p in ["nome da mãe", "nome da mae", "nome mae"]):
        return DADOS_PESSOAIS["nome_mae"]

    # Lattes / currículo acadêmico
    if any(p in pergunta_lower for p in ["lattes", "cnpq", "currículo lattes"]):
        return (
            "Não possuo currículo Lattes. Meu portfólio está disponível em "
            "portfolio--gabriel.vercel.app e GitHub: github.com/gabriell-c"
        )

    # Perguntas condicionais — em branco
    if any(p in pergunta_lower for p in [
        "se sim, qual", "se sim qual", "se houver", "qual empresa",
        "qual cargo público", "qual função", "nome do parente",
        "grau de parentesco", "se afirmativamente", "se respondeu afirmativamente",
    ]):
        return ""

    # Hora/aula — não faz sentido responder com pretensão CLT
    if any(p in pergunta_lower for p in ["hora/aula", "hora aula", "hora-aula", "/aula", "valor hora"]):
        return "A combinar conforme tabela da instituição."

    # Salário — detecta estágio pelo título + contexto da vaga
    if any(p in pergunta_lower for p in ["salari", "pretens", "remuner", "expectativa"]):
        eh_estagio = any(p in (contexto_vaga + pergunta).lower()
                         for p in ["estágio", "estagio", "trainee", "aprendiz",
                                   "bolsista", "jovem aprendiz"])
        eh_pj = any(p in pergunta_lower for p in ["pj", "pessoa jurídica", "pessoa juridica", "mei"])
        if eh_estagio:
            return "R$ 1.600"
        elif eh_pj:
            return f"R$ {config['candidato'].get('pretensao_pj_mensal', '4500')}/mês"
        else:
            return f"R$ {config['candidato'].get('pretensao_clt', '3000')}"

    prompt = f"""Responda essa pergunta de candidatura de emprego de forma direta e humana.

PERFIL DO CANDIDATO (responda SOMENTE com base nele; a lista de exclusões vale):
{perfil.contexto_perfil(config)}

CONTEXTO DA VAGA:
{contexto_vaga[:400] if contexto_vaga else "Não informado"}

PERGUNTA: {pergunta}

REGRAS OBRIGATÓRIAS:
- Máximo 3 frases curtas — seja conciso, não enrole
- Tom direto, como uma pessoa real escreveria — sem floreios
- PROIBIDO usar: "estou ansioso", "estou confiante", "acredito que", "estou emocionado",
  "estou disposto", "como candidato", "venho por meio", "prezados", "atenciosamente",
  "me apresento", "gostaria de", "tenho certeza que", "é um prazer"
- NÃO invente experiências ou certificações
- NÃO mencione pretensão salarial aqui
- NÃO use Markdown (sem **negrito**, *itálico*, # ou [links])
- Se pergunta sobre disponibilidade: "Disponibilidade imediata."
- Se pergunta sobre PJ: "Prefiro CLT, mas posso negociar formato PJ."
- Se pergunta sobre cidade: "Moro em Ribeirão Preto/SP, aceito remoto ou presencial."
- Se pergunta se é colaborador/funcionário da empresa: "Não."
- Se pergunta sobre lattes/currículo acadêmico: informe que não tem lattes mas tem GitHub e portfolio

Resposta (máximo 3 frases):"""

    resposta = _chamar_llm(prompt, config, contexto="pergunta_aberta",
                           temperatura=0.3, max_tokens=200)
    texto = resposta or _fallback_local_pergunta_aberta(pergunta, contexto_vaga)
    return _limpar_markdown(texto)


def gerar_apresentacao(titulo: str, descricao: str) -> str:
    """Gera apresentação pessoal para o campo 'Apresente-se!' via LLM → fallback local."""
    config = carregar_config()

    prompt = f"""Escreva uma apresentação pessoal para candidatura de emprego.

PERFIL DO CANDIDATO (não cite itens da lista de exclusões como habilidade sua):
{_perfil_ctx(config)}

VAGA:
Título: {titulo}
Descrição: {descricao[:500]}

REGRAS OBRIGATÓRIAS:
- Máximo 900 caracteres
- Tom direto e humano — como uma pessoa real escreveria, NÃO como IA
- PROIBIDO usar: "estou ansioso", "estou confiante", "acredito que", "estou emocionado",
  "estou disposto", "me apresento", "venho por meio", "prezados", "atenciosamente",
  "gostaria de", "tenho certeza", "é um prazer", "sou apaixonado", "estou comprometido",
  "ansioso para", "confiante de que", "disposto a aprender", "estou motivado"
- NÃO comece com 'Sou um desenvolvedor júnior' — varie o início
  (comece com um projeto, conquista, número ou tecnologia)
- Mencione 1 projeto concreto com resultado numérico (ex: "80% de automação")
- NÃO use formatação Markdown (sem **negrito**, *itálico*, # títulos ou [links](url))
- NÃO inclua nome, cidade ou dados de contato no texto
- Seja honesto sobre ser júnior, mas foque no que já entregou
- Não mencione pretensão salarial
- Não mencione nome do candidato
- Máximo 3 parágrafos curtos

Apresentação:"""

    resposta = _chamar_llm(prompt, config, contexto="apresentacao",
                           temperatura=0.6, max_tokens=500)
    texto = resposta or _fallback_local_apresentacao(titulo, descricao)
    return _limpar_markdown(texto)


def selecionar_habilidades_relevantes(titulo: str, descricao: str,
                                       habilidades_disponiveis: list) -> list:
    """Seleciona até 3 habilidades via LLM → fallback local."""
    config = carregar_config()

    habilidades_str = ", ".join(habilidades_disponiveis)
    prompt = f"""Selecione as 3 habilidades MAIS relevantes para esta vaga dentre as disponíveis.

Vaga: {titulo}
Descrição: {descricao[:300]}

Habilidades disponíveis: {habilidades_str}

CONTEXTO DO CANDIDATO (respeite a lista de exclusões — nunca escolha um item dela):
{perfil.perfil_compacta(config, limite=400)}

Regras:
- NUNCA escolha uma habilidade que esteja na lista de exclusões acima.
- Escolha apenas nomes que estejam literalmente na lista de disponíveis.

Responda SOMENTE com os nomes exatos das 3 habilidades separados por vírgula.
Exemplo: Python, Django, Git

Resposta:"""

    resposta = _chamar_llm(prompt, config, contexto="habilidades",
                           temperatura=0.2, max_tokens=50)

    if resposta:
        habilidades = [h.strip() for h in resposta.split(",")]
        validas = [h for h in habilidades
                   if any(h.lower() == d.lower() for d in habilidades_disponiveis)]
        if validas:
            return validas[:3]

    return _fallback_local_habilidades(titulo, descricao, habilidades_disponiveis)

