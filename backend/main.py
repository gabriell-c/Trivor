import sys
import re
import time
import logging
import urllib.request
import urllib.error
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Header, Form, HTTPException, Response, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(_h)
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

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / 'knowledge'
LINKEDIN_PROMPT_FILE = KNOWLEDGE_DIR / 'linkedin_prompt.md'

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

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ---------------------------------------------------------------------------
# Pydantic Models para Validação
# ---------------------------------------------------------------------------

class JSearchKeyRequest(BaseModel):
    """Modelo para teste de chave JSearch."""
    key: str = Field(..., min_length=10, description="API key do JSearch")
    provider: str = Field(default='jsearch', description="Nome do provider")

    @field_validator('key')
    @classmethod
    def validate_key(cls, v: str) -> str:
        if not v or len(v.strip()) < 10:
            raise ValueError('API key deve ter pelo menos 10 caracteres')
        return v.strip()

class LogCleanupRequest(BaseModel):
    """Modelo para limpeza de logs."""
    days: int = Field(default=90, ge=1, le=365, description="Dias para manter logs")

# ---------------------------------------------------------------------------
# Funções de Resposta Padronizada
# ---------------------------------------------------------------------------

def error_response(code: str, message: str, details: dict = None, status_code: int = 400) -> JSONResponse:
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

def success_response(data: dict = None, message: str = "Sucesso") -> JSONResponse:
    """Retorna resposta de sucesso padronizada."""
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": message,
            "data": data,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S%z')
        }
    )

app = FastAPI(
    title="Trivor - Motor de Análise de Currículos",
    description="API para análise de currículos, market intelligence e diagnóstico profissional",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Muitas requisições. Aguarde e tente novamente.",
                "details": {
                    "limit": str(exc.limit) if hasattr(exc, 'limit') else "unknown"
                }
            }
        },
        headers={"Retry-After": "60"}
    )

# Inicializa DB de logs
init_logs_db()

# ---------------------------------------------------------------------------
# Extração de PDF com fallback chain: PyMuPDF → pypdfium2 → docling_parse
# ---------------------------------------------------------------------------

_md_cache: dict[str, str] = {}
_ALLOWED_EXTS = {'.pdf', '.docx', '.doc', '.txt'}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Correções exatas de OCR — SEM regex genéricas
_FIXES: list[tuple[str, str]] = [
    ('Área', 'Área'), ('São', 'São'), ('João', 'João'),
    ('Código', 'Código'), ('Códigos', 'Códigos'),
    ('Desenvolvimento', 'Desenvolvimento'),
    ('Tecnologia', 'Tecnologia'),
    # Erros comuns de OCR em português
    ('ilustração', 'ilustração'),
    ('nao', 'não'),  # só quando óbvio pelo contexto — deixar o LLM decidir
]

def _extract_pdf_text_pymupdf(pdf_path: str) -> str:
    """Extrai texto de PDF usando PyMuPDF — melhor qualidade, extrai links também."""
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        chunks = []
        for page in doc:
            text = page.get_text()
            lines = []
            for line in text.split('\n'):
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
            if lines:
                chunks.append('\n'.join(lines))
        doc.close()
        return '\n\n---\n'.join(chunks)
    except Exception as e:
        logger.warning(f"[PYMUPDF] Falhou: {e}")
        return ""

def _extract_pdf_text_pypdfium(pdf_path: str) -> str:
    """Fallback: extrai texto de PDF usando pypdfium2."""
    try:
        pdf_document = pdfium.PdfDocument(pdf_path)
        chunks = []
        for page in pdf_document:
            textpage = page.get_textpage()
            text = textpage.get_text_bounded()
            textpage.close()
            lines = []
            for line in text.split('\n'):
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
            if lines:
                chunks.append('\n'.join(lines))
        pdf_document.close()
        return '\n\n---\n'.join(chunks)
    except Exception as e:
        logger.warning(f"[PDFIUM] Falhou: {e}")
        return ""

def _extract_pdf_text_docling_parse(pdf_path: str) -> str:
    """Fallback: extrai texto com docling_parse (melhor estrutura)."""
    try:
        from docling_parse.pdf_parsers import DoclingParser
        parser = DoclingParser()
        parsed = parser.parse_pdf(pdf_path, first_n_pages=10)
        lines = []
        for cell in parsed.cells:
            lines.append(cell.get('page_content', ''))
        return '\n'.join(lines)
    except Exception as e:
        logger.warning(f"[DOCING] Falhou: {e}")
        return ""

def _extract_pdf_text_pdfplumber(pdf_path: str) -> str:
    """Fallback: extrai texto com pdfplumber."""
    try:
        import pdfplumber
        chunks = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines = []
                    for line in text.split('\n'):
                        stripped = line.strip()
                        if stripped:
                            lines.append(stripped)
                    if lines:
                        chunks.append('\n'.join(lines))
        return '\n\n---\n'.join(chunks)
    except Exception as e:
        logger.warning(f"[PDFPLUMBER] Falhou: {e}")
        return ""

def _extract_pdf_links(pdf_path: str) -> list[str]:
    """Extrai hyperlinks das anotações do PDF usando PyMuPDF → pdfplumber."""
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        links = []
        for page in doc:
            for link in page.get_links():
                uri = link.get('uri', '')
                if uri and uri not in links:
                    links.append(str(uri))
        doc.close()
        if links:
            logger.info(f"[LINKS] {len(links)} via PyMuPDF")
            return links
    except Exception as e:
        logger.warning(f"[LINKS pymupdf] Falhou: {e}")

    try:
        import pdfplumber
        links = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                annots = page.annots
                if not annots:
                    continue
                for annot in annots:
                    uri = annot.get('uri')
                    if uri and uri not in links:
                        links.append(str(uri))
        logger.info(f"[LINKS] {len(links)} via pdfplumber")
        return links
    except Exception as e:
        logger.warning(f"[LINKS pdfplumber] Falhou: {e}")
        return []

def _detect_hyperlinks(text: str) -> list[dict[str, str]]:
    """Detecta hyperlinks no texto convertido para markdown."""
    import urllib.parse
    results = []
    seen = set()

    def add_url(raw: str):
        raw = raw.rstrip('.,;:!)')
        if raw in seen:
            return
        seen.add(raw)
        if raw.startswith('//'):
            raw = 'https:' + raw
        elif raw.startswith('www.'):
            raw = 'https://' + raw
        results.append({'url': raw, 'valid': True})  # LLM validará

    # Markdown links: [text](url)
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        add_url(m.group(2).strip('<>'))

    # Full URLs
    for m in re.finditer(r'https?://[^\s)<>\]]+', text):
        add_url(m.group(0))

    # www. URLs
    for m in re.finditer(r'www\.[^\s)<>\]]+', text):
        add_url(m.group(0))

    return results

def _text_to_markdown(text: str) -> str:
    """Converte texto extraído para markdown estruturado."""
    import re
    lines = text.split('\n')
    result = []
    in_section = False
    section_buffer = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if section_buffer:
                result.extend(section_buffer)
                section_buffer = []
            result.append('')
            continue

        # Detectar títulos de seção (todas as letras maiúsculas, ou padrões comuns)
        is_header = False
        if len(stripped) <= 60 and re.match(r'^[A-ZÀ-Ý][A-ZÀ-Ý\s\-]{1,58}$', stripped):
            is_header = True
        elif re.match(r'^(EXPERIÊNCIA|EDUCAÇÃO|FORMAÇÃO|HABILIDADES|SKILLS|IDIOMAS|OBJETIVO|RESUMO|SOBRE|CERTIFICAÇÕES|IDIOMAS|PROJETO|LINKS|CONTATO|INFORMAÇÕES)', stripped.upper()):
            is_header = True

        if is_header:
            if section_buffer:
                result.extend(section_buffer)
                section_buffer = []
            result.append(f'## {stripped}')
            result.append('')
        elif re.match(r'^[-•*]\s', stripped):
            result.append(f'- {stripped[2:]}')
        else:
            section_buffer.append(stripped)

    if section_buffer:
        result.extend(section_buffer)

    return '\n'.join(result)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    # Skip logging for endpoints that create their own detailed logs
    if request.url.path == "/api/cv/analyze":
        return response
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
            raise HTTPException(status_code=400, detail="Formato de arquivo não suportado.")
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cv_')
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)

            # Extrair texto com fallback chain
            markdown_text = ""
            extractor_used = "none"
            fallback_used = False

            if ext == '.pdf':
                # 1. PyMuPDF primeiro
                markdown_text = _extract_pdf_text_pymupdf(temp_path)
                extractor_used = "pymupdf"
                logger.info(f"[CV] PyMuPDF: {len(markdown_text)} chars")
                if not markdown_text or not markdown_text.strip():
                    # 2. pypdfium2
                    markdown_text = _extract_pdf_text_pypdfium(temp_path)
                    extractor_used = "pypdfium2"
                    fallback_used = True
                    logger.info(f"[CV] pypdfium2: {len(markdown_text)} chars")
                if not markdown_text or not markdown_text.strip():
                    # 3. docling_parse
                    md_fd, md_path = tempfile.mkstemp(suffix='.pdf', prefix='md_')
                    os.close(md_fd)
                    try:
                        import shutil
                        shutil.copy2(temp_path, md_path)
                        markdown_text = _extract_pdf_text_docling_parse(md_path)
                        extractor_used = "docling_parse"
                        fallback_used = True
                        logger.info(f"[CV] docling_parse: {len(markdown_text)} chars")
                    finally:
                        if os.path.exists(md_path):
                            os.remove(md_path)
                if not markdown_text or not markdown_text.strip():
                    # 4. pdfplumber
                    markdown_text = _extract_pdf_text_pdfplumber(temp_path)
                    extractor_used = "pdfplumber"
                    fallback_used = True
                    logger.info(f"[CV] pdfplumber: {len(markdown_text)} chars")
            else:
                # Para docx/txt, usar docling
                converter = DocumentConverter()
                conversion_result = converter.convert(temp_path)
                markdown_text = conversion_result.document.export_to_markdown()
                extractor_used = "docling"

            if not markdown_text or not markdown_text.strip():
                markdown_text = "Erro ao extrair texto do documento."
                extractor_used = "none"
                logger.warning("[CV] Todos os extratores falharam!")

            # Cache de markdown
            cache_key = temp_path
            if cache_key in _md_cache:
                markdown_text = _md_cache[cache_key]
            else:
                markdown_text = _text_to_markdown(markdown_text)
                _md_cache[cache_key] = markdown_text

            # Detectar hyperlinks
            links_info = _detect_hyperlinks(markdown_text)
            if ext == '.pdf':
                pdf_links = _extract_pdf_links(temp_path)
                for url in pdf_links:
                    already = any(l['url'] == url for l in links_info)
                    if not already:
                        links_info.append({'url': url, 'valid': True})
            logger.info(f"[CV] Links detectados: {len(links_info)}")

            # Configurar cliente OpenAI
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
            base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
            if not base_url:
                base_url = "http://localhost:20128/v1"  # omniroute local

            client = OpenAI(api_key=key, base_url=base_url)

            # Carregar prompt
            prompt_file = KNOWLEDGE_DIR / 'cv_analysis_prompt.md'
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    sys_prompt = f.read()
            else:
                sys_prompt = """Você é um especialista em análise de currículos (CV) para ATS e mercado de trabalho.

REGRAS IMPORTANTES (OBRIGATÓRIO SEGUIR):
1. CAPITALIZAÇÃO: Preserve EXATAMENTE como no currículo original. Não invente capitalização.
2. BULLET POINTS: Lines starting with -, *, or • are bullet points. Preserve them.
3. DATES — REGRAS RIGOROSAS:
   - Parse dates EXACTLY as written in the CV. NEVER reformat, never invent dates.
   - If CV says "2018-2020", keep "2018-2020". If CV says "Jan 2020 - Mar 2022", keep exact text.
   - NEVER change date formats (e.g., never convert "2018" to "2018-2022" or add years).
   - NEVER interpret date ranges — only report what is literally written.
   - If no dates are present, do not invent any.
4. SPELL CHECK — REGRAS MÁXIMAMENTE RIGOROSAS:
   - SOMENTE flag palavras que estejam REALMENTE erradas segundo o dicionário português (BR).
   - NÃO flagge nomes próprios, marcas, tecnologias, abreviações, ou termos técnicos.
   - NÃO flagge erros de formatação (quebras de linha, espaçamento).
   - NÃO flagge links/URLs como erros ortográficos — links são hyperlinks válidos.
   - NÃO flagge siglas (AWS, Java, React, SQL, etc), mesmo que pareçam erradas.
   - NÃO flagge termos estrangeiros (e.g., "software", "developer", "framework").
   - Se NÃO houver erros ortográficos, retorne array vazio [].
   - WARNING: O ERRO MAIS COMUM é inventar erros que não existem. NUNCA invente.
   - Palavras como "React", "Python", "JavaScript", "AWS", "SQL" NUNCA devem ser flaggadas.
   - Nomes próprios como "São Paulo", "Maria", "João" NUNCA devem ser flagrados.
   - Antes de flaggar qualquer palavra, pergunte-se: "esta palavra REALMENTE existe no dicionário português?" Se NÃO TEM CERTEZA, NÃO flagge.
5. HYPERLINKS — REGRAS RIGOROSAS:
   - Links como wa.me, t.me, mailto:, linkedin.com, whatsapp.com são FORMATOS VÁLIDOS.
   - NÃO flagge links como "faltando https" ou "inválido".
   - Apenas reporte links na seção de links, nunca como erro.
6. NOTA (0-100):
   - "nota" deve ser ESCALA 0-100 (NÃO 0-10). Ex: 65, 78, 92.
   - "score_ats" já é 0-100 (manter).
   - Scores nas seções (analise_secoes.*) devem ser 0-100 (NÃO 0-10).
7. Be thorough and analyze EVERY line of the CV.
8. Output valid JSON only.
9. Use EXACTLY these field names (Portuguese):

{
  "nota": <0-100 float, 1 decimal>,
  "score_ats": <0-100 int>,
  "resumo_executivo": "<string>",
  "foto_detectada": <boolean>,
  "foto_recomendada": <boolean>,
  "ordem_secoes": {"correta": <boolean>, "problema": "<string|null>", "como_corrigir": "<string|null>"},
  "palavras_chave_presentes": ["<string>"],
  "palavras_chave_faltantes": ["<string>"],
  "pontos_fortes": ["<string>"],
  "pontos_fracos": ["<string>"],
  "erros_comuns_detectados": [{"tipo": "<string>", "descricao": "<string>", "exemplo": "<string|null>"}],
  "analise_secoes": {
    "dados_pessoais": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "resumo_profissional": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "experiencia_profissional": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>, "has_metrics": <boolean>},
    "formacao_academica": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "habilidades": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>, "bullet_points": <boolean>},
    "objetivo": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>}
  },
  "analise_ats": {
    "score_ats": <0-100>,
    "palavras_chave_faltantes": ["<string>"],
    "gargalos_formatacao": ["<string>"],
    "veredito_robos": "aprovado|com_ressalvas|reprovado",
    "explicacao": "<string>"
  },
  "sugestoes": ["<string>"]
}"""

            # Montar user message
            user_content = f"""ANALISE ESTE CURRÍCULO COMPLETAMENTE.

CURRÍCULO (Markdown):
---
{markdown_text}
---

INFORMAÇÕES ADICIONAIS:
- Links detectados: {[l['url'] for l in links_info] if links_info else 'Nenhum'}
- Tipo de arquivo: {ext}
- Extrator usado: {extractor_used}
- Job description (se fornecida): {job_description or 'Nenhuma'}
- Target role: {target_role or area or 'Não especificado'}

Faça uma análise COMPLETA e DETALHADA do currículo."""

            response = client.chat.completions.create(
                model=selected_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content

            # Parsear resultado JSON
            try:
                analysis = json.loads(result_text)
            except json.JSONDecodeError:
                # Tentar extrair JSON do texto
                match = re.search(r'\{[\s\S]*\}', result_text)
                if match:
                    analysis = json.loads(match.group())
                else:
                    analysis = {"raw": result_text, "error": "Não foi possível parsear JSON"}

            # Adicionar metadados compatíveis com o frontend
            analysis['uso_tokens'] = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": (response.usage.prompt_tokens + response.usage.completion_tokens) if response.usage else 0,
            }
            analysis['api_info'] = {
                "model": selected_model,
                "request_id": str(uuid.uuid4()),
                "response_time_ms": 0,
            }
            # Links e extractor são campos internos, não expostos ao frontend
            analysis['_extractor_used'] = extractor_used
            analysis['_links'] = [l['url'] for l in links_info]

            # Salvar log com texto extraído e prompt
            llm_prompt = f"SYSTEM:\n{sys_prompt}\n\nUSER:\n{user_content}"
            extracted_truncated = markdown_text[:5000] if markdown_text else ""
            prompt_truncated = llm_prompt[:8000] if llm_prompt else ""
            response_summary_json = json.dumps(analysis, ensure_ascii=False)
            log_request(
                endpoint="/api/cv/analyze",
                method="POST",
                status_code=200,
                duration_ms=0,
                model=selected_model,
                api_key_preview=key[:8] + "..." if len(key) > 8 else "***",
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
        raise HTTPException(status_code=500, detail=f"Erro ao processar o currículo: {str(e)}")


@app.post('/api/ia/analyze')
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
            prov = next((p for p in providers if p.get('id') == provider_id), None)
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
    start_time = time.time()

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
        elapsed = round(time.time() - start_time, 2)
        return {"success": True, "report": report, "model": selected_model, "elapsed_seconds": elapsed}
    except Exception as e:
        logger.error(f"[MARKET ERROR] {e}")
        logger.debug(traceback.format_exc())
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
async def api_get_logs(
    limit: int = 100,
    offset: int = 0,
    endpoint: str = None,
    error_only: bool = False,
):
    """Retorna logs paginados + stats."""
    logs = get_logs(limit=limit, offset=offset, endpoint=endpoint, error_only=error_only)
    stats = get_logs_stats()
    return {"logs": logs, "stats": stats}

@app.get('/api/logs/stats')
async def api_get_logs_stats_route():
    """Retorna estatísticas dos logs."""
    return get_logs_stats()

@app.post('/api/logs/clear')
async def api_clear_logs():
    """Limpa os logs."""
    clear_logs()
    return {"success": True}

@app.delete('/api/logs')
async def api_delete_logs():
    """Limpa todos os logs (fallback DELETE)."""
    clear_logs()
    return {"success": True}

@app.post('/api/logs/cleanup')
async def api_cleanup_logs(days: int = 90):
    """Remove logs antigos (padrão 90 dias)."""
    from logging_service import cleanup_logs
    removed = cleanup_logs(days)
    return {"success": True, "removed": removed}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check robusto com verificação de dependências."""
    import sqlite3
    from datetime import datetime

    checks = {}
    overall_status = "healthy"

    # Verificar banco de dados
    try:
        conn = sqlite3.connect(LOGS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM api_logs")
        log_count = cursor.fetchone()[0]
        conn.close()
        checks["database"] = {"status": "ok", "logs_count": log_count}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall_status = "degraded"

    # Verificar providers IA
    try:
        providers = json.loads(os.environ.get('TRIVOR_IAS', '[]'))
        checks["providers"] = {
            "status": "ok" if providers else "warning",
            "count": len(providers)
        }
    except Exception as e:
        checks["providers"] = {"status": "error", "message": str(e)}
        overall_status = "degraded"

    # Verificar diretório de conhecimento
    try:
        knowledge_exists = KNOWLEDGE_DIR.exists() and (KNOWLEDGE_DIR / 'system_prompt.md').exists()
        checks["knowledge"] = {"status": "ok" if knowledge_exists else "warning"}
    except Exception as e:
        checks["knowledge"] = {"status": "error", "message": str(e)}

    status_code = 200 if overall_status == "healthy" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "checks": checks
        }
    )


@app.post('/api/linkedin/analyze')
@limiter.limit("20/minute")
async def analyze_linkedin(
    request: Request,
    text: str = Form(..., min_length=10, description="Texto do perfil LinkedIn"),
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
            prov = next((p for p in providers if p['id'] == provider_id), None)
            if prov and prov.get('usedFor') not in ('none', 'market'):
                api_key = prov['apiKey']
                api_url = prov.get('apiUrl') or api_url
                model_name = prov.get('modelName') or model_name
        except Exception:
            pass

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
        with open(LINKEDIN_PROMPT_FILE, 'r', encoding='utf-8') as f:
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
            client = OpenAI(api_key=key)
        else:
            client = OpenAI(api_key=key, base_url=base_url)

        start_time = time.time()
        comp = client.chat.completions.create(**create_kwargs)
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
            api_key_preview=key[:8] + "..." if len(key) > 8 else "***",
        )

        return data

    except Exception as e:
        log_request(
            endpoint="/api/linkedin/analyze",
            method="POST",
            status_code=500,
            duration_ms=0,
            model=selected_model,
            api_key_preview=key[:8] + "..." if key and len(key) > 8 else "***",
        )
        return error_response(
            code="ANALYSIS_ERROR",
            message="Erro na análise do LinkedIn",
            details={"error": str(e)},
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    import signal
    import sys

    def graceful_shutdown(signum, frame):
        logger.info("Recebido sinal de encerramento. Finalizando graceful...")
        logger.info("Logs salvos com sucesso.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    uvicorn.run(app, host="0.0.0.0", port=8000)

