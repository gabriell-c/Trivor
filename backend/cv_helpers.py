"""Facade de compatibilidade do domínio CV (superfície histórica `cv_helpers`).

Os nomes moram em cv_extract (extração), cv_checks (regras puras de texto) e
cv_prompts (prompts/colagem LLM). A facade reexporta tudo para que rotas,
main.py e testes sigam fazendo `from cv_helpers import ...` (e o patch de
`cv_helpers.OpenAI` / `cv_helpers._get_provider_for_tool` continue funcionando)
e guarda `_resolver_credenciais_llm`, que referencia OpenAI/_get_provider_for_tool
no próprio namespace — alvo dos testes. Split do god file.
"""

import os

from cv_checks import (  # noqa: F401
    _RE_NUMERO_TERM,
    _STOPWORDS_PT,
    NICE_TO_HAVE_WEIGHT,
    _check_chronological_order,
    _check_profile_summary,
    _check_project_links,
    _check_tech_stack_by_experience,
    _compute_job_fit,
    _dedupe_keep_order,
    _detect_abbreviations,
    _detect_cover_letter,
    _detect_exit_reason,
    _detect_multiple_cvs,
    _detect_sensitive_data,
    _md_cache,
    _norm_text,
    _term_in_text,
    _text_to_markdown,
    calc_fit_score,
)
from cv_extract import (  # noqa: F401
    _ALLOWED_EXTS,
    _MAX_FILE_SIZE,
    _SUPPORTED_EXTS_MSG,
    _check_pdf_selectable,
    _count_pdf_pages,
    _detect_hyperlinks,
    _extract_cv_text,
    _extract_pdf_links,
    _extract_pdf_text_docling_parse,
    _extract_pdf_text_pdfplumber,
    _extract_pdf_text_pymupdf,
    _extract_pdf_text_pypdfium,
    _format_exts,
)
from cv_prompts import (  # noqa: F401
    _FALLBACK_PROMPT_ESTRUT,
    _FALLBACK_PROMPT_QUAL,
    _blindar_falsos_positivos,
    _carregar_prompt_cv,
    _filtrar_ortografia_grounding,
    _montar_checklist_guia,
    _montar_mensagem_estrutura,
    _montar_mensagem_qualidade,
    _validar_citacoes,
)
from fastapi import HTTPException
from llm_core import _LLM_TIMEOUT, _find_provider_by_id, _get_provider_for_tool
from openai import OpenAI


def _resolver_credenciais_llm(api_key: str | None, api_url: str | None,
                              model_name: str | None,
                              provider_id: str | None = None) -> tuple[str, OpenAI, str]:
    """Chave do form, senão a do provedor 'curriculo' salvo na config;
    sem chave nenhuma → HTTP 400. Devolve (key, client pronto, selected_model).

    L7: provider_id (quando vem do form) é usado EXATAMENTE — inexistente
    → 404; não habilitado para a ferramenta → 400. O fallback implícito
    para outro provider nunca mais tapa a escolha do usuário."""
    if provider_id:
        prov = _find_provider_by_id(provider_id)
        if prov is None:
            raise HTTPException(status_code=404, detail="Provider não encontrado.")
        if prov.get('usedFor') in ('none', 'market'):
            raise HTTPException(status_code=400, detail="Este provider não está habilitado para esta ferramenta.")
        if not prov.get('apiKey'):
            raise HTTPException(status_code=400, detail="O provider selecionado não tem chave de API configurada.")
        api_key = prov['apiKey']
        api_url = prov.get('apiUrl') or api_url
        model_name = prov.get('modelName') or model_name

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

    selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = "http://localhost:20128/v1"  # omniroute local

    return key, OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT), selected_model
