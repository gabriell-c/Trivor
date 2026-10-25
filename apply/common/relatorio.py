"""Relatório compartilhado dos bots (relatorio/candidaturas.json).

Contrato de dados (consumido por backend/apply_service.py):
    {"candidaturas": [...], "ja_candidatado": [...]}
Entrada: {vaga, link, local, site, status, data (dd/mm/aaaa), horario, curriculo}

Cada bot instancia um Relatorio com o próprio caminho/site/fuso e expõe
wrappers locais dos 4 métodos — a lógica vive aqui (1 vez), os nomes no
escopo do bot seguem iguais para os chamadores.
"""
from __future__ import annotations

import json
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Mesmo arquivo para todos os bots: relatorio/ no cwd do bot (apply/)
RELATORIO_PADRAO = Path("relatorio") / "candidaturas.json"
_TZ_PADRAO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class Relatorio:
    arquivo: Path = RELATORIO_PADRAO
    site: str = ""
    tz: ZoneInfo = _TZ_PADRAO

    def carregar(self) -> dict:
        with suppress(Exception):
            if self.arquivo.exists():
                data = json.loads(self.arquivo.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return {
                        "candidaturas": data,
                        "ja_candidatado": [
                            c.get("link", "") for c in data if c.get("status") == "enviado"
                        ],
                    }
                return data
        return {"candidaturas": [], "ja_candidatado": []}

    def salvar(self, rel: dict) -> None:
        self.arquivo.write_text(
            json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
            if c.get("site") == self.site
            and c.get("status") == "enviado"
            and c.get("data") == hoje
        )


# ---------------------------------------------------------------------------
# Leitura crua (bots com writer próprio — nerdin, infojobs, gupy)
#
# Compatível com os dois formatos no disco: lista plana (escrita por gupy)
# e dict {"candidaturas", "ja_candidatado"} (escrito por Relatorio/salvar_log).
# ---------------------------------------------------------------------------

def ler_json_candidaturas(arquivo: str = "relatorio/candidaturas.json") -> tuple[list, list]:
    """Retorna (candidaturas, ja_candidatado); vazio se arquivo inexistente/inválido."""
    if not os.path.exists(arquivo):
        return [], []
    with open(arquivo, encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError:
            return [], []
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
