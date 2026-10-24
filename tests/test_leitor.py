"""Testes do leitor estrutural (apply/common/leitor.py).

Crawler fake injetado via `factory` — nenhum Chrome, nem crawl4ai, nem
navegação real entra: o módulo é duck-typed em `crawler.start()/arun()/stop()`.
Cobre o caminho ok, os quatro modos de falha e a regra de ouro do fallback:
toda leitura ruim devolve o texto do pagelens intacto.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _carregar_leitor():
    p = ROOT / 'apply' / 'common' / 'leitor.py'
    spec = importlib.util.spec_from_file_location('apply_leitor_teste', p)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolve anotações em sys.modules[nome do módulo];
    # registrar antes do exec evita KeyError->None no _process_class
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


leitor = _carregar_leitor()


class _MarkdownFake:
    """Imita StringCompatibleMarkdown: str-able + model_dump opcional."""

    def __init__(self, texto: str = "", referencias: str = ""):
        self._texto = texto
        self._dump = None
        if referencias:
            self._dump = {"references_markdown": referencias}

    def __str__(self) -> str:
        return self._texto

    def model_dump(self) -> dict:
        return self._dump or {}


class _ResFake:
    def __init__(self, markdown="", links=None, success=True, error=""):
        self.url = "https://site/etapa"
        self.markdown = markdown
        self.links = links if links is not None else {
            "internal": [],
            "external": [{"href": "https://site/x", "text": "X"}],
        }
        self.success = success
        self.error = error


class _ContFake:
    def __init__(self, resultados):
        self._results = resultados


class _CrawlerFake:
    def __init__(self, resultados=None, exc=None, close_exc=False):
        self._resultados = resultados
        self.exc = exc
        self.close_exc = close_exc
        self.iniciou = False
        self.parou = False
        self.fechou = False

    async def start(self) -> None:
        if self.exc:
            raise self.exc
        self.iniciou = True

    async def stop(self) -> None:
        self.parou = True

    async def close(self) -> None:
        if self.close_exc:
            raise RuntimeError("close simulado quebrado")
        self.fechou = True

    async def arun(self, url, config=None):
        if self.exc:
            raise self.exc
        return _ContFake(self._resultados or [])


def test_leitura_ok_prende_texto_e_links():
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake("conteudo da pagina"))])
    leitura = leitor.leitura_estruturada("https://site/etapa", "http://127.0.0.1:9333",
                                         factory=lambda u: crawler)
    assert leitura.ok is True
    assert leitura.fonte == "c4a"
    assert leitura.texto == "conteudo da pagina"
    assert "https://site/x" in leitura.links
    assert crawler.fechou is True, "close() libera os recursos do CDP"
    assert crawler.parou is False, "stop() é plano B: só roda se close() falhar"


def test_leitura_corta_no_limite():
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake("a" * 5000))])
    leitura = leitor.leitura_estruturada("u", "c", limite=100, factory=lambda u: crawler)
    assert len(leitura.texto) == 100


def test_sem_resultado_no_container():
    crawler = _CrawlerFake([])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is False
    assert leitura.fonte == "falha_c4a"
    assert "sem resultado" in leitura.erro


def test_crawl_com_sucesso_falso():
    crawler = _CrawlerFake([_ResFake(success=False, error="timeout de navegacao")])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is False
    assert "timeout de navegacao" in leitura.erro
    assert crawler.fechou is True, "teardown roda no finally mesmo com falha de crawl"


def test_close_falha_cai_no_stop():
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake("x"))], close_exc=True)
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is True
    assert crawler.fechou is False
    assert crawler.parou is True, "stop() assume quando close() quebra"


def test_markdown_vazio_vira_falha():
    crawler = _CrawlerFake([_ResFake(markdown="   ")])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is False
    assert "vazio" in leitura.erro


def test_excecao_no_crawl_vira_falha_sem_propagar():
    crawler = _CrawlerFake(exc=TimeoutError("anexo fechado"))
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is False
    assert leitura.fonte == "falha_c4a"
    assert "TimeoutError" in leitura.erro


def test_crawl4ai_nao_instalado_vira_indisponivel():
    def criar_sempre_falha(cdp_url: str):
        raise ImportError("No module named 'crawl4ai'")

    leitura = leitor.leitura_estruturada("u", "c", factory=criar_sempre_falha)
    assert leitura.ok is False
    assert leitura.fonte == "indisponivel"
    assert "crawl4ai" in leitura.erro


def test_links_desduplicados_e_com_teto():
    crawler = _CrawlerFake([_ResFake(
        markdown=_MarkdownFake("x"),
        links={"internal": [{"href": "https://site/a"}, {"href": "https://site/a"}],
               "external": [{"href": f"https://outro/{i}"} for i in range(50)]},
    )])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.links[0] == "https://site/a"
    assert leitura.links.count("https://site/a") == 1
    assert len(leitura.links) == 30, "teto de links devolvidas"


def test_resumo_uma_leitura_bem_sucedida():
    leitura = leitor.Leitura(url="u", ok=True, texto="corpo",
                             referencias="[1] https://x", links=("https://a",))
    texto = leitor.resumo_para_llm(leitura, fallback="fallback")
    assert texto.startswith("corpo")
    assert "[links]" in texto
    assert "https://a" in texto
    assert "fallback" not in texto


def test_resumo_falha_devolves_fallback_intacto():
    leitura = leitor.Leitura(url="u", ok=False, fonte="falha_c4a", erro="x")
    fallback = "digest do pagelens"
    assert leitor.resumo_para_llm(leitura, fallback) == fallback
    assert leitor.resumo_para_llm(leitor.Leitura(url="u", ok=True, texto="  "), "fb") == "fb"


def test_motor_roda_em_thread_separada_do_chamador():
    # Garantia estrutural da isolação: o crawl roda numa thread de
    # trabalho do leitor, nunca na thread (nem no loop) do chamador.
    # É o que protege o módulo de vazamentos de asyncio de terceiros
    # (caso conhecido: pytest-playwright trava o marcador de loop da
    # thread principal) sem tocar no estado deles.
    import threading

    vistos: dict[str, int] = {}

    class _CrawlerRegistrado(_CrawlerFake):
        async def start(self) -> None:
            vistos["motor"] = threading.get_ident()
            await super().start()

    crawler = _CrawlerRegistrado([_ResFake(markdown=_MarkdownFake("x"))])
    vistos["chamador"] = threading.get_ident()
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is True
    assert vistos["motor"] != vistos["chamador"], "o motor do leitor é thread própria"


# ── Mapa de seções (inteligência estrutural pro LLM) ─────────────────────────

def test_leitura_extrai_mapa_de_secoes():
    md = "# Portal de Candidaturas\n## Etapa 2: Dados pessoais\n### Dados bancários\n## Revisão"
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake(md))])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.secoes == ("# Portal de Candidaturas", "## Etapa 2: Dados pessoais",
                               "### Dados bancários", "## Revisão")
    resumo = leitor.resumo_para_llm(leitura)
    assert "[mapa de seções]" in resumo
    assert "## Etapa 2: Dados pessoais" in resumo


def test_mapa_ignora_arrovo_dentro_de_frase():
    md = "texto normal\nprêmio #2 da lista\n# Título de verdade"
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake(md))])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.secoes == ("# Título de verdade",)


def test_mapa_com_teto_e_ordem_preservada():
    md = "\n".join(f"## seção {i}" for i in range(40))
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake(md))])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert len(leitura.secoes) == 15, "teto do mapa: 15 seções"
    assert leitura.secoes[0] == "## seção 0" and leitura.secoes[-1] == "## seção 14"


def test_resumo_sem_secoes_nao_anexa_mapa():
    leitura = leitor.Leitura(url="u", ok=True, texto="corpo")
    assert "[mapa de seções]" not in leitor.resumo_para_llm(leitura, "fb")


def test_limite_zero_vira_falha_markdown_vazio():
    # limite<=0 corta o texto a vazio → leitura não pode passar como ok
    crawler = _CrawlerFake([_ResFake(markdown=_MarkdownFake("conteudo"))])
    leitura = leitor.leitura_estruturada("u", "c", limite=0, factory=lambda u: crawler)
    assert leitura.ok is False
    assert "vazio" in leitura.erro


def test_links_com_items_objeto_nao_dict():
    class _LinkObj:
        def __init__(self, href: str):
            self.href = href

    crawler = _CrawlerFake([_ResFake(
        markdown=_MarkdownFake("x"),
        links={"internal": [_LinkObj("https://site/interna")], "external": []},
    )])
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert "https://site/interna" in leitura.links


def test_container_sem_atributo_results_vira_falha():
    class _ContVazio:
        pass  # nem o atributo _results existe

    crawler = _CrawlerFake()

    async def arun_cru(url, config=None):
        return _ContVazio()

    crawler.arun = arun_cru
    leitura = leitor.leitura_estruturada("u", "c", factory=lambda u: crawler)
    assert leitura.ok is False
    assert "sem resultado" in leitura.erro

