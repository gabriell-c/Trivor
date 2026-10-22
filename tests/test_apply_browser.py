"""
Testes da camada de navegador do Job Hunter (apply/common/browser.py).

Cobrem: import das engines, cadeia de fallback, persistência de sessão entre
runs, interações reais (fill/click) em cada engine, escalada do
find_adaptive (css → xpath estável → texto) e o delay humano.

Os browsers são headless e rodam contra um http.server local em 127.0.0.1 —
nenhum acesso a portal real.
"""
import http.server
import json
import shutil
import sys
import threading
from pathlib import Path

import pytest

APPLY_DIR = Path(__file__).parent.parent / "apply"
sys.path.insert(0, str(APPLY_DIR))

from common import browser as bmod

PAGE_F = """<html><body>
<input id="a">
<button id="go" class="__cls__">ir</button>
<span id="out">inicio</span>
<script>
  document.getElementById('go').onclick = () => document.getElementById('out').textContent = 'fui';
  document.getElementById('a').addEventListener('input', e => {
    document.getElementById('out').textContent = e.target.value + '->ok';
  });
</script>
</body></html>"""

PAGE = PAGE_F.replace('__cls__', '__CLS__')


def _page_for(cls: str, extra_before_input: str = '') -> str:
    html = PAGE.replace('__CLS__', cls)
    if extra_before_input:
        html = html.replace('<input', extra_before_input, 1)
    return html


PAGES = {
    'v1': _page_for('sc-abc123'),
    # v2: classe renomeada pelo portal (caso real: a.sc-4d881605-1 da Gupy),
    # mesma posição na árvore.
    'v2': _page_for('totally-renamed'),
    # v3: elemento extra antes do input → xpath de posição também quebra →
    # só o texto visível salva.
    'v3': _page_for('sc-abc123', extra_before_input='<p>anterior</p>\n<input'),
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.lstrip('/')
        html = PAGES.get(name, '<html><body>404</body></html>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, *a):
        pass


@pytest.fixture(scope='module')
def srv():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    yield base
    httpd.shutdown()


def _clean_profile(name: str) -> None:
    shutil.rmtree(bmod.SESSIONS_DIR / name, ignore_errors=True)


def _with_engine(engine: str | tuple[str, ...], headless: bool = True, profile: str | None = None):
    return BrowserCtx(engine, headless, profile)


class BrowserCtx:
    """Helper: sobe Browser headless com 1 engine (ou cadeia) e fecha no fim."""
    def __init__(self, engine, headless=True, profile=None):
        engines = (engine,) if isinstance(engine, str) else tuple(engine)
        self.b = bmod.Browser(profile=profile, headless=headless, engines=engines)
        self.name = None

    def __enter__(self):
        self.b.start()
        self.name = self.b.engine
        assert self.b.page is not None
        return self.b

    def __exit__(self, *exc):
        self.b.close()


# ============================================================================
# Engines e fallback
# ============================================================================

class TestEngines:
    def test_core_imports(self):
        import camoufox.sync_api
        import patchright.sync_api
        assert hasattr(patchright.sync_api, 'sync_playwright')
        assert hasattr(camoufox.sync_api, 'Camoufox')
        assert bmod.ENGINES == ('camoufox', 'patchright', 'playwright', 'undetected')

    @pytest.mark.parametrize('engine', ['camoufox', 'patchright', 'playwright'])
    def test_interactions(self, engine, srv):
        with _with_engine(engine) as b:
            assert b.engine == engine
            b.page.goto(f'{srv}/v1')
            b.page.fill('#a', 'x')
            assert b.page.locator('#out').inner_text() == 'x->ok'
            b.page.click('#go')
            assert b.page.locator('#out').inner_text() == 'fui'

    def test_camoufox_platform_consistent_with_host(self):
        # Fingerprint de Firefox "Linux" rodando em Windows é sinal de bot
        # (portal faz cross-check platform × canvas/WebGL). A layer deve
        # escolher a plataforma da máquina hospedeira.
        expected = {'win32': 'Win32', 'darwin': 'MacIntel', 'linux': 'Linux x86_64'}[sys.platform]
        with _with_engine('camoufox') as b:
            assert b.page.evaluate('navigator.platform') == expected

    @pytest.mark.parametrize('engine', ['camoufox', 'patchright'])
    def test_session_persists_between_runs(self, engine, srv):
        _clean_profile('pytest_persist')
        try:
            with _with_engine(engine, profile='pytest_persist') as b:
                b.page.goto(f'{srv}/v1')
                b.page.evaluate("localStorage.setItem('jh', 'persistiu')")
            with _with_engine(engine, profile='pytest_persist') as b:
                b.page.goto(f'{srv}/v1')
                assert b.page.evaluate("localStorage.getItem('jh')") == 'persistiu'
        finally:
            _clean_profile('pytest_persist')

    def test_fallback_skips_failed_engine(self, srv, monkeypatch):
        calls = []

        def broken(self):
            calls.append('camoufox')
            raise RuntimeError('explosão de teste')

        monkeypatch.setattr(bmod.Browser, '_start_camoufox', broken)
        with _with_engine(('camoufox', 'patchright')) as b:
            assert b.engine == 'patchright'
            assert calls == ['camoufox']
            assert b.tried and b.tried[0][0] == 'camoufox'

    def test_all_engines_fail(self, monkeypatch):
        monkeypatch.setattr(bmod.Browser, '_start_camoufox', lambda s: (_ for _ in ()).throw(RuntimeError('e1')))
        monkeypatch.setattr(bmod.Browser, '_start_undetected', lambda s: (_ for _ in ()).throw(RuntimeError('e4')))
        monkeypatch.setattr(bmod.Browser, '_launch_chromium_like', lambda s, f, p: (_ for _ in ()).throw(RuntimeError('e2')))
        b = bmod.Browser(headless=True)
        with pytest.raises(bmod.BrowserUnavailable) as exc:
            b.start()
        assert [n for n, _ in exc.value.tried] == list(bmod.ENGINES)


# ============================================================================
# find_adaptive — escalada css → xpath estável → texto
# ============================================================================

class TestFindAdaptive:
    @pytest.fixture
    def patchright(self):
        b = bmod.Browser(headless=True, engines=('patchright',))
        b.start()
        yield b
        b.close()

    def test_escalation_css_xhtml_text(self, patchright, srv, tmp_path):
        spec = tmp_path / 'spec.json'
        page = patchright.page

        # v1: css direto acerta
        page.goto(f'{srv}/v1')
        hit = bmod.find_adaptive(page, 'button.sc-abc123', 'ir', spec)
        assert hit is not None
        hit.click()
        assert page.locator('#out').inner_text() == 'fui'
        assert json.loads(spec.read_text(encoding='utf-8'))['css'] == 'button.sc-abc123'

        # v2: classe renomeada → css falha, xpath estável (salvo em v1) acerta
        page.goto(f'{srv}/v2')
        hit = bmod.find_adaptive(page, 'button.sc-abc123', 'ir', spec)
        assert hit is not None
        hit.click()
        assert page.locator('#out').inner_text() == 'fui'

        # v3: posição mudou também → só o texto visível salva
        page.goto(f'{srv}/v3')
        hit = bmod.find_adaptive(page, 'button.sc-abc123', 'ir', spec)
        assert hit is not None
        hit.click()
        assert page.locator('#out').inner_text() == 'fui'

    def test_total_miss(self, patchright, srv, tmp_path):
        page = patchright.page
        page.goto(f'{srv}/v1')
        assert bmod.find_adaptive(page, 'button.nao-existe', None, tmp_path / 's.json') is None

    def test_selenium_adapter_css_and_saved_xpath(self, tmp_path):
        class FakeEl:
            text = 'ir'

        class FakeDriver:
            def __init__(self):
                self.url = ''
                self.current_url = ''
            def get(self, u): self.url = u
            def find_element(self, by, sel):
                if by == 'css' and sel == 'button.sc-abc123':
                    raise Exception('element not found')
                if by == 'xpath' and 'button' in sel:
                    return FakeEl()
                raise Exception('element not found')
            @property
            def page_source(self): return ''

        pg = bmod._SeleniumPage(FakeDriver(), 5000)
        # sem spec: css falha → None
        assert bmod.find_adaptive(pg, 'button.sc-abc123', 'ir', tmp_path / 's.json') is None
        # com spec (xpath salvo): acerta o xpath
        (tmp_path / 's.json').write_text(json.dumps({'css': 'button.sc-abc123',
                                                      'xpath': '//body/button', 'text': 'ir'}))
        assert bmod.find_adaptive(pg, 'button.sc-abc123', 'ir', tmp_path / 's.json') is not None


# ============================================================================
# human() — delay compartilhado
# ============================================================================

class TestHuman:
    def test_jitter_bounds(self, monkeypatch):
        seen = []
        monkeypatch.setattr(bmod.time, 'sleep', lambda s: seen.append(s))
        cfg = {'automacao': {'delay_entre_acoes': 1.0, 'delay_entre_vagas': 8.0}}
        bmod.human(cfg)
        bmod.human(cfg, kind='vaga')
        assert 0.7 <= seen[0] <= 1.3
        assert 5.6 <= seen[1] <= 10.4

    def test_default_base(self, monkeypatch):
        seen = []
        monkeypatch.setattr(bmod.time, 'sleep', lambda s: seen.append(s))
        bmod.human(None)
        assert 1.05 <= seen[0] <= 1.95
