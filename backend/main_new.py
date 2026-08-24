import sys
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Header, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from openai import OpenAI
import sqlite3, json, os, uuid

# Adiciona o diretório backend ao Python path para importar export_utils
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from export_utils import generate_markdown_export, generate_docx_export, generate_pdf_export
from market_export import generate_market_markdown_export, generate_market_docx_export, generate_market_pdf_export
from market_service import run_market_analysis, init_market_db
from logging_service import init_logs_db, log_request, get_logs, get_logs_stats, clear_logs, LOGS_DB

def _get_provider_for_tool(tool: str):
    """Retorna o melhor provider para uma ferramenta, ou None."""
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        if not providers:
            return None
        # Prioridade: all > tool-specific > qualquer outra
        for priority in ['all', tool]:
            for p in providers:
                if p.get('usedFor') == priority and p.get('apiKey'):
                    return p
        # fallback: qualquer um com apiKey
        for p in providers:
            if p.get('apiKey'):
                return p
        return None
    except Exception:
        return None

app = FastAPI(title="Trivor")

# Inicializa DB de logs
init_logs_db()


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    try:
        log_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
            model="",
            api_key_preview="",
        )
    except Exception:
        pass
    return response


# ---------------------------------------------------------------------------
# Endpoints de IA
# ---------------------------------------------------------------------------

@app.post('/api/cv/analyze')
async def analyze_cv(
    api_key: str = Form(None),
    api_url: str = Form(None),
    model_name: str = Form(None),
    provider_id: str = Form(None),
    cv_file: UploadFile = File(...),
    job_description: str = Form(""),
    target_role: str = Form("fullstack"),
):
    try:
        content = await cv_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")
        ext = os.path.splitext(cv_file.filename or "")[1].lower()
        if ext not in ('.pdf', '.docx', '.doc', '.txt'):
            raise HTTPException(status_code=400, detail="Formato de arquivo não suportado.")
        temp_path = f"/tmp/cv_{uuid.uuid4().hex}{ext}"
        with open(temp_path, "wb") as f:
            f.write(content)
        converter = DocumentConverter()
        conversion_result = converter.convert(temp_path)
        os.remove(temp_path)
        return conversion_result.document.export_to_markdown()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o currículo: {str(e)}")


@app.post('/api/ia/analyze')
async def analyze_ia(
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
        client = OpenAI(api_key=key, base_url=base_url)
        response = client.chat.completions.create(
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
        raise HTTPException(status_code=500, detail=f"Erro na análise de IA: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints de Mercado
# ---------------------------------------------------------------------------

@app.post('/api/market/analyze')
async def analyze_market(
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
            prov = next((p for p in providers if p['id'] == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'curriculo'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            pass

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

    DB_FILE = Path(__file__).parent / "market.db"

    try:
        client = OpenAI(api_key=key, base_url=base_url)
        report = run_market_analysis(
            db_file=DB_FILE,
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
        return {"success": True, "report": report}
    except Exception as e:
        import traceback
        print(f"[MARKET ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao processar inteligência de mercado: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints de Exportação
# ---------------------------------------------------------------------------

@app.post('/api/export')
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração do arquivo: {str(e)}")


@app.post('/api/export/market')
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração do arquivo: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints de Logs
# ---------------------------------------------------------------------------

@app.get('/api/jsearch/keys')
async def api_get_jsearch_keys():
    """Retorna todas as chaves JSearch com status e uso."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM jsearch_keys ORDER BY rowid')
    rows = cursor.fetchall()
    keys = []
    for r in rows:
        key_data = dict(r)
        # Calcula usado com base no remaining
        used = max(0, key_data['rate_limit_total'] - key_data['rate_limit_remaining']) if key_data['rate_limit_remaining'] is not None else None
        key_data['used'] = used
        keys.append(key_data)
    conn.close()
    return {"keys": keys}

@app.post('/api/jsearch/test')
async def api_test_jsearch_key(
    api_key: str = Form(...),
):
    """Testa uma chave JSearch e retorna status."""
    import urllib.request, json
    try:
        req = urllib.request.Request(
            'https://jsearch.p.rapidapi.com/jobs',
            headers={
                'X-RapidAPI-Key': api_key,
                'X-RapidAPI-Host': 'jsearch.p.rapidapi.com'
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return {
                "valid": True,
                "data": {
                    "rate_limit": data.get('x-ratelimit-limit', 'N/A'),
                    "rate_limit_remaining": data.get('x-ratelimit-remaining', 'N/A'),
                    "total_results": data.get('data', {}).get('total', 0)
                }
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}

@app.post('/api/jsearch/save-key')
async def api_save_jsearch_key(
    api_key: str = Form(...),
    description: str = Form(""),
):
    """Salva uma chave JSearch no DB."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO jsearch_keys (api_key, description, rate_limit_total, rate_limit_remaining, created_at) VALUES (?, ?, NULL, NULL, ?)",
            (api_key, description, datetime.now().isoformat())
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.delete('/api/jsearch/delete-key')
async def api_delete_jsearch_key(
    key_id: int = Form(...)
):
    """Remove uma chave JSearch do DB."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM jsearch_keys WHERE id = ?", (key_id,))
        conn.commit()
        return {"success": cursor.rowcount > 0}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Endpoints de Logs
# ---------------------------------------------------------------------------

@app.get('/api/logs')
async def api_get_logs():
    """Retorna os logs de requisições recentes."""
    return get_logs()

@app.get('/api/logs/stats')
async def api_get_logs_stats():
    """Retorna estatísticas dos logs."""
    return get_logs_stats()

@app.post('/api/logs/clear')
async def api_clear_logs():
    """Limpa os logs."""
    clear_logs()
    return {"success": True}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
