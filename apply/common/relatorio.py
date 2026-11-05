"""Relatório compartilhado dos bots (relatorio/candidaturas.json).

Contrato de dados (consumido por backend/apply_service.py):
    {"candidaturas": [...], "ja_candidatado": [...]}
Entrada: {vaga, link, local, site, status, data (dd/mm/aaaa), horario, curriculo}

Cada bot instancia um Relatorio com o próprio caminho/site/fuso e expõe
wrappers locais dos 4 métodos — a lógica vive aqui (1 vez), os nomes no
escopo do bot seguem iguais para os chamadores.

Robustez (dedup global depende disso):
- escrita ATÔMICA (.tmp + os.replace): crash no meio da gravação não deixa
  o JSON truncado;
- cópia .bak do último bom: arquivo corrompido (sync travado na OneDrive)
  cai no backup em vez de "histórico vazio" — histórico vazio faz os bots
  RE-CANDIDATAR vagas já enviadas;
- toda falha de leitura IMPRIME aviso no log do bot (stderr) — nunca em
  silêncio.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Mesmo arquivo para todos os bots: relatorio/ no cwd do bot (apply/)
RELATORIO_PADRAO = Path("relatorio") / "candidaturas.json"
_TZ_PADRAO = ZoneInfo("America/Sao_Paulo")

def _vazio() -> dict:
    return {"candidaturas": [], "ja_candidatado": []}


def _aviso(msg: str) -> None:
    """Avisos de integridade vão para o log do bot (stderr → arquivo do runner)."""
    print(f"[relatorio] {msg}", file=sys.stderr)


@dataclass(frozen=True)
class Relatorio:
    arquivo: Path = RELATORIO_PADRAO
    site: str = ""
    tz: ZoneInfo = _TZ_PADRAO

    @property
    def _bak(self) -> Path:
        return self.arquivo.parent / (self.arquivo.name + ".bak")

    @property
    def _tmp(self) -> Path:
        return self.arquivo.parent / (self.arquivo.name + ".tmp")

    def carregar(self) -> dict:
        if not self.arquivo.exists():
            return _vazio()
        data = self._ler(self.arquivo)
        if data is None:
            # Falha no arquivo atual → última boa cópia (proteção contra
            # sync truncado/corrompido). Histórico vazio significa
            # re-candidatar vagas já enviadas — o backup é o freio.
            _aviso(f"falha ao ler {self.arquivo} — tentando backup .bak")
            data = self._ler(self._bak)
            if data is None:
                _aviso("SEM backup utilizável — recomeçando com histórico vazio (risco de re-candidatar)")
                return _vazio()
        if isinstance(data, list):
            # formato legado do gupy (lista plana) — ressintetiza a blacklist
            return {
                "candidaturas": [c for c in data if isinstance(c, dict)],
                "ja_candidatado": [
                    c.get("link", "") for c in data
                    if isinstance(c, dict) and c.get("status") == "enviado"
                ],
            }
        data.setdefault("candidaturas", [])
        data.setdefault("ja_candidatado", [])
        return data

    def _ler(self, caminho: Path) -> dict | list | None:
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError):
            return None

    def salvar(self, rel: dict) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps(rel, ensure_ascii=False, indent=2)
        # Escrita atômica: .tmp + os.replace (atômico no NTFS). A escrita
        # direta antiga deixava o JSON cortado se o processo caísse no meio.
        try:
            self._tmp.write_text(texto, encoding="utf-8")
            os.replace(self._tmp, self.arquivo)
        except OSError as exc:
            # O alvo pode estar travado pela OneDrive — o arquivo anterior
            # continua íntegro; o erro sobe para o chamador decidir.
            _aviso(f"falha ao salvar {self.arquivo}: {exc}")
            raise
        with contextlib.suppress(OSError):
            # backup é insurance; o arquivo principal já foi gravado
            self._bak.write_text(texto, encoding="utf-8")

    def registrar(self, entry: dict) -> None:
        rel = self.carregar()
        rel["candidaturas"].append(entry)
        if entry.get("status") == "enviado":
            link = entry.get("link", "")
            if link and link not in rel["ja_candidatado"]:
                rel["ja_candidatado"].append(link)
        self.salvar(rel)

    def hoje(self, rel: dict) -> int:
        """Candidaturas enviadas HOJE para este site (dedup por data dd/mm/aaaa)."""
        hoje = datetime.now(self.tz).strftime("%d/%m/%Y")
        return sum(
            1 for c in rel["candidaturas"]
            if isinstance(c, dict) and c.get("site") == self.site
            and c.get("status") == "enviado"
            and c.get("data") == hoje
        )


# ---------------------------------------------------------------------------
# Leitura crua (bots com writer próprio — nerdin, infojobs, gupy)
#
# Compatível com os dois formatos no disco: lista plana (escrita por gupy)
# e dict {"candidaturas", "ja_candidatado"} (escrito por Relatorio/salvar_log).
# ---------------------------------------------------------------------------

def _ler_caminho(caminho: str):
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def ler_json_candidaturas(arquivo: str = "relatorio/candidaturas.json") -> tuple[list, list]:
    """Retorna (candidaturas, ja_candidatado); vazio se arquivo inexistente.

    Arquivo corrompido → AVISO no log + fallback para o .bak do Relatorio
    (escrita atômica mantém o .bak íntegro) — histórico vazio silencioso é
    o que faz os bots RE-CANDIDATAR vagas já enviadas."""
    dados = _ler_caminho(arquivo)
    if dados is None and os.path.exists(arquivo):
        _aviso(f"falha ao ler {arquivo} — tentando backup .bak")
        dados = _ler_caminho(arquivo + ".bak")
        if dados is None:
            _aviso("sem backup utilizável — dedup vazio (risco de re-candidatar)")
    if isinstance(dados, dict):
        c  = dados.get("candidaturas", [])
        jc = dados.get("ja_candidatado", [])
        return (c if isinstance(c, list) else [], jc if isinstance(jc, list) else [])
    if isinstance(dados, list):
        c  = [x for x in dados if isinstance(x, dict)]
        jc = [x["link"] for x in c if x.get("status") == "enviado" and "link" in x]
        return c, jc
    return [], []


def links_ja_candidatados(arquivo: str = "relatorio/candidaturas.json") -> set:
    """Blacklist de links já enviados (unindo ja_candidatado + status enviado)."""
    candidaturas, ja_candidatado = ler_json_candidaturas(arquivo)
    links = set(ja_candidatado)
    for c in candidaturas:
        if isinstance(c, dict) and c.get("status") == "enviado" and "link" in c:
            links.add(c["link"])
    return links
