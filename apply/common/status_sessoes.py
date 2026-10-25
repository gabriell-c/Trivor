"""Estado de sessão dos 5 bots — stdlib puro (sem browser, sem LLM).

Alimenta a UI do Trivor (GET /api/apply/sesoes): diz por provedor se há
sessão local ou credenciais válidas. NUNCA devolve valor de sessão,
cookie ou senha — apenas existência, timestamp e um detalhe legível.

Módulo de propósito independente (`from . import` não é usado): o backend
carrega pelo caminho do arquivo para não puxar a camada de browser.

Onde cada bot guarda "logado":
- gupy:    perfil persistente em apply/sessions/gupy/<engine>/
- indeed:  indeed_session.pkl + google_session.pkl
- solides: solides_session.json (storage_state do Playwright)
- infojobs/nerdin: sem persistência — credenciais no .env (só checa-se
                   a EXISTÊNCIA da chave, nunca o valor)
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

BOTS = ("gupy", "indeed", "infojobs", "nerdin", "solides")

NOMES = {
    "gupy": "GUPY", "indeed": "Indeed", "infojobs": "InfoJobs",
    "nerdin": "Nerdin", "solides": "Sólides",
}

# Bots com sessão LOCAL que o deslogar pode apagar (o .env nunca é tocado):
# gupy → perfis de browser; indeed → pickles; solides → storage_state.
COM_SESSAO_LOCAL = {"gupy", "indeed", "solides"}

# Bots sem persistência de sessão: "logado" = credenciais presentes no .env
_ENV_CREDENCIAIS = {
    "infojobs": ("INFOJOBS_EMAIL", "INFOJOBS_SENHA"),
    "nerdin": ("NERDIN_EMAIL", "NERDIN_SENHA"),
}


def _chave_no_env(apply_dir: Path, chave: str) -> bool:
    """`.env` define `chave`? (só existência — valor nunca sai daqui)"""
    try:
        conteudo = (apply_dir / ".env").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(re.search(rf"^{re.escape(chave)}=", conteudo, re.M))


def _mtime_iso(caminho: Path) -> str | None:
    try:
        return datetime.fromtimestamp(caminho.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _estado_gupy(apply_dir: Path) -> tuple[bool, str, str | None]:
    base = apply_dir / "sessions" / "gupy"
    perfis = [d for d in base.iterdir() if d.is_dir() and any(d.iterdir())] if base.is_dir() else []
    if not perfis:
        return False, "sem sessão local — rode o login uma vez", None
    ultimo = max(perfis, key=lambda d: d.stat().st_mtime)
    return True, f"perfil persistente ({ultimo.name})", _mtime_iso(ultimo)


def _estado_arquivo(apply_dir: Path, nome: str, detalhe: str) -> tuple[bool, str, str | None]:
    arq = apply_dir / nome
    if not arq.exists():
        return False, f"sem sessão local ({nome} ausente)", None
    return True, detalhe, _mtime_iso(arq)


def estados(apply_dir: Path) -> list[dict]:
    """Cartão de status dos 5 bots. `ultima_atualizacao` = quando a sessão
    local mudou (None para credenciais, que não têm timestamp)."""
    apply_dir = Path(apply_dir)
    out: list[dict] = []
    for bot in BOTS:
        if bot == "gupy":
            tem, detalhe, ts = _estado_gupy(apply_dir)
        elif bot == "indeed":
            tem, detalhe, ts = _estado_arquivo(apply_dir, "indeed_session.pkl",
                                                "pickles de sessão (Google + Indeed)")
            if tem and not (apply_dir / "google_session.pkl").exists():
                tem, detalhe, ts = False, "sessão parcial (só Indeed, sem Google)", None
        elif bot == "solides":
            tem, detalhe, ts = _estado_arquivo(apply_dir, "solides_session.json",
                                                "sessão Sólides (storage_state)")
        else:  # infojobs / nerdin
            chaves = _ENV_CREDENCIAIS[bot]
            tem = all(_chave_no_env(apply_dir, c) for c in chaves)
            detalhe = (f"credenciais no .env ({' / '.join(chaves)})" if tem
                       else f"credenciais ausentes: {', '.join(chaves)}")
            ts = None
        out.append({
            "bot": bot,
            "nome": NOMES[bot],
            "tem_sessao": tem,
            "deslogavel": bot in COM_SESSAO_LOCAL,
            "detalhe": detalhe,
            "ultima_atualizacao": ts,
        })
    return out


def deslogar(apply_dir: Path, bot: str) -> list[str]:
    """Apaga a sessão LOCAL do bot (o botão "Deslogar" da UI).

    Só toca em arquivos de sessão do próprio bot — nunca .env,
    credenciais ou qualquer outra coisa:
      - gupy    → apaga os perfis de apply/sessions/gupy/<engine>/
      - indeed  → apaga indeed_session.pkl + google_session.pkl
      - solides → apaga solides_session.json

    Nerdin/InfoJobs não têm sessão local (credenciais no .env) → ValueError.
    Bot desconhecido → ValueError. Idempotente: sem sessão → lista vazia."""
    apply_dir = Path(apply_dir)
    if bot not in BOTS:
        raise ValueError(f"Bot desconhecido '{bot}'.")
    if bot not in COM_SESSAO_LOCAL:
        raise ValueError(
            f"{NOMES[bot]} não tem sessão local (credenciais no .env) — nada para deslogar.")

    removidos: list[str] = []
    if bot == "gupy":
        base = apply_dir / "sessions" / "gupy"
        perfis = sorted(base.iterdir()) if base.is_dir() else []
        for perfil in perfis:
            if perfil.is_dir():
                shutil.rmtree(perfil)
                removidos.append(f"sessions/gupy/{perfil.name}/")
    elif bot == "indeed":
        for nome in ("indeed_session.pkl", "google_session.pkl"):
            arq = apply_dir / nome
            if arq.exists():
                arq.unlink()
                removidos.append(nome)
    else:  # solides
        arq = apply_dir / "solides_session.json"
        if arq.exists():
            arq.unlink()
            removidos.append(arq.name)
    return removidos
