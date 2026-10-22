"""Rota de análise de perfil LinkedIn: /api/linkedin/analyze. Movida do
main.py — corpo inalterado. O helper error_response morava no main e era
usado SOMENTE por esta rota, por isso veio junto.
"""

import json
import os
import time
import uuid

from app_log import get_app_logger
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from llm_core import _LLM_TIMEOUT, LINKEDIN_PROMPT_FILE, _get_provider_for_tool, _mask_key_preview
from logging_service import log_request
from openai import OpenAI
from rate_limit import limiter
from starlette.concurrency import run_in_threadpool

logger = get_app_logger(__name__)
router = APIRouter()


def error_response(code: str, message: str, details: dict | None = None, status_code: int = 400) -> JSONResponse:
    """Retorna resposta de erro padronizada."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S%z')
            }
        }
    )


@router.post('/api/linkedin/analyze')
@limiter.limit("20/minute")
async def analyze_linkedin(
    request: Request,
    text: str = Form(..., description="Texto do perfil LinkedIn"),
    image_url: str = Form(None),
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
):
    """Analisar perfil de LinkedIn a partir de texto colado."""

    if not text or len(text.strip()) < 10:
        return error_response(
            code="INVALID_INPUT",
            message="O texto do perfil deve ter pelo menos 10 caracteres",
            status_code=400
        )
    # Se provider_id fornecido, buscar credenciais salvas
    if provider_id:
        try:
            providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
            prov = next((p for p in providers if p.get('id') == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'market'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            logger.warning(f"[LINKEDIN] provider_id={provider_id} não resolvido (TRIVOR_IAS inválida ou ausente); segue com fallback de chave.")

    # Auto-select provider for linkedin if not provided
    if not api_key or not api_key.strip():
        prov = _get_provider_for_tool('curriculo')
        if prov:
            api_key = prov['apiKey']
            api_url = prov.get('apiUrl') or api_url
            model_name = prov.get('modelName') or model_name

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key or key.strip() == "":
        raise HTTPException(status_code=400, detail="Chave de API de IA não fornecida.")

    selected_model = model_name if (model_name and model_name.strip()) else "gpt-4o"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL") or None

    # Carregar prompt de sistema
    if LINKEDIN_PROMPT_FILE.exists():
        with open(LINKEDIN_PROMPT_FILE, encoding='utf-8') as f:
            sys_p = f.read()
    else:
        sys_p = "Você é um especialista em análise de perfis LinkedIn."

    # Montar user prompt com instruções de limpeza
    user_prompt = (
        f"{sys_p}\n\n"
        "TEXTO DO PERFIL LINKEDIN COLADO PELO USUÁRIO:\n"
        f"---\n{text}\n---\n\n"
        "INSTRUÇÕES:\n"
        "1. Ignore todo lixo do LinkedIn (navegação, footer, recomendações, pessoas que talvez você conheça, etc.)\n"
        "2. Analise APENAS as seções válidas do perfil (nome, headline, sobre, experiências, educação, skills, certificações, idiomas, projetos)\n"
        "3. Se não encontrou uma seção no texto, indique 'Não identificada no texto colado' no campo problema.\n"
        "4. Sua resposta DEVE SER EXCLUSIVAMENTE um objeto JSON válido (sem cercas ```json).\n"
    )

    create_kwargs: dict = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    # Se imagem fornecida e modelo suporta visão, incluir
    if image_url and selected_model in ('gpt-4o', 'gpt-4o-mini', 'claude-sonnet-4', 'claude-3-5-sonnet-20241022'):
        create_kwargs["messages"] = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": [
                {"type": "text", "text": "A imagem abaixo é a FOTO DE PERFIL do usuário no LinkedIn. Analise-a profissionalmente: rosto visível? fundo neutro? iluminação boa? profissional? Em seguida, analise o texto do perfil a seguir seguindo rigorosamente o prompt de sistema."},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]},
            {"role": "user", "content": user_prompt},
        ]

    try:
        if not base_url or 'openai.com' in base_url:
            client = OpenAI(api_key=key, timeout=_LLM_TIMEOUT)
        else:
            client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)

        start_time = time.time()
        comp = await run_in_threadpool(client.chat.completions.create, **create_kwargs)
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = comp.choices[0].message.content or ""
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.split("\n", 1)[-1]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content.rsplit("```", 1)[0]
            cleaned_content = cleaned_content.strip()

        try:
            data = json.loads(cleaned_content)
        except Exception:
            data = {
                "nota": 6.0,
                "resumo_executivo": cleaned_content,
                "pontos_fortes": ["Conteúdo extraído com sucesso"],
                "diagnostico_por_secao": {},
                "analise_ats": {
                    "score_ats": 5.0,
                    "palavras_chave_faltantes": [],
                    "gargalos_formatacao": [],
                    "veredito_robos": cleaned_content
                }
            }

        if hasattr(comp, 'usage') and comp.usage:
            data['uso_tokens'] = {
                'prompt_tokens': comp.usage.prompt_tokens,
                'completion_tokens': comp.usage.completion_tokens,
                'total_tokens': comp.usage.total_tokens
            }
            data['api_info'] = {
                'model': selected_model,
                'request_id': getattr(getattr(comp, 'id', None), 'id', str(comp.id)) if hasattr(comp, 'id') else str(uuid.uuid4()),
                'response_time_ms': int(response_time_ms),
            }

        log_request(
            endpoint="/api/linkedin/analyze",
            method="POST",
            status_code=200,
            duration_ms=int(response_time_ms),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
        )

        return data

    except Exception as e:
        log_request(
            endpoint="/api/linkedin/analyze",
            method="POST",
            status_code=500,
            duration_ms=0,
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
        )
        return error_response(
            code="ANALYSIS_ERROR",
            message="Erro na análise do LinkedIn",
            details={"error": str(e)},
            status_code=500
        )
