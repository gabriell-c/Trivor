"""Teste E2E real do leitor (Chrome + CDP + crawl4ai) — OPT-IN.

Roda só com `TRIVOR_CDP_SMOKE=1` (no Windows: `set TRIVOR_CDP_SMOKE=1`):
sobe um Chrome headless com --remote-debugging-port, anexa o crawl4ai na
porta e lê uma página real — a cadeia exata que os bots usam em produção.
Sem a variável, o teste é skip: CI normal não paga Chrome nem rede.

Quem sobe, desce: o Chrome é encerrado (PID exato) no finally, sempre.
"""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PORT = 9334  # porta própria do teste — não colide com o 9333 dos bots
CHROME_CANDIDATOS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIVOR_CDP_SMOKE") != "1",
    reason="opt-in: defina TRIVOR_CDP_SMOKE=1 (sobe Chrome real, ~20s)",
)


def _carregar_leitor():
    p = ROOT / 'apply' / 'common' / 'leitor.py'
    spec = importlib.util.spec_from_file_location('apply_leitor_cdp_teste', p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _achar_chrome() -> str:
    for caminho in CHROME_CANDIDATOS:
        if Path(caminho).is_file():
            return caminho
    raise AssertionError("Chrome não encontrado nos caminhos padrão")


def _esperar_cdp(segundos: float = 20.0) -> None:
    prazo = time.time() + segundos
    while time.time() < prazo:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise AssertionError(f"CDP não respondeu em {segundos}s na porta {PORT}")


def test_cdp_real_chrome_crawl4ai() -> None:
    """Cadeia de produção: Chrome na porta CDP → crawl4ai anexa → leitura ok."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    chrome = _achar_chrome()
    perfil = tempfile.mkdtemp(prefix="trivor-cdp-")  # %TEMP% ASCII — OneDrive não
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--user-data-dir={perfil}",
         f"--remote-debugging-port={PORT}", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _esperar_cdp()
        leitor = _carregar_leitor()
        leitura = leitor.leitura_estruturada(
            "https://example.com", f"http://127.0.0.1:{PORT}", timeout_s=60
        )
        assert leitura.ok is True, f"leitura falhou: {leitura.erro}"
        assert "This domain is for use" in leitura.texto, "a página lida é a real"
        assert "https://iana.org/help/example-domains" in leitura.links
        resumo = leitor.resumo_para_llm(leitura, fallback="")
        assert resumo and "This domain is for use" in resumo
        # Página com títulos de verdade → o mapa de seções tem que vir
        cdp = f"http://127.0.0.1:{PORT}"
        leitura2 = leitor.leitura_estruturada("https://docs.python.org/3/", cdp,
                                              timeout_s=60)
        assert leitura2.ok is True, f"segunda leitura falhou: {leitura2.erro}"
        assert any(s.startswith("#") for s in leitura2.secoes), \
            f"mapa de seções veio da página: {leitura2.secoes}"
        # Regra de ouro no mundo real: falha do anexo nunca quebra o chamador
        leitura_morta = leitor.leitura_estruturada(
            "https://example.com", "http://127.0.0.1:1", timeout_s=10
        )
        assert leitura_morta.ok is False
        assert leitor.resumo_para_llm(leitura_morta, fallback="fb") == "fb"
    finally:
        # quem sobe, desce: encerra SÓ o PID deste Chrome (e os filhos)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(perfil, ignore_errors=True)
