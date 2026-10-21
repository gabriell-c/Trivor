"""Camada de navegador compartilhada dos bots do Job Hunter.

Substitui o acoplamento de driver de cada bot (playwright/seleniumbase/
undetected_chromedriver) por uma cadeia de engines com fallback:

  camoufox    → Firefox anti-fingerprint (API = playwright.sync)
  patchright  → Chromium stealth, motor do Scrapling (API = playwright.sync)
  playwright  → Chromium/Chrome clássico (o estado atual dos bots)
  undetected  → undetected_chromedriver, último recurso (Selenium, subconjunto)

Do Scrapling entram aqui: o engine patchright (stealth chromium), o
hardening anti-automation (flags) e o parser Selector — `find_adaptive()`
usa o `path` (xpath estável) dele para relocalizar elementos quando o
portal renomeia classes/id's.

Contrato p/ os bots:
    with Browser(profile='gupy', headless=False) as b:
        b.page.goto('https://portal.gupy.io')
        print(b.engine)   # qual engine realmente subiu
Nas 3 primeiras engines, `b.page` É um playwright.sync_api.Page — o código
de preenchimento existente migra sem reescrever. Na engine `undetected`,
`b.page` é um _SeleniumPage (subconjunto documentado, fluxos de login).

Stealth: camoufox/patchright passam na suíte Intoli (bot.sannysoft.com).
Custo conhecido das engines chromium em `headless=True`: o UA expõe
"Headless" e o WebGL cai pro SwiftShader — para portais com detecção
agressiva, preferir camoufox (Firefox com fingerprint coerente com a
plataforma hospedeira) ou rodar com `headless=False`.

Sessões: com `profile="gupy"`, cada engine usa um user_data_dir persistente
em apply/sessions/<profile>/<engine>/ — cookies/localStorage sobrevivem entre
runs, substituindo gupy_session.json / solides_session.json / indeed_session.pkl.
"""
import json
import random
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / 'sessions'

ENGINES = ('camoufox', 'patchright', 'playwright', 'undetected')


class BrowserUnavailable(RuntimeError):
    """Nenhuma engine da cadeia conseguiu subir; `tried` lista o motivo por engine."""

    def __init__(self, tried: list[tuple[str, str]]):
        self.tried = tried
        super().__init__('nenhuma engine disponível — ' + '; '.join(f'{n}: {r}' for n, r in tried))


class Browser:
    """Navegador com cadeia de fallback (engine que sobir primeiro vence)."""

    def __init__(self, profile: str | None = None, headless: bool = False,
                 engines: tuple[str, ...] = ENGINES, channel: str | None = None,
                 timeout_ms: int = 60000):
        self.profile = profile
        self.headless = headless
        self.engines = tuple(e for e in ENGINES if e in tuple(engines))
        self.channel = channel
        self.timeout_ms = timeout_ms
        self.page = None
        self.engine: str | None = None
        self.tried: list[tuple[str, str]] = []
        self._closer = None

    def _profile_dir(self, family: str) -> str:
        if not self.profile:
            return tempfile.mkdtemp(prefix='jh-browse-')
        d = SESSIONS_DIR / self.profile / family
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    @staticmethod
    def _stealth_args() -> list[str]:
        return ['--disable-blink-features=AutomationControlled']

    def _launch_chromium_like(self, sync_playwright, family: str) -> None:
        """patchright e playwright têm a mesma API — diferença é o stealth."""
        pw = sync_playwright().start()
        kwargs = dict(user_data_dir=self._profile_dir(family),
                      headless=self.headless, args=self._stealth_args())
        if self.channel:
            kwargs['channel'] = self.channel
        ctx = pw.chromium.launch_persistent_context(**kwargs)
        self._pw = pw
        self._ctx = ctx
        self.page = ctx.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self._closer = self._close_pw

    def _close_pw(self) -> None:
        self._ctx.close()
        self._pw.stop()

    def _start_camoufox(self) -> None:
        import sys
        from camoufox.sync_api import Camoufox
        # `os` coerente com a máquina hospedeira: fingerprint de Firefox Linux
        # rodando em Windows é sinal de bot (cross-check de platform).
        host_os = {'win32': 'windows', 'darwin': 'macos', 'linux': 'linux'}.get(sys.platform)
        cf = Camoufox(headless=self.headless, user_data_dir=self._profile_dir('firefox'),
                      persistent_context=True, os=host_os)
        ctx = cf.__enter__()  # BrowserContext; __exit__ faz o teardown completo
        self.page = ctx.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        # cf.__exit__ (e não ctx.close()) fecha o browser E o event loop do
        # sync API do playwright — sem isso, qualquer engine sync posterior
        # no mesmo thread/processo falha com "Sync API inside the asyncio
        # loop" (camoufox issue #82).
        self._closer = lambda: cf.__exit__(None, None, None)

    def _start_undetected(self) -> None:
        from undetected_chromedriver import Chrome
        opts = Chrome.Options()
        opts.add_argument(f'--user-data-dir={self._profile_dir("uc")}')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        if self.headless:
            opts.add_argument('--headless=new')
        driver = Chrome(options=opts)
        driver.implicitly_wait(2)
        self._driver = driver
        self.page = _SeleniumPage(driver, self.timeout_ms)
        self._closer = driver.quit

    def start(self) -> 'Browser':
        """Sobe a primeira engine que conseguir; registra falhas em `tried`."""
        for name in self.engines:
            try:
                if name == 'camoufox':
                    self._start_camoufox()
                elif name == 'patchright':
                    from patchright.sync_api import sync_playwright
                    self._launch_chromium_like(sync_playwright, 'chromium')
                elif name == 'playwright':
                    from playwright.sync_api import sync_playwright
                    self._launch_chromium_like(sync_playwright, 'chromium')
                else:  # undetected
                    self._start_undetected()
                self.engine = name
                return self
            except Exception as exc:
                self.tried.append((name, f'{type(exc).__name__}: {exc}'))
        raise BrowserUnavailable(self.tried)

    def close(self) -> None:
        if self._closer:
            try:
                self._closer()
            finally:
                self._closer = None
                self.page = None

    def __enter__(self) -> 'Browser':
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


class _SeleniumPage:
    """Adaptador fino do WebDriver — só a superfície que os fluxos de login usam.

    Não é um Page completo; se um fluxo precisar de mais (iframes, uploads,
    esperas complexas), a engine `undetected` não é a certa p/ ele."""

    def __init__(self, driver, timeout_ms: int):
        self._d = driver
        self._timeout_ms = timeout_ms
        self.url = driver.current_url

    def _find(self, selector: str):
        from selenium.webdriver.common.by import By
        return self._d.find_element(By.CSS_SELECTOR, selector)

    def goto(self, url: str, **_kw) -> None:
        self._d.get(url)
        self.url = self._d.current_url

    def click(self, selector: str, **_kw) -> None:
        self._find(selector).click()

    def fill(self, selector: str, value: str, **_kw) -> None:
        el = self._find(selector)
        el.clear()
        el.send_keys(value)

    def query_selector(self, selector: str):
        return self._find(selector)

    def text_content(self, selector: str) -> str:
        return self._find(selector).text

    def content(self) -> str:
        return self._d.page_source

    def wait_for_selector(self, selector: str, **_kw):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        return WebDriverWait(self._d, self._timeout_ms / 1000).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

    def close(self) -> None:
        self._d.quit()


def human(config: dict | None, kind: str = 'acao') -> None:
    """Atraso "humano" compartilhado — substitui o `esperar` duplicado em
    infojobs.py:129 / nerdin.py:254. kind: 'acao' (entre ações) ou 'vaga'
    (entre vagas); jitter de ±30% para não virar assinatura de máquina."""
    auto = (config or {}).get('automacao', {})
    base = float(auto.get('delay_entre_acoes' if kind == 'acao' else 'delay_entre_vagas', 1.5))
    time.sleep(max(0.0, base * random.uniform(0.7, 1.3)))


def _save_spec(spec_path: Path, css: str, xpath: str | None, text: str | None) -> None:
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps({'css': css, 'xpath': xpath, 'text': text}),
                         encoding='utf-8')


def _load_spec(spec_path: Path) -> dict | None:
    p = Path(spec_path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def find_adaptive(page, css: str, fallback_text: str | None = None,
                  spec_path: Path | None = None):
    """Procura um elemento tolerante à renomeação de classes/id's do portal.

    Escalada:
      1. `css` direto;
      2. xpath estável (via Selector do Scrapling) salvo em `spec_path`;
      3. `fallback_text` — texto visível, que o portal quase nunca renomeia.

    Ao achar, a spec em `spec_path` é atualizada (css + xpath + texto).
    Devolve um handle clicável (playwright Locator / WebElement / None).
    """
    has_playwright = hasattr(page, 'locator')
    spec = _load_spec(spec_path) if spec_path else None

    # 1) css direto
    try:
        if has_playwright:
            loc = page.locator(css)
            if loc.count() > 0:
                hit = loc.first
                if spec_path:
                    _save_spec(Path(spec_path), css, _scrapling_from_page(page, css), fallback_text)
                return hit
        else:  # adaptador selenium: CSS direto
            el = page.query_selector(css)
            if el is not None:
                return el
    except Exception:
        pass

    # 2) xpath estável salvo no run anterior (classe renomeada não muda a posição na árvore)
    if spec and spec.get('xpath'):
        if has_playwright:
            loc2 = page.locator(f"xpath={spec['xpath']}")
            try:
                if loc2.count() > 0:
                    hit = loc2.first
                    if spec_path:
                        _save_spec(Path(spec_path), css, spec['xpath'], fallback_text)
                    return hit
            except Exception:
                pass
        else:  # adaptador selenium
            try:
                from selenium.webdriver.common.by import By
                return page._d.find_element(By.XPATH, spec['xpath'])
            except Exception:
                pass

    # 3) texto visível (só engine playwright; o adaptador selenium não tem get_by_text)
    if has_playwright:
        txt = (spec.get('text') if spec else None) or fallback_text
        if txt:
            try:
                loc3 = page.get_by_text(txt)
                if loc3.count() > 0:
                    return loc3.first
            except Exception:
                pass
    return None


def _scrapling_from_page(page, css: str) -> str | None:
    """Xpath estável do elemento (propriedade do element Selector do Scrapling).

    `generate_full_xpath_selector` não usa posição nem classe — sobrevive a
    renomeações de class/id do portal enquanto a estrutura do body ficar igual."""
    try:
        from scrapling import Selector
        hits = Selector(page.content()).css(css)
        el = hits[0] if hits else None
        return getattr(el, 'generate_full_xpath_selector', None)
    except Exception:
        return None
