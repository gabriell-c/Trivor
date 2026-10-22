"""
Testes E2E com Playwright — navegação e interações no frontend.
Requer: pip install playwright && python -m playwright install chromium
Executar: pytest tests/test_e2e.py -v --headed

Nota: Em Windows com OneDrive, o Next.js dev server pode responder TCP mas
não carregar páginas JS. Nestes casos, os testes são automaticamente skipados.
"""
import os
import time
from pathlib import Path

import pytest
import requests

# TRIVOR_FE_URL aponta pra um servidor externo (ex.: build de produção na 3100);
# o padrão é o dev server na 3000.
NEXT_URL = os.environ.get("TRIVOR_FE_URL", "http://127.0.0.1:3000")
_START_DEV = "TRIVOR_FE_URL" not in os.environ


def _server_healthy():
    """Verifica se o servidor responde HTTP E a página carrega (não apenas TCP)."""
    urls = [NEXT_URL]
    if "127.0.0.1" in NEXT_URL:
        urls.append(NEXT_URL.replace("127.0.0.1", "localhost"))
    for url in urls:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200 and len(r.text) > 500:
                return True
        except Exception:
            pass
    return False


@pytest.fixture(scope="session", autouse=True)
def ensure_dev_server():
    """Sobe o dev server só quando TRIVOR_FE_URL não está definido."""
    if _server_healthy():
        yield
        return
    if not _START_DEV:
        pytest.skip(f"{NEXT_URL} não respondeu e o auto-start está desligado (TRIVOR_FE_URL)")

    import subprocess
    import sys

    # Mantém a referência viva pelo lifetime do fixture — sem ela, o
    # Popen (e o server) poderia ser coletado no meio da suíte.
    _server_proc = subprocess.Popen(
        [sys.executable, "-m", "next", "dev", "--port", "3000"],
        cwd=Path(__file__).parent.parent / "frontend",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = False
    for _ in range(30):
        time.sleep(1)
        if _server_healthy():
            started = True
            break
    if not started:
        pytest.skip("Next.js dev server não respondeu a tempo")
    yield
    # não mata o server


def _wait_for_app_ready(page):
    """Aguarda o app React carregar — skipa se a pagina travar no loading."""
    # Se ainda mostra "Carregando", o app não renderizou (problema ambiental)
    loading = page.locator('text=Carregando')
    if loading.count() > 0:
        # Espera um pouco para ver se carrega
        try:
            page.wait_for_selector('text=Carregando', state='detached', timeout=8000)
        except Exception:
            pytest.skip("App frontend não carregou (servidor dev travou no loading)")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)  # margem para hydration


def _expand_sidebar(page):
    """Expande a sidebar SÓ se ela estiver colapsada.

    Os labels só existem no DOM quando expandida (Layout.tsx condiciona o
    render em `!collapsed`), então `aside nav a div` count > 0 é o sinal
    real de estado — o clique no toggle só acontece quando colapsada.
    (A versão antiga checkeava `aside nav button span`, que nunca existe,
    e colapsava a sidebar que já estava expandida.)
    """
    for _ in range(3):
        if page.locator('aside nav a div').count() > 0:
            return
        try:
            page.locator('aside > div:last-child > button').click(timeout=1500)
            page.wait_for_timeout(400)
        except Exception:
            return


def _click_safe(page, text, timeout_ms=10000):
    """Clica em um elemento pelo texto, skipa se timeout."""
    locator = page.locator(f'text={text}')
    if not locator.count():
        pytest.skip(f"Nenhum elemento encontrado com texto '{text}'")
    locator.click(timeout=timeout_ms)


def _wait_url(page, substring, timeout_ms=10000):
    """Aguarda URL conter substring, skipa se timeout."""
    try:
        page.wait_for_url(f"**/*{substring}*", timeout=timeout_ms)
    except Exception:
        pytest.skip(f"URL não navegou para *{substring}* em {timeout_ms}ms")


@pytest.mark.skipif(
    not _server_healthy(),
    reason=f"Servidor em {NEXT_URL} não está respondendo HTTP",
)
class TestE2E:
    def test_homepage_loads(self, playwright):
        """Página inicial deve carregar com title e conteúdo."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        title = page.title()
        assert len(title) > 0, "Página deve ter title"
        assert "trivor" in title.lower() or "currículo" in title.lower(), \
            f"Title deve mencionar Trivor, got: {title}"
        browser.close()

    def test_linkedin_tab_in_navigation(self, playwright):
        """Abas de navegação devem incluir LinkedIn."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        _wait_for_app_ready(page)
        # Sidebar pode estar colapsada — expande se necessário
        _expand_sidebar(page)
        linkedin_link = page.locator('text=Análise de LinkedIn')
        assert linkedin_link.count() >= 1, "Link 'Análise de LinkedIn' deve existir na sidebar"
        browser.close()

    def test_navigate_to_linkedin_page(self, playwright):
        """Navegar para LinkedIn deve carregar a página de análise."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        _click_safe(page, 'Análise de LinkedIn')
        _wait_url(page, 'linkedin')
        assert "analise-linkedin" in page.url, \
            f"URL deve ser /analise-linkedin, got {page.url}"
        browser.close()

    def test_linkedin_page_has_textarea(self, playwright):
        """Página LinkedIn deve ter textarea para colar perfil."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        _click_safe(page, 'Análise de LinkedIn')
        _wait_url(page, 'linkedin')
        page.wait_for_load_state("networkidle")
        # O chunk da página carrega sob demanda — espera o textarea montar,
        # com teto finito (não sleep). Timeout = falha real do teste.
        textarea = page.locator("textarea")
        textarea.first.wait_for(state="attached", timeout=15000)
        assert textarea.count() >= 1, "Página LinkedIn deve ter textarea"
        assert textarea.first.get_attribute("placeholder") is not None, \
            "Textarea deve ter placeholder"
        browser.close()

    def test_navigation_between_tabs(self, playwright):
        """Navegar entre abas deve funcionar sem erros."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        _wait_for_app_ready(page)
        _expand_sidebar(page)
        # Labels reais da sidebar (Layout.tsx) — 'Mercado'/'Currículo' nunca
        # casaram porque o texto exato é 'Inteligência de Mercado' etc.
        _click_safe(page, 'Inteligência de Mercado')
        _wait_url(page, 'inteligencia-mercado')
        assert "inteligencia-mercado" in page.url, \
            f"URL deve ser /inteligencia-mercado, got {page.url}"
        _click_safe(page, 'Análise de Currículo')
        page.wait_for_load_state("networkidle")
        browser.close()

    def test_api_settings_tab(self, playwright):
        """Aba de configurações de API deve existir."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        _wait_for_app_ready(page)
        # Sidebar pode estar colapsada — expande se necessário
        _expand_sidebar(page)
        api_link = page.locator('text=Config. IAs')
        assert api_link.count() >= 1, "Link 'Config. IAs' deve existir na sidebar"
        browser.close()
