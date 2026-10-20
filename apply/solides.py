"""
╔══════════════════════════════════════════════════════════════╗
║              🤖 JOB HUNTER — SÓLIDES  v1.4                  ║
║  Playwright · Groq/HuggingFace · Sessão salva               ║
╚══════════════════════════════════════════════════════════════╝

CORREÇÕES v1.2 (patch sobre v1.1):
  - Radio das killer questions: query_selector → query_selector_all nos labels.
    O Sólides gera DOIS labels com o mesmo for= por radio: o 1º é o círculo
    visual (sem texto), o 2º contém 'Sim'/'Não'. O código pegava sempre o 1º
    e não achava o texto, então nunca casava. Agora itera todos e usa o
    primeiro com texto não-vazio.
  - Mesmo fix aplicado no fallback _preencher_killer_questions_via_js.

CORREÇÕES v1.1:
  - Seletor das killer questions corrigido:
    ol.flex.flex-col.px-6 → ol[class*="flex"][class*="px-6"]
    (o HTML real tem "flex flex-col px-6 list-decimal", não bate com seletor composto)
  - preencher_killer_questions agora é chamado explicitamente na aba
    "Outras informações" (onde o recrutador coloca as perguntas)
  - CNH removida do preencher_outras_informacoes (já é preenchida pelo perfil
    salvo do candidato, chamá-la aqui causava clique indevido no radio)
  - Detecção de killer questions robustecida: testa múltiplos seletores
    incluindo input[id^="killerQuestion"] direto, sem depender do ol
  - Log extra para debug de radio IDs e textos das opções

Fluxo:
  1. Login com sessão salva (ou login automático na 1ª vez)
  2. Busca paginada em vagas.solides.com.br
  3. Filtra vagas por palavras-chave/exclusão/senioridade
  4. Candidatura:
     a. Abre a vaga → clica "Candidatura rápida"
     b. Modal "você está a 1 passo" → clica Sim
     c. Verifica se candidatura rápida (modal de sucesso direto)
        ou se precisa preencher currículo/perguntas/habilidades
     d. Se redireciona para o RHGestor → descarta (fora do scope)
     e. Preenche etapas: sobre você, habilidades da vaga,
        perguntas do recrutador
     f. Revisão → Salvar e Finalizar
     g. Modal de sucesso → registra como enviado
  5. Salva relatório após cada candidatura
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from groq import Groq
from playwright.sync_api import sync_playwright, Page, BrowserContext

load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

with open("config.yaml", encoding="utf-8") as _f:
    CONFIG: dict = yaml.safe_load(_f)

TZ               = ZoneInfo("America/Sao_Paulo")
CANDIDATO        = CONFIG["candidato"]
DIVERSIDADE      = CONFIG.get("diversidade", {})
LOCALIZACAO      = CONFIG.get("localizacao", {})
GROQ_MODEL       = CONFIG["groq"]["model"]
MAX_POR_DIA      = CONFIG["automacao"]["max_candidaturas_por_dia"]
DELAY_VAGAS      = CONFIG["automacao"]["delay_entre_vagas"]
PALAVRAS_CHAVE   = CONFIG["busca"]["palavras_chave"]
PALAVRAS_EXCLUIR = [p.lower() for p in CONFIG["busca"].get("palavras_excluir", [])]
TECNOLOGIAS      = CONFIG.get("tecnologias", {})

SESSION_FILE  = Path("solides_session.json")
RELATORIO_DIR = Path("relatorio")
RELATORIO_DIR.mkdir(exist_ok=True)
RELATORIO_FILE = RELATORIO_DIR / "candidaturas.json"

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Dados sensíveis do .env
_DOC_CPF        = os.getenv("CANDIDATO_CPF", "")
_END_CEP        = os.getenv("ENDERECO_CEP", "")
_END_BAIRRO     = os.getenv("ENDERECO_BAIRRO", "")
_END_LOGRADOURO = os.getenv("ENDERECO_LOGRADOURO", "")
_END_NUMERO     = os.getenv("ENDERECO_NUMERO", "")

# URLs
URL_PORTAL = "https://vagas.solides.com.br"
URL_LOGIN  = "https://auth.vagas.solides.com.br/sign-in"
URL_BUSCA  = "https://vagas.solides.com.br/vagas?title={termo}&page={pagina}"
URL_PERFIL = "https://perfil.vagas.solides.com.br"

# Credenciais Sólides (lidas do .env)
_SOLIDES_EMAIL = os.getenv("SOLIDES_EMAIL", "")
_SOLIDES_SENHA = os.getenv("SOLIDES_SENHA", "")


# ═══════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO") -> None:
    print(f"[{_now()}] [{level}] {msg}")

def log_ok(msg: str)   -> None: log(msg, "✅")
def log_err(msg: str)  -> None: log(msg, "❌")
def log_skip(msg: str) -> None: log(msg, "⏭️ ")
def log_info(msg: str) -> None: log(msg, "ℹ️ ")
def log_warn(msg: str) -> None: log(msg, "⚠️ ")


# ═══════════════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════════════

def esperar(page: Page, segundos: float, variacao: float = 0.3) -> None:
    total = max(0.2, segundos + random.uniform(-variacao * 0.3, variacao))
    page.wait_for_timeout(int(total * 1000))


def scroll_humano(page: Page) -> None:
    with suppress(Exception):
        altura = random.randint(200, 500)
        page.evaluate(f"window.scrollBy({{top: {altura}, behavior: 'smooth'}})")
        time.sleep(random.uniform(0.4, 0.8))


def horario_ok() -> bool:
    return 5 <= datetime.now(TZ).hour <= 23


def _calcular_idade() -> int:
    n = datetime.strptime(CANDIDATO["data_nascimento"], "%d/%m/%Y")
    h = datetime.now()
    return h.year - n.year - ((h.month, h.day) < (n.month, n.day))

IDADE = _calcular_idade()


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
    import urllib.request, urllib.error
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

PERFIL_COMPLETO = f"""
CANDIDATO: {CANDIDATO['nome']}
IDADE: {IDADE} anos
CIDADE: {CANDIDATO.get('cidade_uf', 'Ribeirão Preto - SP')}
EMAIL: {CANDIDATO['email']}
TELEFONE: {CANDIDATO['telefone']}
LINKEDIN: {CANDIDATO['linkedin']}
GITHUB: {CANDIDATO['github']}
PORTFOLIO: {CANDIDATO.get('portfolio', '')}
DATA NASCIMENTO: {CANDIDATO['data_nascimento']}
CPF: {_DOC_CPF}

FORMAÇÃO:
- Engenharia de Software (cursando, 1º semestre) — Estácio de Sá (EAD)
- Previsão de conclusão: 2029
- NÃO tem ensino superior completo ainda (está no 1º semestre)

EXPERIÊNCIA:
- Desenvolvedor Web Freelancer desde novembro/2022 (~2-3 anos)
- NUNCA teve emprego CLT formal
- Empresa atual: Autônomo / Freelancer

TECNOLOGIAS (nível real):
- Python: avançado/intermediário (2-3 anos, Django, DRF, Flask, automações, IA/NLP)
- PHP: avançado (2-3 anos, APIs RESTful, sistemas web)
- JavaScript: avançado (2-3 anos, lógica, DOM, consumo de APIs)
- React: intermediário (2-3 anos, frontend moderno)
- HTML: avançado (certificação B7Web)
- CSS: avançado (certificação B7Web, Tailwind, Bootstrap)
- MySQL: avançado (2-3 anos, modelagem, queries)
- PostgreSQL: básico/intermediário (uso em projetos)
- Docker: básico (containerização)
- TypeScript: básico
- Flask: básico/intermediário
- Django REST Framework: intermediário
- NumPy: básico
- Pandas: básico
- Bootstrap: avançado
- Tailwind CSS: avançado
- API REST: avançado
- Git/GitHub: avançado
- Windows: avançado

CONHECIMENTOS IMPLÍCITOS (desenvolvedor web full stack):
- Performance de sites: avançado (desenvolvimento web)
- Segurança de sites: intermediário/avançado
- WordPress (plugins/temas PHP): intermediário (tem base PHP sólida)
- SEO básico: básico/intermediário

NÃO POSSUI:
- .NET / C# / C++: nenhum
- Java / Spring: nenhum
- Mobile (iOS/Android/Flutter/Kotlin): nenhum
- Ensino superior completo: NÃO (está no 1º semestre)

IDIOMAS:
- Português: nativo
- Inglês: básico
- Espanhol: básico
- Outros: nenhum

PRETENSÃO SALARIAL:
- CLT: R$ {CANDIDATO.get('pretensao_clt', '3000')}/mês
- PJ/hora: R$ {CANDIDATO.get('pretensao_pj_hora', '22')}/hora
- PJ/mensal: R$ {CANDIDATO.get('pretensao_pj_mensal', '4500')}/mês
- Estágio: R$ {CANDIDATO.get('pretensao_estagio', '1600')}/mês

DIVERSIDADE:
- Raça/Cor: {DIVERSIDADE.get('raca_cor', 'Pardo')}
- Gênero: {DIVERSIDADE.get('genero', 'Homem cisgênero')} → valor select: cisgenero
- Orientação sexual: {DIVERSIDADE.get('orientacao_sexual', 'Heterossexual')} → valor: heterossexual
- Sexo: Masculino → valor select: male
- PCD: NÃO
- Indicado: NÃO
- Instagram: https://www.instagram.com/gabri3l.cardoso
"""


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
        f"Se é algo que ele claramente NÃO sabe (ex: .NET, Java, C++), responda 0.\n\n"
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
        log_info(f"    [killer] Pergunta de confirmação → Sim")
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
        f"- Se a pergunta pede confirmação/ciência de condição da vaga → Sim\n"
        f"- Se pede experiência/habilidade que o candidato TEM → Sim\n"
        f"- Se pede formação superior completa → Não (está no 1º semestre)\n"
        f"- Se pede experiência que NÃO TEM → Não\n"
        f"- Em caso de dúvida → Sim (melhor tentar do que desistir)\n\n"
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


# ═══════════════════════════════════════════════════════════════
#  SESSÃO
# ═══════════════════════════════════════════════════════════════

def salvar_sessao(context: BrowserContext) -> None:
    with suppress(Exception):
        context.storage_state(path=str(SESSION_FILE))
        log_ok(f"  Sessão salva em {SESSION_FILE}")


def sessao_valida(page: Page) -> bool:
    try:
        page.goto(URL_PORTAL, timeout=15000)
        page.wait_for_timeout(2000)
        src = page.content()
        # handle do login = parte local do email configurado (SOLIDES_EMAIL no .env)
        email_handle = _SOLIDES_EMAIL.split("@")[0].lower()
        return (
            (bool(email_handle) and email_handle in src.lower())
            or "avatar-menu" in src
            or "trigger-avatar-menu" in src
            or "sign-out" in src
            or page.query_selector("[data-cy='trigger-avatar-menu']") is not None
            or page.query_selector("[data-cy='avatar-menu-mobile-sign-out']") is not None
        )
    except Exception:
        return False


def _fazer_login_automatico(page: Page) -> bool:
    if not _SOLIDES_EMAIL or not _SOLIDES_SENHA:
        log_err("  SOLIDES_EMAIL ou SOLIDES_SENHA não configurados no .env!")
        return False

    try:
        log_info(f"  🔐 Fazendo login automático como {_SOLIDES_EMAIL}...")
        page.goto(URL_LOGIN, timeout=20000)
        page.wait_for_timeout(2500)

        campo_email = page.wait_for_selector(
            "input[data-testid='field-email'], input[name='email'], input[type='email']",
            timeout=8000,
        )
        if not campo_email:
            log_err("  Campo de email não encontrado")
            return False
        campo_email.click()
        campo_email.fill("")
        campo_email.type(_SOLIDES_EMAIL, delay=60)
        page.wait_for_timeout(500)

        campo_senha = page.wait_for_selector(
            "input[data-testid='field-password'], input[name='password'], input[type='password']",
            timeout=5000,
        )
        if not campo_senha:
            log_err("  Campo de senha não encontrado")
            return False
        campo_senha.click()
        campo_senha.fill("")
        campo_senha.type(_SOLIDES_SENHA, delay=60)
        page.wait_for_timeout(500)

        btn_entrar = page.query_selector(
            "button[data-testid='button-sign-in'], "
            "button[data-cy='button-sign-in'], "
            "button[type='submit']"
        )
        if not btn_entrar:
            log_err("  Botão Entrar não encontrado")
            return False

        btn_entrar.click()

        with suppress(Exception):
            page.wait_for_url(
                lambda url: "sign-in" not in url and "login" not in url,
                timeout=15000,
            )

        for _ in range(20):
            page.wait_for_timeout(500)
            url_agora = page.url

            if "sign-in" not in url_agora and "login" not in url_agora:
                log_ok(f"  ✅ Login realizado com sucesso! ({url_agora[:60]})")
                return True

            with suppress(Exception):
                src = page.content()
                if any(e in src.lower() for e in [
                    "senha incorreta", "email incorreto",
                    "credenciais inválidas", "invalid credentials",
                    "usuário não encontrado", "incorrect password",
                ]):
                    log_err("  Credenciais inválidas — verifique SOLIDES_EMAIL e SOLIDES_SENHA no .env")
                    return False

        log_err("  Timeout: não redirecionou após 10s — credenciais podem estar erradas")
        return False

    except Exception as exc:
        log_err(f"  Erro no login automático: {exc}")
        return False


def fazer_login(p) -> tuple:
    browser = p.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--start-maximized"],
    )

    if SESSION_FILE.exists():
        log_info("🔑 Sessão encontrada, carregando...")
        context = browser.new_context(
            storage_state=str(SESSION_FILE),
            no_viewport=True,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page = context.new_page()

        if sessao_valida(page):
            log_ok("✅ Sessão válida!")
            return context, browser, page

        log_warn("⚠️  Sessão expirada — fazendo login automático...")
        SESSION_FILE.unlink(missing_ok=True)
        page.close()
        context.close()

    context = browser.new_context(
        no_viewport=True,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    page = context.new_page()

    if _fazer_login_automatico(page):
        page.goto(URL_PORTAL, timeout=15000)
        page.wait_for_timeout(2000)
        salvar_sessao(context)
        log_ok("Login automático concluído! Sessão salva para próximas execuções.")
        return context, browser, page

    log_warn("Login automático falhou — abrindo browser para login manual...")
    page.goto(URL_LOGIN, timeout=15000)

    print("\n" + "═" * 60)
    print("👆 LOGIN MANUAL NECESSÁRIO:")
    print("   1. Preencha email e senha no browser aberto")
    print("   2. Quando logado no portal, pressione ENTER aqui")
    print("═" * 60)
    input("   Pressione ENTER após logar... ")
    page.wait_for_timeout(2000)

    salvar_sessao(context)
    log_ok("Login manual concluído! Sessão salva.")
    return context, browser, page


# ═══════════════════════════════════════════════════════════════
#  BUSCA DE VAGAS
# ═══════════════════════════════════════════════════════════════

def _filtrar_vaga(titulo: str, badges: list[str] | None = None) -> bool:
    t = titulo.lower()
    b = [x.lower() for x in (badges or [])]

    SENIORIDADE_BADGE  = {"pleno", "sênior", "senior", "sênior/pleno"}
    SENIORIDADE_TITULO = {"sr", "sr.", " sr ", "(sr)", "- sr", "sênior", "senior"}

    EXCLUIR_TITULO = [p for p in PALAVRAS_EXCLUIR
                      if p.lower() not in SENIORIDADE_BADGE | SENIORIDADE_TITULO]
    EXCLUIR_NIVEL_BADGE = [p for p in PALAVRAS_EXCLUIR if p.lower() in SENIORIDADE_BADGE]

    for excluir in EXCLUIR_TITULO:
        if excluir in t:
            log_skip(f"Excluída ('{excluir}' no título): {titulo}")
            return False

    for sn in SENIORIDADE_TITULO:
        if sn in t:
            nivel_baixo_titulo = any(j in t for j in ["júnior", "junior", "jr", "estágio", "estagio"])
            if not nivel_baixo_titulo:
                log_skip(f"Excluída ('{sn}' no título): {titulo}")
                return False

    nivel_baixo = any(j in b for j in ["júnior", "junior", "jr", "estágio", "estagio", "trainee", "aprendiz"])
    for excluir in EXCLUIR_NIVEL_BADGE:
        if any(excluir in badge for badge in b) and not nivel_baixo:
            log_skip(f"Excluída (badge '{excluir}'): {titulo} | badges={b}")
            return False

    return True


def buscar_vagas(page: Page) -> list[dict]:
    vagas: list[dict] = []
    links_vistos: set[str] = set()

    for termo in PALAVRAS_CHAVE:
        log(f"\n🔍 Buscando: '{termo}'")

        for pagina in range(1, 6):
            url = URL_BUSCA.format(
                termo=termo.replace(" ", "+"),
                pagina=pagina,
            )
            try:
                page.goto(url, timeout=15000)
                esperar(page, random.uniform(2, 4))
                scroll_humano(page)

                cards = page.query_selector_all("li.h-full")
                if not cards:
                    log_info(f"  Pág {pagina}: sem vagas")
                    break

                novas = 0
                for card in cards:
                    try:
                        link_el = card.query_selector("a[href*='/vaga/']")
                        if not link_el:
                            continue

                        href = link_el.get_attribute("href") or ""
                        if not href:
                            continue

                        if href.startswith("/"):
                            link = URL_PORTAL + href
                        elif href.startswith("http"):
                            link = href
                        else:
                            link = URL_PORTAL + "/" + href

                        if link in links_vistos:
                            continue

                        titulo = (link_el.get_attribute("title") or link_el.inner_text()).strip()
                        if not titulo:
                            continue

                        empresa = ""
                        emp_el = card.query_selector("[data-cy='vacancy-company-name']")
                        if emp_el:
                            empresa = emp_el.inner_text().strip()

                        local = ""
                        loc_el = card.query_selector("p.flex.items-center")
                        if loc_el:
                            local = loc_el.inner_text().strip()

                        badges = []
                        with suppress(Exception):
                            badges_raw = card.evaluate("""
                                (el) => {
                                    var result = [];
                                    var divs = el.querySelectorAll('div[class*="bg-info-500"]');
                                    divs.forEach(function(d) {
                                        var inner = d.querySelector('div');
                                        if (inner) result.push(inner.innerText.trim().toLowerCase());
                                    });
                                    return result;
                                }
                            """)
                            if isinstance(badges_raw, list):
                                badges = [b for b in badges_raw if b]

                        log_info(f"    Vaga: {titulo[:50]} | badges: {badges}")

                        if not _filtrar_vaga(titulo, badges):
                            continue

                        links_vistos.add(link)
                        vagas.append({
                            "titulo": titulo,
                            "empresa": empresa,
                            "local": local,
                            "badges": badges,
                            "link": link,
                            "termo": termo,
                            "data_coleta": datetime.now().isoformat(),
                        })
                        novas += 1

                    except Exception:
                        continue

                log_info(f"  Pág {pagina}: +{novas} | total: {len(vagas)}")

                btn_next = page.query_selector("[data-testid='pagination-next-page']:not([disabled])")
                if not btn_next:
                    break

                esperar(page, random.uniform(2, 4))

            except Exception as exc:
                log_warn(f"  Erro na pág {pagina}: {exc}")
                break

    log(f"\n📊 Total de vagas coletadas: {len(vagas)}")
    return vagas


# ═══════════════════════════════════════════════════════════════
#  FECHAR MODAIS / POPUPS
# ═══════════════════════════════════════════════════════════════

def fechar_modal_generico(page: Page) -> bool:
    seletores = [
        "button[aria-label='close-icon']",
        "button:has-text('Ok, entendi!')",
        "button:has-text('Encontrar mais vagas')",
        "button:has-text('Fechar')",
    ]
    for sel in seletores:
        with suppress(Exception):
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                esperar(page, 0.5)
                return True
    return False


def verificar_sucesso_modal(page: Page) -> bool:
    """
    Verifica candidatura com sucesso usando APENAS sinais inequívocos.
    NÃO usa 'check_circle' (aparece nas abas do currículo).
    """
    with suppress(Exception):
        url = page.url
        if any(x in url for x in ["post-apply", "success", "application-submitted"]):
            return True

    with suppress(Exception):
        src = page.content().lower()
        sinais_inequivocos = [
            "candidatura efetuada com sucesso",
            "candidatura realizada com sucesso",
            "candidatura realizada!",
            "sua candidatura na vaga",
            "foi realizada com sucesso",
            "candidatura com sucesso na vaga",
            "você receberá um e-mail com mais detalhes",
        ]
        if any(s in src for s in sinais_inequivocos):
            return True

    with suppress(Exception):
        modal_sucesso = page.query_selector(
            "[data-testid='modal-body']:has-text('Candidatura efetuada'), "
            "[data-testid='modal-body']:has-text('Candidatura realizada'), "
            ".hj-application-success"
        )
        if modal_sucesso and modal_sucesso.is_visible():
            return True

    return False


def detectar_redirecionamento_externo(page: Page) -> bool:
    with suppress(Exception):
        src = page.content()
        if "rhgestor" in src.lower() or "você será redirecionado" in src.lower():
            return True
    return False


def detectar_erro_servidor(page: Page) -> bool:
    """
    Detecta erros HTTP do servidor Sólides (500, 404 após sessão expirar).
    Esses erros aparecem como páginas HTML com textos específicos, não como
    exceções do Playwright.
    """
    with suppress(Exception):
        url = page.url
        src = page.content().lower()

        sinais_erro = [
            "internal server error",
            "500",
            "ops! desculpa, mas sua página não foi encontrada",
            "página não foi encontrada",
            "buscar vagas",           # botão da página 404 do Sólides
            "next/error",             # Next.js error page
            "application error: a client-side exception",
        ]

        # 404 só é erro de sessão se veio de uma URL do perfil/currículo
        eh_pagina_solides = any(d in url for d in [
            "perfil.vagas.solides", "vagas.solides", "solides.com.br"
        ])

        if eh_pagina_solides and any(s in src for s in sinais_erro):
            return True

        # HTTP status via response — verifica título da página
        titulo = page.title().lower() if page.title() else ""
        if any(c in titulo for c in ["500", "404", "error", "not found"]):
            return True

    return False


def tentar_reautenticar(page: Page, context) -> bool:
    """
    Tenta reautenticar quando a sessão expira no meio do fluxo.
    Faz login automático e retorna True se teve sucesso.
    """
    log_warn("  🔄 Tentando reautenticar...")
    SESSION_FILE.unlink(missing_ok=True)

    ok = _fazer_login_automatico(page)
    if ok:
        salvar_sessao(context)
        log_ok("  ✅ Reautenticado com sucesso!")
    else:
        log_err("  ❌ Reautenticação falhou — será necessário login manual na próxima execução")
    return ok


# ═══════════════════════════════════════════════════════════════
#  ETAPAS DO FORMULÁRIO DE CURRÍCULO
# ═══════════════════════════════════════════════════════════════

def _clicar_label_radio(page: Page, input_id: str) -> bool:
    with suppress(Exception):
        label = page.query_selector(f"label[for='{input_id}']")
        if label and label.is_visible():
            label.click()
            return True
    with suppress(Exception):
        inp = page.query_selector(f"#{input_id}")
        if inp:
            inp.evaluate("el => el.click()")
            return True
    return False


def preencher_informacoes_pessoais(page: Page) -> None:
    log_info("  📝 Preenchendo informações pessoais...")
    esperar(page, 1)

    c = CANDIDATO

    with suppress(Exception):
        campo = page.query_selector("input[name='about.name']")
        if campo and not campo.input_value():
            campo.fill(c["nome"])

    with suppress(Exception):
        campo = page.query_selector("input[name='about.cpf']")
        if campo and not campo.input_value():
            campo.fill(_DOC_CPF)

    with suppress(Exception):
        tel = c["telefone"].replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        ddd = tel[:2]
        numero = tel[2:]
        campo_ddd = page.query_selector("input[name='about.phone_ddd']")
        campo_tel = page.query_selector("input[name='about.phone']")
        if campo_ddd and not campo_ddd.input_value():
            campo_ddd.fill(ddd)
        if campo_tel and not campo_tel.input_value():
            campo_tel.fill(numero)

    with suppress(Exception):
        campo = page.query_selector("input[name='about.birthday']")
        if campo and not campo.input_value():
            campo.fill(c["data_nascimento"])

    with suppress(Exception):
        campo = page.query_selector("input[name='about.linkedin']")
        if campo and not campo.input_value():
            campo.fill(c["linkedin"])

    with suppress(Exception):
        _clicar_label_radio(page, "hasSpecialNeedsRadio_child_2")

    esperar(page, 0.5)


def preencher_diversidade(page: Page) -> None:
    log_info("  🌈 Preenchendo diversidade...")

    with suppress(Exception):
        page.select_option("select[name='about.sex']", value="male")

    raca_map = {"pardo": "parda", "branco": "branca", "preto": "preta",
                "amarelo": "amarela", "indígena": "indígena"}
    raca_cfg = DIVERSIDADE.get("raca_cor", "Pardo").lower()
    raca_val = raca_map.get(raca_cfg, "parda")
    with suppress(Exception):
        page.select_option("select[name='about.ethnicity']", value=raca_val)

    with suppress(Exception):
        page.select_option("select[name='about.sexual_orientation']", value="heterossexual")

    with suppress(Exception):
        page.select_option("select[name='about.gender']", value="cisgenero")

    esperar(page, 0.5)


def preencher_outras_informacoes(page: Page) -> None:
    """
    Preenche 'Outras informações' (endereço, pretensão, redes sociais, etc).

    NOTA: CNH foi removida daqui — ela já é preenchida automaticamente pelo
    perfil salvo do candidato no Sólides. Chamá-la aqui gerava clique indevido
    no radio e era confundido com uma "killer question".
    """
    log_info("  📋 Preenchendo outras informações...")
    esperar(page, 0.5)

    c = CANDIDATO

    # Portfólio / vídeo
    with suppress(Exception):
        campo = page.query_selector("input[name='other.portfolioUrl']")
        if campo:
            val = campo.input_value() or ""
            if not val:
                campo.fill(c.get("portfolio", ""))

    # RG
    rg = os.getenv("CANDIDATO_RG", "")
    with suppress(Exception):
        campo = page.query_selector("input[name='other.rg']")
        if campo and not (campo.input_value() or "").strip() and rg:
            campo.fill(rg)

    # CEP
    with suppress(Exception):
        campo = page.query_selector("input[name='other.zipCode']")
        if campo and not (campo.input_value() or "").strip() and _END_CEP:
            campo.fill(_END_CEP)
            esperar(page, 1.5)  # aguarda preenchimento automático por CEP

    # Bairro
    with suppress(Exception):
        campo = page.query_selector("input[name='other.district']")
        if campo and not (campo.input_value() or "").strip() and _END_BAIRRO:
            campo.fill(_END_BAIRRO)

    # Rua
    with suppress(Exception):
        campo = page.query_selector("input[name='other.street']")
        if campo and not (campo.input_value() or "").strip() and _END_LOGRADOURO:
            campo.fill(_END_LOGRADOURO)

    # Número
    with suppress(Exception):
        campo = page.query_selector("input[name='other.number']")
        if campo and not (campo.input_value() or "").strip() and _END_NUMERO:
            campo.fill(_END_NUMERO)

    # Pretensão salarial
    with suppress(Exception):
        campo = page.query_selector("input[name='other.salaryExpectation']")
        if campo and not (campo.input_value() or "").strip():
            campo.fill(f"R$ {c.get('pretensao_clt', '3000')},00")

    # Estado civil — Solteiro
    with suppress(Exception):
        page.select_option("select[name='other.maritalStatus']", value="solteiro")

    # Instagram
    with suppress(Exception):
        campo = page.query_selector("input[name='other.instagram']")
        if campo and not (campo.input_value() or "").strip():
            campo.fill("https://www.instagram.com/gabri3l.cardoso")

    # Indicação — Não (radio "nao")
    with suppress(Exception):
        _clicar_label_radio(page, "hasRecommendation_child_2")

    esperar(page, 0.5)


def preencher_habilidades_vaga(page: Page, titulo_vaga: str, descricao: str) -> None:
    log_info("  🔧 Preenchendo habilidades da vaga...")
    esperar(page, 0.5)

    ctx = f"Vaga: {titulo_vaga} | {descricao[:200]}"

    grupos = page.query_selector_all("div.flex.flex-col.items-start.gap-2")

    for grupo in grupos:
        try:
            label_el = grupo.query_selector("label.font-semibold")
            if not label_el:
                continue

            nome_hab = label_el.inner_text().strip()
            if not nome_hab:
                continue

            nivel = ia_nivel_habilidade(nome_hab, ctx)
            log_info(f"    {nome_hab} → {_nivel_para_texto(nivel)}")

            radios = grupo.query_selector_all("input[type='radio']")
            if not radios:
                continue

            alvo = None
            for radio in radios:
                val = radio.get_attribute("value") or ""
                if val == str(nivel):
                    alvo = radio
                    break

            if not alvo and radios:
                alvo = radios[0]

            if alvo:
                radio_id = alvo.get_attribute("id") or ""
                if radio_id:
                    lbl = page.query_selector(f"label[for='{radio_id}']")
                    if lbl:
                        lbl.scroll_into_view_if_needed()
                        lbl.click()
                        esperar(page, 0.3)
                        continue
                alvo.evaluate("el => el.click()")
                esperar(page, 0.3)

        except Exception as exc:
            log_warn(f"    Erro em habilidade: {exc}")


def _detectar_killer_questions(page: Page) -> bool:
    """
    Verifica se há killer questions na página atual.

    Usa múltiplas estratégias para ser robusto:
    1. Input com id começando por killerQuestion (mais confiável)
    2. OL com classe flex e px-6 (seletor corrigido com contains)
    3. Título de seção "Perguntas ao recrutador"
    """
    # Estratégia 1: inputs diretos (mais confiável — o ID é definido pelo Sólides)
    with suppress(Exception):
        inp = page.query_selector("input[id^='killerQuestionSingle_']")
        if inp:
            log_info("    [KQ detectada] via input[id^='killerQuestionSingle_']")
            return True

    # Estratégia 2: OL com classes flex e px-6
    # O seletor CSS composto ol.flex.flex-col.px-6 falha porque o elemento tem
    # TAMBÉM a classe list-decimal — no Playwright cada ponto é um AND de classes,
    # então funciona. O problema era que a ordem importa: usamos :is() para garantir.
    with suppress(Exception):
        ol = page.query_selector("ol.list-decimal")
        if ol:
            log_info("    [KQ detectada] via ol.list-decimal")
            return True

    # Estratégia 3: título de seção
    with suppress(Exception):
        resultado = page.evaluate("""
            () => {
                var btns = document.querySelectorAll('button h6, h6');
                for (var el of btns) {
                    if (el.textContent && el.textContent.includes('Perguntas ao recrutador')) {
                        return true;
                    }
                }
                return false;
            }
        """)
        if resultado:
            log_info("    [KQ detectada] via título 'Perguntas ao recrutador'")
            return True

    return False


def preencher_killer_questions(page: Page, titulo_vaga: str, descricao: str) -> None:
    """
    Preenche as killer questions (perguntas do recrutador).

    CORREÇÃO PRINCIPAL v1.1:
    - Seletor do <ol> corrigido: usa ol.list-decimal (presente no HTML real)
      em vez de ol.flex.flex-col.px-6 (falha quando há mais classes no elemento)
    - Expande a seção antes de tentar interagir
    - Busca os <li> tanto pelo ol quanto diretamente pelos inputs killerQuestion
    - Log detalhado de cada radio ID encontrado para facilitar debug
    """
    log_info("  ❓ Preenchendo killer questions...")
    ctx = f"Vaga: {titulo_vaga} | {descricao[:300]}"
    esperar(page, 0.5)

    # ── 1. Expande a seção "Perguntas ao recrutador" se colapsada ──
    with suppress(Exception):
        page.evaluate("""
            () => {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var h6 = b.querySelector('h6');
                    if (h6 && h6.textContent && h6.textContent.includes('Perguntas ao recrutador')) {
                        var sibling = b.closest('div') && b.closest('div').nextElementSibling;
                        if (!sibling) sibling = b.parentElement && b.parentElement.nextElementSibling;
                        if (sibling) {
                            var style = window.getComputedStyle(sibling);
                            if (style.maxHeight === '0px' || style.display === 'none') {
                                b.click();
                            }
                        } else {
                            // Clica mesmo sem checar — se já aberto, clica de novo,
                            // mas isso é controlado pelo estado React
                            b.click();
                        }
                        break;
                    }
                }
            }
        """)
        esperar(page, 0.8)

    # ── 2. Verifica se há killer questions ────────────────────────
    if not _detectar_killer_questions(page):
        log_info("    Nenhuma killer question encontrada nesta página")
        return

    # ── 3. Coleta os <li> de perguntas ────────────────────────────
    # Tenta pelo <ol> com list-decimal primeiro, depois fallback por contexto
    itens = page.query_selector_all("ol.list-decimal > li")
    if not itens:
        # Fallback: qualquer <ol> dentro de um card que tenha inputs killerQuestion
        itens = page.query_selector_all("ol > li:has(input[id^='killerQuestionSingle_'])")

    if not itens:
        # Último fallback: pega os itens via JS para garantir
        qtd = page.evaluate("""
            () => {
                var ol = document.querySelector('ol.list-decimal');
                return ol ? ol.querySelectorAll('li').length : 0;
            }
        """)
        log_warn(f"    query_selector_all retornou 0, mas JS vê {qtd} itens")
        if qtd == 0:
            return
        # Usa avaliação JS para processar diretamente
        _preencher_killer_questions_via_js(page, titulo_vaga, descricao)
        return

    log_info(f"    {len(itens)} killer question(s) encontrada(s)")

    for i, item in enumerate(itens):
        try:
            textarea = item.query_selector("textarea")
            radios   = item.query_selector_all("input[type='radio']")

            # Extrai o texto da pergunta — tenta várias formas
            pergunta = ""
            for sel in ["label p", "p", "label", "span"]:
                el = item.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    if txt and len(txt) > 5:
                        pergunta = txt
                        break

            if not pergunta:
                # Fallback JS
                pergunta = item.evaluate("el => el.querySelector('p,label,span')?.innerText?.trim() || ''")

            if not pergunta:
                log_warn(f"    Item {i+1}: não conseguiu extrair texto da pergunta — pulando")
                continue

            log_info(f"    Q{i+1}: {pergunta[:80]}")

            # ── Textarea (pergunta aberta) ──────────────────────
            if textarea:
                resposta = ia_responder_killer_question_texto(pergunta, ctx)
                ta_name = textarea.get_attribute("name") or ""
                ta_id   = textarea.get_attribute("id") or ""
                seletor = f"textarea[name='{ta_name}']" if ta_name else (
                    f"textarea[id='{ta_id}']" if ta_id else "textarea"
                )
                page.evaluate("""
                    ([selector, value]) => {
                        var el = document.querySelector(selector);
                        if (!el) { el = document.querySelector('textarea'); }
                        if (!el) return;
                        var proto = window.HTMLTextAreaElement.prototype;
                        var setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                        if (setter) setter.call(el, value);
                        else el.value = value;
                        ['focus','input','change','blur'].forEach(function(ev) {
                            el.dispatchEvent(new Event(ev, {bubbles: true}));
                        });
                    }
                """, [seletor, resposta])
                log_ok(f"    → {resposta[:60]}")
                esperar(page, 0.4)

            # ── Radio (Sim/Não) ─────────────────────────────────
            elif radios:
                resposta = ia_responder_killer_question_radio(pergunta)
                log_info(f"    → Resposta decidida: '{resposta}'")

                # Coleta os IDs e textos de TODAS as opções.
                # ATENÇÃO: o Sólides gera DOIS labels com o mesmo for= por radio:
                #   1º label — círculo visual (sem texto, apenas layout)
                #   2º label — class="flex-1 text-gray-800" com <p>Sim</p> / <p>Não</p>
                # query_selector() retorna sempre o 1º (vazio), por isso usamos
                # query_selector_all() e pegamos o primeiro label que tem texto.
                opcoes: list[dict] = []
                for radio in radios:
                    rid  = radio.get_attribute("id") or ""
                    rval = radio.get_attribute("value") or ""
                    rtxt = ""
                    if rid:
                        todos_labels = page.query_selector_all(f"label[for='{rid}']")
                        for lbl in todos_labels:
                            p_el = lbl.query_selector("p")
                            candidato_txt = (p_el.inner_text() if p_el else lbl.inner_text()).strip()
                            if candidato_txt:
                                rtxt = candidato_txt
                                break
                    opcoes.append({"id": rid, "value": rval, "texto": rtxt})

                log_info(f"    Opções disponíveis: {opcoes}")

                clicou = False
                for opcao in opcoes:
                    rid  = opcao["id"]
                    rtxt = opcao["texto"]

                    if not rtxt and not rid:
                        continue

                    # Verifica match por texto ("Sim" / "Não")
                    match_texto = rtxt.lower() == resposta.lower()
                    # Match por value ("sim" / "nao" / "s" / "n")
                    match_value = (
                        opcao["value"].lower() in [resposta.lower(), resposta[0].lower()]
                        or (resposta == "Sim" and opcao["value"].lower() in ["sim", "yes", "s", "true", "1"])
                        or (resposta == "Não" and opcao["value"].lower() in ["nao", "não", "no", "n", "false", "0"])
                    )

                    if match_texto or match_value:
                        # Tenta via label
                        if rid:
                            lbl = page.query_selector(f"label[for='{rid}']")
                            if lbl:
                                try:
                                    lbl.scroll_into_view_if_needed()
                                    lbl.click(force=True)
                                    clicou = True
                                    log_ok(f"    ✅ Clicou label[for='{rid}'] texto='{rtxt}'")
                                except Exception:
                                    pass

                        # Fallback JS se o click do Playwright falhou
                        if not clicou and rid:
                            resultado_js = page.evaluate(f"""
                                () => {{
                                    var lbl = document.querySelector('label[for="{rid}"]');
                                    if (lbl) {{ lbl.click(); return 'label_click'; }}
                                    var inp = document.getElementById('{rid}');
                                    if (inp) {{
                                        inp.checked = true;
                                        ['click','change','input'].forEach(function(ev) {{
                                            inp.dispatchEvent(new MouseEvent(ev, {{bubbles: true, cancelable: true}}));
                                        }});
                                        return 'input_events';
                                    }}
                                    return 'not_found';
                                }}
                            """)
                            if resultado_js != "not_found":
                                clicou = True
                                log_ok(f"    ✅ JS fallback: {resultado_js} para '{rid}'")

                        if clicou:
                            esperar(page, 0.5)
                            break

                if not clicou:
                    log_warn(f"    ⚠️ Nenhuma opção casou com '{resposta}' | opcoes={opcoes}")

        except Exception as exc:
            log_warn(f"    Erro em killer question item {i+1}: {exc}")


def _preencher_killer_questions_via_js(page: Page, titulo_vaga: str, descricao: str) -> None:
    """
    Fallback: processa killer questions via JS quando query_selector_all não encontra os <li>.
    Coleta todas as perguntas e responde diretamente manipulando o DOM.
    """
    log_info("    [KQ fallback JS] processando via JavaScript...")
    ctx = f"Vaga: {titulo_vaga} | {descricao[:300]}"

    perguntas_info = page.evaluate("""
        () => {
            var result = [];
            var ol = document.querySelector('ol.list-decimal');
            if (!ol) return result;
            var items = ol.querySelectorAll('li');
            items.forEach(function(li, idx) {
                var pergunta = '';
                var p = li.querySelector('p');
                if (p) pergunta = p.innerText.trim();
                if (!pergunta) {
                    var lbl = li.querySelector('label');
                    if (lbl) pergunta = lbl.innerText.trim();
                }
                var radios = [];
                li.querySelectorAll('input[type="radio"]').forEach(function(r) {
                    // Dois labels por radio no Sólides — pega o que tem texto
                    var ptxt = '';
                    var allLbls = document.querySelectorAll('label[for="' + r.id + '"]');
                    for (var l = 0; l < allLbls.length; l++) {
                        var p = allLbls[l].querySelector('p');
                        var t = p ? p.innerText.trim() : allLbls[l].innerText.trim();
                        if (t) { ptxt = t; break; }
                    }
                    radios.push({id: r.id, value: r.value, texto: ptxt});
                });
                var temTextarea = !!li.querySelector('textarea');
                var taName = temTextarea ? (li.querySelector('textarea').name || '') : '';
                result.push({idx: idx, pergunta: pergunta, radios: radios,
                             temTextarea: temTextarea, taName: taName});
            });
            return result;
        }
    """)

    if not perguntas_info:
        log_warn("    [KQ fallback JS] nenhuma pergunta encontrada via JS")
        return

    for info in perguntas_info:
        pergunta = info.get("pergunta", "")
        if not pergunta:
            continue

        log_info(f"    [JS] Q: {pergunta[:80]}")

        if info.get("temTextarea"):
            resposta = ia_responder_killer_question_texto(pergunta, ctx)
            ta_name = info.get("taName", "")
            seletor = f"textarea[name='{ta_name}']" if ta_name else "textarea"
            page.evaluate("""
                ([selector, value]) => {
                    var el = document.querySelector(selector);
                    if (!el) return;
                    var setter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, value);
                    else el.value = value;
                    ['focus','input','change','blur'].forEach(function(ev) {
                        el.dispatchEvent(new Event(ev, {bubbles: true}));
                    });
                }
            """, [seletor, resposta])
            log_ok(f"    [JS] → {resposta[:60]}")

        elif info.get("radios"):
            radios = info["radios"]
            resposta = ia_responder_killer_question_radio(pergunta)
            log_info(f"    [JS] → '{resposta}' | radios={radios}")

            for opcao in radios:
                rid  = opcao.get("id", "")
                rtxt = opcao.get("texto", "")
                rval = opcao.get("value", "")

                match_t = rtxt.lower() == resposta.lower()
                match_v = (
                    rval.lower() in [resposta.lower(), resposta[0].lower()]
                    or (resposta == "Sim" and rval.lower() in ["sim", "yes", "s", "true", "1"])
                    or (resposta == "Não" and rval.lower() in ["nao", "não", "no", "n", "false", "0"])
                )

                if (match_t or match_v) and rid:
                    page.evaluate(f"""
                        () => {{
                            var lbl = document.querySelector('label[for="{rid}"]');
                            if (lbl) {{ lbl.click(); return; }}
                            var inp = document.getElementById('{rid}');
                            if (inp) {{
                                inp.checked = true;
                                ['click','change','input'].forEach(function(ev) {{
                                    inp.dispatchEvent(new MouseEvent(ev, {{bubbles:true}}));
                                }});
                            }}
                        }}
                    """)
                    log_ok(f"    [JS] ✅ Clicou rid={rid} texto='{rtxt}'")
                    esperar(page, 0.4)
                    break

        esperar(page, 0.3)


# ═══════════════════════════════════════════════════════════════
#  MODAL DE INDICAÇÃO
# ═══════════════════════════════════════════════════════════════

def tratar_modal_indicacao(page: Page) -> bool:
    """
    Trata o modal 'Você possui indicação?' — sempre responde Não.
    Retorna True se a candidatura foi efetivamente enviada.
    """
    try:
        modal = page.query_selector(
            "#headlessui-portal-root [data-testid='modal-body'], "
            "[data-testid='modal-body']"
        )
        if not modal:
            return False

        titulo_el = modal.query_selector("h5")
        if not titulo_el:
            return False
        titulo_txt = titulo_el.inner_text().lower()
        if "indicação" not in titulo_txt and "recomenda" not in titulo_txt:
            return False

        log_info("  Modal de indicação detectado → selecionando Não via JS")

        clicou = page.evaluate("""
            () => {
                var radios = document.querySelectorAll('input[name="hasRecommendation"]');
                for (var r of radios) {
                    if (r.value === 'nao') {
                        var lbl = document.querySelector('label[for="' + r.id + '"]');
                        if (lbl) {
                            lbl.click();
                        } else {
                            r.checked = true;
                            r.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                            r.dispatchEvent(new Event('change', {bubbles: true}));
                            r.dispatchEvent(new Event('input', {bubbles: true}));
                        }
                        return r.value;
                    }
                }
                return null;
            }
        """)
        log_info(f"  Radio 'Não' JS result: {clicou}")
        esperar(page, 1.0)

        btn_ok = False
        for _ in range(16):
            esperar(page, 0.5)
            habilitado = page.evaluate("""
                () => {
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var txt = (b.innerText || b.textContent || '').trim();
                        if (txt === 'Efetuar candidatura') {
                            return !b.disabled && b.offsetParent !== null;
                        }
                    }
                    return null;
                }
            """)
            if habilitado:
                btn_ok = True
                log_ok("  Botão 'Efetuar candidatura' habilitou!")
                break
            log_info(f"  Aguardando botão habilitar... ({_ + 1}/16)")

        if not btn_ok:
            log_warn("  Botão não habilitou — tentando forçar estado via React")
            page.evaluate("""
                () => {
                    var radios = document.querySelectorAll('input[name="hasRecommendation"]');
                    for (var r of radios) {
                        if (r.value === 'nao') {
                            var keys = Object.keys(r);
                            for (var k of keys) {
                                if (k.startsWith('__reactFiber') || k.startsWith('__reactProps')) {
                                    try {
                                        var fiber = r[k];
                                        if (fiber && fiber.onChange) {
                                            fiber.onChange({target: r, currentTarget: r});
                                        }
                                    } catch(e) {}
                                }
                            }
                            r.checked = true;
                            ['click','change','input'].forEach(function(ev) {
                                r.dispatchEvent(new Event(ev, {bubbles: true}));
                            });
                            break;
                        }
                    }
                }
            """)
            esperar(page, 1.5)

        clicou_btn = page.evaluate("""
            () => {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var txt = (b.innerText || b.textContent || '').trim();
                    if (txt === 'Efetuar candidatura') {
                        if (!b.disabled) {
                            b.click();
                            return 'clicked';
                        }
                        return 'still_disabled';
                    }
                }
                return 'not_found';
            }
        """)
        log_info(f"  Botão 'Efetuar candidatura' JS result: {clicou_btn}")

        if clicou_btn == "still_disabled":
            log_warn("  Botão ainda disabled — candidatura não enviada pelo modal")
            return False

        if clicou_btn == "not_found":
            log_warn("  Botão não encontrado")
            return False

        esperar(page, 3)

        if verificar_sucesso_modal(page):
            log_ok("  ✅ Candidatura confirmada pelo modal de indicação!")
            return True

        log_info("  Modal tratado mas sucesso não confirmado — loop principal verifica")
        return False

    except Exception as exc:
        log_warn(f"  Erro no modal de indicação: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════
#  FLUXO PRINCIPAL DE CANDIDATURA
# ═══════════════════════════════════════════════════════════════

def candidatar_vaga(page: Page, vaga: dict) -> dict:
    now = datetime.now(TZ)
    resultado: dict = {
        "vaga":    vaga["titulo"],
        "empresa": vaga.get("empresa", ""),
        "link":    vaga["link"],
        "local":   vaga.get("local", ""),
        "site":    "Solides",
        "status":  "erro",
        "data":    now.strftime("%d/%m/%Y"),
        "horario": now.strftime("%H:%M:%S"),
    }

    log(f"\n🎯 {vaga['titulo']} — {vaga.get('empresa', '')}")

    try:
        # ── 1. Abre a vaga ──────────────────────────────────────
        page.goto(vaga["link"], timeout=20000)
        esperar(page, random.uniform(2, 3))

        if "application error" in page.content().lower() or detectar_erro_servidor(page):
            log_err("  Erro de servidor / sessão expirada na página da vaga")
            resultado["status"] = "sessao_expirada"
            return resultado

        descricao = ""
        with suppress(Exception):
            desc_el = page.query_selector("[data-cy='description']")
            if desc_el:
                descricao = desc_el.inner_text()[:1500]

        # ── Verificação de nível via badge da página da vaga ─────
        badges_vaga: list[str] = []
        with suppress(Exception):
            badges_vaga = page.evaluate("""
                () => {
                    var result = [];
                    var divs = document.querySelectorAll('div[class*="bg-info-500"]');
                    divs.forEach(function(d) {
                        var inner = d.querySelector('div');
                        if (inner) result.push(inner.innerText.trim().toLowerCase());
                    });
                    return result;
                }
            """) or []

        if badges_vaga:
            log_info(f"  Badges da vaga: {badges_vaga}")
            if not _filtrar_vaga(vaga["titulo"], badges_vaga):
                log_skip(f"  ⏭️  Vaga descartada na página (badge confirma nível indesejado)")
                resultado["status"] = "nivel_excluido"
                return resultado

        # ── Verificação de tecnologias excluídas na descrição ─────
        EXCLUIR_SEMPRE = [p for p in PALAVRAS_EXCLUIR
                          if p.lower() not in {"pleno", "sênior", "senior", "sr", "sr.", "sênior/pleno"}]
        desc_lower = descricao.lower()
        for excluir in EXCLUIR_SEMPRE:
            if excluir in desc_lower:
                contexto_obrigatorio = any(
                    excluir in linha.lower()
                    for linha in descricao.split("\n")
                    if any(req in linha.lower() for req in [
                        "requisito", "obrigatório", "necessário", "você precisa",
                        "exigido", "experiência com", "experiência comprovada",
                        "conhecimento em", "domínio", "required",
                    ])
                )
                if contexto_obrigatorio:
                    log_skip(f"  ⏭️  Vaga descartada ('{excluir}' é requisito obrigatório na descrição)")
                    resultado["status"] = "tecnologia_excluida"
                    return resultado

        # ── 2. Clica em "Candidatura rápida" ────────────────────
        btn_rapida   = page.query_selector("button:has-text('Candidatura rápida')")
        btn_revisada = page.query_selector("button:has-text('Candidatura revisada')")

        if not btn_rapida and not btn_revisada:
            btn_rapida = page.query_selector("button:has-text('Quero me candidatar')")

        if not btn_rapida and not btn_revisada:
            src_lower = page.content().lower()
            if any(x in src_lower for x in [
                "excluir candidatura", "sua candidatura foi realizada",
                "candidatura já realizada", "você já se candidatou",
            ]):
                log_skip("  Já candidatado anteriormente")
                resultado["status"] = "ja_candidatado"
            else:
                log_skip("  Nenhum botão de candidatura encontrado")
                resultado["status"] = "sem_botao"
            return resultado

        if btn_rapida:
            btn_rapida.scroll_into_view_if_needed()
            btn_rapida.click()
            esperar(page, 1.5)
        elif btn_revisada:
            btn_revisada.scroll_into_view_if_needed()
            btn_revisada.click()
            esperar(page, 1.5)

        # ── 3. Modal "Você está a 1 passo" ──────────────────────
        modal_1passo = page.query_selector("button:has-text('Sim')")
        if modal_1passo and modal_1passo.is_visible():
            log_info("  Modal '1 passo' detectado → clicando Sim")
            modal_1passo.click()
            esperar(page, 2)

        # ── 4. Verifica candidatura direta ───────────────────────
        if verificar_sucesso_modal(page):
            log_ok("  ✅ Candidatura realizada diretamente!")
            resultado["status"] = "enviado"
            fechar_modal_generico(page)
            return resultado

        # ── 5. Detecta redirecionamento externo (RHGestor) ───────
        if detectar_redirecionamento_externo(page):
            log_skip("  ⏭️  Redirecionamento para site externo (RHGestor) — descartando")
            resultado["status"] = "externo_rhgestor"
            btn_cancel = page.query_selector("button:has-text('Cancelar')")
            if btn_cancel:
                btn_cancel.click()
            return resultado

        # ── 6. Modal de indicação ────────────────────────────────
        if tratar_modal_indicacao(page):
            log_ok("  ✅ Candidatura realizada via modal indicação!")
            resultado["status"] = "enviado"
            fechar_modal_generico(page)
            return resultado

        esperar(page, 2)
        if verificar_sucesso_modal(page):
            log_ok("  ✅ Candidatura realizada!")
            resultado["status"] = "enviado"
            fechar_modal_generico(page)
            return resultado

        # ── 7. Verifica redirecionamento para currículo ──────────
        esperar(page, 2)
        url_atual = page.url

        if "perfil.vagas.solides" not in url_atual and "curriculo" not in url_atual:
            if verificar_sucesso_modal(page):
                log_ok("  ✅ Candidatura realizada!")
                resultado["status"] = "enviado"
                fechar_modal_generico(page)
                return resultado
            log_warn(f"  URL inesperada: {url_atual[:80]}")
            resultado["status"] = "url_inesperada"
            return resultado

        log_info(f"  → Redirecionado para currículo: {url_atual[:80]}")

        if "application error" in page.content().lower() or detectar_erro_servidor(page):
            log_err("  Erro de servidor / sessão expirada no perfil")
            resultado["status"] = "sessao_expirada"
            return resultado

        # ── 8. Percorre as etapas do currículo ───────────────────
        MAX_ITERACOES = 20
        etapa_anterior = ""
        repeticoes = 0

        for iteracao in range(MAX_ITERACOES):
            esperar(page, 1.5)
            url_atual = page.url
            src = page.content()

            log_info(f"  Iter {iteracao+1}/{MAX_ITERACOES} — {url_atual.split('?')[0][-50:]}")

            if verificar_sucesso_modal(page):
                log_ok("  ✅ Candidatura finalizada com sucesso!")
                resultado["status"] = "enviado"
                fechar_modal_generico(page)
                return resultado

            if "application error" in src.lower() or detectar_erro_servidor(page):
                log_err("  Erro de servidor / sessão expirada no loop")
                resultado["status"] = "sessao_expirada"
                return resultado

            eh_review = (
                "aba=review" in url_atual
                or "revisao" in url_atual.lower()
                or (
                    "curriculo" in url_atual
                    and "salvar e finalizar" in src.lower()
                    and page.query_selector("button:has-text('Salvar e Finalizar')") is not None
                )
            )
            eh_curriculo = "curriculo" in url_atual and not eh_review

            # Anti-loop — fingerprint inclui campos obrigatórios vazios
            # (URL sozinha não muda entre iterações de revisão)
            _fp_vazios = ""
            with suppress(Exception):
                _fp_vazios = page.evaluate(
                    """() => [...document.querySelectorAll("""
                    """'input[required],select[required],textarea[required]')]"""
                    """.filter(el => !el.value)"""
                    """.map(el => el.name||el.id||'?').join(',') """
                ) or ""
            etapa_id = url_atual + "|" + _fp_vazios
            if etapa_id == etapa_anterior:
                repeticoes += 1
                if repeticoes >= 4:
                    log_err("  Anti-loop: etapa travada 4x — abortando")
                    resultado["status"] = "travado"
                    return resultado
            else:
                repeticoes = 0
                etapa_anterior = etapa_id

            # ── ETAPA DE REVISÃO ──────────────────────────────────
            if eh_review:
                log_info("  → Etapa: REVISÃO")

                if tratar_modal_indicacao(page):
                    log_ok("  ✅ Candidatura realizada via modal indicação!")
                    resultado["status"] = "enviado"
                    fechar_modal_generico(page)
                    return resultado
                esperar(page, 1)
                if verificar_sucesso_modal(page):
                    log_ok("  ✅ Candidatura realizada!")
                    resultado["status"] = "enviado"
                    fechar_modal_generico(page)
                    return resultado

                # ── Diagnóstico: campos / KQ ainda pendentes na revisão ──
                # O site bloqueia o submit silenciosamente quando há campos vazios
                # ou killer questions não respondidas. Identificamos e corrigimos
                # ANTES de clicar "Salvar e Finalizar" para não ficar em loop.
                _diag = {}
                with suppress(Exception):
                    _diag = page.evaluate("""
                        () => {
                            var abasErro = [];
                            document.querySelectorAll('button').forEach(function(b) {
                                if (b.querySelector('span[data-icon="error_outline"]')) {
                                    var t = b.innerText.trim();
                                    if (t) abasErro.push(t);
                                }
                            });
                            var vazios = [...document.querySelectorAll(
                                'input[required],select[required],textarea[required]')]
                                .filter(function(el) { return !el.value; })
                                .map(function(el) {
                                    return (el.name || el.id || el.placeholder || '?').substring(0,40);
                                });
                            var kqPend = [];
                            var grupos = {};
                            document.querySelectorAll('input[id^="killerQuestionSingle_"]')
                                .forEach(function(r) {
                                    if (!grupos[r.name]) grupos[r.name] = [];
                                    grupos[r.name].push(r);
                                });
                            Object.values(grupos).forEach(function(g) {
                                if (!g.some(function(r) { return r.checked; })) {
                                    kqPend.push(g[0].name);
                                }
                            });
                            return {abasErro: abasErro, vazios: vazios, kqPend: kqPend};
                        }
                    """) or {}

                _abas_erro = _diag.get("abasErro", [])
                _vazios    = _diag.get("vazios", [])
                _kq_pend   = _diag.get("kqPend", [])

                if _abas_erro or _vazios or _kq_pend:
                    log_warn(f"  [REVISÃO] Abas c/ erro: {_abas_erro}")
                    log_warn(f"  [REVISÃO] Campos vazios: {_vazios}")
                    log_warn(f"  [REVISÃO] KQ pendentes: {_kq_pend}")

                    # Responde KQ diretamente se visíveis na página
                    if _kq_pend and _detectar_killer_questions(page):
                        log_info("  [REVISÃO] Respondendo KQ pendentes...")
                        preencher_killer_questions(page, vaga["titulo"], descricao)
                        esperar(page, 1)

                    # Navega para a aba com erro e repreenche
                    if _abas_erro:
                        _aba = _abas_erro[0].lower()
                        log_info(f"  [REVISÃO] Voltando à aba '{_aba}' para corrigir")
                        with suppress(Exception):
                            for _btn_aba in page.query_selector_all(
                                "div.flex.items-center.justify-around button"
                            ):
                                if _aba in _btn_aba.inner_text().lower():
                                    _btn_aba.click()
                                    esperar(page, 1.5)
                                    if "outras" in _aba:
                                        preencher_outras_informacoes(page)
                                        if _detectar_killer_questions(page):
                                            preencher_killer_questions(page, vaga["titulo"], descricao)
                                    elif "sobre" in _aba:
                                        preencher_informacoes_pessoais(page)
                                        preencher_diversidade(page)
                                    elif "habilidade" in _aba:
                                        preencher_habilidades_vaga(page, vaga["titulo"], descricao)
                                    esperar(page, 0.8)
                                    _tentar_avancar(page)
                                    esperar(page, 2)
                                    break
                        continue  # volta ao topo do loop para re-detectar etapa

                btn_finalizar = page.query_selector("button:has-text('Salvar e Finalizar')")
                if btn_finalizar and btn_finalizar.is_visible():
                    btn_finalizar.scroll_into_view_if_needed()
                    btn_finalizar.click()
                    esperar(page, 3)
                    log_info("  Clicou Salvar e Finalizar")
                    continue
                else:
                    log_warn("  Botão Salvar e Finalizar não encontrado")
                    _tentar_avancar(page)
                    continue

            # ── ETAPA DE CURRÍCULO ────────────────────────────────
            if eh_curriculo:
                # Detecta aba ativa
                abas = page.query_selector_all("div.flex.items-center.justify-around button")
                aba_ativa = None
                for aba in abas:
                    cls = aba.get_attribute("class") or ""
                    if "text-primary" in cls and "text-success" not in cls:
                        aba_ativa = aba.inner_text().strip()
                        break

                if not aba_ativa:
                    if "informações pessoais" in src.lower() or 'name="about.name"' in src:
                        aba_ativa = "Sobre você"
                    elif 'name="skill' in src.lower() or "habilidades para a vaga" in src.lower():
                        aba_ativa = "habilidades"
                    elif "outras informações" in src.lower() or "pretensão salarial" in src.lower():
                        aba_ativa = "Outras informações"

                log_info(f"  → Aba ativa: {aba_ativa or 'desconhecida'}")

                # Preenche conforme a aba
                if aba_ativa and "sobre" in aba_ativa.lower():
                    preencher_informacoes_pessoais(page)
                    preencher_diversidade(page)

                elif aba_ativa and ("habilidade" in aba_ativa.lower() or "skill" in aba_ativa.lower()):
                    preencher_habilidades_vaga(page, vaga["titulo"], descricao)

                elif aba_ativa and "outras" in aba_ativa.lower():
                    # CORREÇÃO: na aba "Outras informações" preenchemos o formulário
                    # E verificamos/preenchemos killer questions separadamente.
                    # A CNH NÃO é chamada aqui pois já está no perfil salvo.
                    preencher_outras_informacoes(page)
                    esperar(page, 0.5)

                    # Verifica e preenche killer questions (seção exclusiva do recrutador)
                    if _detectar_killer_questions(page):
                        preencher_killer_questions(page, vaga["titulo"], descricao)
                    else:
                        log_info("  Nenhuma killer question nesta aba")

                # Verifica killer questions em qualquer aba (às vezes aparecem fora de "Outras")
                elif _detectar_killer_questions(page):
                    log_info("  KQ fora da aba 'Outras' — preenchendo")
                    preencher_killer_questions(page, vaga["titulo"], descricao)

                # Verifica habilidades da vaga em qualquer aba
                if page.query_selector("div.flex.flex-col.items-start.gap-2"):
                    preencher_habilidades_vaga(page, vaga["titulo"], descricao)

                esperar(page, 0.8)
                avancou = _tentar_avancar(page)
                if not avancou:
                    log_warn("  Não conseguiu avançar — tentando salvar")
                    _tentar_salvar(page)
                continue

            # ── Etapa não reconhecida ─────────────────────────────
            log_info(f"  → Etapa não reconhecida: {url_atual[-50:]}")
            _tentar_avancar(page)

        if verificar_sucesso_modal(page):
            resultado["status"] = "enviado"
            log_ok("  ✅ Candidatura finalizada!")
        else:
            resultado["status"] = "incompleto"
            log_err("  Atingiu máximo de iterações sem concluir")

    except Exception as exc:
        log_err(f"  Exceção: {exc}")
        resultado["status"] = "erro"

    return resultado


def _tentar_avancar(page: Page) -> bool:
    seletores = [
        "button:has-text('Avançar')",
        "button:has-text('Próximo')",
        "button:has-text('Continuar')",
        "button:has-text('Salvar e revisar')",
        "button:has-text('Salvar e Finalizar')",
        "button:has-text('Salvar e finalizar')",
    ]
    for sel in seletores:
        with suppress(Exception):
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and btn.is_enabled():
                btn.scroll_into_view_if_needed()
                btn.click()
                esperar(page, 2)
                return True

    with suppress(Exception):
        info = page.evaluate("""
            () => {
                var btns = [...document.querySelectorAll('button')]
                    .filter(b => b.offsetParent !== null)
                    .map(b => ({
                        text: (b.innerText || '').trim().substring(0, 40),
                        disabled: b.disabled
                    }));
                var erros = [...document.querySelectorAll('[class*="text-error"], [class*="border-error"]')]
                    .map(e => (e.innerText || '').trim().substring(0, 80))
                    .filter(t => t.length > 2);
                var vazios = [...document.querySelectorAll('input[required], textarea[required]')]
                    .filter(el => !el.value)
                    .map(el => el.name || el.id || el.placeholder || '?');
                return {btns, erros: erros.slice(0, 5), vazios: vazios.slice(0, 5)};
            }
        """)
        if info:
            log_info(f"    [debug] Botões: {[b['text'] for b in info.get('btns', []) if b['text']]}")
            if info.get('erros'):
                log_warn(f"    [debug] Campos com erro: {info['erros']}")
            if info.get('vazios'):
                log_warn(f"    [debug] Campos obrigatórios vazios: {info['vazios']}")

    return False


def _tentar_salvar(page: Page) -> bool:
    with suppress(Exception):
        btn = page.query_selector("button:has-text('Salvar currículo')")
        if btn and btn.is_visible():
            btn.click()
            esperar(page, 2)
            return True
    return False


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
    RELATORIO_FILE.write_text(
        json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
        if c.get("site") == "Solides"
        and c.get("status") == "enviado"
        and c.get("data") == hoje
    )


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║              🤖 JOB HUNTER — SÓLIDES  v1.4                  ║
╚══════════════════════════════════════════════════════════════╝""")

    if not horario_ok():
        log_info("Fora do horário permitido (06h–23h).")
        return

    rel  = carregar_relatorio()
    hoje = candidaturas_hoje(rel)
    log_info(f"Candidaturas Sólides hoje: {hoje}/{MAX_POR_DIA}")

    if hoje >= MAX_POR_DIA:
        log_info("Limite diário atingido. Encerrando.")
        return

    ja_candidatado: set[str] = set(rel.get("ja_candidatado", []))

    with sync_playwright() as p:
        context, browser, page = fazer_login(p)

        try:
            log_info("\n🔍 Coletando vagas...")
            vagas = buscar_vagas(page)

            vagas_novas = [v for v in vagas if v["link"] not in ja_candidatado]

            vistos: set[str] = set()
            vagas_unicas: list[dict] = []
            for v in vagas_novas:
                if v["link"] not in vistos:
                    vistos.add(v["link"])
                    vagas_unicas.append(v)

            vagas_unicas = vagas_unicas[: MAX_POR_DIA - hoje]

            log(f"\n📊 {len(vagas_unicas)} vagas na fila")
            if not vagas_unicas:
                log_info("Nenhuma vaga nova encontrada.")
                return

            log_info("\n🚀 Iniciando candidaturas...\n")

            contadores = {
                "enviado":          0,
                "sem_botao":        0,
                "ja_candidatado":   0,
                "externo_rhgestor": 0,
                "nivel_excluido":   0,
                "sessao_expirada":  0,
                "erro":             0,
            }

            for i, vaga in enumerate(vagas_unicas, 1):
                if hoje + contadores["enviado"] >= MAX_POR_DIA:
                    log_info("Limite diário atingido — parando.")
                    break

                log(f"[{i}/{len(vagas_unicas)}]")
                resultado = candidatar_vaga(page, vaga)
                registrar_candidatura(resultado)

                status = resultado["status"]
                if status == "enviado":
                    contadores["enviado"] += 1
                    log_info(f"  📅 Total hoje: {hoje + contadores['enviado']}/{MAX_POR_DIA}")
                elif status == "externo_rhgestor":
                    contadores["externo_rhgestor"] += 1
                elif status in ("sem_botao", "botao_nao_clicavel"):
                    contadores["sem_botao"] += 1
                elif status == "ja_candidatado":
                    contadores["ja_candidatado"] += 1
                elif status in ("nivel_excluido", "tecnologia_excluida"):
                    contadores["nivel_excluido"] += 1
                elif status == "sessao_expirada":
                    contadores["sessao_expirada"] += 1
                    log_warn("  Sessão expirou — tentando reautenticar automaticamente...")
                    if tentar_reautenticar(page, context):
                        # Reautenticou: recoloca a vaga atual no início da fila
                        vagas_unicas.insert(i, vaga)
                        log_info("  Vaga reinserida na fila para nova tentativa")
                        esperar(page, 3)
                    else:
                        log_err("  Reautenticação falhou — encerrando")
                        break
                else:
                    contadores["erro"] += 1

                if i < len(vagas_unicas):
                    delay = random.uniform(DELAY_VAGAS, DELAY_VAGAS + 8)
                    log_info(f"  ⏳ Aguardando {delay:.0f}s...\n")
                    time.sleep(delay)

            total_hoje = hoje + contadores["enviado"]
            print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 RESUMO SÓLIDES                        ║
╠══════════════════════════════════════════════════════════════╣
║  ✅ Enviadas esta sessão : {contadores['enviado']:<33}║
║  📅 Total hoje           : {total_hoje}/{MAX_POR_DIA:<31}║
║  ⏭️  RHGestor (externo)   : {contadores['externo_rhgestor']:<33}║
║  ⏭️  Já candidatado       : {contadores['ja_candidatado']:<33}║
║  ⏭️  Nível excluído       : {contadores['nivel_excluido']:<33}║
║  ⏭️  Sem botão            : {contadores['sem_botao']:<33}║
║  🔑 Sessão expirada      : {contadores['sessao_expirada']:<33}║
║  ❌ Erros                : {contadores['erro']:<33}║
╚══════════════════════════════════════════════════════════════╝""")

        finally:
            with suppress(Exception):
                salvar_sessao(context)
            with suppress(Exception):
                browser.close()


if __name__ == "__main__":
    main()