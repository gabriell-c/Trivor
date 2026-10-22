"""Rotas de integração apply (Job Hunter): histórico de candidaturas,
execução/stop dos bots, admin (config, IA, currículos). Movidas do main.py
— corpos inalterados.
"""

import apply_admin
from app_log import get_app_logger
from apply_runner import ApplyRunError, bot_log, list_bots, start_bot, stop_bot
from apply_service import ApplyDataError, apply_applications, apply_overview, resolve_apply_dir
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

logger = get_app_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Integração apply (Job Hunter) — Nível 1: Trivor apenas EXIBE o histórico
# dos bots de candidatura; o projeto apply continua gravando seus arquivos.
# ---------------------------------------------------------------------------

@router.get('/api/apply/overview')
def api_apply_overview():
    """Resumo do histórico de candidaturas. Handler síncrono de propósito:
    leitura local rápida — FastAPI o roda na thread pool, fora do event loop."""
    return apply_overview()

@router.get('/api/apply/applications')
def api_apply_applications(
    site: str = '',
    bucket: str = '',
    q: str = '',
    limit: int = 50,
    offset: int = 0,
):
    if bucket and bucket not in ('sucesso', 'parcial', 'skip', 'falha'):
        raise HTTPException(status_code=400, detail=f"Bucket inválido '{bucket}'. Use: sucesso, parcial, skip, falha.")
    try:
        return apply_applications(site=site, bucket=bucket, q=q, limit=limit, offset=offset)
    except ApplyDataError as exc:
        if resolve_apply_dir() is None:
            raise HTTPException(status_code=404, detail="Projeto apply não encontrado. Defina APPLY_DIR no .env ou mova apply para ../apply.")
        logger.warning(f"[APPLY] {exc}")
        raise HTTPException(status_code=502, detail="Arquivo de candidaturas ilegível.")

@router.post('/api/apply/run')
async def api_apply_run(request: Request):
    """Dispara um bot do Job Hunter em background (Nível 3 — execução pela UI).

    Body: {"bot": "gupy" | "infojobs" | "nerdin" | "indeed" | "solides"}."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    bot = data.get('bot')
    if not isinstance(bot, str):
        raise HTTPException(status_code=400, detail="Body deve ser {\"bot\": \"gupy\"} — um dos bots do apply.")
    try:
        info = start_bot(bot)
    except ApplyRunError as exc:
        # "já está em execução" → 409; demais (desconhecido, apply ausente) → 400
        status = 409 if 'já está em execução' in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    logger.info(f"[APPLY] bot {bot} iniciado (pid {info['pid']})")
    return info

@router.get('/api/apply/runs')
def api_apply_runs():
    """Estado dos bots (rodando/pid/início + últimas linhas do log) — a UI faz poll."""
    return list_bots()


@router.get('/api/apply/log/{bot}')
def api_apply_log(bot: str, lines: int = 200):
    """Log completo (últimas N linhas) de um bot — a aba Executar do Trivor
    mostra o passo a passo em tempo real."""
    try:
        return bot_log(bot, min(max(lines, 5), 1000))
    except ApplyRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post('/api/apply/stop')
async def api_apply_stop(request: Request):
    """Para um bot em execução (body: {"bot": "gupy"}). Parada limpa com
    fallback de força — nunca é taskkill global, sempre o PID específico."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    bot = data.get('bot')
    if not isinstance(bot, str):
        raise HTTPException(status_code=400, detail="Body deve ser {\"bot\": \"gupy\"}.")
    try:
        return stop_bot(bot)
    except ApplyRunError as exc:
        detail = str(exc)
        code = 404 if 'não encontrado' in detail else (409 if 'execução' in detail else 400)
        raise HTTPException(status_code=code, detail=detail)


# ── Admin do apply (Nível 3: config, IA, currículos) ────────────────────────

def _admin_handler(fn, *args, **kwargs):
    """Executa a fn de admin convertendo os erros dela em HTTP.

    ApplyNotFound → 404 (sem apply), ApplyAdminError → 400 (mensagem legível)."""
    try:
        return fn(*args, **kwargs)
    except apply_admin.ApplyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except apply_admin.ApplyAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get('/api/apply/config')
def api_apply_config_get():
    """Config inteira (a UI lê/grava seções dela); api_keys de IA só saem
    mascaradas — para a UI nunca precisar lidar com o segredo."""
    cfg = _admin_handler(apply_admin.load_config)
    ia = cfg.get('ia')
    if isinstance(ia, dict):
        ia['providers'] = [apply_admin._publicar(p) for p in ia.get('providers', [])]
    return cfg


@router.put('/api/apply/config')
async def api_apply_config_put(request: Request):
    """Salva a config editada na aba Perfil. A UI manda api_key vazia para
    provedores que não mudou; o backend restaura a chave salva (nunca apaga
    a chave só porque o campo estava mascarado)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Config inválida.")

    def salvar(payload: dict) -> dict:
        salva = apply_admin.load_config()
        salvas = {p.get('id'): p for p in ((salva.get('ia') or {}).get('providers') or [])}
        provs = ((payload.get('ia') or {}).get('providers')) or []
        for p in provs:
            if p.get('id') in salvas and not p.get('api_key'):
                p['api_key'] = salvas[p['id']].get('api_key', '')
            p.pop('api_key_masked', None)
        return apply_admin.save_config(payload)

    return _admin_handler(salvar, payload)


@router.get('/api/apply/env')
def api_apply_env_get():
    """Segredos dos bots (apply/.env) — só as chaves liberadas;
    *_SENHA saem mascaradas, com a mesma regra de api_key de IA."""
    return _admin_handler(apply_admin.load_env)


@router.put('/api/apply/env')
async def api_apply_env_put(request: Request):
    """Salva os segredos editados na aba Perfil (documentos, filiação,
    endereço, credenciais de portal). Só chaves liberadas; valor vazio
    remove a chave; mask original devolve o valor real. As demais linhas
    do .env (GROQ_API_KEY etc.) não são tocadas."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _admin_handler(apply_admin.save_env, payload)


@router.get('/api/apply/perfil-contexto')
def api_apply_perfil_contexto():
    """O bloco de contexto que a IA dos bots recebe — a aba Perfil mostra isso
    para o usuário conferir exatamente o que os LLMs enxergam."""
    return _admin_handler(apply_admin.perfil_contexto)


@router.get('/api/apply/ia')
def api_apply_ia_list():
    return _admin_handler(apply_admin.ia_list)


@router.post('/api/apply/ia')
async def api_apply_ia_add(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _admin_handler(apply_admin.ia_add, payload)


@router.patch('/api/apply/ia/{pid}')
async def api_apply_ia_update(pid: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _admin_handler(apply_admin.ia_update, pid, payload)


@router.delete('/api/apply/ia/{pid}')
def api_apply_ia_delete(pid: str):
    return _admin_handler(apply_admin.ia_delete, pid)


@router.post('/api/apply/ia/{pid}/active')
def api_apply_ia_active(pid: str):
    return _admin_handler(apply_admin.ia_set_active, pid)


@router.post('/api/apply/ia/test')
async def api_apply_ia_test(request: Request):
    """Pong: aceita o form ainda não salvo {tipo, base_url, api_key, modelo}
    ou um {"id": "salvo"} — devolve {"ok": true, "resposta": ...}."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _admin_handler(apply_admin.ia_test, payload)


@router.get('/api/apply/resumes')
def api_apply_resumes_list():
    return _admin_handler(apply_admin.resumes_list)


@router.post('/api/apply/resumes')
async def api_apply_resume_upload(
    file: UploadFile = File(...),
    perfil: str = Form('geral'),
    nome: str = Form(''),
    descricao: str = Form(''),
):
    data = await file.read()
    return _admin_handler(
        apply_admin.resume_upload, data, file.filename or 'resume.pdf',
        nome, descricao, perfil,
    )


@router.patch('/api/apply/resumes/{rid}')
async def api_apply_resume_update(rid: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _admin_handler(apply_admin.resume_update, rid, payload)


@router.delete('/api/apply/resumes/{rid}')
def api_apply_resume_delete(rid: str):
    return _admin_handler(apply_admin.resume_delete, rid)
