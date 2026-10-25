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
  - LLM: somente provedores cadastrados na UI do Trivor (config.yaml → ia)
    · Provedor ativo em 1º, demais em ordem de cadastro (fallback)
    · Nenhum cadastrado ou todos falharem → fallbacks locais
      para perguntas abertas e apresentação
  - Salvamento de respostas das perguntas e apresentação no relatório
  - .txt diário com append (não sobrescreve a cada vaga)
"""

import contextlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from common import dryrun, loginonly, pagelens, perfil
from common.browser import (
    SESSIONS_DIR,
    Browser,
    BrowserUnavailable,
    aba_morta,
    find_adaptive,
    reabrir_aba,
)
from dotenv import load_dotenv
from playwright.sync_api import Page

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
#  IA — LLM + FALLBACKS + GERADORES (em gupy_ia.py)
# ══════════════════════════════════════════════════════════════════════════════

from gupy_ia import *  # noqa: F403 — camada de IA (roteador Groq/Gemini/Mistral, fallbacks, geradores)

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

    for _ in range(300):
        if "portal.gupy.io" in page.url or "app.gupy.io" in page.url:
            break
        time.sleep(1)
    else:
        if sys.stdin.isatty():
            input("  ▶  Portal não carregou. Pressione ENTER quando carregar... ")
        else:
            log("  ⏳ Espera do portal esgotada — seguindo (a verificação de sessão abaixo decide)")

    log("✅ Logado! (sessão fica guardada em apply/sessions/gupy/)")


def verificar_sessao_valida(page: Page) -> bool:
    try:
        page.goto(URL_PORTAL, timeout=15000)
        esperar(page, 2)
        return "signin" not in page.url and "login" not in page.url
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  BUSCA DE VAGAS
# ══════════════════════════════════════════════════════════════════════════════

def filtrar_vaga(titulo: str, config: dict) -> bool:
    negativas = config["busca"].get("palavras_excluir", [])
    # fronteira de palavra: "java" não cai em "Javascript"
    return perfil.titulo_excluido(titulo, negativas) is None


def buscar_vagas_gupy(page: Page, config: dict) -> tuple[list, Page]:
    vagas        = []
    links_vistos = set()
    termos       = config["busca"]["palavras_chave"]

    # Em dry-run dá pra testar o fluxo num único termo (busca completa dura
    # ~40min): TRIVOR_DRY_RUN_TERMO="analista de sistemas". Só em dry-run,
    # a produção varre todos os termos.
    if dryrun.ativo():
        termo_unico = os.environ.get("TRIVOR_DRY_RUN_TERMO", "").strip()
        if termo_unico and termo_unico in termos:
            log(f"🧪 [dry-run] testando o fluxo só com '{termo_unico}'")
            termos = [termo_unico]

    for termo in termos:
        log(f"\n🔍 Buscando: {termo}")
        if aba_morta(page):
            log("  🔄 Aba cravou — reabrindo para continuar a busca")
            page = reabrir_aba(page)
        termo_url = termo.replace(" ", "%20")
        url = URL_BUSCA.format(termo=termo_url)

        try:
            page.goto(url, timeout=20000)
            esperar(page, 3)
            scroll_humano(page)

            pagina    = 1
            max_pags  = 5

            while pagina <= max_pags:
                if aba_morta(page):
                    log("  🔄 Aba cravou — reabrindo e voltando à página 1")
                    page = reabrir_aba(page)
                    page.goto(url, timeout=20000)
                    esperar(page, 3)
                    pagina = 1
                    continue

                cards = page.query_selector_all('a[href*="gupy.io/job/"]')
                if not cards:
                    # Portal renomeou a classe → relocaliza o 1º card pelo
                    # seletor adaptativo (css → xpath estável salvo → texto)
                    first = find_adaptive(page, 'a[href*="gupy.io/job/"]', None, SPEC_DIR / "cards.json")
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
    return vagas, page


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

        if dryrun.ativo():
            log("  [dry-run] cheguei nas etapas da candidatura — parando antes de preencher (nada enviado)")
            resultado["status"] = dryrun.STATUS
            nova_aba.close()
            return resultado

        # ── Loop de etapas ──────────────────────────────────────────────────
        max_etapas = 15
        etapa_num  = 0
        finalizado = False
        bloqueios_seguidos = 0

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

            # ── Supervisor de tela: overlay que os tratadores específicos da
            #    Gupy não cobriram (layout mudou, modal novo). Escalonamento:
            #    texto conhecido (SEM LLM) → LLM (2 rodadas) → ESC → parada.
            bloqueio = pagelens.tratar_bloqueio_pw(
                nova_aba,
                chamar=lambda prompt, max_tokens=300: _chamar_llm(
                    prompt, config, contexto=vaga.get("titulo", ""),
                    temperatura=0.05, max_tokens=max_tokens),
                log=log,
            )
            if bloqueio["tipo"] == "fechou":
                if bloqueio["el"] is not None:
                    with contextlib.suppress(Exception):
                        bloqueio["el"].click()
                log(f"  [bloqueio] modal fechado: {bloqueio['detalhe'][:80]}")
                esperar(nova_aba, 1.5)
                continue
            if bloqueio["tipo"] == "captcha":
                log(f"  [bloqueio] desafio humano: {bloqueio['detalhe'][:80]}")
                bloqueios_seguidos += 1
                if bloqueios_seguidos >= 3:
                    log("  [bloqueio] captcha sem resolução — parando a vaga")
                    resultado["status"] = "captcha_nao_resolvido"
                    break
                esperar(nova_aba, 8)  # dá chance de um humano resolver (headed)
                continue
            if bloqueio["detalhe"]:
                # "indeciso" ou overlay que o LLM mandou ignorar
                bloqueios_seguidos += 1
                log(f"  [bloqueio] tela bloqueada ({bloqueios_seguidos} seguidas): "
                    f"{bloqueio['detalhe'][:80]}")
                if bloqueios_seguidos >= 3:
                    log("  [bloqueio] modal sem resolução — parando a vaga")
                    resultado["status"] = "modal_nao_resolvido"
                    break
                continue
            bloqueios_seguidos = 0

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

        if not finalizado and resultado["status"] not in ("modal_nao_resolvido", "captcha_nao_resolvido"):
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

    # IA: somente provedores cadastrados na UI (config.yaml → ia, aba IA)
    from common import llm as _llm
    if not _llm.providers_ativos(config):
        print("❌ Sem IA configurada: cadastre um provedor na aba IA do Trivor")
        return

    ja_candidatados = links_ja_candidatados_gupy()
    log(f"📋 {len(ja_candidatados)} vagas já candidatadas anteriormente")

    cdp_port = int(config["automacao"].get("cdp_port", 9333))
    b = Browser(profile="gupy", headless=False, cdp_port=cdp_port)
    try:
        b.start()
    except BrowserUnavailable as e:
        log("❌ Nenhum browser disponível — " + " | ".join(f"{n}: {r}" for n, r in e.tried))
        return
    page = b.page
    log(f"🌐 Engine no uso: {b.engine} (fallback tentado: {[n for n, _ in b.tried] or 'nenhum'})")
    # Leitor estrutural (crawl4ai lê a página viva via CDP) — só quando a
    # engine é Chromium; camoufox (Firefox) segue o fluxo clássico.
    pagelens.habilitar_leitor(b.cdp_url)
    log(f"🔎 Leitor estrutural: {'CDP ' + b.cdp_url if b.cdp_url else 'desligado (engine Firefox)'}")

    if not verificar_sessao_valida(page):
        log("🔑 Sem sessão válida. Login manual necessário...")
        fazer_login_manual(page, config)
        page.goto(URL_PORTAL, timeout=15000)
        esperar(page, 2)
        if not verificar_sessao_valida(page):
            log("❌ Login falhou. Encerrando.")
            b.close()
            if loginonly.ativo():
                raise SystemExit(1)
            return
    else:
        log("✅ Sessão válida!")

    # Botão "Logar" da UI: sessão garantida → para aqui, sem buscar/candidatar
    if loginonly.ativo():
        log("✅ Sessão GUPY salva (perfil persistente) — modo só-login, encerrando")
        b.close()
        return

    # Se a aba cravou durante a busca, `page` volta como a tab reaberta —
    # o loop de candidatura continua nela (a sessão do perfil persiste)
    vagas, page = buscar_vagas_gupy(page, config)
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
            if dryrun.ativo():
                if resultado.get("status") == dryrun.STATUS:
                    log("[dry-run] cheguei na aba de preenchimento — parando sem salvar nada")
                    break
                log(f"[dry-run] {resultado.get('status')} — sem chegar no formulário; tentando a próxima vaga")
                continue
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
