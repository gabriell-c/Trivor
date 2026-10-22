"""
╔══════════════════════════════════════════╗
║       🤖 JOB HUNTER — GUPY  v1.1        ║
╚══════════════════════════════════════════╝

Fluxo:
  1. Login com sessão salva (ou login manual na 1ª vez)
  2. Busca paginada em portal.gupy.io
  3. Filtra vagas por palavras-chave/exclusão
  4. Candidatura multi-etapa:
     a. Continuar
     b. Dados adicionais (indicação=Não, funcionário=Não)
     c. Aviso → Responder agora
     d. Perguntas abertas (LLM responde)
     e. Modal "Apresente-se!" → Personalizar candidatura
     f. Carta + seleção de habilidades
     g. Finalizar candidatura
  5. Salva relatório após cada candidatura

VERSÃO v1.1:
  - LLM router Groq → Gemini → Mistral → fallback local
    · Groq rate limit curto (< 5min): aguarda e retenta automaticamente
    · Groq rate limit diário: troca para Gemini até meia-noite
    · Gemini 2.5 Flash-Lite: 1.000 req/dia, 15 RPM, com retry automático
    · Mistral Small: ~1 bilhão tokens/mês, praticamente ilimitado
    · Fallback local para perguntas abertas e apresentação
  - Salvamento de respostas das perguntas e apresentação no relatório
  - .txt diário com append (não sobrescreve a cada vaga)
  - Variáveis de ambiente necessárias:
    · GROQ_API_KEY    — console.groq.com
    · GEMINI_API_KEY  — aistudio.google.com
    · MISTRAL_API_KEY — console.mistral.ai
"""

import contextlib
import datetime as _dt
import json
import os
import random
import re
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from common import llm as _llm_lib
from common import perfil
from common.browser import SESSIONS_DIR, Browser, BrowserUnavailable, find_adaptive
from dotenv import load_dotenv
from playwright.sync_api import Page

load_dotenv()

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

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

# A sessão vive no perfil persistente (apply/sessions/gupy/<engine>/) —
# o antigo gupy_session.json (migração de cookies entre browsers) foi
# descartado junto com ele. As specs de seletores estáveis também ficam lá.
SPEC_DIR      = SESSIONS_DIR / "gupy" / "specs"
RELATORIO_DIR = "relatorio"
URL_LOGIN     = "https://login.gupy.io/candidates/signin"
URL_PORTAL    = "https://portal.gupy.io"
URL_BUSCA     = "https://portal.gupy.io/job-search/term={termo}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


def carregar_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def log(msg: str):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M:%S")
    print(f"[{agora}] {msg}")


# ══════════════════════════════════════════════════════════════════════════════
#  SEGURANÇA ANTI-BAN
# ══════════════════════════════════════════════════════════════════════════════

def esperar(page: Page, segundos: float, variacao: float = 0.4):
    total = segundos + random.uniform(-variacao * 0.5, variacao)
    total = max(0.3, total)
    time.sleep(total)


def scroll_humano(page: Page):
    try:
        altura = random.randint(200, 600)
        page.evaluate(f"window.scrollBy({{top: {altura}, behavior: 'smooth'}})")
        time.sleep(random.uniform(0.5, 1.2))
    except Exception:
        pass


def mover_mouse_aleatorio(page: Page):
    try:
        x = random.randint(200, 1400)
        y = random.randint(100, 800)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


def delay_entre_vagas(config: dict):
    base  = config["automacao"].get("delay_entre_vagas", 8)
    total = base + random.uniform(2, 7)
    log(f"  ⏳ Aguardando {total:.1f}s antes da próxima vaga...")
    time.sleep(total)


def horario_ok() -> bool:
    hora = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    return 7 <= hora <= 22


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


def _agendar_retorno_groq(reset_utc: "_dt.datetime") -> None:
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
#  SESSÃO
# ══════════════════════════════════════════════════════════════════════════════

def fazer_login_manual(page, config: dict) -> None:
    """Login manual no browser persistente da layer nova (camoufox/patchright).

    Se GUPY_EMAIL/GUPY_SENHA estiverem no .env, pré-preenche as credenciais
    e a pessoa passa o desafio do Cloudflare (Turnstile) na tela. A sessão
    fica no perfil apply/sessions/gupy/ — sem migração de cookies entre
    browsers (o fluxo antigo com undetected-chromedriver + gupy_session.json
    era em si um padrão de detecção: browser A loga, browser B continua)."""
    email = os.environ.get("GUPY_EMAIL", "")
    senha = os.environ.get("GUPY_SENHA", "")

    log("\n🔐 Abrindo a tela de login...")
    page.goto(URL_LOGIN, timeout=30000)
    esperar(page, 2)

    if email:
        try:
            campo = page.locator("#username")
            campo.clear()
            campo.fill(email)
            esperar(page, 0.5)
            page.locator("#password-input").fill(senha)
            esperar(page, 0.5)
            page.locator("#button-signin").click()
            log("  ✓ Credenciais enviadas. Se aparecer desafio, complete manualmente no browser.")
        except Exception as e:
            log(f"  ⚠️  Não deu pra pré-preencher ({type(e).__name__}): digite as credenciais no browser.")
    else:
        log("  👆 Digite as credenciais manualmente no browser.")

    for _ in range(120):
        if "portal.gupy.io" in page.url or "app.gupy.io" in page.url:
            break
        time.sleep(1)
    else:
        input("  ▶  Portal não carregou. Pressione ENTER quando carregar... ")

    log("✅ Logado! (sessão fica guardada em apply/sessions/gupy/)")


def verificar_sessao_valida(page: Page) -> bool:
    try:
        page.goto(URL_PORTAL, timeout=15000)
        esperar(page, 2)
        return "signin" not in page.url and "login" not in page.url
    except Exception:
        return False


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


# ══════════════════════════════════════════════════════════════════════════════
#  BUSCA DE VAGAS
# ══════════════════════════════════════════════════════════════════════════════

def filtrar_vaga(titulo: str, config: dict) -> bool:
    titulo_lower = titulo.lower()
    for palavra in config["busca"].get("palavras_excluir", []):
        if palavra.lower() in titulo_lower:
            return False
    return True


def buscar_vagas_gupy(page: Page, config: dict) -> list:
    vagas        = []
    links_vistos = set()
    termos       = config["busca"]["palavras_chave"]

    for termo in termos:
        log(f"\n🔍 Buscando: {termo}")
        termo_url = termo.replace(" ", "%20")
        url = URL_BUSCA.format(termo=termo_url)

        try:
            page.goto(url, timeout=20000)
            esperar(page, 3)
            scroll_humano(page)

            pagina    = 1
            max_pags  = 5

            while pagina <= max_pags:
                cards = page.query_selector_all("a.sc-4d881605-1")
                if not cards:
                    # Portal renomeou a classe → relocaliza o 1º card pelo
                    # seletor adaptativo (css → xpath estável salvo → texto)
                    first = find_adaptive(page, "a.sc-4d881605-1", None, SPEC_DIR / "cards.json")
                    cards = [first] if first else []
                log(f"  📄 Página {pagina}: {len(cards)} vagas encontradas")

                for card in cards:
                    try:
                        href = card.get_attribute("href")
                        if not href or href in links_vistos:
                            continue

                        h3     = card.query_selector("h3")
                        titulo = h3.inner_text().strip() if h3 else (card.get_attribute("aria-label") or "")

                        if not titulo or not filtrar_vaga(titulo, config):
                            continue

                        local_el = card.query_selector("[data-testid='job-location']")
                        local    = local_el.inner_text().strip() if local_el else "Não informado"

                        data_el  = card.query_selector("[data-testid='listing-card-footer'] p")
                        data_pub = data_el.inner_text().strip() if data_el else ""

                        links_vistos.add(href)
                        vagas.append({
                            "titulo":          titulo,
                            "link":            href,
                            "local":           local,
                            "data_publicacao": data_pub,
                            "termo_busca":     termo,
                        })

                    except Exception as e:
                        log(f"  ⚠️  Erro ao ler card: {e}")

                btn_prox = page.query_selector("button[aria-label='Próxima página']:not([disabled])")
                if not btn_prox:
                    break

                scroll_humano(page)
                mover_mouse_aleatorio(page)
                btn_prox.click()
                esperar(page, random.uniform(2, 4))
                pagina += 1

        except Exception as e:
            log(f"  ❌ Erro na busca por '{termo}': {e}")

    log(f"\n📊 Total de vagas encontradas: {len(vagas)}")
    return vagas


# ══════════════════════════════════════════════════════════════════════════════
#  ETAPAS DE CANDIDATURA
# ══════════════════════════════════════════════════════════════════════════════

def clicar_botao(page: Page, seletores: list, timeout: float = 5) -> bool:
    for seletor in seletores:
        try:
            el = page.query_selector(seletor)
            if el and el.is_visible():
                el.scroll_into_view_if_needed()
                esperar(page, 0.3)
                el.click()
                return True
        except Exception:
            pass
    return False


def etapa_continuar(page: Page) -> bool:
    return clicar_botao(page, [
        "button:has-text('Continuar')",
        "button[aria-label='Continuar']",
    ])


def etapa_dados_adicionais(page: Page) -> bool:
    try:
        radio_ind = page.query_selector("input[name='radioGroupIsIndicatedNo']")
        if radio_ind:
            label = page.query_selector("label[arialabel='no'][data-testid='radioGroupIsIndicatedNo']")
            if label:
                label.click()
            else:
                radio_ind.click(force=True)
            esperar(page, 0.4)

        radio_func = page.query_selector("input[name='radioGroupIsCompanyEmployeeNo']")
        if radio_func:
            label = page.query_selector("label[arialabel='no']:not([data-testid='radioGroupIsIndicatedNo'])")
            if label:
                label.click()
            else:
                radio_func.click(force=True)
            esperar(page, 0.4)

        return clicar_botao(page, [
            "button[name='saveAndContinueButton']",
            "button:has-text('Salvar e continuar')",
        ])
    except Exception as e:
        log(f"  ⚠️  Erro nos dados adicionais: {e}")
        return False


def etapa_aviso_perguntas(page: Page) -> bool:
    return clicar_botao(page, [
        "button[aria-label='Responder agora']",
        "button:has-text('Responder agora')",
    ])


def etapa_perguntas_empresa(page: Page, titulo: str, descricao: str,
                             respostas_salvas: dict) -> bool:
    """
    Responde perguntas da empresa e registra em respostas_salvas.
    Suporta: radio buttons, inputs de texto, textareas.
    """
    try:
        config = carregar_config()
        log("  📝 Respondendo perguntas da empresa...")

        # ── Radio buttons ──────────────────────────────────────────────────────
        for fs in page.query_selector_all("fieldset[name^='additional-question-input']"):
            try:
                label_el = fs.query_selector("label.radio-group__label")
                pergunta = label_el.inner_text().strip() if label_el else ""
                pergunta_lower = pergunta.lower()
                log(f"    ❓ Radio: {pergunta[:70]}")

                opcoes_labels = fs.query_selector_all("label.radio-button")
                opcoes_texto  = []
                for lbl in opcoes_labels:
                    inp_el = lbl.query_selector("input[type='radio']")
                    spans  = lbl.query_selector_all("span")
                    texto  = spans[-1].inner_text().strip() if spans else ""
                    if inp_el:
                        opcoes_texto.append((inp_el, texto))

                if not opcoes_texto:
                    continue

                escolhida       = None
                texto_escolhido = ""

                def _nao(ops):
                    """Retorna a primeira opção que começa com 'Não' ou contém 'não'."""
                    for op, t in ops:
                        if t.lower().startswith("não") or t.lower() == "não":
                            return op, t
                    for op, t in ops:
                        if "não" in t.lower():
                            return op, t
                    return ops[0]  # fallback: primeira opção

                # ── Sempre "Não" — vínculo com empresa ───────────────────────
                if any(p in pergunta_lower for p in [
                    "já trabalhou", "trabalhou no", "trabalhou na", "ex-colaborador",
                    "vínculo", "vinculo", "faz parte do grupo", "grupo positivo",
                    "grupo empresarial", "pertence ao grupo",
                ]) or any(p in pergunta_lower for p in [
                    "prestou serviço", "presta serviço", "prestou serviços",
                    "forma direta ou indireta", "terceirizado",
                ]) or any(p in pergunta_lower for p in [
                    "cargo público", "função pública", "emprego público",
                    "administração pública", "servidor público", "poder executivo",
                    "poder legislativo", "poder judiciário", "mandato",
                    "órgão público", "ente público",
                ]) or any(p in pergunta_lower for p in [
                    "parente", "familiar", "cônjuge", "companheiro",
                    "relação de amizade", "amigo", "relacionamento",
                    "pessoa politicamente exposta",
                ]) or any(p in pergunta_lower for p in ["indicad", "recomendad", "referência"]):
                    escolhida, texto_escolhido = _nao(opcoes_texto)

                # ── PCD — lê do config ────────────────────────────────────────
                elif any(p in pergunta_lower for p in ["deficiência", "deficiente", "pcd"]):
                    pcd = config.get("diversidade", {}).get("pcd", False)
                    for op, t in opcoes_texto:
                        if ("sim" in t.lower()) == pcd:
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Raça/cor ──────────────────────────────────────────────────
                elif any(p in pergunta_lower for p in ["raça", "cor", "étnico"]):
                    raca = config.get("diversidade", {}).get("raca_cor", "Pardo").lower()
                    for op, t in opcoes_texto:
                        if raca in t.lower():
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Gênero ────────────────────────────────────────────────────
                elif any(p in pergunta_lower for p in ["gênero", "genero"]):
                    genero = config.get("diversidade", {}).get("genero", "Homem cisgênero").lower()
                    for op, t in opcoes_texto:
                        if all(p in t.lower() for p in genero.split()[:2]):
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        for op, t in opcoes_texto:
                            if "homem" in t.lower():
                                escolhida, texto_escolhido = op, t
                                break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Orientação sexual ─────────────────────────────────────────
                elif any(p in pergunta_lower for p in ["orientação sexual", "orientacao"]):
                    orient = config.get("diversidade", {}).get("orientacao_sexual", "Heterossexual").lower()
                    for op, t in opcoes_texto:
                        if orient[:5] in t.lower():
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Colaborador / funcionário — ANTES de disponibilidade ─────
                elif any(p in pergunta_lower for p in [
                    "você é colaborador", "é colaborador", "colaborador do sistema",
                    "colaborador da empresa", "empregado da empresa",
                    "funcionário da empresa", "faz parte do quadro",
                    "trabalha na empresa", "trabalha no sistema",
                ]):
                    escolhida, texto_escolhido = _nao(opcoes_texto)

                # ── Disponibilidade / aceite de condições ─────────────────────
                elif any(p in pergunta_lower for p in [
                    "disponibilidade", "disponível", "aceita", "concorda",
                    "ciente", "declara",
                ]):
                    for op, t in opcoes_texto:
                        if "sim" in t.lower():
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Cidade: tenta casar com Ribeirão Preto, senão escolhe a que ──
                # ── tiver "outra" / "sim" (disponibilidade de residência)  ────────
                elif any(p in pergunta_lower for p in [
                    "cidade", "município", "municipio", "reside", "mora",
                    "qual cidade",
                ]):
                    cidade_candidato = DADOS_PESSOAIS.get("cidade", "ribeirão preto").lower()
                    # Tenta casar com a cidade do candidato
                    for op, t in opcoes_texto:
                        if cidade_candidato in t.lower() or "ribeirão preto" in t.lower():
                            escolhida, texto_escolhido = op, t
                            break
                    # Se não achou, tenta "outra cidade" ou "sim" (disponibilidade)
                    if not escolhida:
                        for op, t in opcoes_texto:
                            if any(x in t.lower() for x in ["outra", "sim", "outras"]):
                                escolhida, texto_escolhido = op, t
                                break
                    # Último fallback: primeira opção
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Turno: prefere integral/indiferente, senão manhã ──────────────
                elif any(p in pergunta_lower for p in [
                    "turno", "horário", "horario", "período", "periodo",
                    "carga horária", "carga horaria",
                ]):
                    for op, t in opcoes_texto:
                        if any(x in t.lower() for x in [
                            "integral", "indiferente", "flexível", "flexivel",
                            "qualquer", "ambos", "todos",
                        ]):
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        for op, t in opcoes_texto:
                            if "manhã" in t.lower() or "manha" in t.lower():
                                escolhida, texto_escolhido = op, t
                                break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Faixa salarial: escolhe a mais próxima de R$3.000 ─────────────
                elif any(p in pergunta_lower for p in [
                    "expectativa salarial", "faixa salarial", "pretensão salarial",
                    "remuneração", "salário esperado",
                ]):
                    import re as _re
                    alvo = 3000
                    melhor_op, melhor_texto, menor_diff = None, "", float("inf")
                    for op, t in opcoes_texto:
                        # Extrai todos os números do texto da opção
                        nums = [int(n.replace(".", "")) for n in _re.findall(r"[0-9.]+", t.replace(",", "."))]
                        if nums:
                            # Usa o número mais próximo de 3000
                            diff = min(abs(n - alvo) for n in nums)
                            if diff < menor_diff:
                                menor_diff = diff
                                melhor_op, melhor_texto = op, t
                    if melhor_op:
                        escolhida, texto_escolhido = melhor_op, melhor_texto
                    else:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Modelo de trabalho: prefere remoto/híbrido ────────────────────
                elif any(p in pergunta_lower for p in [
                    "modelo de trabalho", "modalidade", "formato de trabalho",
                    "trabalho remoto", "home office", "presencial ou remoto",
                    "como você prefere trabalhar",
                ]):
                    # Prefere remoto/híbrido — nunca seleciona opção que menciona
                    # uma cidade específica diferente de Ribeirão Preto
                    cidade_cand = DADOS_PESSOAIS.get("cidade", "ribeirão preto").lower()
                    for op, t in opcoes_texto:
                        tl = t.lower()
                        if any(x in tl for x in ["remoto", "home office", "100% remoto"]):
                            escolhida, texto_escolhido = op, t
                            break
                    if not escolhida:
                        for op, t in opcoes_texto:
                            tl = t.lower()
                            if "híbrido" in tl or "hibrido" in tl:
                                # Só aceita híbrido se não mencionar cidade alheia
                                if cidade_cand in tl or "blumenau" not in tl:
                                    escolhida, texto_escolhido = op, t
                                    break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                # ── Default: usa LLM para decidir (com lista de opções) ───────────
                else:
                    config_llm = carregar_config()
                    lista_ops = " | ".join(t for _, t in opcoes_texto)
                    prompt_radio = f"""Você está respondendo uma pergunta de seleção em nome de um candidato.

PERFIL (contexto completo; a lista de exclusões vale): {perfil.perfil_compacta(config_llm, limite=500)}

PERGUNTA: {pergunta}
OPÇÕES DISPONÍVEIS: {lista_ops}

Responda APENAS com o texto EXATO de uma das opções acima — nada mais.
Escolha a opção que melhor representa o candidato.
Se a pergunta tocare em item da lista de exclusões, escolha a opção que nega experiência ("Nenhum", "Não", "0 anos").
Se for pergunta sobre trabalho anterior na empresa, responda com a opção de "Não".
Se for sobre disponibilidade presencial, prefira "Sim".

Opção escolhida:"""
                    resp_llm = _chamar_llm(prompt_radio, config_llm,
                                           contexto="radio_default", temperatura=0.0,
                                           max_tokens=50)
                    if resp_llm:
                        resp_limpo = resp_llm.strip().lower()
                        for op, t in opcoes_texto:
                            if resp_limpo in t.lower() or t.lower() in resp_limpo:
                                escolhida, texto_escolhido = op, t
                                break
                    if not escolhida:
                        escolhida, texto_escolhido = opcoes_texto[0]

                if escolhida:
                    escolhida.evaluate("el => el.click()")
                    respostas_salvas[pergunta] = texto_escolhido
                    esperar(page, 0.5)
                    log(f"    ✓ Selecionado: {texto_escolhido[:40]}")

            except Exception as e:
                log(f"    ⚠️  Erro em radio: {e}")

        # ── Inputs de texto ────────────────────────────────────────────────────
        for inp in page.query_selector_all("input[id^='additional-question-input']"):
            try:
                if inp.get_attribute("type") == "radio":
                    continue

                inp_id   = inp.get_attribute("id") or ""
                label_el = page.query_selector(f"label[for='{inp_id}']")
                pergunta = label_el.inner_text().strip() if label_el else ""
                pergunta_lower = pergunta.lower()

                # ── Dados pessoais sensíveis — sempre do .env ─────────────
                if any(p in pergunta_lower for p in ["cpf", "cadastro de pessoa física"]):
                    resposta = DADOS_PESSOAIS["cpf"]
                elif any(p in pergunta_lower for p in ["\brg\b", "registro geral",
                                                        "carteira de identidade"]):
                    resposta = DADOS_PESSOAIS["rg"]
                elif any(p in pergunta_lower for p in ["nome do pai", "nome pai",
                                                        "filiação paterna"]):
                    resposta = DADOS_PESSOAIS["nome_pai"]
                elif any(p in pergunta_lower for p in ["nome da mãe", "nome mae",
                                                        "nome da mae", "filiação materna"]):
                    resposta = DADOS_PESSOAIS["nome_mae"]
                elif any(p in pergunta_lower for p in ["logradouro", "endereço", "rua",
                                                        "avenida", "alameda"]):
                    resposta = DADOS_PESSOAIS["logradouro"]
                elif any(p in pergunta_lower for p in ["número", "numero", "nº"]):
                    resposta = DADOS_PESSOAIS["numero"]
                elif "bairro" in pergunta_lower:
                    resposta = DADOS_PESSOAIS["bairro"]
                elif any(p in pergunta_lower for p in ["cep", "código postal"]):
                    resposta = DADOS_PESSOAIS["cep"]
                elif "complemento" in pergunta_lower:
                    resposta = DADOS_PESSOAIS["complemento"] or "N/A"
                elif any(p in pergunta_lower for p in ["cidade", "município", "municipio"]):
                    resposta = DADOS_PESSOAIS["cidade"]
                elif any(p in pergunta_lower for p in ["estado", "uf", "unidade federativa"]):
                    resposta = DADOS_PESSOAIS["estado"]

                # ── Perguntas condicionais ("se sim, qual?") ─────────────────
                # Se a pergunta é um desdobramento de algo que respondemos "Não",
                # deixa em branco ou responde "Não se aplica"
                elif any(p in pergunta_lower for p in [
                    "se sim, qual", "se sim qual", "se houver", "qual empresa",
                    "qual cargo público", "qual função", "qual órgão",
                    "nome do parente", "grau de parentesco",
                ]):
                    resposta = ""  # Campo em branco — não se aplica

                # ── Sempre "Não" em formato texto ────────────────────────────
                elif any(p in pergunta_lower for p in [
                    "vínculo", "vinculo", "cargo público", "função pública",
                    "prestou serviço", "presta serviço",
                    "indicad", "matrícula", "colaborador", "funcionário",
                ]):
                    resposta = "Não"

                # ── Dados de diversidade ──────────────────────────────────────
                elif any(p in pergunta_lower for p in ["deficiência", "deficiente", "pcd"]):
                    resposta = "Não possuo deficiência" if not config.get("diversidade", {}).get("pcd") else "Sim"
                elif any(p in pergunta_lower for p in ["raça", "cor", "étnico", "etnia"]):
                    resposta = config.get("diversidade", {}).get("raca_cor", "Pardo")
                elif any(p in pergunta_lower for p in ["gênero", "genero"]):
                    resposta = config.get("diversidade", {}).get("genero", "Homem cisgênero")
                elif any(p in pergunta_lower for p in ["orientação sexual", "orientacao sexual"]):
                    resposta = config.get("diversidade", {}).get("orientacao_sexual", "Heterossexual")

                # ── Pretensão salarial ────────────────────────────────────────
                elif any(p in pergunta_lower for p in ["remuner", "último", "atual",
                                                        "expectativa", "pretens", "salarial"]):
                    resposta = f"R$ {config['candidato'].get('pretensao_clt', '3000')}"

                # ── LLM para o resto ──────────────────────────────────────────
                else:
                    resposta = responder_pergunta_aberta(pergunta, descricao)

                inp.scroll_into_view_if_needed()
                esperar(page, 0.2)
                page.evaluate("el => el.click()", inp)
                esperar(page, 0.2)
                inp.fill(resposta)
                respostas_salvas[pergunta] = resposta
                log(f"    ✓ Input '{pergunta[:50]}' → {resposta[:40]}")
                esperar(page, random.uniform(0.3, 0.6))

            except Exception as e:
                log(f"    ⚠️  Erro em input: {e}")

        # ── Textareas ──────────────────────────────────────────────────────────
        for textarea in page.query_selector_all("textarea[name^='additional-question-textarea']"):
            try:
                ta_id    = textarea.get_attribute("id") or ""
                label_el = page.query_selector(f"label[for='{ta_id}']")
                pergunta = label_el.inner_text().strip() if label_el else "Pergunta da empresa"
                pergunta = re.sub(r"^\d+\.\s*", "", pergunta)
                log(f"    ❓ Textarea: {pergunta[:70]}")
                pergunta_lower_ta = pergunta.lower()

                # Perguntas condicionais — deixa em branco
                if any(p in pergunta_lower_ta for p in [
                    "se sim, qual", "se sim qual", "se houver", "qual empresa",
                    "qual cargo", "qual função", "qual órgão",
                    "nome do parente", "grau de parentesco",
                ]):
                    resposta = ""
                # Dados pessoais do .env
                elif any(p in pergunta_lower_ta for p in ["cpf", "cadastro de pessoa"]):
                    resposta = DADOS_PESSOAIS["cpf"]
                elif any(p in pergunta_lower_ta for p in ["\brg\b", "registro geral"]):
                    resposta = DADOS_PESSOAIS["rg"]
                elif any(p in pergunta_lower_ta for p in ["nome do pai", "nome pai"]):
                    resposta = DADOS_PESSOAIS["nome_pai"]
                elif any(p in pergunta_lower_ta for p in ["nome da mãe", "nome da mae", "nome mae"]):
                    resposta = DADOS_PESSOAIS["nome_mae"]
                # Sempre Não
                elif any(p in pergunta_lower_ta for p in [
                    "vínculo", "vinculo", "cargo público", "função pública",
                    "prestou serviço", "presta serviço",
                ]):
                    resposta = "Não"
                else:
                    resposta = responder_pergunta_aberta(pergunta, descricao)
                textarea.scroll_into_view_if_needed()
                textarea.click()
                esperar(page, 0.3)
                textarea.fill(resposta)
                respostas_salvas[pergunta] = resposta
                log(f"    ✓ {resposta[:60]}...")
                esperar(page, random.uniform(0.5, 1.0))
            except Exception as e:
                log(f"    ⚠️  Erro em textarea: {e}")

        # ── Salvar e continuar ─────────────────────────────────────────────────
        esperar(page, 1.0)
        clicou = clicar_botao(page, [
            "button:has-text('Salvar e continuar')",
            "button[name='saveAndContinueButton']",
        ])
        if clicou:
            log("  ✓ Salvar e continuar clicado")
        else:
            log("  ⚠️  Botão Salvar não encontrado")
        return clicou

    except Exception as e:
        log(f"  ⚠️  Erro nas perguntas da empresa: {e}")
        return False


def remover_backdrop(page: Page):
    page.evaluate("""
        const old = document.getElementById('__fix_backdrop__');
        if (old) old.remove();
        document.querySelectorAll('[data-state="open"][aria-hidden="true"]').forEach(el => {
            if (!el.querySelector('[role="dialog"]') && el.children.length === 0) {
                el.style.setProperty('pointer-events', 'none', 'important');
                el.style.setProperty('display', 'none', 'important');
            }
        });
        document.querySelectorAll('.sc-YysOf, [role="dialog"]').forEach(el => {
            el.style.setProperty('pointer-events', 'auto', 'important');
        });
        const btn = document.getElementById('dialog-save-personalization-step');
        if (btn) {
            btn.style.setProperty('pointer-events', 'auto', 'important');
            let el = btn.parentElement;
            while (el && el !== document.body) {
                el.style.setProperty('pointer-events', 'auto', 'important');
                el = el.parentElement;
            }
        }
    """)


def etapa_apresentacao(page: Page, titulo: str, descricao: str,
                        respostas_salvas: dict) -> bool:
    """Modal 'Apresente-se!' — preenche apresentação + seleciona habilidades."""
    try:
        btn_personalizar = page.query_selector("#dialog-save-personalization-step")
        if not btn_personalizar:
            return False

        esperar(page, 1)
        with contextlib.suppress(Exception):
            page.wait_for_selector("#dialog-save-personalization-step",
                                   state="visible", timeout=5000)

        log("  ✨ Modal 'Apresente-se!' detectado, personalizando...")

        def react_click(pg, btn_id):
            js = """(btnId) => {
                const btn = document.getElementById(btnId);
                if (!btn) return 'btn_not_found';
                const fiberKey = Object.keys(btn).find(k =>
                    k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance')
                );
                if (!fiberKey) return 'fiber_not_found';
                let fiber = btn[fiberKey];
                while (fiber) {
                    const props = fiber.memoizedProps || fiber.pendingProps;
                    if (props && props.onClick) {
                        props.onClick({ type: 'click', preventDefault: () => {}, stopPropagation: () => {} });
                        return 'react_click_ok';
                    }
                    fiber = fiber.return;
                }
                return 'onClick_not_found';
            }"""
            try:
                r = pg.evaluate(f"({js})('{btn_id}')")
                if r == 'react_click_ok':
                    return r
            except Exception:
                pass
            for frame in pg.frames:
                try:
                    r = frame.evaluate(f"({js})('{btn_id}')")
                    if r == 'react_click_ok':
                        return r
                except Exception:
                    pass
            return 'not_found_in_any_frame'

        clicou = react_click(page, 'dialog-save-personalization-step')
        log(f"  🔬 React fiber click: {clicou}")
        esperar(page, 2)

        if not page.query_selector("#personalization-step-text-area"):
            log("  ⚠️  Não abriu personalização, finalizando sem ela...")
            react_click(page, 'dialog-give-up-personalization-step')
            esperar(page, 2)
            return True

        # Preenche apresentação
        textarea_apres = page.query_selector("#personalization-step-text-area")
        if textarea_apres:
            apresentacao = gerar_apresentacao(titulo, descricao)
            textarea_apres.click(force=True)
            esperar(page, 0.3)
            textarea_apres.fill(apresentacao)
            respostas_salvas["Apresentação pessoal"] = apresentacao
            log(f"  ✓ Apresentação gerada: {apresentacao[:60]}...")
            esperar(page, 0.5)

        # Seleciona habilidades
        botoes_hab = page.query_selector_all("button[data-testid='candidate-skill']")
        if botoes_hab:
            habilidades_disponiveis = []
            for btn in botoes_hab:
                try:
                    nome_el = btn.query_selector("div.sc-hmdomO")
                    if nome_el:
                        habilidades_disponiveis.append(nome_el.inner_text().strip())
                except Exception:
                    pass

            if habilidades_disponiveis:
                selecionadas = selecionar_habilidades_relevantes(
                    titulo, descricao, habilidades_disponiveis)
                log(f"  🏷️  Habilidades selecionadas: {', '.join(selecionadas)}")
                respostas_salvas["Habilidades selecionadas"] = ", ".join(selecionadas)

                count = 0
                for btn in botoes_hab:
                    if count >= 3:
                        break
                    try:
                        nome_el = btn.query_selector("div.sc-hmdomO")
                        if nome_el:
                            nome = nome_el.inner_text().strip()
                            if any(nome.lower() == s.lower() for s in selecionadas):
                                btn.scroll_into_view_if_needed()
                                btn.click()
                                count += 1
                                esperar(page, 0.3)
                    except Exception:
                        pass

        esperar(page, 0.5)
        return clicar_botao(page, [
            "button:has-text('Finalizar candidatura')",
            "button.sc-fYKINB",
        ])

    except Exception as e:
        log(f"  ⚠️  Erro na apresentação: {e}")
        return False


def verificar_candidatura_finalizada(page: Page) -> bool:
    try:
        esperar(page, 2)
        for h1 in page.query_selector_all("h1"):
            texto = h1.inner_text().strip().lower()
            if "finalizada" in texto or "concluída" in texto:
                return True
        return "success" in page.url or "finaliz" in page.url
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  FLUXO COMPLETO DE CANDIDATURA
# ══════════════════════════════════════════════════════════════════════════════

def candidatar_vaga_gupy(page: Page, vaga: dict, config: dict) -> dict:
    resultado = {
        "vaga":      vaga["titulo"],
        "link":      vaga["link"],
        "local":     vaga.get("local", ""),
        "site":      "Gupy",
        "status":    "erro",
        "data":      datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"),
        "horario":   datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M:%S"),
        "curriculo": "perfil Gupy",
        "respostas": {},   # perguntas respondidas + apresentação + habilidades
        "carta":     "",   # Gupy não usa carta separada
    }

    respostas_salvas: dict = {}

    try:
        log(f"\n🚀 Abrindo vaga: {vaga['titulo']}")

        nova_aba = page.context.new_page()
        nova_aba.goto(vaga["link"], timeout=20000)
        esperar(nova_aba, 2)
        scroll_humano(nova_aba)
        mover_mouse_aleatorio(nova_aba)
        esperar(nova_aba, 1)

        # Pega descrição
        descricao = ""
        try:
            for secao in nova_aba.query_selector_all("[data-testid='text-section']"):
                descricao += secao.inner_text() + "\n"
            descricao = descricao[:1500]
        except Exception:
            pass

        # Verifica se já candidatado
        try:
            btn_text = nova_aba.query_selector("a[data-testid='job-cta-link']")
            if btn_text:
                texto = btn_text.inner_text().strip().lower()
                if "candidatado" in texto or "inscrito" in texto:
                    log("  ⏭️  Já candidatado, pulando...")
                    resultado["status"] = "ja_candidatado"
                    nova_aba.close()
                    return resultado
        except Exception:
            pass

        # Clica em Candidatar-se
        clicou = clicar_botao(nova_aba, [
            "a[data-testid='fixed-applyButton']",
            "a[data-testid='job-cta-link']",
            "a:has-text('Candidatar-se')",
        ])
        if not clicou:
            log("  ❌ Botão 'Candidatar-se' não encontrado")
            resultado["status"] = "botao_nao_encontrado"
            nova_aba.close()
            return resultado

        esperar(nova_aba, 3)
        scroll_humano(nova_aba)

        # ── Loop de etapas ──────────────────────────────────────────────────
        max_etapas = 15
        etapa_num  = 0
        finalizado = False

        while etapa_num < max_etapas:
            etapa_num += 1
            esperar(nova_aba, 1.5)
            url_atual = nova_aba.url
            log(f"  📋 Etapa {etapa_num}: {url_atual.split('/')[-1]}")

            # ── Detecta sessão expirada dentro da candidatura ─────────────────
            if "/signin" in url_atual or "/candidates/signin" in url_atual:
                log("  🔒 Sessão expirada detectada — marcando para relogin")
                resultado["status"] = "sessao_expirada"
                nova_aba.close()
                return resultado

            if verificar_candidatura_finalizada(nova_aba):
                log("  ✅ Candidatura finalizada com sucesso!")
                resultado["status"] = "enviado"
                finalizado = True
                break

            # ── PRIORIDADE 1: Modal de perguntas eliminatórias ──────────────────
            # DEVE vir antes de "tem_perguntas" porque o modal fica sobreposto
            # aos fieldsets — sem isso o bot fica em loop respondendo perguntas
            # que já respondeu, sem encontrar o botão Salvar.
            if nova_aba.query_selector("#eliminatory-questions-modal-header"):
                log("  → Modal eliminatório: clicando Confirmar...")
                nova_aba.evaluate("""
                    () => {
                        document.body.style.removeProperty('pointer-events');
                        // Busca o botão Confirmar dentro do modal especificamente
                        const modal = document.getElementById('eliminatory-questions-modal');
                        const alvo = modal || document;
                        const btns = alvo.querySelectorAll('button');
                        for (const btn of btns) {
                            const txt = (btn.querySelector('span')?.textContent || btn.textContent).trim();
                            if (txt === 'Confirmar') {
                                btn.dispatchEvent(new MouseEvent('click',
                                    {bubbles: true, cancelable: true, view: window}));
                                return 'clicou_confirmar';
                            }
                        }
                        return 'confirmar_nao_encontrado';
                    }
                """)
                esperar(nova_aba, 3)
                continue

            # ── PRIORIDADE 2: Modal de apresentação pessoal ───────────────────
            if nova_aba.query_selector("#dialog-save-personalization-step"):
                log("  → Modal de apresentação pessoal (prioridade)...")
                etapa_apresentacao(nova_aba, vaga["titulo"], descricao, respostas_salvas)
                continue

            # ── Perguntas da empresa (só quando modal NÃO está aberto) ────────
            tem_perguntas = (
                nova_aba.query_selector("fieldset[name^='additional-question-input']") or
                nova_aba.query_selector("textarea[name^='additional-question-textarea']") or
                nova_aba.query_selector("input[id^='additional-question-input']")
            )
            # Garante que não é o modal eliminatório sobreposto
            tem_modal_eliminatorio = nova_aba.query_selector("#eliminatory-questions-modal-header")
            if tem_perguntas and not tem_modal_eliminatorio:
                log("  → Perguntas da empresa detectadas, respondendo...")
                etapa_perguntas_empresa(nova_aba, vaga["titulo"], descricao, respostas_salvas)
                esperar(nova_aba, 1.5)
                continue

            # Aviso de perguntas
            if nova_aba.query_selector("button[aria-label='Responder agora']"):
                log("  → Aviso de perguntas, clicando Responder agora...")
                etapa_aviso_perguntas(nova_aba)
                continue

            # Dados adicionais
            if (nova_aba.query_selector("input[name='radioGroupIsIndicatedYes']") or
                    nova_aba.query_selector("input[name='radioGroupIsIndicatedNo']")):
                log("  → Dados adicionais, respondendo Não...")
                etapa_dados_adicionais(nova_aba)
                continue

            # Tela de boas-vindas
            if nova_aba.query_selector("button:has-text('Continuar')"):
                log("  → Tela de boas-vindas, clicando Continuar...")
                etapa_continuar(nova_aba)
                continue

            # Tela de personalização aberta
            if nova_aba.query_selector("#personalization-step-text-area"):
                log("  → Tela de apresentação pessoal...")
                textarea_apres = nova_aba.query_selector("#personalization-step-text-area")
                if textarea_apres:
                    apresentacao = gerar_apresentacao(vaga["titulo"], descricao)
                    textarea_apres.click(force=True)
                    esperar(nova_aba, 0.3)
                    textarea_apres.fill(apresentacao)
                    respostas_salvas["Apresentação pessoal"] = apresentacao
                    esperar(nova_aba, 0.5)

                botoes_hab = nova_aba.query_selector_all("button[data-testid='candidate-skill']")
                if botoes_hab:
                    habilidades_disponiveis = []
                    for btn in botoes_hab:
                        try:
                            nome_el = btn.query_selector("div.sc-hmdomO")
                            if nome_el:
                                habilidades_disponiveis.append(nome_el.inner_text().strip())
                        except Exception:
                            pass
                    if habilidades_disponiveis:
                        selecionadas = selecionar_habilidades_relevantes(
                            vaga["titulo"], descricao, habilidades_disponiveis)
                        respostas_salvas["Habilidades selecionadas"] = ", ".join(selecionadas)
                        count = 0
                        for btn in botoes_hab:
                            if count >= 3:
                                break
                            try:
                                nome_el = btn.query_selector("div.sc-hmdomO")
                                if nome_el and any(
                                    nome_el.inner_text().strip().lower() == s.lower()
                                    for s in selecionadas
                                ):
                                    btn.scroll_into_view_if_needed()
                                    btn.click()
                                    count += 1
                                    esperar(nova_aba, 0.3)
                            except Exception:
                                pass

                clicar_botao(nova_aba, [
                    "button:has-text('Finalizar candidatura')",
                    "button.sc-fYKINB",
                ])
                continue

            # Modal "Finalizar" opcional
            if nova_aba.query_selector("#dialog-give-up-personalization-step"):
                log("  → Modal de apresentação (opcional), finalizando...")
                clicar_botao(nova_aba, ["#dialog-give-up-personalization-step"])
                continue

            # Botão genérico "Salvar e continuar"
            btn_salvar = nova_aba.query_selector(
                "button[name='saveAndContinueButton'], button:has-text('Salvar e continuar')"
            )
            if btn_salvar and btn_salvar.is_visible():
                log("  → Clicando Salvar e continuar...")
                btn_salvar.click()
                continue

            # Sem ação reconhecida
            log(f"  ⚠️  Etapa não reconhecida: {url_atual}")
            avancou = clicar_botao(nova_aba, [
                "button:has-text('Continuar')",
                "button:has-text('Próximo')",
                "button:has-text('Avançar')",
                "button:has-text('Salvar e continuar')",
                "button:has-text('Finalizar candidatura')",
            ])
            if not avancou:
                log("  ⚠️  Nenhum botão encontrado, encerrando etapas")
                break

        resultado["respostas"] = respostas_salvas

        if not finalizado:
            if verificar_candidatura_finalizada(nova_aba):
                resultado["status"] = "enviado"
            else:
                resultado["status"] = "preenchido_sem_confirmacao"

    except Exception as e:
        import traceback
        log(f"  ❌ Erro: {e}")
        log(traceback.format_exc())
        resultado["status"] = f"erro: {str(e)[:100]}"
        resultado["respostas"] = respostas_salvas
    finally:
        with contextlib.suppress(Exception):
            nova_aba.close()

    return resultado


# ══════════════════════════════════════════════════════════════════════════════
#  RELATÓRIO
# ══════════════════════════════════════════════════════════════════════════════

def links_ja_candidatados_gupy() -> set:
    arquivo = f"{RELATORIO_DIR}/candidaturas.json"
    if not os.path.exists(arquivo):
        return set()
    try:
        with open(arquivo, encoding="utf-8") as f:
            dados = json.load(f)
        # Suporta tanto lista plana quanto formato {candidaturas: [...]}
        if isinstance(dados, dict):
            dados = dados.get("candidaturas", [])
        return {c["link"] for c in dados if c.get("site") == "Gupy"}
    except Exception:
        return set()


def _formatar_respostas_txt(respostas: dict) -> str:
    if not respostas:
        return "    (sem perguntas respondidas)\n"
    linhas = []
    for chave, valor in respostas.items():
        if chave == "Apresentação pessoal":
            linhas.append("    ✉️  Apresentação pessoal:")
            for linha in str(valor).splitlines():
                linhas.append(f"       {linha}")
        else:
            # Quebra valores longos
            valor_str = str(valor)
            if len(valor_str) > 80:
                linhas.append(f"    📌 {chave}:")
                linhas.append(f"       {valor_str}")
            else:
                linhas.append(f"    📌 {chave}: {valor_str}")
    return "\n".join(linhas) + "\n"


def salvar_log(candidatura: dict):
    """Salva candidatura individual imediatamente após cada vaga."""
    os.makedirs(RELATORIO_DIR, exist_ok=True)
    hoje         = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    data_hoje    = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
    arquivo_json = f"{RELATORIO_DIR}/candidaturas.json"

    # ── JSON ──────────────────────────────────────────────────────────────────
    existentes = []
    if os.path.exists(arquivo_json):
        try:
            with open(arquivo_json, encoding="utf-8") as f:
                dados = json.load(f)
            # Suporta ambos os formatos
            existentes = dados.get("candidaturas", dados) if isinstance(dados, dict) else dados
        except Exception:
            existentes = []

    existentes.append(candidatura)
    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(existentes, f, ensure_ascii=False, indent=2)

    # ── TXT diário com append ─────────────────────────────────────────────────
    resumo   = f"{RELATORIO_DIR}/gupy_{hoje}.txt"
    enviadas_hoje = [c for c in existentes
                     if c.get("data") == data_hoje and c.get("site") == "Gupy"]
    enviadas = [c for c in enviadas_hoje if c["status"] == "enviado"]

    with open(resumo, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write(f"📊 GUPY — {hoje}\n{'='*50}\n\n")

        f.write(f"[{candidatura['status'].upper()}] {candidatura['vaga']} | {candidatura.get('local','')}\n")
        f.write(f"  🔗 {candidatura['link']}\n")
        f.write(f"  🕐 {candidatura.get('data','')} {candidatura.get('horario','')}\n\n")

        respostas = candidatura.get("respostas", {})
        if respostas:
            f.write("  📋 Perguntas respondidas:\n")
            f.write(_formatar_respostas_txt(respostas))
        else:
            f.write("  📋 Perguntas respondidas: (nenhuma)\n")

        f.write("\n" + "-"*50 + "\n\n")

    log(f"  📄 Relatório salvo: {resumo} | ✅ {len(enviadas)} enviadas hoje")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════╗
║       🤖 JOB HUNTER — GUPY  v1.1        ║
╚══════════════════════════════════════════╝
    """)

    hora_atual = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    if not horario_ok():
        log(f"⏰ Fora do horário comercial (7h-22h) — hora atual: {hora_atual}h. Continuando mesmo assim...")

    config = carregar_config()

    # IA configurável pela UI do Trivor (config.yaml → ia) ou via .env legado
    from common import llm as _llm
    tem_ia_ui = bool(_llm.providers_ativos(config))
    if not GROQ_API_KEY and not tem_ia_ui:
        print("❌ Sem IA configurada: crie um provedor na aba IA do Trivor (ou defina GROQ_API_KEY no .env)")
        return
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY não configurada — Gemini desativado como fallback")
    if not MISTRAL_API_KEY:
        print("⚠️  MISTRAL_API_KEY não configurada — Mistral desativado como fallback")

    ja_candidatados = links_ja_candidatados_gupy()
    log(f"📋 {len(ja_candidatados)} vagas já candidatadas anteriormente")

    b = Browser(profile="gupy", headless=False)
    try:
        b.start()
    except BrowserUnavailable as e:
        log("❌ Nenhum browser disponível — " + " | ".join(f"{n}: {r}" for n, r in e.tried))
        return
    page = b.page
    log(f"🌐 Engine no uso: {b.engine} (fallback tentado: {[n for n, _ in b.tried] or 'nenhum'})")

    if not verificar_sessao_valida(page):
        log("🔑 Sem sessão válida. Login manual necessário...")
        fazer_login_manual(page, config)
        page.goto(URL_PORTAL, timeout=15000)
        esperar(page, 2)
        if not verificar_sessao_valida(page):
            log("❌ Login falhou. Encerrando.")
            b.close()
            return
    else:
        log("✅ Sessão válida!")

    vagas       = buscar_vagas_gupy(page, config)
    vagas_novas = [v for v in vagas if v["link"] not in ja_candidatados]

    # Remove duplicatas
    vistos      = set()
    vagas_unicas = []
    for v in vagas_novas:
        if v["link"] not in vistos:
            vistos.add(v["link"])
            vagas_unicas.append(v)

    max_dia      = config["automacao"].get("max_candidaturas_por_dia", 10)
    vagas_unicas = vagas_unicas[:max_dia]

    print(f"\n🎯 Vagas novas para candidatar: {len(vagas_unicas)}")
    print("=" * 50)

    if not vagas_unicas:
        print("Nenhuma vaga nova encontrada.")
        b.close()
        return

    candidaturas   = []
    sessao_ok      = True
    RELOGIN_CADA   = 50  # verifica sessão a cada N vagas

    try:
        for i, vaga in enumerate(vagas_unicas, 1):
            print(f"\n[{i}/{len(vagas_unicas)}]")

            # ── Verifica sessão periodicamente e após sessao_expirada ────────
            if not sessao_ok or i % RELOGIN_CADA == 1:
                log("🔍 Verificando sessão...")
                if not verificar_sessao_valida(page):
                    log("🔒 Sessão expirada! Fazendo relogin automático...")
                    fazer_login_manual(page, config)
                    page.goto(URL_PORTAL, timeout=15000)
                    esperar(page, 2)
                    if not verificar_sessao_valida(page):
                        log("❌ Relogin falhou. Encerrando.")
                        break
                    log("✅ Relogin bem-sucedido!")
                sessao_ok = True

            resultado = candidatar_vaga_gupy(page, vaga, config)
            candidaturas.append(resultado)
            salvar_log(resultado)

            # Se sessão expirou durante a candidatura, força verificação na próxima
            if resultado.get("status") == "sessao_expirada":
                log("🔒 Sessão expirada durante candidatura — relogando...")
                sessao_ok = False
                continue

            if i < len(vagas_unicas):
                delay_entre_vagas(config)
    finally:
        b.close()

    print("\n" + "=" * 50)
    enviadas = [c for c in candidaturas if c["status"] == "enviado"]
    print(f"✅ Enviadas: {len(enviadas)}/{len(candidaturas)}")
    print("\n🏁 Finalizado!")


if __name__ == "__main__":
    main()
