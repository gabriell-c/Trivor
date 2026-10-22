"""Rotas do domínio Mercado: /api/market/analyze + exports (/api/export,
/api/export/market). Movidas do main.py — corpos inalterados.

DB_FILE agora mora em market_db (mesmo caminho físico de antes, backend/
market.db); as rotas acessam por market_db.DB_FILE para os testes poderem
apontar o DB via monkeypatch.
"""

import json
import os
import time
import uuid

import market_db
from app_log import get_app_logger
from export_utils import generate_docx_export, generate_markdown_export, generate_pdf_export
from fastapi import APIRouter, Form, HTTPException, Request, Response
from llm_core import _LLM_TIMEOUT, _get_provider_for_tool
from market_export import (
    generate_market_docx_export,
    generate_market_markdown_export,
    generate_market_pdf_export,
)
from market_service import run_market_analysis
from openai import OpenAI
from rate_limit import limiter
from starlette.concurrency import run_in_threadpool

logger = get_app_logger(__name__)
router = APIRouter()


@router.post('/api/market/analyze')
@limiter.limit("10/minute")
async def analyze_market(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    jsearch_api_keys: str = Form(None),
    jsearch_api_key: str = Form(None),
    job_title: str = Form(...),
    target_stack: str = Form(""),
    seniority: str = Form("Pleno"),
    location: str = Form("Remoto Nacional"),
    time_window: str = Form("90 dias"),
    negative_keywords: str = Form("")
):
    # Se provider_id fornecido, buscar credenciais salvas
    if provider_id:
        try:
            providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
            prov = next((p for p in providers if p.get('id') == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'curriculo'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            logger.warning(f"[MARKET/ANALYZE] provider_id={provider_id} não resolvido (TRIVOR_IAS inválida ou ausente); segue com fallback de chave.")

    # Use system-level OPENAI_API_KEY as primary fallback before checking stored providers
    key = api_key or os.getenv("OPENAI_API_KEY", "")

    # Only use TRIVOR_IAS provider if no system key was found and no explicit api_key was sent
    if not key or not key.strip():
        prov = _get_provider_for_tool('market')
        if prov:
            api_key = prov['apiKey']
            api_url = prov.get('apiUrl') or api_url
            model_name = prov.get('modelName') or model_name
            key = api_key

    if not key or key.strip() == "":
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    selected_model = model_name if (model_name and model_name.strip()) else "gpt-4o"
    base_url = api_url
    if not base_url or base_url.strip() == "":
        base_url = "https://api.openai.com/v1"

    start_time = time.time()

    try:
        client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
        report = await run_in_threadpool(run_market_analysis,
            db_file=market_db.DB_FILE,
            client=client,
            selected_model=selected_model,
            job_title=job_title,
            target_stack=target_stack,
            seniority=seniority,
            location=location,
            time_window=time_window,
            negative_keywords=negative_keywords,
            jsearch_api_keys=[k.strip() for k in (jsearch_api_keys or jsearch_api_key or "").split(",") if k.strip()] if (jsearch_api_keys or jsearch_api_key) else []
        )
        elapsed = round(time.time() - start_time, 2)
        return {"success": True, "report": report, "model": selected_model, "elapsed_seconds": elapsed}
    except Exception:
        # Detalhe vai só para os logs (com stacktrace); o cliente recebe mensagem genérica
        logger.exception("[MARKET ERROR] falha interna na análise de mercado")
        raise HTTPException(status_code=500, detail="Falha interna na análise de mercado. Tente novamente em instantes.")


# ---------------------------------------------------------------------------
# Endpoints de Exportação
# ---------------------------------------------------------------------------

@router.post('/api/export')
async def export_analysis(
    format: str = Form(...), # json, md, docx, pdf
    filename: str = Form(None),
    job_target: str = Form(None),
    model_name: str = Form(None),
    data_json: str = Form(...)
):
    try:
        data = json.loads(data_json)
        fname = filename or "curriculo.pdf"
        vaga = job_target or "Geral"
        model = model_name or "gpt-4o"

        if format == 'json':
            content = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                content=content,
                media_type='application/json',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.json"'}
            )
        elif format == 'md':
            content = generate_markdown_export(data, fname, vaga, model)
            return Response(
                content=content,
                media_type='text/markdown',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.md"'}
            )
        elif format == 'docx':
            buffer = generate_docx_export(data, fname, vaga, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.docx"'}
            )
        elif format == 'pdf':
            buffer = generate_pdf_export(data, fname, vaga, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="diagnostico_{uuid.uuid4().hex[:6]}.pdf"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração do arquivo: {e!s}")


@router.post('/api/export/market')
async def export_market_analysis(
    format: str = Form(...),
    filename: str = Form(None),
    job_title: str = Form(None),
    seniority: str = Form(None),
    location: str = Form(None),
    model_name: str = Form(None),
    report_json: str = Form(...)
):
    try:
        report = json.loads(report_json)
        fname = filename or "analise_mercado"
        job = job_title or "Geral"
        senior = seniority or "Pleno"
        loc = location or "Remoto"
        model = model_name or "gpt-4o"

        if format == 'md':
            content = generate_market_markdown_export(report, job, senior, loc, model)
            return Response(
                content=content,
                media_type='text/markdown',
                headers={'Content-Disposition': f'attachment; filename="{fname}_{model}_{uuid.uuid4().hex[:6]}.md"'}
            )
        elif format == 'docx':
            buffer = generate_market_docx_export(report, job, senior, loc, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={'Content-Disposition': f'attachment; filename="{fname}_{model}_{uuid.uuid4().hex[:6]}.docx"'}
            )
        elif format == 'pdf':
            buffer = generate_market_pdf_export(report, job, senior, loc, model)
            return Response(
                content=buffer.getvalue(),
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="{fname}_{model}_{uuid.uuid4().hex[:6]}.pdf"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use: md, docx, pdf")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração do arquivo: {e!s}")
