"""Infraestrutura LLM compartilhada pelas rotas de domínio: caminhos de
arquivos de prompt, resolução de chave/provider (provider_id → TRIVOR_IAS →
OPENAI_API_KEY → provider salvo), parse da resposta JSON da LLM e
construção do client.

Separada do main.py para as rotas importarem sem ciclo (um router nunca
importa main; main importa os routers). O main.py mantém uma facade para os
nomes históricos (testes fazem `from main import _get_provider_for_tool`
e similares).
"""

import json
import os
import re
from pathlib import Path

import httpx
from app_log import get_app_logger
from fastapi import HTTPException
from openai import OpenAI

logger = get_app_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / 'knowledge'
LINKEDIN_PROMPT_FILE = KNOWLEDGE_DIR / 'linkedin_prompt.md'
CV_FIT_PROMPT_FILE = KNOWLEDGE_DIR / 'cv_fit_prompt.md'
RECRUITER_PROMPT_FILE = KNOWLEDGE_DIR / 'recruiter_prompt.md'
COVER_LETTER_PROMPT_FILE = KNOWLEDGE_DIR / 'cover_letter_prompt.md'
CV_DIFF_PROMPT_FILE = KNOWLEDGE_DIR / 'cv_diff_prompt.md'

# Timeout global das chamadas LLM: 120s no total (gerações longas), 10s para
# abrir a conexão — sem timeout, uma base_url morta pendura o request por um tempo indeterminado.
_LLM_TIMEOUT = httpx.Timeout(120, connect=10.0)


def _mask_key_preview(key: str) -> str:
    """Preview da chave para logs: apenas o SUFIXO (últimos 4 chars).
    O prefixo nunca vai para o banco de logs (retention 90d)."""
    if not key or len(key) <= 4:
        return "***"
    return f"…{key[-4:]}"


def _find_provider_by_id(provider_id: str | None):
    """Localiza um provider por id em TRIVOR_IAS (ou None se ausente/inválido).
    Sem 'any provider' — a escolha explícita do usuário tem que bater em algo
    concreto, senão a rota levanta 404 (veja _resolve_key_and_client)."""
    if not provider_id:
        return None
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        return next((p for p in providers if p.get('id') == provider_id), None)
    except Exception:
        return None


def _get_provider_for_tool(tool: str):
    """Retorna o melhor provider para uma ferramenta, ou None.
    Considera apenas usedFor em ('all', tool) — um provider dedicado a OUTRA
    ferramenta nunca entra como fallback (o fallback 'qualquer um com apiKey'
    antes ignorava usedFor e podia usar, p.ex., a chave de 'market' para o
    currículo)."""
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        if not providers:
            return None
        # Prioridade: all > tool-specific
        for priority in ('all', tool):
            for p in providers:
                if p.get('usedFor') == priority and p.get('apiKey'):
                    return p
        return None
    except Exception:
        return None


def _parse_llm_json(result_text: str) -> dict:
    """Faz parse da resposta JSON da LLM (response_format json_object).
    Se a resposta vier com markdown/lixo, tenta extrair o primeiro {...};
    se tudo falhar, devolve um dict mínimo com o texto bruto (o endpoint decide)."""
    text = (result_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"raw": result_text}
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                data = json.loads(match.group())
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                pass
        return {"raw": result_text, "error": "Não foi possível parsear JSON"}


# Fallbacks de endpoints LLM quando model/base_url não vêm da requisição
# (omniroute local na porta 20128)
_LLM_FALLBACK_MODEL = "auto/best-coding"
_LLM_FALLBACK_BASE_URL = "http://localhost:20128/v1"


def _resolve_key_and_client(provider_id: str | None, api_key: str | None,
                           api_url: str | None, model_name: str | None):
    """Resolve as credenciais LLM na ordem:
    provider_id (via TRIVOR_IAS no ambiente) → api_key fornecida →
    OPENAI_API_KEY → provider salvo de 'curriculo' (_get_provider_for_tool).

    Retorna (client, key, model, base_url). Sem chave em nenhum nível,
    client vem None — o endpoint levanta 400. provider_id inexistente
    levanta 404 na hora (não pode silenciosamente virar outra chave)."""
    resolved_key = api_key
    resolved_url = api_url
    resolved_model = model_name

    if provider_id:
        prov = _find_provider_by_id(provider_id)
        if prov is None:
            # Escolha explícita da UI que não bate com nenhum provider salvo:
            # 404 honesto, nunca fallback para uma chave diferente
            raise HTTPException(status_code=404, detail="Provider não encontrado.")
        if prov.get('usedFor') in ('none', 'market'):
            raise HTTPException(status_code=400, detail="Este provider não está habilitado para esta ferramenta.")
        if not prov.get('apiKey'):
            raise HTTPException(status_code=400, detail="O provider selecionado não tem chave de API configurada.")
        resolved_key = prov['apiKey']
        resolved_url = prov.get('apiUrl') or api_url
        resolved_model = prov.get('modelName') or model_name

    key = resolved_key or os.getenv("OPENAI_API_KEY", "")
    if not key or key.strip() == "":
        prov = _get_provider_for_tool('curriculo')
        if prov:
            key = prov['apiKey']
            resolved_url = prov.get('apiUrl') or resolved_url
            resolved_model = prov.get('modelName') or resolved_model

    if not key or key.strip() == "":
        return None, None, None, None

    selected_model = resolved_model if (resolved_model and resolved_model.strip()) else _LLM_FALLBACK_MODEL
    base_url = resolved_url if (resolved_url and resolved_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = _LLM_FALLBACK_BASE_URL

    client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
    return client, key, selected_model, base_url
