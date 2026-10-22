"""Rotas de IA genérica: /api/test-connection (ping do provedor) e
/api/ia/analyze. Movidas do main.py — corpos inalterados.
"""

import os
import time

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from llm_core import _LLM_TIMEOUT, _get_provider_for_tool
from openai import OpenAI
from rate_limit import limiter
from starlette.concurrency import run_in_threadpool

router = APIRouter()


@router.post('/api/test-connection')
@limiter.limit("10/minute")
async def api_test_ia_connection(
    request: Request,
    api_key: str = Form(...),
    api_url: str = Form(''),
    model_name: str = Form(''),
    text: str = Form(''),
):
    """Ping de conexão do provedor de IA com custo mínimo: 1 chamada,
    1 token de saída. `text` não é usado de propósito (o prompt do ping
    é fixo e pequeno, independente do que o front envie)."""
    key = (api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")
    base_url = (api_url or "").strip() or "https://api.openai.com/v1"
    model = (model_name or "").strip() or "gpt-4o"
    start = time.time()
    try:
        client = OpenAI(api_key=key, base_url=base_url,
                        timeout=httpx.Timeout(20, connect=10.0))
        response = await run_in_threadpool(client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        usage = response.usage
        return {
            "success": True,
            "message": f"Conexão OK ({model})",
            "model": model,
            "latency_ms": round((time.time() - start) * 1000),
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
            },
        }
    except Exception as e:
        # Sanitiza: a chave nunca deve aparecer na resposta nem no log.
        detail = str(e).replace(key, "")[:300]
        raise HTTPException(status_code=502, detail=f"Erro na conexão: {detail}")


@router.post('/api/ia/analyze')
@limiter.limit("20/minute")
async def analyze_ia(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    content: str = Form(...),
    filename: str = Form(None),
):
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key or key.strip() == "":
        prov = _get_provider_for_tool('curriculo')
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
    try:
        client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
        response = await run_in_threadpool(client.chat.completions.create,
            model=selected_model,
            messages=[
                {"role": "system", "content": "Você é um especialista em análise de currículos e mercado de trabalho."},
                {"role": "user", "content": content}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return {
            "success": True,
            "result": response.choices[0].message.content,
            "model": selected_model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise de IA: {e!s}")
