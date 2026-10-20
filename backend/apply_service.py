"""Leitor dos dados do Job Hunter (projeto `apply`) — integração de Nível 1.

Trivor apenas EXIBE o histórico de candidaturas; os bots do apply continuam
gravando os arquivos. Nada aqui escreve no diretório do apply.

Localização (sem APPLY_DIR, primeiro que existir ganha):
  1. variável de ambiente APPLY_DIR (ex.: /caminho/para/apply) — se definida, é autoritativa
  2. <repo>/apply          (quando o apply for movido para dentro do repo)
  3. <repo>/../apply       (caso atual: apply e curriculo são irmãos)

Contrato dos dados lidos (gravados pelos bots do apply):
  relatorio/candidaturas.json → {"candidaturas": [...], "ja_candidatado": [...]}
  cada registro: {vaga, link, local, site, status, data (dd/mm/aaaa), horario (HH:MM:SS), curriculo}
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Buckets de status para a UI — o apply usa dezenas de strings de status,
# algumas até com texto de erro embutido ("erro: Page.goto: ...").
# Agrupamos 4 caixas estáveis; o status bruto segue no campo `status`.
_BUCKET_SUCESSO = {'enviado'}
_BUCKET_PARCIAL = {'preenchido_sem_confirmacao'}
_BUCKET_SKIP = {'ja_candidatado'}


class ApplyDataError(Exception):
    """Arquivo do apply ausente/inlegível — o endpoint vira 502 com mensagem genérica."""


def resolve_apply_dir() -> Path | None:
    """Retorna o diretório do apply se existir, senão None (a UI mostra orientação).

    Com APPLY_DIR definida, ela é autoritativa (sem fallback): configuração
    explícita errada não deve silenciosamente apontar para outro lugar."""
    env = os.getenv('APPLY_DIR', '').strip()
    if env:
        cand = Path(env)
        try:
            return cand if (cand / 'relatorio' / 'candidaturas.json').is_file() else None
        except OSError:
            return None

    for cand in (BASE_DIR / 'apply', BASE_DIR.parent / 'apply'):
        try:
            if cand.is_dir() and (cand / 'relatorio' / 'candidaturas.json').is_file():
                return cand
        except OSError:
            continue
    return None


def _status_bucket(status: str) -> str:
    s = (status or '').strip()
    if s in _BUCKET_SUCESSO:
        return 'sucesso'
    if s in _BUCKET_PARCIAL:
        return 'parcial'
    if s in _BUCKET_SKIP:
        return 'skip'
    return 'falha'


def _sort_key(reg: dict) -> tuple:
    """Ordena por data desc; formato dd/mm/aaaa — parse fraco (valor bruto como fallback)."""
    d = str(reg.get('data', '')).strip()
    parts = d.split('/')
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        day, month, year = (int(parts[0]), int(parts[1]), int(parts[2]))
    else:
        day = month = year = 0
    return (year, month, day, str(reg.get('horario', '')))


def _load_records(apply_dir: Path) -> list[dict]:
    """Lê relatorio/candidaturas.json e devolve os registros com bucket calculado."""
    raw = apply_dir / 'relatorio' / 'candidaturas.json'
    try:
        payload = json.loads(raw.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ApplyDataError(f"arquivo não encontrado: {raw}")
    except (json.JSONDecodeError, OSError) as exc:
        raise ApplyDataError(f"leitura falhou: {exc}") from exc

    records = payload.get('candidaturas') if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ApplyDataError("estrutura inesperada em candidaturas.json (campo 'candidaturas' ausente)")

    for reg in records:
        if not isinstance(reg, dict):
            continue
        reg['status_bucket'] = _status_bucket(str(reg.get('status', '')))
    return records


def apply_overview() -> dict:
    """Resumo p/ o cabeçalho da página. `available=False` se o apply não foi encontrado."""
    apply_dir = resolve_apply_dir()
    if apply_dir is None:
        return {"available": False, "path": None, "hint": "Defina APPLY_DIR no .env ou mova apply para ../apply (relatorio/candidaturas.json)"}

    records = _load_records(apply_dir)
    por_bucket: dict[str, int] = {"sucesso": 0, "parcial": 0, "skip": 0, "falha": 0}
    por_site: dict[str, int] = {}
    datas = [str(r.get('data', '')) for r in records if str(r.get('data', '')).strip()]
    for reg in records:
        por_bucket[reg.get('status_bucket', 'falha')] += 1
        site = str(reg.get('site', '')).strip() or 'desconhecido'
        por_site[site] = por_site.get(site, 0) + 1

    return {
        "available": True,
        "path": str(apply_dir),
        "total": len(records),
        "por_bucket": por_bucket,
        "por_site": dict(sorted(por_site.items(), key=lambda kv: -kv[1])),
        "periodo": {"primeiro": min(datas), "ultimo": max(datas)} if datas else {"primeiro": None, "ultimo": None},
    }


def apply_applications(site: str = '', bucket: str = '', q: str = '',
                       limit: int = 50, offset: int = 0) -> dict:
    """Lista de candidaturas (mais recentes primeiro) com filtros opcionais.

    bucket: 'sucesso' | 'parcial' | 'skip' | 'falha' (vazio = todos)
    q: busca livre em `vaga` (case-insensitive)
    """
    apply_dir = resolve_apply_dir()
    if apply_dir is None:
        raise ApplyDataError("diretório do apply não encontrado")

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    records = _load_records(apply_dir)
    if site:
        records = [r for r in records if str(r.get('site', '')).strip() == site]
    if bucket:
        records = [r for r in records if r.get('status_bucket') == bucket]
    if q:
        needle = q.lower()
        records = [r for r in records if needle in str(r.get('vaga', '')).lower()]

    records.sort(key=_sort_key, reverse=True)
    page = records[offset:offset + limit]
    return {"items": page, "total": len(records), "limit": limit, "offset": offset}
