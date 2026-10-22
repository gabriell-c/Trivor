"""Rotas de logs: /api/logs, /api/logs/stats, /clear, DELETE e /cleanup.
Movidas do main.py — corpos inalterados.
"""

from fastapi import APIRouter
from logging_service import clear_logs, get_logs, get_logs_stats
from starlette.concurrency import run_in_threadpool

router = APIRouter()


@router.get('/api/logs')
async def api_get_logs(
    limit: int = 100,
    offset: int = 0,
    endpoint: str | None = None,
    error_only: bool = False,
):
    """Retorna logs paginados + stats."""
    logs = await run_in_threadpool(
        lambda: get_logs(limit=limit, offset=offset, endpoint=endpoint, error_only=error_only)
    )
    stats = await run_in_threadpool(get_logs_stats)
    return {"logs": logs, "stats": stats}

@router.get('/api/logs/stats')
async def api_get_logs_stats_route():
    """Retorna estatísticas dos logs."""
    return await run_in_threadpool(get_logs_stats)

@router.post('/api/logs/clear')
async def api_clear_logs():
    """Limpa os logs."""
    await run_in_threadpool(clear_logs)
    return {"success": True}

@router.delete('/api/logs')
async def api_delete_logs():
    """Limpa todos os logs (fallback DELETE)."""
    await run_in_threadpool(clear_logs)
    return {"success": True}

@router.post('/api/logs/cleanup')
async def api_cleanup_logs(days: int = 90):
    """Remove logs antigos (padrão 90 dias)."""
    from logging_service import cleanup_logs
    removed = await run_in_threadpool(cleanup_logs, days)
    return {"success": True, "removed": removed}
