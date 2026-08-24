"""
Testes E2E com Playwright — navegação e interações no frontend.
Requer: pip install playwright && python -m playwright install chromium
Executar: pytest tests/test_e2e.py -v --headed
"""
import pytest
import requests
import time
import socket
import os

NEXT_URL = "http://127.0.0.1:3000"


def _server_http_ready():
    """Verifica se o servidor responde HTTP 200 — não apenas TCP ouvindo."""
    try:
        r = requests.get(NEXT_URL, timeout=10)
        return r.status_code == 200
    except Exception:
        pass
    try:
        r = requests.get("http://localhost:3000", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def ensure_dev_server():
    """Inicia o dev server se necessário."""
    started = False
    if not _server_http_ready():
        import subprocess, sys
        proc = subprocess.Popen(
            [sys.executable, "-m", "next", "dev", "--port", "3000"],
            cwd=r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\frontend",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Aguarda up
        for _ in range(30):
            time.sleep(1)
            if _server_http_ready():
                started = True
                break
        if not started:
            pytest.skip("Next.js dev server não respondeu HTTP a tempo")
    yield
    # cleanup: se iniciamos, manter rodando (não kill)


@pytest.mark.skipif(
    not _server_http_ready(),
    reason="Next.js dev server não respondendo HTTP em http://127.0.0.1:3000",
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
        # Verifica link "Análise de LinkedIn" na sidebar
        linkedin_link = page.locator('text=Análise de LinkedIn')
        assert linkedin_link.count() >= 1, "Link 'Análise de LinkedIn' deve existir na sidebar"
        browser.close()

    def test_navigate_to_linkedin_page(self, playwright):
        """Navegar para LinkedIn deve carregar a página de análise."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        page.click('text=Análise de LinkedIn')
        page.wait_for_load_state("networkidle")
        assert "/linkedin" in page.url, f"URL deve ser /linkedin, got {page.url}"
        browser.close()

    def test_linkedin_page_has_textarea(self, playwright):
        """Página LinkedIn deve ter textarea para colar perfil."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        page.click('text=Análise de LinkedIn')
        page.wait_for_load_state("networkidle")
        textarea = page.locator("textarea")
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
        # Navega para Mercado
        page.click('text=Mercado')
        page.wait_for_load_state("networkidle")
        assert "/market" in page.url or "market" in page.url.lower(), \
            f"URL deve conter 'market', got {page.url}"
        # Volta para o início
        page.click('text=Currículo')
        page.wait_for_load_state("networkidle")
        browser.close()

    def test_api_settings_tab(self, playwright):
        """Aba de configurações de API deve existir."""
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(NEXT_URL)
        page.wait_for_load_state("networkidle")
        api_link = page.locator('text=Configurações de API')
        assert api_link.count() >= 1, "Link 'Configurações de API' deve existir na sidebar"
        browser.close()
