"""Rotas do domínio CV: /api/cv/analyze, /api/market/cv-fit,
/api/cv/semantic-fit, /api/cv/recruiter-sim, /api/cv/cover-letter e
/api/cv/diff.

Movidas do main.py — corpos dos handlers inalterados; helpers de análise
(pedidos do guia, fit determinístico, extração de texto) ficaram em
cv_helpers, infraestrutura LLM em llm_core. Os validadores de saída de
LLM (anti-alucinação) ficam neste módulo junto das rotas que os usam.
"""

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from collections import Counter

import market_db
from app_log import get_app_logger
from cv_helpers import (
    _ALLOWED_EXTS,
    _FALLBACK_PROMPT_ESTRUT,
    _FALLBACK_PROMPT_QUAL,
    _MAX_FILE_SIZE,
    _STOPWORDS_PT,
    _SUPPORTED_EXTS_MSG,
    NICE_TO_HAVE_WEIGHT,
    _blindar_falsos_positivos,
    _carregar_prompt_cv,
    _compute_job_fit,
    _dedupe_keep_order,
    _detect_hyperlinks,
    _extract_cv_text,
    _extract_pdf_links,
    _filtrar_ortografia_grounding,
    _md_cache,
    _montar_checklist_guia,
    _montar_mensagem_estrutura,
    _montar_mensagem_qualidade,
    _norm_text,
    _resolver_credenciais_llm,
    _term_in_text,
    _text_to_markdown,
    _validar_citacoes,
    calc_fit_score,
)
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from llm_core import (
    COVER_LETTER_PROMPT_FILE,
    CV_DIFF_PROMPT_FILE,
    CV_FIT_PROMPT_FILE,
    KNOWLEDGE_DIR,
    RECRUITER_PROMPT_FILE,
    _mask_key_preview,
    _parse_llm_json,
    _resolve_key_and_client,
)
from logging_service import log_request
from rate_limit import limiter
from starlette.concurrency import run_in_threadpool

logger = get_app_logger(__name__)
router = APIRouter()


@router.post('/api/cv/analyze')
@limiter.limit("30/minute")
async def analyze_cv(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file: UploadFile = File(...),
    job_description: str = Form(""),
    target_role: str = Form(""),
    area: str = Form(""),
):
    try:
        content = await cv_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")
        ext = os.path.splitext(cv_file.filename or "")[1].lower()
        if ext not in _ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cv_')
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)

            # Extrair texto com fallback chain (helper reutilizado pelo /api/market/cv-fit)
            markdown_text, extractor_used, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
            if not markdown_text:
                markdown_text = "Erro ao extrair texto do documento."

            # Cache de markdown — chaveada pelo CONTEÚDO do texto:
            # o nome do mkstemp é único por request, então chave por path nunca acertaria.
            cache_key = hashlib.md5(markdown_text.encode('utf-8', 'ignore')).hexdigest() if markdown_text else None
            if cache_key:
                cached_md = _md_cache.get(cache_key)
                if cached_md is not None:
                    markdown_text = cached_md
                else:
                    markdown_text = _text_to_markdown(markdown_text)
                    _md_cache[cache_key] = markdown_text
                    # Evicção simples (dict preserva ordem de inserção): mantém as últimas 64
                    while len(_md_cache) > 64:
                        _md_cache.pop(next(iter(_md_cache)))

            # Detectar hyperlinks
            links_info = _detect_hyperlinks(markdown_text)
            if ext == '.pdf':
                pdf_links = await run_in_threadpool(_extract_pdf_links, temp_path)
                for url in pdf_links:
                    already = any(link['url'] == url for link in links_info)
                    if not already:
                        links_info.append({'url': url, 'valid': True})
            logger.info(f"[CV] Links detectados: {len(links_info)}")

            # ====================================================================
            # VALIDAÇÕES DO GUIA (CHECKLIST COMPLETO)
            # ====================================================================
            checklist_validacao = _montar_checklist_guia(
                temp_path, ext, cv_file.filename or "", markdown_text, links_info, logger)

            # Configurar cliente LLM (chave do form → provedor 'curriculo' salvo → env)
            key, client, selected_model = _resolver_credenciais_llm(api_key, api_url, model_name)

            # Carregar prompts — análise em 2 passes (estrutura → qualidade).
            # O prompt monolítico cv_analysis_prompt.md continua em knowledge/
            # apenas para referência/histórico; o endpoint usa os prompts divididos.
            sys_prompt_estrut = _carregar_prompt_cv(KNOWLEDGE_DIR / 'cv_analysis_estrutura.md', _FALLBACK_PROMPT_ESTRUT)
            sys_prompt_qual = _carregar_prompt_cv(KNOWLEDGE_DIR / 'cv_analysis_qualidade.md', _FALLBACK_PROMPT_QUAL)

            # Montar user message — PASSO 1 (estrutura)
            area_info = target_role or area or ''
            user_content_estrut = _montar_mensagem_estrutura(
                markdown_text, links_info, ext, extractor_used, job_description, area_info)

            # PASSO 1 — estrutura (nota base, seções, ortografia, erros comuns, ATS)
            response_estrut = await run_in_threadpool(client.chat.completions.create,
                model=selected_model,
                messages=[
                    {"role": "system", "content": sys_prompt_estrut},
                    {"role": "user", "content": user_content_estrut},
                ],
                temperature=0.3,
                max_tokens=3500,
                response_format={"type": "json_object"},
            )

            analysis = _parse_llm_json(response_estrut.choices[0].message.content)

            # PASSO 2 — qualidade (XYZ, métricas, narrativa), com o resumo do
            # passo 1 como contexto. Sequencial de propósito: o passo 2 depende
            # do resultado do passo 1. Se falhar, segue com a estrutura só.
            user_content_qual = _montar_mensagem_qualidade(markdown_text, analysis, area_info)

            response_qual = None
            try:
                response_qual = await run_in_threadpool(client.chat.completions.create,
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": sys_prompt_qual},
                        {"role": "user", "content": user_content_qual},
                    ],
                    temperature=0.2,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                )
                qualidade = _parse_llm_json(response_qual.choices[0].message.content)
                # Merge: só os campos de qualidade vêm do passo 2; o resto
                # permanece do passo 1 (contrato final = campos de hoje).
                for campo in ("pontos_fortes", "pontos_fracos"):
                    val = qualidade.get(campo)
                    analysis[campo] = [i for i in val if isinstance(i, str)] if isinstance(val, list) else []
            except Exception as qual_err:
                logger.warning(f"[CV] Passo 2 (qualidade) falhou; mantendo apenas a análise estrutural: {qual_err}")

            # VALIDAÇÃO DE CITAÇÕES (passo 2): cada trecho em (trecho: '...')
            # tem que existir no texto extraído (comparação ignora acentos/maiúsculas).
            # Trecho inválido → remover a citação, manter o item.
            _validar_citacoes(analysis, markdown_text)

            # VALIDAÇÃO DE GROUNDING: remover erros ortográficos alucinados
            _filtrar_ortografia_grounding(analysis, markdown_text)

            # === PÓS-PROCESSAMENTO DEFINITIVO: blindar contra falsos positivos ===
            _blindar_falsos_positivos(analysis, markdown_text, area_info)

            # Adicionar metadados compatíveis com o frontend
            # Uso_tokens: soma dos 2 passes (estrutura + qualidade)
            _u1 = getattr(response_estrut, 'usage', None)
            _u2 = getattr(response_qual, 'usage', None) if response_qual is not None else None
            analysis['uso_tokens'] = {
                "prompt_tokens": (_u1.prompt_tokens if _u1 else 0) + (_u2.prompt_tokens if _u2 else 0),
                "completion_tokens": (_u1.completion_tokens if _u1 else 0) + (_u2.completion_tokens if _u2 else 0),
                "total_tokens": ((_u1.prompt_tokens + _u1.completion_tokens) if _u1 else 0)
                                + ((_u2.prompt_tokens + _u2.completion_tokens) if _u2 else 0),
            }
            analysis['api_info'] = {
                "model": selected_model,
                "request_id": str(uuid.uuid4()),
                "response_time_ms": 0,
            }
            # Adicionar checklist de validação do guia
            analysis['checklist_validacao'] = checklist_validacao

            # Fit determinístico CV × vaga (sem LLM) — só com descrição real da vaga
            jd_clean = (job_description or "").strip()
            if len(jd_clean) >= 40 and markdown_text and not markdown_text.startswith("Erro ao extrair"):
                analysis['fit_com_vaga'] = _compute_job_fit(markdown_text, jd_clean)

            analysis['_extractor_used'] = extractor_used
            analysis['_links'] = [link['url'] for link in links_info]

            # Salvar log com texto extraído e prompt
            llm_prompt = (f"SYSTEM (passo 1):\n{sys_prompt_estrut}\n\nUSER (passo 1):\n{user_content_estrut}\n\n"
                          f"SYSTEM (passo 2):\n{sys_prompt_qual}\n\nUSER (passo 2):\n{user_content_qual}")
            extracted_truncated = markdown_text[:5000] if markdown_text else ""
            prompt_truncated = llm_prompt[:8000] if llm_prompt else ""
            response_summary_json = json.dumps(analysis, ensure_ascii=False)
            log_request(
                endpoint="/api/cv/analyze",
                method="POST",
                status_code=200,
                duration_ms=0,
                model=selected_model,
                api_key_preview=_mask_key_preview(key),
                response_summary=response_summary_json,
                extracted_text=extracted_truncated,
                llm_prompt=prompt_truncated,
            )

            return JSONResponse(content=analysis)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CV] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar o currículo: {e!s}")


# ---------------------------------------------------------------------------
# Fit CV × Vagas do Mercado — ranking determinístico (sem LLM, sem chave)
# ---------------------------------------------------------------------------

def _list_relevant_market_jobs() -> list:
    """Leitura síncrona da base de vagas (SQLite).

    Chamar via run_in_threadpool a partir de endpoints async para não
    bloquear o event loop. Lê market_db.DB_FILE por acesso de módulo (e não
    import de cópia) para os testes poderem apontar o DB via monkeypatch."""
    conn = sqlite3.connect(market_db.DB_FILE)
    try:
        return conn.execute(
            "SELECT id, title, company, location, modality, source_url, requirements, nice_to_have "
            "FROM market_jobs WHERE is_relevant = 1"
        ).fetchall()
    finally:
        conn.close()


@router.post('/api/market/cv-fit')
@limiter.limit("10/minute")
async def market_cv_fit(
    request: Request,
    cv_file: UploadFile = File(...),
    limit: int = Form(20),
):
    """Ranking: quais vagas da base do market têm melhor fit com o CV enviado.
    100% determinístico — lê a base local (market_jobs), faz matching de
    requisitos normalizado por acento e devolve top-N + faltantes agregados."""
    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    ext = os.path.splitext(cv_file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

    limit = max(1, min(limit, 50))

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvfit_')
    extractor_used = "none"
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, extractor_used, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    rows = await run_in_threadpool(_list_relevant_market_jobs)

    if not rows:
        raise HTTPException(status_code=400, detail="Base de mercado vazia. Rode uma análise de mercado primeiro (aba Mercado).")

    cv_norm = _norm_text(cv_text)
    results = []
    missing_counter: Counter = Counter()
    for (job_id, title, company, location, modality, source_url, reqs_json, nice_json) in rows:
        try:
            reqs = json.loads(reqs_json) if reqs_json else []
            nice = json.loads(nice_json) if nice_json else []
        except json.JSONDecodeError:
            reqs, nice = [], []
        reqs = [r for r in reqs if isinstance(r, str) and r.strip()]
        nice = [n for n in nice if isinstance(n, str) and n.strip()]
        total_units = len(reqs) + NICE_TO_HAVE_WEIGHT * len(nice)
        if total_units <= 0:
            continue
        cobertos = [t for t in reqs if _term_in_text(t, cv_norm)]
        faltantes = [t for t in reqs if not _term_in_text(t, cv_norm)]
        nice_cobertas = [t for t in nice if _term_in_text(t, cv_norm)]
        nice_faltantes = [t for t in nice if not _term_in_text(t, cv_norm)]
        nota = calc_fit_score(cobertos, nice_cobertas, total_units)
        results.append({
            "id": job_id,
            "titulo": title,
            "empresa": company,
            "localizacao": location,
            "modalidade": modality,
            "url": source_url or None,
            "score": nota,
            "cobertos": cobertos,
            "faltantes": faltantes,
            "desejaveis_faltantes": nice_faltantes,
        })
        for term in faltantes:
            missing_counter[term] += 1

    if not results:
        raise HTTPException(status_code=400, detail="Nenhuma vaga relevante com requisitos extraíveis na base do mercado.")

    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:limit]
    score_medio = round(sum(r["score"] for r in results) / len(results), 1)
    faltantes_topicos = [
        {"termo": term, "em_quantas_vagas": count}
        for term, count in missing_counter.most_common(10)
    ]
    resumo = (
        f"{len(results)} vaga(s) da base do mercado comparadas. Fit médio: {score_medio}%. "
        + (f"Mais faltas do seu CV: {', '.join(t['termo'] for t in faltantes_topicos[:5])}." if faltantes_topicos else "Seu CV cobre a maior parte do que o mercado exige.")
    )
    log_request(
        "/api/market/cv-fit", "POST", 200, round((time.time() - t0) * 1000, 1), None, None,
        request_body={"limit": limit, "total_vagas": len(results)},
        response_summary=f"Fit médio {score_medio}% sobre {len(results)} vagas; top: {top[0]['titulo'][:60]}",
    )
    return {
        "total_vagas": len(results),
        "vagas": top,
        "faltantes_topicos": faltantes_topicos,
        "resumo": resumo,
        "extractor_used": extractor_used,
    }

# ---------------------------------------------------------------------------
# Fit Semântico CV × Vaga (LLM) — requisitos reais da vaga + reescritas XYZ
# ---------------------------------------------------------------------------

def _semantic_fit_evidence_valid(citation: str, cv_text: str) -> bool:
    """Validação anti-alucinação: True se a citação (trecho citado como
    evidência/texto atual do CV) ocorre no texto extraído.
    Comparação normalizada: minúsculas + sem acentos + espaços colapsados.
    - Substring direto → válido.
    - Citação longa com palavra em ordem/outro grafia → válida se TODAS as
      palavras relevantes (>3 letras) estiverem no CV (mín. 2 palavras).
    - Citação com menos de 2 palavras relevantes e sem match exato → inválida.
    """
    def normalize(s: str) -> str:
        return _norm_text(re.sub(r'\s+', ' ', s).strip())
    cit = normalize(citation)
    cv = normalize(cv_text)
    if not cit:
        return False
    if cit in cv:
        return True
    words = [w for w in cit.split() if len(w) > 3]
    if len(words) < 2:
        return False
    return all(w in cv for w in words)


def _semantic_fit_validate(fit: dict, cv_text: str) -> dict:
    """Pós-processo do fit semântico: zera `evidencia` e `texto_atual` que não
    ocorrem no CV — citação que não bate com o texto extraído é alucinação
    e vira null (com `presente=false` no requisito). Retorna o mesmo dict."""
    requisitos = fit.get('requisitos')
    if isinstance(requisitos, list):
        for req in requisitos:
            if not isinstance(req, dict):
                continue
            ev = req.get('evidencia')
            if isinstance(ev, str) and ev.strip() and not _semantic_fit_evidence_valid(ev, cv_text):
                req['evidencia'] = None
                req['presente'] = False
                req['alias_encontrado'] = None
    sugestoes = fit.get('sugestoes_de_reescrita')
    if isinstance(sugestoes, list):
        for sug in sugestoes:
            if not isinstance(sug, dict):
                continue
            atual = sug.get('texto_atual')
            if isinstance(atual, str) and atual.strip() and not _semantic_fit_evidence_valid(atual, cv_text):
                sug['texto_atual'] = None
    return fit


# ---------------------------------------------------------------------------
# Simulador de Recrutador CV × Vaga (LLM) — veredito honesto + perguntas
# ---------------------------------------------------------------------------

_RECRUITER_VEREDICTS = {'aprovado', 'duvida', 'reprovado'}
# Teto de itens por lista, como definido no prompt (e ≤ ao limite geral de 8)
_RECRUITER_LIST_MAX = {'por_que': 6, 'sinais_vermelhos': 5, 'perguntas_de_entrevista': 3}


def _clean_recruiter_list(items, max_items: int) -> list:
    """Remove itens não-texto/ vazios e trunca a lista do simulador ao teto
    definido pelo prompt."""
    if not isinstance(items, list):
        return []
    clean = [str(i).strip() for i in items if isinstance(i, str) and i.strip()]
    return clean[:max_items]


def _recruiter_sim_validate(sim: dict) -> dict:
    """Pós-processo do simulador: normaliza o JSON da LLM sem confiar nele.
    `veredito` fora do mapa → 'duvida' (veredito conservador); `confianca`
    fora de 0-10 → 5; listas perdem itens vazios/não-texto e truncam ao teto.
    Retorna o mesmo dict."""
    if not isinstance(sim, dict):
        sim = {}

    veredito = sim.get('veredito')
    if not isinstance(veredito, str) or veredito.strip().lower() not in _RECRUITER_VEREDICTS:
        veredito = 'duvida'
    sim['veredito'] = veredito.strip().lower()

    conf = sim.get('confianca')
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        conf = 5
    sim['confianca'] = max(0.0, min(10.0, round(float(conf), 1)))

    for campo, max_items in _RECRUITER_LIST_MAX.items():
        sim[campo] = _clean_recruiter_list(sim.get(campo), max_items)

    return sim


# ---------------------------------------------------------------------------
# Comparação de Duas Versões de CV — diff determinístico + narrativa LLM
# ---------------------------------------------------------------------------

# Métricas numéricas no CV: percentuais ("30%"), moeda ("R$ 120 mil"),
# ordens de grandeza ("50 mil", "3k"), contadores ("15 pontos", "3 vezes")
# e verbos de resultado com número ("redução em 30%", "aumento de 12").
_METRIC_RE = re.compile(
    r"""\d+(?:[.,]\d+)?\s*%
      |R\$\s?\d+(?:[.,]\d+)?
      |\b\d+(?:[.,]\d+)?\s*(?:mil|mi|k)\b
      |\b\d+(?:[.,]\d+)?\s*(?:pontos|vezes)\b
      |\b(?:reduz|reduc|reducao|diminui|aument|cresc|economiz|eleva|gera)\w*\s+(?:em|de|para)\s+\d+(?:[.,]\d+)""",
    re.IGNORECASE | re.VERBOSE,
)

# Cabeçalhos que abrem a seção de experiências e cabeçalhos estruturais que a
# encerram (em linha própria, como sai dos extratores markdown).
_EXP_HEADING_RE = re.compile(
    r'^(experi[êe]ncias?|trabalho|atu[açc][ãa]o|hist[oó]rico profissional|experi[êe]ncia profissional)(\s*:.*)?$'
)
_END_HEADING_RE = re.compile(
    r'^(forma[çc][ãa]o(s)?|educa[çc][ãa]o|cursos|h[áa]bilidades|tecnologias|idiomas|certifica[çc][oõ]es|projetos|links|contatos?|informa[çc][oõ]es)(\s*:.*)?$'
)
_BULLET_LINE_RE = re.compile(r'^\s*[-•*▪·]\s+\S')


def _count_bullets_experiencia(text: str) -> int:
    """Nº de bullet points na seção de experiência do CV. A seção vai do
    cabeçalho "Experiência(s)/Trabalho/Atuação" até o próximo cabeçalho
    estrutural (Formação, Habilidades, Projetos...) ou fim do texto; sem
    cabeçalho de experiências, conta bullets no texto inteiro."""
    linhas = text.splitlines()
    inicio = None
    fim = None
    for i, linha in enumerate(linhas):
        low = re.sub(r'\s+', ' ', linha.strip().lower())
        if inicio is None:
            if _EXP_HEADING_RE.fullmatch(low):
                inicio = i + 1
        elif _END_HEADING_RE.fullmatch(low):
            fim = i
            break
    corpo = linhas[inicio:fim] if inicio is not None else linhas
    return sum(1 for linha in corpo if _BULLET_LINE_RE.match(linha))


def _repeated_terms(text: str) -> dict:
    """Termos (4+ letras, fora das stopwords) que se repetem no texto —
    candidatos a skills/palavras-chave do próprio CV, no padrão de
    _check_tech_stack_by_experience. Retorna {termo: ocorrencias}."""
    counts = Counter(
        t.lower() for t in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,}", text)
        if t.lower() not in _STOPWORDS_PT
    )
    return {t: c for t, c in counts.items() if c >= 2}


def _diff_cv_deterministic(texto_anterior: str, texto_novo: str) -> dict:
    """Diff determinístico (sem LLM) entre duas versões do CV: bullets da
    seção de experiência, métricas numéricas e termos-chave repetidos que
    entraram/saíram entre as versões. Reproducível entre execuções."""
    bullets_ant = _count_bullets_experiencia(texto_anterior)
    bullets_nov = _count_bullets_experiencia(texto_novo)
    metricas_ant = len(_METRIC_RE.findall(texto_anterior))
    metricas_nov = len(_METRIC_RE.findall(texto_novo))

    termos_ant = _repeated_terms(texto_anterior)
    termos_nov = _repeated_terms(texto_novo)
    # Ordem: termos mais frequentes na versão de origem primeiro, teto de 20
    novos = sorted(set(termos_nov) - set(termos_ant), key=lambda t: -termos_nov[t])[:20]
    removidos = sorted(set(termos_ant) - set(termos_nov), key=lambda t: -termos_ant[t])[:20]

    return {
        "bullets_experiencia": {"anterior": bullets_ant, "novo": bullets_nov},
        "metricas_numericas": {"anterior": metricas_ant, "novo": metricas_nov},
        "termos_adicionados": novos,
        "termos_removidos": removidos,
    }


def _diff_cv_validate(narrativa: dict, texto_anterior: str, texto_novo: str) -> dict:
    """Pós-processo anti-alucinação do diff: normaliza os itens de
    `melhorias`/`piorou` e zera evidências que não ocorrem no texto da versão
    correspondente (mesma regra do fit semântico, via
    _semantic_fit_evidence_valid). Retorna o mesmo dict."""
    if not isinstance(narrativa, dict):
        narrativa = {}

    def _item_str(item, *campos):
        for c in campos:
            v = item.get(c)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _normalizar(lista: list, max_itens: int) -> list:
        if not isinstance(lista, list):
            return []
        out = []
        for item in lista[:max_itens]:
            if isinstance(item, str):
                item = {"item": item, "evidencia_antiga": None, "evidencia_nova": None}
            if not isinstance(item, dict):
                continue
            desc = _item_str(item, 'item', 'texto', 'descricao')
            ev_ant = item.get('evidencia_antiga')
            ev_nov = item.get('evidencia_nova')
            # Zera evidência que não existe no texto da versão citada
            if isinstance(ev_ant, str) and ev_ant.strip() and not _semantic_fit_evidence_valid(ev_ant, texto_anterior):
                ev_ant = None
            if isinstance(ev_nov, str) and ev_nov.strip() and not _semantic_fit_evidence_valid(ev_nov, texto_novo):
                ev_nov = None
            if not desc:
                continue
            out.append({
                "item": desc,
                "evidencia_antiga": ev_ant if isinstance(ev_ant, str) else None,
                "evidencia_nova": ev_nov if isinstance(ev_nov, str) else None,
            })
        return out

    narrativa['melhorias'] = _normalizar(narrativa.get('melhorias'), 8)
    narrativa['piorou'] = _normalizar(narrativa.get('piorou'), 8)

    for campo in ('resumo', 'recomendacao_proxima'):
        v = narrativa.get(campo)
        narrativa[campo] = v.strip() if isinstance(v, str) else ""

    return narrativa

@router.post('/api/cv/semantic-fit')
@limiter.limit("10/minute")
async def cv_semantic_fit(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file: UploadFile = File(...),
    job_description: str = Form(""),
    area: str = Form(""),
):
    """Fit semântico CV × vaga via LLM: extrai os requisitos de verdade da
    descrição (obrigatórios + diferenciais), cruza com o CV por semântica
    (aceita alias) com evidência literal e devolve reescritas prontas (XYZ).
    Pós-processamento zera evidências que não existem no texto extraído."""
    if len(job_description.strip()) < 40:
        raise HTTPException(status_code=400, detail="Cole a descrição completa da vaga (mín. 40 caracteres).")

    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    ext = os.path.splitext(cv_file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

    # Resolve credenciais e client LLM (provider_id → TRIVOR_IAS → OPENAI_API_KEY → provider salvo)
    client, key, selected_model, _ = _resolve_key_and_client(provider_id, api_key, api_url, model_name)
    if client is None:
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvfitsem_')
    extractor_used = "none"
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, extractor_used, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if CV_FIT_PROMPT_FILE.exists():
        with open(CV_FIT_PROMPT_FILE, encoding='utf-8') as f:
            sys_prompt = f.read()
    else:
        sys_prompt = ("Você é um consultor sênior de recrutamento. Compare o currículo com a "
                      "descrição da vaga e retorne o JSON exato especificado. NUNCA invente "
                      "requisitos nem evidências: toda citação do currículo deve existir "
                      "literalmente no texto fornecido.")

    user_content = f"""DESCRIÇÃO COMPLETA DA VAGA:
---
{job_description.strip()}
---

CURRÍCULO DO CANDIDATO (texto extraído, Markdown):
---
{cv_text}
---

ÁREA DO CANDIDATO: {area.strip() if area and area.strip() else 'Não especificada (analise de forma genérica, não assuma tecnologia)'}

Compare os dois textos seguindo rigorosamente o prompt de sistema e retorne o JSON exato."""

    try:
        start_time = time.time()
        response = await run_in_threadpool(client.chat.completions.create,
            model=selected_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = response.choices[0].message.content or ""
        fit = _parse_llm_json(raw_content)

        # Anti-alucinação: zera evidências/texto_atual que não existem no CV
        fit = _semantic_fit_validate(fit, cv_text)

        uso_tokens = None
        if hasattr(response, 'usage') and response.usage:
            uso_tokens = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }

        reqs_list = fit.get('requisitos') if isinstance(fit.get('requisitos'), list) else []
        sugg_list = fit.get('sugestoes_de_reescrita') if isinstance(fit.get('sugestoes_de_reescrita'), list) else []
        log_request(
            endpoint="/api/cv/semantic-fit",
            method="POST",
            status_code=200,
            duration_ms=int(response_time_ms),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            response_summary=json.dumps(
                {"requisitos": len(reqs_list), "sugestoes": len(sugg_list)},
                ensure_ascii=False,
            ),
            extracted_text=(cv_text[:5000] if cv_text else ""),
        )

        result: dict = {"analise": fit, "extractor_used": extractor_used}
        if uso_tokens:
            result["uso_tokens"] = uso_tokens
        result["api_info"] = {
            "model": selected_model,
            "request_id": str(getattr(response, 'id', None) or uuid.uuid4()),
            "response_time_ms": int(response_time_ms),
        }
        return result

    except Exception as e:
        logger.error(f"[SEMANTIC-FIT] Erro na chamada LLM: {e}")
        log_request(
            endpoint="/api/cv/semantic-fit",
            method="POST",
            status_code=500,
            duration_ms=int((time.time() - t0) * 1000),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Erro ao gerar o fit semântico. Verifique a chave de API e tente novamente.")


@router.post('/api/cv/recruiter-sim')
@limiter.limit("10/minute")
async def cv_recruiter_sim(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file: UploadFile = File(...),
    job_description: str = Form(""),
    target_role: str = Form(""),
    area: str = Form(""),
):
    """Simulador de recrutador CV × vaga via LLM: a LLM faz o papel de um
    recrutador experiente da área, lê o CV contra a descrição da vaga e
    devolve veredito honesto (aprovado/duvida/reprovado), confiança 0-10,
    motivos, sinais vermelhos e as 3 perguntas que faria na entrevista.
    Pós-processo normaliza o JSON sem confiar na saída bruta da LLM."""
    if len(job_description.strip()) < 40:
        raise HTTPException(status_code=400, detail="Cole a descrição completa da vaga (mín. 40 caracteres).")

    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    ext = os.path.splitext(cv_file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

    # Resolve credenciais e client LLM (mesmo padrão dos demais endpoints CV)
    client, key, selected_model, _ = _resolve_key_and_client(provider_id, api_key, api_url, model_name)
    if client is None:
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvrecruit_')
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, _, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if RECRUITER_PROMPT_FILE.exists():
        with open(RECRUITER_PROMPT_FILE, encoding='utf-8') as f:
            sys_prompt = f.read()
    else:
        sys_prompt = ("Você é um recrutador experiente. Leia a descrição da vaga e o "
                      "currículo e retorne o JSON exato especificado. NUNCA invente "
                      "lacunas que não existem no currículo: todo apontamento deve "
                      "citar um trecho do texto fornecido.")

    user_content = f"""DESCRIÇÃO COMPLETA DA VAGA:
---
{job_description.strip()}
---

CARGO ALVO: {target_role.strip() if target_role and target_role.strip() else 'Não especificado'}

CURRÍCULO DO CANDIDATO (texto extraído, Markdown):
---
{cv_text}
---

ÁREA DO CANDIDATO: {area.strip() if area and area.strip() else 'Não especificada (analise de forma genérica, não assuma que o candidato é dev)'}

Execute a simulação seguindo rigorosamente o prompt de sistema e retorne o JSON exato."""

    try:
        start_time = time.time()
        response = await run_in_threadpool(client.chat.completions.create,
            model=selected_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = response.choices[0].message.content or ""
        sim = _parse_llm_json(raw_content)

        # Normalização: não confiar no JSON bruto da LLM
        sim = _recruiter_sim_validate(sim)

        uso_tokens = None
        if hasattr(response, 'usage') and response.usage:
            uso_tokens = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }

        log_request(
            endpoint="/api/cv/recruiter-sim",
            method="POST",
            status_code=200,
            duration_ms=int(response_time_ms),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            response_summary=json.dumps(
                {"veredito": sim.get('veredito'), "confianca": sim.get('confianca')},
                ensure_ascii=False,
            ),
            extracted_text=(cv_text[:5000] if cv_text else ""),
        )

        result: dict = {"analise": sim}
        if uso_tokens:
            result["uso_tokens"] = uso_tokens
        result["api_info"] = {
            "model": selected_model,
            "request_id": str(getattr(response, 'id', None) or uuid.uuid4()),
            "response_time_ms": int(response_time_ms),
        }
        return result

    except Exception as e:
        logger.error(f"[RECRUITER-SIM] Erro na chamada LLM: {e}")
        log_request(
            endpoint="/api/cv/recruiter-sim",
            method="POST",
            status_code=500,
            duration_ms=int((time.time() - t0) * 1000),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Erro ao rodar a simulação do recrutador. Verifique a chave de API e tente novamente.")


# ---------------------------------------------------------------------------
# Geração de Cover Letter CV × Vaga (LLM) — carta pronta a partir do CV + vaga
# ---------------------------------------------------------------------------

_COVER_LETTER_FORMATS = {'completa', 'curta'}


def _cover_letter_validate(carta: dict, cv_text: str, formato_solicitado: str) -> dict:
    """Pós-processo da cover letter: normaliza o JSON da LLM e aplica a
    auditoria anti-alucinação — cada `fatos_usados` precisa ocorrer no
    texto extraído do CV; os ausentes são descartados (com log). Retorna
    o mesmo dict."""
    if not isinstance(carta, dict):
        carta = {}

    texto = carta.get('texto')
    carta['texto'] = texto if isinstance(texto, str) else ""

    formato = carta.get('formato')
    if not isinstance(formato, str) or formato.strip().lower() not in _COVER_LETTER_FORMATS:
        formato = formato_solicitado
    carta['formato'] = formato.strip().lower()

    brutos = carta.get('fatos_usados')
    brutos = brutos if isinstance(brutos, list) else []
    validos = [f for f in brutos if isinstance(f, str) and f.strip()]
    dedupados = _dedupe_keep_order(validos)
    mantidos = []
    descartados = []
    for fato in dedupados:
        if _semantic_fit_evidence_valid(fato, cv_text):
            mantidos.append(fato)
        else:
            descartados.append(fato)
    if descartados:
        logger.info(f"[COVER-LETTER] fatos_usados descartados (não ocorrem no CV): {descartados}")
    carta['fatos_usados'] = mantidos

    return carta


@router.post('/api/cv/cover-letter')
@limiter.limit("10/minute")
async def cv_cover_letter(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file: UploadFile = File(...),
    job_description: str = Form(""),
    target_role: str = Form(""),
    formato: str = Form("completa"),
):
    """Geração de cover letter CV × vaga via LLM: escreve a carta no formato
    solicitado (curta = 2 parágrafos, completa = 5) usando SOMENTE fatos do
    CV ou afirmações genéricas. Pós-processo descarta `fatos_usados` que
    não ocorrem no texto extraído (auditoria anti-alucinação)."""
    if len(job_description.strip()) < 40:
        raise HTTPException(status_code=400, detail="Cole a descrição completa da vaga (mín. 40 caracteres).")

    formato_norm = formato.strip().lower() if isinstance(formato, str) else ""
    if formato_norm not in _COVER_LETTER_FORMATS:
        raise HTTPException(status_code=400, detail="Formato inválido. Use 'completa' ou 'curta'.")

    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    ext = os.path.splitext(cv_file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

    # Resolve credenciais e client LLM (mesmo padrão dos demais endpoints CV)
    client, key, selected_model, _ = _resolve_key_and_client(provider_id, api_key, api_url, model_name)
    if client is None:
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvcover_')
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, _, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if COVER_LETTER_PROMPT_FILE.exists():
        with open(COVER_LETTER_PROMPT_FILE, encoding='utf-8') as f:
            sys_prompt = f.read()
    else:
        sys_prompt = ("Você escreve cartas de apresentação profissionais, em PT-BR, "
                      "com tom simpático. Use SOMENTE fatos do currículo fornecido ou "
                      "afirmações genéricas; NUNCA invente empresa, cargo, métrica ou "
                      "formação. Retorne o JSON exato especificado.")

    user_content = f"""DESCRIÇÃO COMPLETA DA VAGA:
---
{job_description.strip()}
---

CARGO ALVO: {target_role.strip() if target_role and target_role.strip() else 'Não especificado'}

FORMATO SOLICITADO DA CARTA: {formato_norm}

CURRÍCULO DO CANDIDATO (texto extraído, Markdown):
---
{cv_text}
---

Escreva a cover letter seguindo rigorosamente o prompt de sistema e retorne o JSON exato."""

    try:
        start_time = time.time()
        response = await run_in_threadpool(client.chat.completions.create,
            model=selected_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = response.choices[0].message.content or ""
        carta = _parse_llm_json(raw_content)

        # Normalização + auditoria anti-alucinação (fatos ausentes no CV saem)
        carta = _cover_letter_validate(carta, cv_text, formato_norm)

        uso_tokens = None
        if hasattr(response, 'usage') and response.usage:
            uso_tokens = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }

        log_request(
            endpoint="/api/cv/cover-letter",
            method="POST",
            status_code=200,
            duration_ms=int(response_time_ms),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            response_summary=json.dumps(
                {"formato": carta.get('formato'), "fatos_usados": len(carta.get('fatos_usados', []))},
                ensure_ascii=False,
            ),
            extracted_text=(cv_text[:5000] if cv_text else ""),
        )

        result: dict = {"carta": carta}
        if uso_tokens:
            result["uso_tokens"] = uso_tokens
        result["api_info"] = {
            "model": selected_model,
            "request_id": str(getattr(response, 'id', None) or uuid.uuid4()),
            "response_time_ms": int(response_time_ms),
        }
        return result

    except Exception as e:
        logger.error(f"[COVER-LETTER] Erro na chamada LLM: {e}")
        log_request(
            endpoint="/api/cv/cover-letter",
            method="POST",
            status_code=500,
            duration_ms=int((time.time() - t0) * 1000),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Erro ao gerar a cover letter. Verifique a chave de API e tente novamente.")


@router.post('/api/cv/diff')
@limiter.limit("10/minute")
async def cv_diff(
    request: Request,
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file_novo: UploadFile = File(None),
    cv_file_anterior: UploadFile = File(None),
    area: str = Form(""),
):
    """Compara duas versões do currículo: diff determinístico (bullets da
    seção de experiência, métricas numéricas, termos-chave que entraram ou
    saíram) + narrativa LLM do que melhorou/piorou. Pós-processo zera
    evidências que não existem no texto da versão citada."""
    if cv_file_novo is None or cv_file_anterior is None:
        raise HTTPException(
            status_code=400,
            detail="Envie os dois arquivos: a versão anterior (cv_file_anterior) e a versão nova (cv_file_novo) do currículo.",
        )

    async def _validar_upload(uf: UploadFile, rotulo: str):
        content = await uf.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"Arquivo {rotulo} vazio.")
        ext = os.path.splitext(uf.filename or "")[1].lower()
        if ext not in _ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado ({rotulo}). Use {_SUPPORTED_EXTS_MSG}.")
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Arquivo {rotulo} excede 10MB.")
        return content, ext

    content_novo, ext_novo = await _validar_upload(cv_file_novo, "novo")
    content_anterior, ext_anterior = await _validar_upload(cv_file_anterior, "anterior")

    async def _extrair(content: bytes, ext: str, prefixo: str, rotulo: str) -> tuple:
        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix=prefixo)
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)
            texto, extractor_used, _ = await run_in_threadpool(_extract_cv_text, temp_path, ext)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        if not texto or not texto.strip():
            raise HTTPException(status_code=400, detail=f"Não foi possível extrair texto do arquivo {rotulo}. Tente outro PDF ou um .docx.")
        return texto, extractor_used

    texto_novo, extractor_novo = await _extrair(content_novo, ext_novo, 'cvdiffnovo_', "novo")
    texto_anterior, extractor_anterior = await _extrair(content_anterior, ext_anterior, 'cvdiffant_', "anterior")

    # Diferença determinística não depende de LLM — calculada antes de tudo
    deterministico = _diff_cv_deterministic(texto_anterior, texto_novo)

    # Resolve credenciais e client LLM (mesmo padrão dos demais endpoints CV)
    client, key, selected_model, _ = _resolve_key_and_client(provider_id, api_key, api_url, model_name)
    if client is None:
        raise HTTPException(status_code=400, detail="Chave de API não fornecida.")

    t0 = time.time()

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if CV_DIFF_PROMPT_FILE.exists():
        with open(CV_DIFF_PROMPT_FILE, encoding='utf-8') as f:
            sys_prompt = f.read()
    else:
        sys_prompt = ("Você compara duas versões do currículo de um candidato, em PT-BR, "
                      "e devolve JSON exato. NUNCA invente conteúdo: toda citação deve "
                      "existir literalmente na versão referida; evidências que não existem "
                      "ficam null.")

    user_content = f"""VERSÃO ANTIGUA DO CURRÍCULO (texto extraído, Markdown):
---
{texto_anterior}
---

VERSÃO NOVA DO CURRÍCULO (texto extraído, Markdown):
---
{texto_novo}
---

ÁREA DO CANDIDATO: {area.strip() if area and area.strip() else 'Não especificada (analise de forma genérica, não assuma tecnologia)'}

Compare as duas versões seguindo rigorosamente o prompt de sistema e retorne o JSON exato."""

    try:
        start_time = time.time()
        response = await run_in_threadpool(client.chat.completions.create,
            model=selected_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        response_time_ms = (time.time() - start_time) * 1000

        raw_content = response.choices[0].message.content or ""
        narrativa = _parse_llm_json(raw_content)

        # Anti-alucinação: zera evidências que não existem na versão citada
        narrativa = _diff_cv_validate(narrativa, texto_anterior, texto_novo)

        uso_tokens = None
        if hasattr(response, 'usage') and response.usage:
            uso_tokens = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
            }

        log_request(
            endpoint="/api/cv/diff",
            method="POST",
            status_code=200,
            duration_ms=int(response_time_ms),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            response_summary=json.dumps(
                {
                    "melhorias": len(narrativa.get('melhorias', [])),
                    "piorou": len(narrativa.get('piorou', [])),
                    "termos_adicionados": len(deterministico['termos_adicionados']),
                },
                ensure_ascii=False,
            ),
            extracted_text=(texto_novo[:2500] + "\n---VERSÃO ANTIGA---\n" + texto_anterior[:2500]),
        )

        result: dict = {
            "narrativa": narrativa,
            "deterministico": deterministico,
            "extractor_used": {"novo": extractor_novo, "anterior": extractor_anterior},
        }
        if uso_tokens:
            result["uso_tokens"] = uso_tokens
        result["api_info"] = {
            "model": selected_model,
            "request_id": str(getattr(response, 'id', None) or uuid.uuid4()),
            "response_time_ms": int(response_time_ms),
        }
        return result

    except Exception as e:
        logger.error(f"[CV-DIFF] Erro na chamada LLM: {e}")
        log_request(
            endpoint="/api/cv/diff",
            method="POST",
            status_code=500,
            duration_ms=int((time.time() - t0) * 1000),
            model=selected_model,
            api_key_preview=_mask_key_preview(key),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Erro ao comparar as versões do currículo. Verifique a chave de API e tente novamente.")
