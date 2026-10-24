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
from contextlib import suppress

_BY_CSS = "css selector"
_BY_XPATH = "xpath"

# ── Leitor estrutural (crawl4ai via CDP) — camada opcional ──────────────────
# O digest abaixo é a fonte da verdade (DOM vivo da aba do bot). A leitura
# do crawl4ai entra como SEÇÃO EXTRA, nunca como substituta: ela descreve
# a estrutura da página (seções, rótulos, links) pro LLM, mas modais e
# estados que só existem na aba do bot só o DOM vivo mostra. Sem cdp_url
# (ou falha do c4a), tudo segue exatamente como o fluxo clássico.
_LEITOR_CDP: str | None = None


def habilitar_leitor(cdp_url: str | None) -> None:
    """Liga/desliga a seção extra do crawl4ai em todos os resgates do pagelens.

    Chamado 1x no start do bot, com a porta CDP do Chrome dele
    (http://127.0.0.1:9333). `None` desativa (comportamento clássico).
    """
    global _LEITOR_CDP
    _LEITOR_CDP = cdp_url


def _estrutura_extra(url: str | None, limite: int = 1200) -> str:
    """Seção estrutural do crawl4ai; "" quando desligado, indisponível ou em falha."""
    if not _LEITOR_CDP or not url:
        return ''
    try:
        from common import leitor
    except ImportError:
        return ''  # c4a não instalado — fluxo clássico intacto
    try:
        leitura = leitor.leitura_estruturada(url, _LEITOR_CDP, limite=limite)
    except Exception:
        return ''  # regra de ouro: nunca pior que o fluxo clássico
    return leitor.resumo_para_llm(leitura, fallback='')


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
    """Snapshot compacto (Selenium) — JSON: título, passo atual, elementos.

    Com o leitor ligado, anexa a seção estrutural do crawl4ai (seções,
    rótulos, links da página) — o DOM vivo continua sendo a verdade."""
    try:
        bruto = driver.execute_script(DIGEST_JS)
    except Exception:
        return ''
    texto = _digeste_para_texto(bruto, limite)
    extra = _estrutura_extra(getattr(driver, 'current_url', None))
    if texto and extra:
        texto += f"\n\n[estrutura da página — {getattr(driver, 'current_url', '')}]\n{extra}"
    return texto


def resumo_pagina_pw(page, limite: int = 2800) -> str:
    """Snapshot compacto (Playwright) — mesmo JS, via evaluate.

    Com o leitor ligado, anexa a seção estrutural do crawl4ai (mesma regra
    do resumo_pagina: extra é complemento, o DOM vivo é a verdade)."""
    try:
        bruto = page.evaluate(DIGEST_JS)
    except Exception:
        return ''
    texto = _digeste_para_texto(bruto, limite)
    extra = _estrutura_extra(getattr(page, 'url', None))
    if texto and extra:
        texto += f"\n\n[estrutura da página — {getattr(page, 'url', '')}]\n{extra}"
    return texto


# ── Rótulo de campo (layout mudou → LLM inferiu a pergunta) ────────────────
# Se o site redesenha o formulário, os rótulos somem e o bot coleta campos
# com `pergunta` vazia ou parecendo identificador ("q_123", "input-q_456").
# O CAMPOS_JS lista os campos visíveis com atributos/opções; o agente devolve
# a pergunta inferida de cada um. Execução continua no DOM do bot (verdade).

def rotulo_irresolvido(lbl: str) -> bool:
    """True se `lbl` é vazio ou parece identificador técnico, não pergunta."""
    s = (lbl or '').strip()
    if not s or s.lower() in ('campo', 'q_'):
        return True
    # Identificador técnico: só [a-z0-9_-] com pelo menos um dígito
    # ("q_123", "input-q_456", "question_7", "a-1-b2"). Pergunta de verdade
    # tem espaços/acentos — "Qual seu nível?" não cai aqui.
    return bool(re.fullmatch(r'[a-z0-9_-]+', s, re.IGNORECASE)
                 and re.search(r'\d', s))


CAMPOS_JS = """(() => {
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; } catch (e) { return false; } };
  const out = { passo: '', campos: [] };
  const head = (document.querySelector('h1') || document.querySelector('h2') || {}).innerText || '';
  const grp = (document.querySelector('[data-testid*="stepper"], [data-testid*="step"], [role="progressbar"]') || {}).innerText || '';
  out.passo = (head + ' ' + grp).replace(/\\s+/g, ' ').trim().slice(0, 140);
  const vistos = {};
  const rotuloOpcao = el => {
    try {
      if (el.id) {
        const l = document.querySelector('label[for="' + el.id + '"]');
        if (l) { const t = (l.innerText || '').replace(/\\s+/g, ' ').trim(); if (t) return t; }
      }
      return (el.getAttribute('aria-label') || el.value || '').trim();
    } catch (e) { return ''; }
  };
  const jaVisto = el => {
    const k = el.id || el.name || '';
    if (k && vistos[k]) return true;
    if (k) vistos[k] = 1;
    return false;
  };
  const addInput = el => {
    if (!el || out.campos.length >= 20 || !vis(el) || jaVisto(el)) return;
    out.campos.push({ k: String(el.id || el.name || '').slice(0, 40),
      t: el.type || 'campo',
      ph: (el.getAttribute('placeholder') || '').slice(0, 50), opt: [] });
  };
  document.querySelectorAll('input[type="text"],input[type="number"],input[type="email"],input[type="tel"],input[type="url"],input[type="date"]').forEach(addInput);
  document.querySelectorAll('textarea').forEach(addInput);
  document.querySelectorAll('select').forEach(el => {
    if (!el || out.campos.length >= 20 || !vis(el) || jaVisto(el)) return;
    const opcoes = Array.from(el.options || []).map(o => (o.textContent || '').trim()).filter(Boolean).slice(0, 8);
    out.campos.push({ k: String(el.id || el.name || '').slice(0, 40),
      t: 'select', ph: '', opt: opcoes });
  });
  document.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(el => {
    if (!el || out.campos.length >= 20 || !vis(el)) return;
    const key = el.name || el.id || '';
    if (jaVisto(el)) return;
    const ty = el.type;
    const opcoes = Array.from(document.querySelectorAll('input[type="' + ty + '"]'))
      .filter(r => (r.name || r.id) === key)
      .map(r => rotuloOpcao(r) || (r.value || '')).filter(Boolean).slice(0, 8);
    out.campos.push({ k: String(key).slice(0, 40), t: ty, ph: '', opt: opcoes });
  });
  return out;
})()"""


def resumo_campos(driver, limite: int = 2600) -> str:
    """Snapshot de campos (Selenium): passo atual + campos visíveis com
    id/name, tipo, placeholder e opções. JSON — ou '' se vazio."""
    try:
        bruto = driver.execute_script(CAMPOS_JS)
    except Exception:
        return ''
    if not isinstance(bruto, dict) or not bruto.get('campos'):
        return ''
    return json.dumps(bruto, ensure_ascii=False)[:limite]


def resumo_campos_pw(page, limite: int = 2600) -> str:
    """Snapshot de campos (Playwright) — mesmo JS via evaluate."""
    try:
        bruto = page.evaluate(CAMPOS_JS)
    except Exception:
        return ''
    if not isinstance(bruto, dict) or not bruto.get('campos'):
        return ''
    return json.dumps(bruto, ensure_ascii=False)[:limite]


def agente_rotulos(desc: str, contexto: str, chamar: Callable[[str, int], str] | None = None,
                   log: Callable[[str], None] | None = None,
                   passo: str = '') -> dict:
    """Agente de rótulos: 1 chamada de LLM infere a pergunta de CADA campo
    sem rótulo a partir do snapshot (passo, tipo, opções, contexto da vaga).

    `desc` vem de `resumo_campos`/`resumo_campos_pw`. Retorna {k: pergunta}
    (chave = id/name do campo); {} sem LLM ou em falha — o chamador segue o
    fluxo clássico (o agente nunca piora o estado)."""
    def diz(msg: str) -> None:
        if log:
            log(msg)

    if not desc or chamar is None:
        return {}
    prompt = (
        "Você lê a tela de um navegador durante uma candidatura automatizada. "
        "O layout do site mudou e os campos ficaram SEM RÓTULO legível.\n"
        f"PASSO ATUAL: {passo or '(desconhecido)'}\n"
        f"VAGA: {contexto[:200]}\n"
        f"CAMPOS VISÍVEIS (k=id/name, t=tipo, ph=placeholder, opt=opções visíveis):\n{desc}\n\n"
        "TAREFA: para CADA campo, escreva a PERGUNTA que ele está fazendo, inferida do "
        "passo, da vaga, das opções e da ordem. Idioma do site. Máx 12 palavras cada.\n"
        'RESPOSTA: SOMENTE JSON válido, sem markdown: {"respostas": {"<k>": "pergunta"}} — '
        "uma chave por campo, usando o MESMO k de cada item acima."
    )
    try:
        resp = chamar(prompt, 500)
    except Exception as exc:
        diz(f'    [rotulos] LLM falhou: {exc}')
        return {}
    dados = _primeiro_json(resp) or {}
    bruto = dados.get('respostas')
    if not isinstance(bruto, dict):
        return {}
    gotas = {str(k): str(v).strip()[:80] for k, v in bruto.items() if str(v).strip()}
    diz(f'    [rotulos] {len(gotas)} rótulo(s) inferido(s) pelo LLM')
    return gotas


# ── Prompt + parsing ────────────────────────────────────────────────────────

def _primeiro_json(texto: str) -> dict | None:
    """Extrai o primeiro objeto JSON de `texto` (tolerante a cercas de
    markdown/prosador ao redor). Falha → None."""
    s = (texto or '').strip()
    if s.startswith('```'):
        s = re.sub(r'^```[a-zA-Z]*\s*', '', s)
        s = re.sub(r'\s*```$', '', s)
    i, j = s.find('{'), s.rfind('}')
    if i == -1 or j <= i:
        return None
    try:
        dados = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, dict) else None


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
    """Extrai a lista de seletores da resposta do LLM. Falha → []."""
    dados = _primeiro_json(resposta) or {}
    itens = dados.get('seletores')
    if not isinstance(itens, list):
        return []
    return [str(x).strip() for x in itens if isinstance(x, (str, int)) and str(x).strip()][:3]


def parse_acao(resposta: str) -> dict:
    """Extrai {acao, seletor, texto} da resposta de tratar_bloqueio (desconhecido → 'nada')."""
    dados = _primeiro_json(resposta) or {}
    acao = str(dados.get('acao', 'nada')).lower()
    if acao not in ('clicar', 'humano', 'nada'):
        acao = 'nada'
    return {'acao': acao,
            'seletor': str(dados.get('seletor') or '').strip(),
            'texto': str(dados.get('texto') or '')[:240]}


# ── Supervisor de bloqueios (modal/overlay/captcha) ─────────────────────────
# Checagem barata (~5ms, SEM LLM): existe overlay visível na tela? Só quando
# SIM e o modal não foi fechado pelos seletores conhecidos do bot, o LLM lê o
# snapshot e decide: fechar (qual botão), esperar humano (captcha) ou ignorar.

BLOCKER_JS = """(() => {
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; } catch (e) { return false; } };
  const cands = document.querySelectorAll(
    '[role="dialog"], [aria-modal="true"], [class*="modal" i], [class*="popup" i], [class*="overlay" i]');
  for (const el of cands) {
    if (!vis(el)) continue;
    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 160);
    const rot = String(el.getAttribute('role') || el.className || 'overlay').slice(0, 40);
    return rot + (t ? ' :: ' + t : '');
  }
  return null;
})()"""


def detecta_bloqueio(driver) -> str | None:
    """Descrição curta do overlay visível, ou None (tela livre). Não usa LLM."""
    try:
        bruto = driver.execute_script(BLOCKER_JS)
    except Exception:
        return None
    return bruto if isinstance(bruto, str) and bruto else None


# Botões de fechamento reconhecíveis sem LLM (texto exato, minúsculo).
# Restrito a palavras de fechamento unívocas — nunca "continuar"/"avançar"
# (isso é botão de formulário, não de modal).
_CLOSE_BTN_JS = """(() => {
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; } catch (e) { return false; } };
  const fech = { ok:1, okay:1, 'got it':1, understood:1, entendi:1, 'entendido':1,
                 aceito:1, aceitei:1, aceitar:1, concordo:1, 'fechar':1, close:1,
                 dismiss:1, 'li e aceito':1, x:1, '×':1 };
  let ov = null;
  for (const sel of ['[role="dialog"]', '[aria-modal="true"]',
                     '[class*="modal" i]', '[class*="popup" i]']) {
    for (const el of document.querySelectorAll(sel)) { if (vis(el)) { ov = el; break; } }
    if (ov) break;
  }
  const escopo = ov || document;
  for (const el of escopo.querySelectorAll('button, a, [role="button"]')) {
    if (el.disabled || !vis(el)) continue;
    const t = ((el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase());
    const aria = ((el.getAttribute('aria-label') || '').trim().toLowerCase());
    if (fech[t] || fech[aria]) return el;
  }
  return null;
})()"""


def fechar_por_texto(driver) -> object | None:
    """Camada 1 (SEM LLM): overlay com botão visível de fechamento conhecido.

    Procura DENTRO do overlay primeiro (nunca clica em botão de formulário
    que esteja atrás dele). Retorna o elemento pronto pra `_click` ou None."""
    try:
        el = driver.execute_script(_CLOSE_BTN_JS)
    except Exception:
        return None
    if el is None or isinstance(el, (str, dict, list, int, float, bool)):
        return None
    return el


_KEYWORDS_CAPTCHA = ("robot", "captcha", "cf-turnstile", "recaptcha",
                     "verifying you are human", "verificação humana",
                     "i am not a robot")


def parse_bloqueio(resposta: str) -> dict:
    """Extrai {humano, seletores (máx 3), texto} da resposta do supervisor.

    Aceita o formato antigo ({"acao": "clicar"|"humano"|"nada", "seletor"})
    e o novo ({"humano": bool, "seletores": [...], "texto"})."""
    dados = _primeiro_json(resposta) or {}
    if "acao" in dados:  # formato antigo
        acao = str(dados.get("acao", "nada")).lower()
        if acao == "humano":
            return {"humano": True, "seletores": [],
                    "texto": str(dados.get("texto", ""))[:240]}
        if acao == "clicar" and dados.get("seletor"):
            return {"humano": False, "seletores": [str(dados["seletor"])],
                    "texto": str(dados.get("texto", ""))[:240]}
        return {"humano": False, "seletores": [],
                "texto": str(dados.get("texto", ""))[:240]}
    itens = dados.get("seletores")
    if not isinstance(itens, list):
        itens = []
    sels = [str(x).strip() for x in itens
            if isinstance(x, (str, int)) and str(x).strip()][:3]
    return {"humano": bool(dados.get("humano")), "seletores": sels,
            "texto": str(dados.get("texto", ""))[:240]}


def _prompt_bloqueio(bloqueio: str, resumo: str, erro_anterior: str = "") -> str:
    base = (
        f"Durante uma candidatura automatizada, um BLOQUEIO/overlay apareceu na tela:\n{bloqueio}\n\n"
        f"ELEMENTOS VISÍVEIS AGORA (snapshot; t=tipo, txt=texto, id/tid/aria/n=atributos):\n{resumo}\n\n"
        "REGRAS DE DECISÃO:\n"
        "1. Modal de aviso/informação/consentimento/marketing com botão 'ok', 'entendi', "
        "'aceitar', 'concordo', 'fechar', 'x', 'continue' → proponha ATÉ 3 seletores candidatos "
        "desse botão, feitos dos ATRIBUTOS do snapshot: id → '#id'; "
        "tid → \"[data-testid='x']\"; aria → \"[aria-label='x']\"; "
        "texto → \"//button[normalize-space(.)='Texto']\" (XPath).\n"
        "2. Captcha / 'I am not a robot' / desafio de verificação → humano: true.\n"
        "3. Mensagem de erro de campo ou algo que se resolve sozinho → NÃO proponha seletores; "
        "explique em 'texto'.\n"
        "4. Em dúvida → NÃO proponha seletores.\n"
        "NUNCA proponha campo de formulário, botões 'Voltar'/'Cancelar' ou seletor genérico "
        "('button', 'div').\n\n"
        'RESPOSTA: SOMENTE um JSON válido, sem markdown: '
        '{"humano": false, "seletores": ["até 3 seletores de fechamento"], '
        '"texto": "o que está aparecendo (máx 60 palavras)"}'
    )
    if erro_anterior:
        base += f"\nTENTATIVA ANTERIOR FALHOU: {erro_anterior}\n"
    return base


def montar_prompt_enviada(resumo: str) -> str:
    """Pergunta ao LLM se a tela atual é confirmação de candidatura enviada.

    O passo é necessário quando o site mudou o texto/seletores da tela de
    sucesso e `verificar_enviada` (regras determinísticas) não reconhece.
    Tela de REVISÃO com botão "Enviar" NÃO conta como enviada."""
    return (
        "Você lê a tela de um navegador durante uma candidatura automatizada.\n"
        f"SNAPSHOT (t=tipo, txt=texto, id/tid/aria/n=atributos):\n{resumo}\n\n"
        "ESTA PÁGINA INDICA QUE A CANDIDATURA JÁ FOI ENVIADA/CONCLUÍDA "
        "(mensagem de obrigado/sucesso, 'application submitted', tela pós-envio, "
        "pedido de avaliação da empresa)?"
        " ATENÇÃO: uma tela de REVISÃO final que ainda tem botão 'Enviar/Submit' "
        "NÃO significa enviada.\n\n"
        'RESPOSTA: SOMENTE JSON válido, sem markdown: '
        '{"enviada": true|false, "motivo": "máx 20 palavras"}'
    )


def parse_enviada(resposta: str) -> bool:
    dados = _primeiro_json(resposta) or {}
    return str(dados.get('enviada', '')).lower() in ('true', 'sim', 'yes', '1')


def _tecla_esc(driver) -> bool:
    try:
        corpo = driver.find_element(by="tag name", value="body")
        if corpo is None:
            return False
        corpo.send_keys("\ue007")  # tecla ESC
        time.sleep(0.8)
        return True
    except Exception:
        return False


def _tenta_iframe(driver, diz) -> bool:
    """Muitos modais vivem dentro de iframe: repete a camada de texto + ESC lá dentro."""
    try:
        iframes = driver.find_elements(by="tag name", value="iframe")
    except Exception:
        return False
    if not iframes:
        return False
    for fr in iframes:
        try:
            driver.switch_to.frame(fr)
        except Exception:
            continue
        try:
            bloqueio = detecta_bloqueio(driver)
            if not bloqueio:
                continue
            el = fechar_por_texto(driver)
            if el is not None:
                with suppress(Exception):
                    driver.execute_script("arguments[0].click();", el)
                diz(f'    [bloqueio] modal fechado em iframe: {bloqueio[:80]}')
                time.sleep(1.0)
                return True
            if _tecla_esc(driver) and not detecta_bloqueio(driver):
                diz('    [bloqueio] modal de iframe fechado via ESC')
                return True
        finally:
            with suppress(Exception):
                driver.switch_to.default_content()
    return False


def _rodadas_llm(tentar, resumo_fn, bloqueio: str,
                 chamar: Callable[[str, int], str],
                 diz: Callable[[str], None]) -> tuple:
    """Rodadas LLM do supervisor de bloqueio (compartilhado Selenium/Playwright).

    `tentar(sel)` → elemento/locator ou None; `resumo_fn()` → snapshot.
    Retorna (situação, detalhe, el): 'fechou' | 'captcha' | 'nada' | 'falhou'."""
    erro_anterior = ''
    for rodada in (1, 2):
        resumo = resumo_fn()
        if not resumo:
            return ('falhou', '', None)
        try:
            resp = chamar(_prompt_bloqueio(bloqueio, resumo, erro_anterior), 300)
        except Exception as exc:
            diz(f'    [bloqueio] LLM falhou na rodada {rodada}: {exc}')
            return ('falhou', '', None)
        if not str(resp or '').strip():
            # Provedor sem resposta (ex.: `_chamar_llm` → None) — não é "julgou
            # inofensivo", é rodar de novo: tratar vazio como "nada" faria o
            # bot acreditar que a tela abriu quando o overlay continua lá.
            erro_anterior = ('chamada anterior voltou vazia — proponha os '
                            'seletores de fechamento mesmo assim')
            continue
        p = parse_bloqueio(resp)
        if p['humano']:
            diz(f'    [bloqueio] captcha/desafio — aguardando humano: {p["texto"][:80]}')
            return ('captcha', p['texto'] or bloqueio[:200], None)
        if not p['seletores']:
            diz(f'    [bloqueio] LLM: ignorar — {p["texto"][:80]}')
            return ('nada', p['texto'], None)
        falhas = []
        for sel in p['seletores']:
            diz(f'    [bloqueio] tentando seletor de fechamento (rodada {rodada}): {sel[:70]}')
            el = tentar(sel)
            if el is not None:
                return ('fechou', p['texto'] or sel, el)
            falhas.append(f'{sel[:70]} não achou elemento visível')
        erro_anterior = '; '.join(falhas)
    return ('falhou', '', None)


def tratar_bloqueio(driver, chamar: Callable[[str, int], str] | None = None,
                    log: Callable[[str], None] | None = None) -> dict:
    """Supervisor de tela em escalonamento (mais barato → mais caro):

    0. Checar overlay (~5ms, SEM LLM) — tela livre → `nada`.
    1. Captcha por palavras-chave (determinístico, SEM LLM).
    2. Fechamento rápido por texto (SEM LLM): overlay com botão "ok",
       "fechar", "aceitar"... — cobre o caso comum até com provedor fora.
    3. LLM (1–2 rodadas): lê o snapshot e propõe ATÉ 3 seletores de
       fechamento por rodada; erro da rodada N alimenta a N+1.
    4. Iframe + tecla ESC (o modal pode estar em outro frame).
    5. Ainda aberto → `indeciso` — quem chama conta repetições e para
       a vaga com status claro (3 seguidas).

    Retorna `{"tipo": "nada"|"captcha"|"fechou"|"indeciso", "detalhe": str,
    "el": element|None}`:
      - `nada`     → tela livre OU LLM julgou o overlay inofensivo
                     (`detalhe` vazio = tela livre; preenchido = ignorado)
      - `captcha`  → verificação humana → quem chama resolve manualmente
      - `fechou`   → `el` pronto pra `_click` (None se fechado em iframe/ESC)
      - `indeciso` → detectado e nada resolveu — loga e segue

    LLM é chamado APENAS quando um overlay visível existe e a camada de
    texto não fechou (0 custo no happy path)."""
    def diz(msg: str) -> None:
        if log:
            log(msg)

    bloqueio = detecta_bloqueio(driver)
    if not bloqueio:
        return {'tipo': 'nada', 'detalhe': '', 'el': None}

    # Camada 1: captcha determinístico (sem LLM)
    if any(k in bloqueio.lower() for k in _KEYWORDS_CAPTCHA):
        diz(f'    [bloqueio] captcha/desafio detectado — aguardando humano: {bloqueio[:80]}')
        return {'tipo': 'captcha', 'detalhe': bloqueio[:200], 'el': None}

    # Camada 2: fechamento rápido por texto (sem LLM)
    el = fechar_por_texto(driver)
    if el is not None:
        diz(f'    [bloqueio] fechamento rápido por texto (sem LLM): {bloqueio[:80]}')
        return {'tipo': 'fechou', 'detalhe': f'botão de fechamento por texto — {bloqueio[:80]}',
                'el': el}

    # Camada 3: LLM com múltiplos candidatos (2 rodadas, erro retroalimenta)
    if chamar is not None:
        situacao, detalhe, el = _rodadas_llm(
            lambda sel: _encontrar(driver, sel),
            lambda: resumo_pagina(driver),
            bloqueio, chamar, diz,
        )
        if situacao == 'fechou':
            diz('    [bloqueio] ✅ fechado via LLM')
            return {'tipo': 'fechou', 'detalhe': detalhe, 'el': el}
        if situacao == 'captcha':
            return {'tipo': 'captcha', 'detalhe': detalhe, 'el': None}
        if situacao == 'nada':
            return {'tipo': 'nada', 'detalhe': detalhe, 'el': None}
        # 'falhou' → camadas 4 (iframe + ESC)

    # Camada 4: iframe + ESC (com re-checagem: ESC pode ter fechado o modal)
    if _tenta_iframe(driver, diz):
        return {'tipo': 'fechou', 'detalhe': f'fechado em iframe — {bloqueio[:80]}', 'el': None}
    if _tecla_esc(driver) and not detecta_bloqueio(driver):
        diz('    [bloqueio] ESC pressionado — overlay fechou')
        return {'tipo': 'fechou', 'detalhe': f'fechado via ESC — {bloqueio[:80]}', 'el': None}
    diz(f'    [bloqueio] sem fechamento: {bloqueio[:80]}')
    return {'tipo': 'indeciso', 'detalhe': bloqueio[:200], 'el': None}


# ── Bloqueio (Playwright) ────────────────────────────────────────────────────
# Versão de `tratar_bloqueio` para `page` do Playwright (gupy/infojobs/
# solides/nerdin): mesmos lances escalonados, mesmo contrato de retorno —
# só a mecânica muda (locator em vez de WebElement, ESC via
# `page.keyboard`, `page.frames` em vez de `switch_to`).

def detecta_bloqueio_pw(page) -> str | None:
    """Mesma detecção de overlay de `detecta_bloqueio`, para Playwright."""
    try:
        bruto = page.evaluate(BLOCKER_JS)
    except Exception:
        return None
    return bruto if isinstance(bruto, str) and bruto else None


def fechar_por_texto_pw(page) -> object | None:
    """Camada 1 (SEM LLM) para Playwright.

    `page.evaluate` devolve um ElementHandle quando acha o botão — quem chama
    fecha com `el.click()` (mesmo contrato de `fechar_por_texto`)."""
    try:
        el = page.evaluate(_CLOSE_BTN_JS)
    except Exception:
        return None
    if el is None or isinstance(el, (str, dict, list, int, float, bool)):
        return None
    return el


def _tecla_esc_pw(page) -> bool:
    try:
        page.keyboard.press('Escape')
        time.sleep(0.8)
        return True
    except Exception:
        return False


def _tenta_iframe_pw(page, diz: Callable[[str], None]) -> bool:
    """Igual a `_tenta_iframe`: modal costuma morar em iframe (cookie etc.)."""
    try:
        frames = [f for f in page.frames if f is not page.main_frame]
    except Exception:
        return False
    for fr in frames:
        try:
            bloqueio = fr.evaluate(BLOCKER_JS)
        except Exception:
            continue
        if not (isinstance(bloqueio, str) and bloqueio):
            continue
        try:
            el = fr.evaluate(_CLOSE_BTN_JS)
        except Exception:
            el = None
        if el is not None:
            with suppress(Exception):
                el.click()
            diz(f'    [bloqueio] modal fechado em iframe: {bloqueio[:80]}')
            time.sleep(1.0)
            return True
        with suppress(Exception):
            page.keyboard.press('Escape')
        time.sleep(0.8)
        try:
            if not fr.evaluate(BLOCKER_JS):
                diz('    [bloqueio] modal de iframe fechado via ESC')
                return True
        except Exception:
            pass
    return False


def tratar_bloqueio_pw(page, chamar: Callable[[str, int], str] | None = None,
                       log: Callable[[str], None] | None = None) -> dict:
    """Supervisor de bloqueio para Playwright — mesmo contrato de `tratar_bloqueio`.

    Camadas: 0) checar overlay (~5ms, SEM LLM); 1) captcha por palavras-
    chave; 2) fechamento rápido por texto (SEM LLM); 3) LLM (2 rodadas,
    até 3 seletores cada, erro retroalimenta); 4) iframe + ESC.

    Retorna `{"tipo", "detalhe", "el"}`: `el` é um Locator/ElementHandle
    pronto para `.click()` quando a camada 2 ou 3 encontrou o botão
    (None quando fechado em iframe/ESC ou quando não há nada a clicar).
    """
    def diz(msg: str) -> None:
        if log:
            log(msg)

    bloqueio = detecta_bloqueio_pw(page)
    if not bloqueio:
        return {'tipo': 'nada', 'detalhe': '', 'el': None}

    if any(k in bloqueio.lower() for k in _KEYWORDS_CAPTCHA):
        diz(f'    [bloqueio] captcha/desafio detectado — aguardando humano: {bloqueio[:80]}')
        return {'tipo': 'captcha', 'detalhe': bloqueio[:200], 'el': None}

    el = fechar_por_texto_pw(page)
    if el is not None:
        diz(f'    [bloqueio] fechamento rápido por texto (sem LLM): {bloqueio[:80]}')
        return {'tipo': 'fechou', 'detalhe': f'botão de fechamento por texto — {bloqueio[:80]}',
                'el': el}

    if chamar is not None:
        situacao, detalhe, el = _rodadas_llm(
            lambda sel: _encontrar_pw(page, sel),
            lambda: resumo_pagina_pw(page),
            bloqueio, chamar, diz,
        )
        if situacao == 'fechou':
            diz('    [bloqueio] ✅ fechado via LLM')
            return {'tipo': 'fechou', 'detalhe': detalhe, 'el': el}
        if situacao == 'captcha':
            return {'tipo': 'captcha', 'detalhe': detalhe, 'el': None}
        if situacao == 'nada':
            return {'tipo': 'nada', 'detalhe': detalhe, 'el': None}
        # 'falhou' → camada 4 (iframe + ESC)

    if _tenta_iframe_pw(page, diz):
        return {'tipo': 'fechou', 'detalhe': f'fechado em iframe — {bloqueio[:80]}', 'el': None}
    if _tecla_esc_pw(page) and not detecta_bloqueio_pw(page):
        diz('    [bloqueio] ESC pressionado — overlay fechou')
        return {'tipo': 'fechou', 'detalhe': f'fechado via ESC — {bloqueio[:80]}', 'el': None}
    diz(f'    [bloqueio] sem fechamento: {bloqueio[:80]}')
    return {'tipo': 'indeciso', 'detalhe': bloqueio[:200], 'el': None}


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


# ── Agente de passo: o LLM responde TODOS os campos em 1 chamada ────────────
# Substitui o "campo por campo" quando as regras determinísticas não resolveram:
# uma única chamada lê todas as perguntas do passo de uma vez → respostas
# consistentes entre si (mesmo nível, mesma pretensão salarial) e cobertura de
# tipos de pergunta que a tabela de regras não conhece. Contrato de resposta:
# radio/select → índice int; checkbox → lista de índices; texto → string curta
# ou "PULAR". Item inválido é omitido → o bot faz fallback per-field ali.

def _linha_campo(idx: int, c: dict) -> str:
    partes = [f'[{idx}] ID={c["id"]}', f'tipo={c["tipo"]}']
    if c.get("pergunta"):
        partes.append(f'pergunta="{c["pergunta"][:120]}"')
    if c.get("opcoes"):
        ops = " / ".join(f'{j}:{o[:40]}' for j, o in enumerate(c["opcoes"][:12]))
        partes.append(f'opcoes=[{ops}{" ..." if len(c["opcoes"]) > 12 else ""}]')
    return " ".join(partes)


def montar_prompt_agente(campos: list[dict], contexto_vaga: str,
                         regras: str = "") -> str:
    """Prompt do agente: todos os campos do passo + regras do perfil."""
    linhas = "\n".join(_linha_campo(i, c) for i, c in enumerate(campos))
    base = (
        "Você opera um navegador automatizado em um formulário de candidatura a emprego.\n"
        f"VAGA: {contexto_vaga[:200]}\n"
        f"CAMPOS DO PASSO ATUAL:\n{linhas}\n"
    )
    if regras:
        base += f"\nPERFIL DO CANDIDATO E REGRAS:\n{regras}\n"
    base += (
        "\nREGRAS DE RESPOSTA:\n"
        "1. radio/select: use o ÍNDICE (o número antes do texto em opcoes) da opção correta.\n"
        "2. checkbox: use uma LISTA de índices de TODAS as opções corretas "
        "(lista vazia se nenhuma se aplica).\n"
        "3. texto: resposta curta e direta (máx 15 palavras), com base no perfil. "
        "Se pedir salário atual/último ou for campo condicional que não se aplica → \"PULAR\".\n"
        "4. Respeite as regras de exclusão: tecnologia/senioridade excluída → NÃO/NENHUM.\n"
        "5. Seja consistente entre os campos (mesmo nível, mesma pretensão, mesma disponibilidade).\n\n"
        'RESPOSTA: SOMENTE um JSON válido, sem markdown: '
        '{"respostas": {"<ID>": valor}} — um item por campo, com o MESMO ID da lista acima.'
    )
    return base


def parse_batch(campos: list[dict], resposta: str) -> dict:
    """Extrai {id: valor} da resposta do agente. Itens inválidos são omitidos
    (o bot faz fallback per-field neles — nunca vira resposta errada)."""
    dados = _primeiro_json(resposta) or {}
    bruto = dados.get("respostas")
    if not isinstance(bruto, dict):
        return {}
    out: dict = {}
    for campo in campos:
        cid = campo["id"]
        if cid not in bruto:
            continue
        v = bruto[cid]
        if campo["tipo"] in ("radio", "select"):
            try:
                idx = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(campo.get("opcoes") or []):
                out[cid] = idx
        elif campo["tipo"] == "checkbox":
            if isinstance(v, list):
                nums = [int(x) for x in v if str(x).strip().isdigit()]
            else:
                nums = [int(x) for x in re.findall(r"\d+", str(v))]
            out[cid] = nums  # [] = "nenhuma se aplica" (o aplicador trata)
        else:
            out[cid] = str(v).strip()
    return out


def agente_campos(
    campos: list[dict],
    contexto_vaga: str,
    regras: str = "",
    chamar: Callable[[str, int], str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict:
    """Agente de passo: responde `campos` em UMA chamada de LLM.

    `campos` no formato dos bots: {"id","tipo","pergunta","opcoes":[...]} (mesmo
    formato que ia_processar_formulario usa). Retorna {id: valor} no contrato
    de `parse_batch`; {} quando não há LLM ou a chamada falhou — quem chama
    aplica o clássico per-field nesses casos (o agente nunca piora o estado).
    Custo: 1 chamada (~3-6s com Groq) no lugar de N chamadas campo a campo."""
    def diz(msg: str) -> None:
        if log:
            log(msg)

    if not campos or chamar is None:
        return {}
    prompt = montar_prompt_agente(campos, contexto_vaga, regras)
    try:
        resp = chamar(prompt, 900)
    except Exception as exc:
        diz(f'    [agente] LLM falhou: {exc}')
        return {}
    obtidas = parse_batch(campos, resp)
    diz(f'    [agente] {len(obtidas)}/{len(campos)} campo(s) resolvido(s) em 1 chamada')
    return obtidas
