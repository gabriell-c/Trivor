"""Leitor estrutural — o "olho" do bot via crawl4ai (anexa no Chrome vivo por CDP).

O crawl4ai lê a página em andamento e devolve a estrutura dela em markdown
(texto limpo + referências + links), pronto pra LLM entender como o site é.
Ele NÃO age: preencher o formulário logado continua sendo Selenium/Playwright.

Chamar só no caminho de resgate/fallback — o happy path segue zerado de
custo extra. Se o crawl4ai falhar ou não estiver instalado, o chamador
cai no digest do pagelens (mesmo resultado de antes, nunca pior).

Uso:
    from common import leitor
    leitura = leitor.leitura_estruturada(url, cdp_url="http://127.0.0.1:9333")
    texto   = leitor.resumo_para_llm(leitura, fallback=pagelens.resumo_pagina(driver))
"""
from __future__ import annotations

import asyncio
import atexit
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

__all__ = ["Leitura", "leitura_estruturada", "resumo_para_llm"]

log = logging.getLogger(__name__)

# Limite de links devolvidas: exceder não ajuda o LLM e infla o prompt.
_LIMITE_LINKS = 30


@dataclass(frozen=True)
class Leitura:
    """Resultado de uma leitura estrutural da página viva."""

    url: str
    ok: bool
    texto: str = ""             # markdown da página (já cortado no limite)
    referencias: str = ""       # seção de citações/links gerada pelo markdown
    links: tuple[str, ...] = () # links interno+externo (dedup, com teto)
    fonte: str = ""             # "c4a" | "falha_c4a" | "indisponivel"
    erro: str = ""


def _criar_crawler(cdp_url: str) -> Any:
    """Cria o crawler anexado ao Chrome do bot na porta CDP informada.

    Import tardio de propósito: sem crawl4ai instalado o módulo segue
    importável e o fallback (digest do pagelens) continua funcionando.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    config = BrowserConfig(cdp_url=cdp_url, headless=False)
    if hasattr(config, "verbose"):
        config.verbose = False
    return AsyncWebCrawler(config=config)


def _definir(model: Any, nome: str, valor: Any) -> None:
    """Atribui um campo se a versão instalada do crawl4ai o aceita.

    As configs do crawl4ai 0.9.x são classes planas (aceitam setattr
    livre); em versão futura com pydantic, campo inexistente levanta
    AttributeError — aí seguimos o padrão da versão. Nunca quebra o
    módulo por drift de API.
    """
    try:
        setattr(model, nome, valor)
    except AttributeError:
        log.debug("leitor: campo '%s' ausente nesta versão do crawl4ai; usando o padrão", nome)


async def _leer(crawler: Any, url: str, timeout_s: float) -> Any:
    """Executa o crawl (navega a URL numa aba NOVA do browser anexado).

    Abre uma aba separada: a aba logada onde o bot trabalha não é tocada.
    Encerra o crawler no finally (o Chrome em si segue rodando).
    """
    from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator

    await crawler.start()
    try:
        config = CrawlerRunConfig()
        config.markdown_generator = DefaultMarkdownGenerator()
        _definir(config, "remove_overlay_elements", True)
        _definir(config, "page_timeout", int(timeout_s * 1000))
        _definir(config, "verbose", False)
        return await crawler.arun(url, config=config)
    finally:
        await _encerrar(crawler)


async def _encerrar(crawler: Any) -> None:
    """Encerra o anexo sem deixar transporte aberto.

    Em 0.9.5 o encerramento real é close() (mesmo do context manager);
    stop() nem existe. Nas versões em que os dois existirem, close()
    com sucesso já resolve — stop() fica como plano B. Falha aqui não
    joga fora a leitura já capturada.
    """
    fechar = getattr(crawler, "close", None)
    if fechar is not None:
        try:
            await fechar()
            return
        except Exception:
            log.warning("leitor: erro no close() do crawler; tentando stop()")
    parar = getattr(crawler, "stop", None)
    if parar is not None:
        try:
            await parar()
        except Exception:
            log.warning("leitor: erro ao encerrar o crawler (leitura já capturada)")


# O motor do leitor roda numa thread de trabalho com o próprio loop
# persistente (um por processo). Isolar assim a proteção de verdade:
# o estado asyncio da thread que CHAMA não interfere e não é
# interferido — vazamentos de libs de terceiros (caso conhecido: o
# marcador "loop andante" que o pytest-playwright trava na thread
# principal) não bloqueiam a leitura nem corrompem o teardown delas.
_WORKER: ThreadPoolExecutor | None = None
_WORKER_LOOP: asyncio.AbstractEventLoop | None = None


def _obter_worker() -> ThreadPoolExecutor:
    global _WORKER
    if _WORKER is None:
        _WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="leitor-c4a")
        atexit.register(_WORKER.shutdown)
    return _WORKER


def _rodar_async(coro: Any) -> Any:
    """Executa o coroutine numa thread de trabalho (API bloqueante).

    O chamador espera o resultado (a API é síncrona por contrato). Na
    thread do worker roda no loop persistente dela — vivo até o fim
    do processo, o que evita a traceback de GC de loops fechados no
    Windows e deixa o estado asyncio da thread principal intacto.
    """
    def rodar_no_worker() -> Any:
        global _WORKER_LOOP
        if _WORKER_LOOP is None or _WORKER_LOOP.is_closed():
            _WORKER_LOOP = asyncio.new_event_loop()
            asyncio.set_event_loop(_WORKER_LOOP)
        return _WORKER_LOOP.run_until_complete(coro)

    return _obter_worker().submit(rodar_no_worker).result()


def _links_do_resultado(res: Any) -> tuple[str, ...]:
    mapa = getattr(res, "links", None) or {}
    if not isinstance(mapa, dict):
        return ()
    vistos: dict[str, None] = {}
    for chave in ("internal", "external"):
        for item in mapa.get(chave) or []:
            href = item.get("href") if isinstance(item, dict) else getattr(item, "href", "")
            if href:
                vistos.setdefault(href, None)
    return tuple(vistos)[:_LIMITE_LINKS]


def leitura_estruturada(
    url: str,
    cdp_url: str,
    limite: int = 2600,
    timeout_s: float = 90.0,
    factory: Callable[[str], Any] | None = None,
) -> Leitura:
    """Lê a estrutura da página viva anexando ao Chrome por CDP.

    `factory` existe só p/ testes (injetar crawler fake); em produção, None.
    Qualquer falha vira `Leitura(ok=False)` — nunca propaga exceção.
    """
    criar = factory if factory is not None else _criar_crawler
    try:
        crawler = criar(cdp_url)
    except ImportError as exc:
        return Leitura(url=url, ok=False, fonte="indisponivel", erro=str(exc))

    coro = _leer(crawler, url, timeout_s)
    try:
        cont = _rodar_async(coro)
    except Exception as exc:
        # Anexo fechado, timeout, Chrome fora do ar, crash do crawl:
        # tudo vira Leitura de falha pra o chamador decidir o fallback.
        coro.close()  # não deixou o coroutine agendado — evita aviso de GC
        return Leitura(url=url, ok=False, fonte="falha_c4a", erro=f"{type(exc).__name__}: {exc}")

    resultados = getattr(cont, "_results", None) or []
    if not resultados:
        return Leitura(url=url, ok=False, fonte="falha_c4a", erro="sem resultado no container")
    res = resultados[0]
    if not bool(getattr(res, "success", False)):
        return Leitura(url=url, ok=False, fonte="falha_c4a",
                       erro=str(getattr(res, "error", "falha de crawl")))

    markdown = getattr(res, "markdown", "") or ""
    texto = str(markdown)[: max(0, limite)]
    if not texto.strip():
        return Leitura(url=url, ok=False, fonte="falha_c4a", erro="markdown vazio")
    dump = markdown.model_dump() if callable(getattr(markdown, "model_dump", None)) else {}
    referencias = str(dump.get("references_markdown") or "")[: max(0, limite) // 2]
    return Leitura(url=url, ok=True, texto=texto, referencias=referencias,
                   links=_links_do_resultado(res), fonte="c4a")


def resumo_para_llm(leitura: Leitura, fallback: str = "") -> str:
    """Texto pronto para o prompt: a leitura c4a se deu ok, senão o digest de fallback.

    É aqui que o "nunca pior que o fluxo clássico" é garantido: leitura
    malformada ou falha → o fallback (ex.: resumo do pagelens) entra intacto.
    """
    if not (leitura.ok and leitura.texto.strip()):
        return fallback
    partes = [leitura.texto]
    if leitura.referencias.strip():
        partes.append(f"\n\n[referências de links]\n{leitura.referencias}")
    if leitura.links:
        partes.append("\n\n[links]\n" + "\n".join(leitura.links))
    return "\n".join(partes)
