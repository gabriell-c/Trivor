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

import os
import pickle
import random
import re
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from common import dryrun, loginonly, pagelens, perfil
from common.relatorio import Relatorio
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
#  IA — LLM + PROMPTS + DETECÇÃO DE INGLÊS (em indeed_ia.py)
# ═══════════════════════════════════════════════════════════════

from indeed_ia import *  # noqa: F403 — camada de IA (roteador Groq/HF, prompts, detecção de inglês)

# ═══════════════════════════════════════════════════════════════
#  REGRAS DETERMINÍSTICAS — APENAS DADOS 100% MECÂNICOS
# ═══════════════════════════════════════════════════════════════
from indeed_regras import *  # noqa: F403 — engine de regras (20 _regra_*, _CtxRegras, _REGRAS_DETERMINISTICAS, _resolver_por_regra)

# ═══════════════════════════════════════════════════════════════
#  RELATÓRIO
# ═══════════════════════════════════════════════════════════════

_rel = Relatorio(arquivo=RELATORIO_FILE, site="Indeed", tz=TZ)
carregar_relatorio = _rel.carregar
salvar_relatorio = _rel.salvar
registrar_candidatura = _rel.registrar
candidaturas_hoje = _rel.hoje


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


def _cdp_url_do_driver(driver) -> str | None:
    """Porta CDP que o driver UC abriu (options.debugger_address).

    O UC sorteia uma porta livre; ler a que ele usou evita colisão com
    outro Chrome da máquina. None (driver sem CDP) → leitor fica off."""
    addr = getattr(getattr(driver, "options", None), "debugger_address", None)
    return f"http://{addr}" if addr else None


def _novo_driver() -> Driver:
    brave = _encontrar_brave()
    if brave:
        log_info(f"  🦁 Usando Brave: {brave}")
        driver = Driver(uc=True, binary_location=brave)
    else:
        log_warn("  Brave não encontrado — usando Chrome")
        driver = Driver(uc=True)
    driver.maximize_window()
    cdp_url = _cdp_url_do_driver(driver)
    pagelens.habilitar_leitor(cdp_url)
    log_info(f"  🔎 Leitor estrutural: CDP {cdp_url}" if cdp_url
             else "  🔎 Leitor estrutural: desligado (driver sem CDP)")
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


# ── Login sem bloquear o terminal ────────────────────────────────
# Terminal interativo: o fluxo segue de ENTER (comportamento original).
# Rodada em background: o bot fica POLANDO a janela do browser aberta —
# o usuário só digita as senhas nela e o bot detecta e segue.
# Obs.: isatty() não é confiável em Windows+Git-Bash (retorna True até
# com stdin em /dev/null) — a rodada em background define TRIVOR_LOGIN_POLL=1.
_INTERATIVO = sys.stdin.isatty() and not os.environ.get("TRIVOR_LOGIN_POLL")

# Cookies que o Google só define após um login válido
_GOOGLE_COOKIES_AUTH = {"SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID", "__Host-GPW"}


def _google_logado(driver: Driver) -> bool:
    """Verifica se a sessão Google está ativa pelos cookies de auth."""
    try:
        return any(c["name"] in _GOOGLE_COOKIES_AUTH for c in driver.get_cookies())
    except WebDriverException:
        return False


def _aguardar_login(mensagem_enter: str, detectar: Any, timeout_min: int = 50) -> bool:
    """Interativo: espera ENTER. Não-interativo: polla `detectar()` a cada 5s
    até o timeout — o login em si continua sendo feito pelo usuário na janela."""
    if _INTERATIVO:
        input(mensagem_enter)
        return True
    log_info(f"   (modo automático) faça o login na janela do browser — até {timeout_min} min")
    prazo = time.time() + timeout_min * 60
    while time.time() < prazo:
        time.sleep(5)
        with suppress(WebDriverException):
            if detectar():
                return True
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
    if not _aguardar_login("   Pressione ENTER após logar no Google... ", lambda: _google_logado(driver)):
        log_err("   Login no Google não detectado — reabra a janela, faça o login e rode de novo")
        with suppress(Exception):
            driver.quit()
        raise SystemExit(1)
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

    if not _aguardar_login("   Pressione ENTER após logar no Indeed... ", lambda: _esta_logado_indeed(driver)):
        log_err("   Login no Indeed não detectado — finalize o login na janela e rode de novo")
        with suppress(Exception):
            driver.quit()
        raise SystemExit(1)
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
    excluida = perfil.titulo_excluido(titulo, PALAVRAS_EXCLUIR)
    if excluida:
        log_skip(f"Excluída ('{excluida}' no título): {titulo}")
        return False
    t = titulo.lower()
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

    # ── Resgate de rótulos: o site trocou o layout e o rótulo do campo sumou
    #    ("" , "campo", "q_123"). Uma chamada de LLM infere a pergunta de cada
    #    campo pelo snapshot (id/name, tipo, opções, passo) — só corre quando
    #    existe rótulo irresolvido, zero custo no happy path.
    sem_rotulo = [c for c in campos_ia if pagelens.rotulo_irresolvido(c["pergunta"])]
    if sem_rotulo:
        desc = pagelens.resumo_campos(driver)
        gotas = pagelens.agente_rotulos(
            desc, ctx,
            chamar=lambda prompt, max_tokens=500: chamar_llm(
                [{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0.1,
            ),
            log=log_info,
        )
        if gotas:
            def chave_do_campo(cid: str) -> str:
                item = elementos[cid]
                if item[0] == "select":  # select não guarda name na tupla
                    with suppress(Exception):
                        return item[1].get_attribute("id") or item[1].get_attribute("name") or ""
                    return ""
                return item[2] or ""

            resolvidos = 0
            for campo in sem_rotulo:
                rotulo = gotas.get(chave_do_campo(campo["id"]))
                if rotulo:
                    campo["pergunta"] = rotulo
                    resolvidos += 1
            log_info(f"  [rotulos] {resolvidos}/{len(sem_rotulo)} campo(s) sem rótulo → "
                     f"pergunta inferida pelo LLM")

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

    # ── Resgate semântico: o site trocou o layout e o botão de submit sumou
    #    (ou não é o que `_encontrar_btn_submit` conhece). O LLM lê a página
    #    viva e propõe o botão que ENVIA/CONFIRMA — só roda após as 3
    #    tentativas clássicas falharem (zero custo no happy path).
    log_warn("  Submit: resgate semântico do botão (LLM lê a página)")
    btn_ia = pagelens.achar(
        driver, [],
        objetivo=("botão que ENVIA/CONFIRMA a candidatura ('Enviar', 'Submit', "
                  "'Confirmar', 'Apply', 'Finalizar') — NUNCA 'Voltar', 'Back', "
                  "'Cancelar' ou 'Salvar e fechar'"),
        chamar=lambda prompt, max_tokens=260: chamar_llm(
            [{"role": "user", "content": prompt}], max_tokens=max_tokens,
        ),
        log=log_info,
    )
    if not btn_ia:
        return False

    with suppress(Exception):
        _js(driver, "arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", btn_ia)
    clicou_ia = False
    with suppress(Exception):
        btn_ia.click()
        clicou_ia = True
    if not clicou_ia:
        with suppress(Exception):
            _js(driver, "arguments[0].click();", btn_ia)
    esperar(3)
    if verificar_enviada(driver):
        log_info("  Submit: ✅ enviado via resgate semântico")
        return True
    if _url(driver) != url_antes:
        log_info("  Submit: ✅ URL mudou via resgate semântico")
        return True
    log_warn("  Submit: resgate semântico não confirmou envio")
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


def _resgate_avancar(driver: Driver) -> str:
    """Resgate de parada "invisível": o bot não avança e não sabe por quê
    (layout trocou, campo novo apareceu, botão mudou de nome). Três
    camadas — nunca chute:

    1. LLM lê a tela viva (`montar_prompt_enviada`): se a candidatura JÁ
       ESTÁ ENVIADA → "enviada" (o `verificar_enviada` determinístico não
       reconheceu o novo texto/tela de sucesso).
    2. LLM propõe o elemento que AVANÇA a candidatura neste passo (botão
       de continuar/enviar/confirmar ou campo pendente que impede o avanço)
       → `achar` clica → "progresso".
    3. Nada resolveu → "falha" (quem chama decide; 1 tentativa por travamento).

    Só roda quando não há progresso — o caminho normal nem o conhece."""
    resumo = pagelens.resumo_pagina(driver)
    if resumo:
        try:
            resp = chamar_llm(
                [{"role": "user", "content": pagelens.montar_prompt_enviada(resumo)}],
                max_tokens=150,
            )
            if pagelens.parse_enviada(resp):
                log_info("  [resgate] LLM: a tela indica que a candidatura JÁ foi enviada")
                return "enviada"
        except Exception as exc:
            log_warn(f"  [resgate] LLM falhou no julgamento de envio: {exc}")
    el = pagelens.achar(
        driver, [],
        objetivo=("elemento que AVANÇA/CONCLUI a candidatura neste passo "
                  "(botão 'Continuar', 'Next', 'Enviar', 'Confirmar', 'Finalizar' "
                  "ou o campo pendente que impede o avanço — NUNCA 'Voltar'/'Cancelar'"),
        chamar=lambda prompt, max_tokens=260: chamar_llm(
            [{"role": "user", "content": prompt}], max_tokens=max_tokens,
        ),
        log=log_info,
    )
    if el is None:
        return "falha"
    if _click(driver, el):
        log_info("  [resgate] LLM encontrou o elemento de avanço — clicou")
        esperar(2)
        if verificar_enviada(driver):
            return "enviada"
        return "progresso"
    return "falha"


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

        if dryrun.ativo():
            log_info("  [dry-run] widget Indeed Apply carregado — parando antes de preencher (nada enviado)")
            resultado["status"] = dryrun.STATUS
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
                    log_warn(f"  Anti-loop: etapa '{etapa}' repetida {repeticoes}x — "
                             f"resgate semântico antes de abortar")
                    saida = _resgate_avancar(driver)
                    if saida == "progresso":
                        repeticoes    = 0
                        etapa_anterior = ""
                        continue
                    if saida == "enviada":
                        resultado["status"] = "enviado"
                        log_ok("  ✅ Candidatura enviada (detectada pelo resgate semântico)!")
                        break
                    log_err(f"  Anti-loop: etapa '{etapa}' repetida {repeticoes}x "
                            f"e o resgate não avançou — abortando")
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
                        log_warn("  Etapa desconhecida e sem botão continuar — resgate semântico")
                        saida = _resgate_avancar(driver)
                        if saida == "enviada":
                            resultado["status"] = "enviado"
                            log_ok("  ✅ Candidatura enviada (detectada pelo resgate semântico)!")
                            break
                        if saida == "progresso":
                            continue
                        log_warn("  Resgate não avançou — abortando a vaga")
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

    # Botão "Logar" da UI: pickles de sessão já salvos no fazer_login → para aqui
    if loginonly.ativo():
        log_info("✅ Sessão Indeed salva (pickles) — modo só-login, encerrando")
        driver.quit()
        return

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
            if dryrun.ativo():
                if resultado["status"] == dryrun.STATUS:
                    log_info("[dry-run] cheguei no widget de candidatura — parando sem salvar nada")
                    break
                log_info(f"[dry-run] {resultado['status']} — sem chegar no widget; tentando a próxima vaga")
                continue
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
