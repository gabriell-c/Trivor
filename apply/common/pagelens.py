"""Pagelens — leitura semântica de página para os bots de apply (rede de segurança).

O happy path continua rápido: os seletores conhecidos do bot são testados
primeiro (timeout curto de 2s cada). SÓ quando todos falham, o Pagelens tira
um "snapshot" compacto da página (elementos interativos visíveis + passo
atual) e pergunta ao LLM do bot: "qual elemento atende a este objetivo?". O
modelo responde 1 a 3 seletores candidatos montados com os ATRIBUTOS do
snapshot (id, data-testid, aria-label, texto); o bot tenta cada um.

Resultado: o site pode mudar o layout sem quebrar o fluxo — o LLM lê a
página viva. E a latência só entra quando o site mudou algo (1-2 chamadas
LLM em página ~2800 chars; com Groq, ~5-10s no pior caso, só em falha).

Duck-typing de browser (aqui o módulo NÃO importa selenium nem playwright):
  - Selenium → `driver` (WebDriver): find_element(by=..., value=...) +
    execute_script. Passa `achar()`.
  - Playwright → `page` (Page): locator + evaluate. Passa `achar_pw()`.

O chamador LLM é injetado: `chamar(prompt, max_tokens) -> str` — cada bot
adapta sua própria cadeia de provedores (Groq→HF, Mistral, config.yaml...)
sem acoplar o módulo a um provider.

Nota de segurança: o snapshot nunca inclui `value` de input (evita vazar
CPF/salário digitados no formulário para o LLM) — só id/atributos/texto.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

_BY_CSS = "css selector"
_BY_XPATH = "xpath"


# ── Snapshot compacto da página (roda no DOM) ──────────────────────────────
# Sem `value` de input (PII digitada no formulário não vai ao LLM).
DIGEST_JS = """(() => {
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; } catch (e) { return false; } };
  const out = { titulo: document.title || '', passo: '', els: [] };
  const head = (document.querySelector('h1') || document.querySelector('h2') || {}).innerText || '';
  const grp = (document.querySelector('[data-testid*="stepper"], [data-testid*="step"], [role="progressbar"]') || {}).innerText || '';
  out.passo = (head + ' ' + grp).replace(/\\s+/g, ' ').trim().slice(0, 140);
  const add = (el, t) => {
    if (!el || out.els.length >= 28 || !vis(el)) return;
    out.els.push({
      t: t,
      txt: (el.innerText || el.getAttribute('placeholder') || '').toString().replace(/\\s+/g, ' ').slice(0, 60),
      id: el.id ? String(el.id).slice(0, 40) : '',
      tid: (el.getAttribute('data-testid') || '').slice(0, 40),
      aria: (el.getAttribute('aria-label') || '').slice(0, 60),
      n: (el.name || '').slice(0, 40),
      ty: el.type || ''
    });
  };
  document.querySelectorAll('button').forEach(el => add(el, 'botao'));
  document.querySelectorAll('[role="button"]').forEach(el => add(el, 'botao'));
  document.querySelectorAll('input').forEach(el => add(el, el.type || 'campo'));
  document.querySelectorAll('select').forEach(el => add(el, 'select'));
  document.querySelectorAll('textarea').forEach(el => add(el, 'textarea'));
  document.querySelectorAll('a').forEach(el => {
    const h = (el.innerText || '').trim();
    if (h && h.length < 80) add(el, 'link');
  });
  return out;
})()"""


def _digeste_para_texto(bruto, limite: int) -> str:
    """JSON compacto do snapshot; sem elementos → '' (resgate sem lido é perda)."""
    if isinstance(bruto, str):
        return bruto[:limite]
    if not isinstance(bruto, dict) or not bruto.get('els'):
        return ''
    dados = dict(bruto)
    texto = json.dumps(dados, ensure_ascii=False)
    els = list(dados['els'])
    while len(texto) > limite and els:
        els.pop()
        dados['els'] = els
        texto = json.dumps(dados, ensure_ascii=False)
    return texto[:limite]


def resumo_pagina(driver, limite: int = 2800) -> str:
    """Snapshot compacto (Selenium) — JSON: título, passo atual, elementos."""
    try:
        bruto = driver.execute_script(DIGEST_JS)
    except Exception:
        return ''
    return _digeste_para_texto(bruto, limite)


def resumo_pagina_pw(page, limite: int = 2800) -> str:
    """Snapshot compacto (Playwright) — mesmo JS, via evaluate."""
    try:
        bruto = page.evaluate(DIGEST_JS)
    except Exception:
        return ''
    return _digeste_para_texto(bruto, limite)


# ── Prompt + parsing ────────────────────────────────────────────────────────

def montar_prompt(objetivo: str, resumo: str, regras: str = '',
                  erro_anterior: str = '') -> str:
    """Prompt enxuto: objetivo + snapshot + regras de perfil + tentativa anterior."""
    base = (
        "Você opera um navegador automatizado em um formulário de candidatura a emprego.\n"
        f"OBJETIVO: {objetivo}\n\n"
        f"PÁGINA ATUAL (snapshot compacto dos elementos visíveis; i=tipo, txt=texto, "
        f"id/tid/aria/n=atributos):\n{resumo}\n"
    )
    if regras:
        base += f"\nREGRAS DO CANDIDATO (o que dizer em campo aberto): {regras}\n"
    if erro_anterior:
        base += f"\nTENTATIVA ANTERIOR FALHOU: {erro_anterior}\n"
    base += (
        "\nRESPOSTA: SOMENTE um JSON válido, sem markdown: "
        '{"seletores": ["até 3 seletores que atendem ao objetivo"], "motivo": "máx 40 palavras"}\n'
        "Monte os seletores dos ATRIBUTOS do snapshot: id → '#id'; tid → \"[data-testid='x']\"; "
        "aria → \"[aria-label='x']\"; texto → \"//button[normalize-space(.)='Texto']\" (XPath). "
        "Nunca seletor genérico ('button', 'div'). Nenhum atende → {\"seletores\": [], \"motivo\": \"nenhum atende\"}"
    )
    return base


def parse_seletores(resposta: str) -> list[str]:
    """Extrai a lista de seletores da resposta do LLM (tolerante a cercas de
    markdown/JSON extra). Falha → [] (o bot segue o fluxo normal de erro)."""
    s = (resposta or '').strip()
    if s.startswith('```'):
        s = re.sub(r'^```[a-zA-Z]*\s*', '', s)
        s = re.sub(r'\s*```$', '', s)
    i, j = s.find('{'), s.rfind('}')
    if i == -1 or j <= i:
        return []
    try:
        dados = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return []
    itens = dados.get('seletores') if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        return []
    return [str(x).strip() for x in itens if isinstance(x, (str, int)) and str(x).strip()][:3]


# ── Localização (Selenium) ──────────────────────────────────────────────────

def _por(sel: str) -> tuple:
    s = sel.strip()
    if s.startswith(('//', '(')):
        return _BY_XPATH, s
    return _BY_CSS, s


def _encontrar(driver, sel: str, segundos: float = 2.0) -> object | None:
    """Tenta `sel` com polling curto (3 verif./2s) — sem bloquear o happy path."""
    por, valor = _por(sel)
    tentativas = 3
    passo = segundos / tentativas
    for _ in range(tentativas):
        try:
            el = driver.find_element(by=por, value=valor)
        except Exception:
            el = None
        if el is not None:
            try:
                if not el.is_displayed():
                    el = None
            except Exception:
                pass  # driver fake/teste sem is_displayed
            if el is not None:
                return el
        time.sleep(passo)
    return None


def achar(
    driver,
    seletores: list[str],
    objetivo: str,
    regras: str = '',
    chamar: Callable[[str, int], str] | None = None,
    log: Callable[[str], None] | None = None,
    tentativas_llm: int = 2,
) -> object | None:
    """Seletor primeiro (rápido), resgate semântico depois (LLM lê a página).

    1. Testa cada `seletores` conhecidos (2s cada, sem LLM).
    2. Falhou todos → snapshot + LLM (máx. `tentativas_llm` rodadas): o modelo
       devolve até 3 seletores candidatos; tenta cada um (2s) e valida se
       apareceu um elemento visível.
    3. Nada → None (o bot segue seu caminho normal de erro — Pagelens nunca
       inverte a decisão: só adiciona chance de acerto em página alterada).

    `chamar(prompt, max_tokens) -> str` — se None, pula o resgate (modo
    economia: só seletores conhecidos)."""
    def diz(msg: str) -> None:
        if log:
            log(msg)

    for sel in seletores or []:
        el = _encontrar(driver, sel)
        if el is not None:
            return el
    if chamar is None:
        return None

    erro_anterior = ''
    for rodada in range(1, tentativas_llm + 1):
        resumo = resumo_pagina(driver)
        if not resumo:
            diz('    [pagelens] snapshot vazio — resgate indisponível')
            return None
        try:
            resposta = chamar(montar_prompt(objetivo, resumo, regras, erro_anterior), 260)
        except Exception as exc:
            diz(f'    [pagelens] LLM falhou na rodada {rodada}: {exc}')
            if rodada < tentativas_llm:
                continue
            return None
        candidatos = parse_seletores(resposta)
        if not candidatos:
            diz(f'    [pagelens] LLM não indicou seletor (rodada {rodada})')
            return None
        for sel in candidatos:
            diz(f'    [pagelens] tentando candidato (rodada {rodada}): {sel[:70]}')
            el = _encontrar(driver, sel)
            if el is not None:
                diz(f'    [pagelens] ✅ localizado via LLM: {sel[:70]}')
                return el
            erro_anterior = f'o seletor {sel[:70]} não achou elemento visível'
    return None


# ── Localização (Playwright) ────────────────────────────────────────────────

def _encontrar_pw(page, sel: str, segundos: float = 2.0) -> object | None:
    s = sel.strip()
    locador = f'xpath={s}' if s.startswith(('//', '(')) else s
    try:
        el = page.locator(locador).first
        el.wait_for(state='visible', timeout=int(segundos * 1000))
        return el
    except Exception:
        return None


def achar_pw(
    page,
    seletores: list[str],
    objetivo: str,
    regras: str = '',
    chamar: Callable[[str, int], str] | None = None,
    log: Callable[[str], None] | None = None,
    tentativas_llm: int = 2,
) -> object | None:
    """Mesma estratégia de `achar`, para bot Playwright (gupy/infojobs/solides).

    Retorna o Locator (`.click()`, `.fill()`) ou None — nunca lança: se o
    resgate falhar, o bot segue o fluxo normal de erro."""
    def diz(msg: str) -> None:
        if log:
            log(msg)

    for sel in seletores or []:
        el = _encontrar_pw(page, sel)
        if el is not None:
            return el
    if chamar is None:
        return None

    erro_anterior = ''
    for rodada in range(1, tentativas_llm + 1):
        resumo = resumo_pagina_pw(page)
        if not resumo:
            diz('    [pagelens] snapshot vazio — resgate indisponível')
            return None
        try:
            resposta = chamar(montar_prompt(objetivo, resumo, regras, erro_anterior), 260)
        except Exception as exc:
            diz(f'    [pagelens] LLM falhou na rodada {rodada}: {exc}')
            if rodada < tentativas_llm:
                continue
            return None
        candidatos = parse_seletores(resposta)
        if not candidatos:
            diz(f'    [pagelens] LLM não indicou seletor (rodada {rodada})')
            return None
        for sel in candidatos:
            diz(f'    [pagelens] tentando candidato (rodada {rodada}): {sel[:70]}')
            el = _encontrar_pw(page, sel)
            if el is not None:
                diz(f'    [pagelens] ✅ localizado via LLM: {sel[:70]}')
                return el
            erro_anterior = f'o seletor {sel[:70]} não achou elemento visível'
    return None
