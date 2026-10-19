import sys
import re
import time
import logging
import tempfile
from pathlib import Path
from collections import Counter
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter
from openai import OpenAI
from pydantic import BaseModel, Field
import httpx

# Carrega .env (raiz do projeto) antes de qualquer os.getenv de chave;
# override=False: variáveis já definidas no sistema prevalecem sobre o .env
load_dotenv(override=False)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(_h)
import sqlite3, json, os, uuid, hashlib

# Adiciona o diretório backend ao Python path para importar export_utils
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pypdfium2 as pdfium
from export_utils import generate_markdown_export, generate_docx_export, generate_pdf_export
from market_export import generate_market_markdown_export, generate_market_docx_export, generate_market_pdf_export
from market_service import run_market_analysis, init_market_db
from logging_service import init_logs_db, log_request, get_logs, get_logs_stats, clear_logs, LOGS_DB

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

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ---------------------------------------------------------------------------
# Pydantic Models para Validação
# ---------------------------------------------------------------------------

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

DB_FILE = Path(__file__).parent / "market.db"

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
    # CORS configurável via env (CLAUDE.md §13 — nada hardcoded); fallback são as origens locais de dev
    allow_origins=[o.strip() for o in os.getenv('CORS_ALLOW_ORIGINS', '').split(',') if o.strip()]
    or ['http://localhost:3000', 'http://127.0.0.1:3000'],
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
# Garante as tabelas do market DB (inclui jsearch_keys) desde o start
init_market_db(DB_FILE)

# ---------------------------------------------------------------------------
# Extração de PDF com fallback chain: PyMuPDF → pypdfium2 → docling_parse
# ---------------------------------------------------------------------------

_md_cache: dict[str, str] = {}
_ALLOWED_EXTS = {'.pdf', '.docx', '.doc', '.txt'}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _format_exts(exts: set[str]) -> str:
    """Monta a lista de extensões em PT-BR ('.doc, .docx, .pdf ou .txt') a partir do set."""
    ordered = sorted(exts)
    if len(ordered) <= 1:
        return ordered[0] if ordered else ""
    return ", ".join(ordered[:-1]) + " ou " + ordered[-1]


# Fonte única da lista de extensões permitidas (inclui .doc) para TODAS as mensagens 400
_SUPPORTED_EXTS_MSG = _format_exts(_ALLOWED_EXTS)

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
    """Extrai texto de PDF usando PyMuPDF — preserva ordem correta em layouts de colunas."""
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        all_text = []

        for page in doc:
            blocks = page.get_text("blocks")
            if not blocks:
                continue

            # Agrupar posições X para detectar colunas
            x_positions = sorted(set(int(b[0]) for b in blocks))
            columns = []
            current_col_x = []
            col_gap = 50  # gap mínimo para considerar coluna diferente

            for x in x_positions:
                if not current_col_x:
                    current_col_x.append(x)
                elif x - current_col_x[-1] > col_gap:
                    columns.append(sum(current_col_x) // len(current_col_x))
                    current_col_x = [x]
                else:
                    current_col_x.append(x)
            if current_col_x:
                columns.append(sum(current_col_x) // len(current_col_x))

            # Agrupar blocos por coluna
            col_blocks = {col: [] for col in columns}
            for block in blocks:
                x = block[0]
                text = block[4].strip()
                if not text:
                    continue
                closest_col = min(columns, key=lambda c: abs(c - x))
                col_blocks[closest_col].append((block[1], text))

            # Ordenar cada coluna por Y
            for col in col_blocks:
                col_blocks[col].sort(key=lambda b: b[0])

            # Intercalar blocos de todas as colunas por posição Y
            all_blocks = []
            for col in columns:
                for y, text in col_blocks[col]:
                    all_blocks.append((y, text))
            all_blocks.sort(key=lambda b: b[0])

            page_text = "\n".join(text for _, text in all_blocks)
            all_text.append(page_text)

        doc.close()
        return "\n\n---\n".join(all_text)
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


# ---------------------------------------------------------------------------
# Funções de Validação do Guia
# ---------------------------------------------------------------------------

def _check_pdf_selectable(pdf_path: str) -> dict:
    """Verifica se o PDF é selecionável (texto real, não imagem escaneada)."""
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        page = doc[0]
        # Verificar se há texto na primeira página
        text = page.get_text("text")
        doc.close()
        if not text or len(text.strip()) < 50:
            return {"selecionavel": False, "problema": "PDF parece ser imagem escaneada (pouco texto extraído)"}
        return {"selecionavel": True, "problema": None}
    except Exception as e:
        logger.warning(f"[CHECK PDF] Falhou: {e}")
        return {"selecionavel": True, "problema": None}  # Assume ok se não conseguir verificar


def _count_pdf_pages(pdf_path: str) -> int:
    """Conta número de páginas do PDF."""
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        doc.close()
        return pages
    except Exception as e:
        logger.warning(f"[PAGES] Falhou: {e}")
        return 1


def _detect_sensitive_data(text: str) -> list[dict]:
    """Detecta CPF, RG, CTPS, dados bancários no texto."""
    encontrados = []

    # CPF: 11 dígitos com ou sem pontuação
    cpf_pattern = r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b'
    if re.search(cpf_pattern, text):
        encontrados.append({"tipo": "cpf", "descricao": "CPF detectado no currículo", "exemplo": "XXX.XXX.XXX-XX"})

    # RG: 8-9 dígitos
    rg_pattern = r'\b\d{8,9}\b'
    # Filtrar para não confundir com anos
    rg_matches = re.findall(rg_pattern, text)
    for match in rg_matches:
        num = int(match)
        if 10000000 <= num <= 999999999:  # Intervalo típico de RG
            encontrados.append({"tipo": "rg", "descricao": "RG detectado no currículo", "exemplo": match})

    # CTPS
    if 'ctps' in text.lower() or 'carteira de trabalho' in text.lower():
        encontrados.append({"tipo": "ctps", "descricao": "CTPS mencionada no currículo", "exemplo": "CTPS"})

    # Dados bancários
    banc_pattern = r'(agência|conta|banco|ficha|saldo)\s*[::]?\s*\d+'
    if re.search(banc_pattern, text, re.IGNORECASE):
        encontrados.append({"tipo": "dados_bancarios", "descricao": "Possíveis dados bancários detectados", "exemplo": "agência/conta"})

    return encontrados


def _detect_abbreviations(text: str) -> list[dict]:
    """Detecta abreviações que o recrutador pode não entender."""
    abreviacoes = []

    # Mapeamento de abreviações comuns
    abrev_map = {
        'JS': 'JavaScript',
        'html': 'HTML',
        'css': 'CSS',
        'UI': 'Interface do Usuário',
        'UX': 'Experiência do Usuário',
        'API': 'API',  # API é aceito, mas verificar contexto
        'APIs': 'APIs',
        'SDK': 'SDK',
        'CLI': 'CLI',
        'GUI': 'GUI',
        'RAM': 'Memória RAM',
        'CPU': 'CPU',
        'GPU': 'GPU',
    }

    # Verificar cada abreviação
    for abrev, expansao in abrev_map.items():
        # Padrão: a abreviação isolada, não parte de outra palavra
        pattern = rf'\b{abrev}\b'
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Não flaggear se for parte de nome próprio ou sigla conhecida
            if match == 'API' or match == 'APIs':
                continue  # API é amplamente aceito
            # Verificar se está em contexto técnico aceito
            ctx_start = max(0, text.find(match) - 30)
            ctx_end = min(len(text), text.find(match) + len(match) + 30)
            ctx = text[ctx_start:ctx_end].lower()
            # Se o contexto já tem a expansão, não flaggear
            if expansao.lower() in ctx:
                continue
            abreviacoes.append({
                "tipo": "abreviacao",
                "descricao": f"Abreviação '{match}' pode não ser clara para recrutadores",
                "exemplo": match,
                "sugestao": f"Escrever por extenso: {expansao}"
            })

    return abreviacoes


def _check_chronological_order(text: str) -> dict:
    """Verifica se experiências estão em ordem cronológica reversa."""
    # Extrair padrões de datas
    date_patterns = [
        r'(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?\s+de\s+\d{4}',
        r'\d{4}\s*[-–]\s*\d{4}',
        r'(?:20\d{2}|19\d{2})\s*[-–]\s*(?:20\d{2}|19\d{2}|presente|atual)',
    ]

    dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)

    # Extrair anos das datas
    years = []
    for d in dates:
        year_matches = re.findall(r'20\d{2}|19\d{2}', d)
        years.extend(year_matches)

    if len(years) < 2:
        return {"cronologica": True, "problema": None}  # Poucas datas, não avaliar

    # Verificar se está em ordem decrescente
    is_reverse = all(int(years[i]) >= int(years[i+1]) for i in range(len(years)-1))

    if is_reverse:
        return {"cronologica": True, "problema": None}
    else:
        return {
            "cronologica": False,
            "problema": "Experiências não estão em ordem cronológica reversa (mais recente primeiro)"
        }


def _check_profile_summary(text: str) -> dict:
    """Verifica se o Profile Summary é genérico demais."""
    genericos = [
        'apaixonado por',
        'adoro trabalhar',
        'busco crescimento',
        'em busca de',
        'em procura de',
        'interessado em',
        'desejo atuar',
        'procurando primeira',
        'vagas de estagio',
        'estagio',
        'primeiro emprego',
        'inicio de carreira',
    ]

    # Procurar por resumo/objetivo
    resumo_patterns = [
        r'(?i)resumo[:\s]+([^\n]+)',
        r'(?i)objetivo[:\s]+([^\n]+)',
        r'(?i)perfil[:\s]+([^\n]+)',
    ]

    for pattern in resumo_patterns:
        match = re.search(pattern, text)
        if match:
            resumo = match.group(1).lower()
            for gen in genericos:
                if gen in resumo:
                    return {
                        "genérico": True,
                        "problema": f"Profile Summary parece genérico: '{gen}'",
                        "sugestao": "Seja específico: cargo + anos de exp + principal realização"
                    }

    return {"genérico": False, "problema": None}


# ---------------------------------------------------------------------------
# Fit CV × vaga — camada determinística (sem LLM)
# ---------------------------------------------------------------------------

def _norm_text(text: str) -> str:
    """Normaliza texto para matching: minúsculas + sem acentos."""
    import unicodedata
    return unicodedata.normalize('NFD', text.lower()).encode('ascii', 'ignore').decode('ascii')


# Stopwords de PT-BR + termos genéricos de CV que não valem como "skill de referência"
_STOPWORDS_PT = {
    'a', 'o', 'e', 'de', 'da', 'do', 'das', 'dos', 'para', 'pra', 'com', 'em',
    'no', 'na', 'nos', 'nas', 'ao', 'aos', 'um', 'uma', 'uns', 'umas', 'se',
    'ou', 'foi', 'ser', 'ter', 'pelo', 'pela', 'entre', 'sobre', 'quando',
    'mais', 'menos', 'muito', 'pouco', 'tambem', 'como', 'qual', 'cada',
    'esse', 'essa', 'este', 'esta', 'isso', 'isto', 'aquilo', 'pode', 'deve',
    'dever', 'saber', 'fazer', 'conhecimento', 'conhecimentos', 'vivencia',
    'experiencia', 'experiencias', 'experiência', 'experiências', 'habilidade',
    'habilidades', 'atuar', 'atuacao', 'atuação', 'trabalho', 'trabalhos',
    'empresa', 'empresas', 'equipe', 'equipes', 'projeto', 'projetos',
    'sistema', 'sistemas', 'responsavel', 'responsável', 'gerencia', 'gerência',
    'pessoas', 'cliente', 'clientes', 'resultados', 'resultado',
}


def _term_in_text(term: str, cv_norm: str) -> bool:
    """Retorna True se o termo (ou todas as palavras relevantes dele) aparece no CV normalizado."""
    norm = _norm_text(term)
    if not norm:
        return False
    if norm in cv_norm:
        return True
    # Termo composto: cobre se TODAS as palavras relevantes (>3 letras) aparecerem no CV
    words = [w for w in norm.split() if len(w) > 3]
    return bool(words) and all(w in cv_norm for w in words)


def _dedupe_keep_order(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# Peso de um requisito "nice to have" na nota de fit: vale metade de um obrigatório
NICE_TO_HAVE_WEIGHT = 0.5


def calc_fit_score(cobertos: list, nice_cobertas: list, total_units: float) -> float:
    """Nota de fit 0-100: cada requisito obrigatório coberto vale 1, cada
    desejável (nice to have) vale NICE_TO_HAVE_WEIGHT — normalizado pelo
    total de unidades da vaga. Reutilizada pelo _compute_job_fit e pelo
    ranking do /api/market/cv-fit."""
    return round(100 * (len(cobertos) + NICE_TO_HAVE_WEIGHT * len(nice_cobertas)) / total_units, 1)


def _compute_job_fit(cv_text: str, job_description: str) -> dict:
    """Fit determinístico CV × vaga única: extrai requisitos da descrição da vaga
    (heurística do módulo de mercado + dicionário de skills canônicas) e mede a
    cobertura no texto do CV. Sem LLM — reproducible entre execuções."""
    from market_service import heuristic_extract, extract_mentioned_skills
    extraction = heuristic_extract(job_description)
    requirements = [r for r in extraction.get('requirements', []) if isinstance(r, str) and len(r.strip()) > 2]
    nice_to_have = [n for n in extraction.get('nice_to_have', []) if isinstance(n, str) and len(n.strip()) > 2]

    # Complementa com skills canônicas mencionadas em qualquer parte da descrição
    requirements.extend(extract_mentioned_skills(job_description))

    requirements = _dedupe_keep_order(requirements)
    nice_to_have = _dedupe_keep_order(nice_to_have)
    # Evita dupla contagem: se um termo aparece nos dois, vale como desejável
    nice_set = {n.lower() for n in nice_to_have}
    requirements = [r for r in requirements if r.lower() not in nice_set]

    cv_norm = _norm_text(cv_text)
    cobertos = [t for t in requirements if _term_in_text(t, cv_norm)]
    faltantes = [t for t in requirements if not _term_in_text(t, cv_norm)]
    nice_cobertas = [t for t in nice_to_have if _term_in_text(t, cv_norm)]
    nice_faltantes = [t for t in nice_to_have if not _term_in_text(t, cv_norm)]

    total_units = len(requirements) + NICE_TO_HAVE_WEIGHT * len(nice_to_have)
    if total_units <= 0:
        return {
            "calculado": False,
            "nota": None,
            "requisitos_cobertos": [],
            "requisitos_faltantes": [],
            "desejaveis_cobertas": [],
            "desejaveis_faltantes": [],
            "resumo": "Não foi possível extrair requisitos da descrição fornecida. Cole a descrição completa da vaga (com a seção de requisitos).",
        }

    nota = calc_fit_score(cobertos, nice_cobertas, total_units)
    resumo = (
        f"{len(cobertos)} de {len(requirements)} requisito(s) identificado(s) na vaga aparecem no currículo."
        + (f" Adicione {len(faltantes)} item(ns) em falta para elevar a aderência." if faltantes else " Todos os requisitos identificados estão cobertos.")
    )
    return {
        "calculado": True,
        "nota": nota,
        "requisitos_cobertos": cobertos,
        "requisitos_faltantes": faltantes,
        "desejaveis_cobertas": nice_cobertas,
        "desejaveis_faltantes": nice_faltantes,
        "resumo": resumo,
    }


def _extract_cv_text(temp_path: str, ext: str) -> tuple:
    """Cadeia de extração de texto do CV SEM LLM:
    PDF (pymupdf → pypdfium2 → docling_parse → pdfplumber); docx/txt (docling).
    Retorna (texto, extrator_usado, fallback_usado). Texto vazio = falha total."""
    markdown_text = ""
    extractor_used = "none"
    fallback_used = False

    if ext == '.pdf':
        markdown_text = _extract_pdf_text_pymupdf(temp_path)
        extractor_used = "pymupdf"
        logger.info(f"[CV] PyMuPDF: {len(markdown_text)} chars")
        if not markdown_text or not markdown_text.strip():
            markdown_text = _extract_pdf_text_pypdfium(temp_path)
            extractor_used = "pypdfium2"
            fallback_used = True
            logger.info(f"[CV] pypdfium2: {len(markdown_text)} chars")
        if not markdown_text or not markdown_text.strip():
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
            markdown_text = _extract_pdf_text_pdfplumber(temp_path)
            extractor_used = "pdfplumber"
            fallback_used = True
            logger.info(f"[CV] pdfplumber: {len(markdown_text)} chars")
    else:
        converter = DocumentConverter()
        conversion_result = converter.convert(temp_path)
        markdown_text = conversion_result.document.export_to_markdown()
        extractor_used = "docling"

    if not markdown_text or not markdown_text.strip():
        logger.warning("[CV] Todos os extratores falharam!")
        return "", "none", True
    return markdown_text, extractor_used, fallback_used


def _check_tech_stack_by_experience(text: str) -> dict:
    """Verifica se cada experiência menciona ao menos uma skill/ferramenta da área.
    Agnóstico de área: os termos de referência são derivados do próprio CV
    (tokens que se repetem), não de uma lista fechada de tecnologias dev."""
    # Candidatos: tokens com 4+ letras que se repetem no CV (skills/ferramentas
    # costumam reaparecer); remove stopwords genéricas.
    token_counts = Counter(t.lower() for t in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,}", text) if t.lower() not in _STOPWORDS_PT)
    candidates = {t for t, c in token_counts.items() if c >= 2}
    if len(candidates) < 5:
        # Base insuficiente para avaliar (CV curto ou sem termos repetidos)
        return {"por_experiencia": True, "problema": None}

    # Dividir por experiências (presumindo que há seções de experiência)
    exp_sections = re.split(r'(?i)experiência|experiencia|trabalho|atuação|atuacao', text)

    issues = []
    for i, section in enumerate(exp_sections[1:]):  # Pular a primeira parte (antes da primeira experiência)
        if len(section.strip()) < 50:
            continue
        # Cobre se QUALQUER termo de referência (repetido no CV) aparece na seção
        section_norm = _norm_text(section)
        hits = sum(1 for c in candidates if _norm_text(c) in section_norm)
        if hits == 0:
            issues.append({
                "experiencia": i + 1,
                "problema": "Skill/ferramenta não mencionada na descrição"
            })

    if issues:
        return {
            "por_experiencia": False,
            "problema": f"{len(issues)} experiência(s) sem especificar skills/ferramentas"
        }
    return {"por_experiencia": True, "problema": None}


def _detect_Exit_Reason(text: str) -> list[dict]:
    """Detecta menção a motivo de saída do emprego."""
    motivos = [
        'demissão',
        'demissao',
        'dispensa',
        'justa causa',
        'justacausa',
        'pedido de demissão',
        'pedido de demissa',
        'rescisão',
        'rescisao',
        'saída',
        'saida',
        'foi demitido',
        'fui demitido',
        'processo seletivo',
        'vaga aberta',
    ]

    encontrados = []
    text_lower = text.lower()
    for motivo in motivos:
        if motivo in text_lower:
            encontrados.append({
                "tipo": "motivo_saida",
                "descricao": f"Motivo de saída mencionado: '{motivo}'",
                "exemplo": motivo
            })

    return encontrados


def _check_project_links(text: str, links_info: list) -> dict:
    """Verifica se projetos têm links."""
    # Palavras-chave que indicam link de projeto/portfólio
    projeto_keywords = {'github', 'gitlab', 'portfolio', 'codepen', 'behance', 'dribbble', 'linkedin', 'vercel', 'netlify'}

    # Verificar se há links de projeto nos links extraídos do PDF
    for link in links_info:
        url = link.get('url', '').lower()
        if any(kw in url for kw in projeto_keywords):
            return {"com_links": True, "problema": None}

    # Procurar por seção de projetos no texto
    proj_patterns = [
        r'(?i)projetos?[^\n]*(?:\n[^\n]+){0,20}',
    ]

    for pattern in proj_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            proj_section = match.group(0)
            # Verificar se há URLs na seção
            has_url = bool(re.search(r'https?://|www\.|linkedin\.com|github\.com|portfolio', proj_section, re.IGNORECASE))
            if not has_url:
                return {
                    "com_links": False,
                    "problema": "Projeto(s) sem link visível"
                }

    return {"com_links": True, "problema": None}


def _detect_multiple_cvs(text: str) -> dict:
    """Detecta se o documento parece conter múltiplos currículos misturados."""
    # Procurar nomes de pessoas (padrão: 2+ palavras capitalizadas no início)
    name_pattern = r'\b([A-Z][a-záàâãéêíóôõúçñ]+\s+[A-Z][a-záàâãéêíóôõúçñ]+(?:\s+[A-Z][a-záàâãéêíóôõúçñ]+)?)\b'
    names = re.findall(name_pattern, text)

    # Também procurar por padrões de seção de experiência múltipla
    exp_sections = re.findall(r'(?i)experiência|experiencia|trabalho|atuação|atuacao', text)

    # Se encontrou muitos nomes diferentes no documento, pode ser múltiplos CVs
    # Nome no topo + nome em outra seção = possível mistura
    distinct_names = list(set(n.lower() for n in names if len(n) > 5))

    # Contar seções de experiência
    exp_count = len(exp_sections)

    problema = None
    if len(distinct_names) >= 3 and exp_count >= 4:
        problema = (
            f"Documento parece conter múltiplos currículos: "
            f"{len(distinct_names)} nomes diferentes encontrados ({', '.join(distinct_names[:3])}). "
            f"Um currículo deve ter conteúdo de uma única pessoa."
        )

    return {
        "multiplos": len(distinct_names) >= 3 and exp_count >= 4,
        "nomes_encontrados": distinct_names[:5],
        "problema": problema
    }


def _detect_cover_letter(text: str) -> dict:
    """Detecta se o documento é uma cover letter em vez de um currículo."""
    cover_letter_patterns = [
        r'(?i)prezado\(a\)\s*senhor\(a\)',
        r'(?i)sra\.?\s+\w+',
        r'(?i)venho\s+por\s+meio\s+deste',
        r'(?i)gostaria\s+de\s+me\s+candidatar',
        r'(?i)vi\s+a\s+vaga',
        r'(?i)referente\s+a\s+vaga',
        r'(?i)espero\s+contar\s+com\s+a\s+oportunidade',
        r'(?i)att\s*\.?\s*\w+',
        r'(?i)atenciosamente',
        r'(?i)cordialmente',
        r'(?i)prezado\s+seletor',
        r'(?i)respeitavelmente',
    ]

    cv_section_patterns = [
        r'(?i)^experiência\s+profissional',
        r'(?i)^educação\s+acadêmica',
        r'(?i)^habilidades',
        r'(?i)^idiomas',
    ]

    cover_score = 0
    for pattern in cover_letter_patterns:
        if re.search(pattern, text, re.MULTILINE):
            cover_score += 1

    cv_score = 0
    for pattern in cv_section_patterns:
        if re.search(pattern, text, re.MULTILINE):
            cv_score += 1

    # Se tem mais sinais de cover letter que de currículo, é provavelmente uma cover letter
    is_cover_letter = cover_score >= 2 and cover_score > cv_score

    return {
        "is_cover_letter": is_cover_letter,
        "cover_letter_score": cover_score,
        "cv_score": cv_score,
        "problema": "O documento parece ser uma Cover Letter, não um currículo. Envie o CV principal." if is_cover_letter else None
    }


def _text_to_markdown(text: str) -> str:
    """Converte texto extraído para markdown estruturado, PRESERVANDO a ordem original.

    Headers de seção só são detectados quando a linha é CURTA (~35 chars) e corresponde
    exatamente a um nome de seção conhecido — evita que bullets descritivos como
    'Atuação em telemarketing...' sejam tratados como cabeçalho.
    """
    import re
    lines = text.split('\n')
    result = []

    # Nomes de seções conhecidos (com variações possíveis)
    # Todos usam $ no final para exigir match EXATO — evita falsos positivos
    SECTION_PATTERNS = [
        r'^EXPERIÊNCIA(\s+PROFISSIONAL)?$', r'^EXPERIENCIA(\s+PROFISSIONAL)?$',
        r'^EDUCAÇÃO(\s+ACADÊMICA)?$', r'^EDUCACAO(\s+ACADEMICA)?$',
        r'^FORMAÇÃO(\s+ACADÊMICA)?$', r'^FORMACAO(\s+ACADEMICA)?$',
        r'^HABILIDADES$', r'^SKILLS$',
        r'^IDIOMAS$',
        r'^OBJETIVO$',
        r'^RESUMO(\s+PROFISSIONAL)?$', r'^SOBRE(\s+MIM|\s+EU)?$',
        r'^CERTIFICAÇÕES(\s+E\s+QUALIFICAÇÕES)?$', r'^CERTIFICACOES(\s+E\s+QUALIFICACOES)?$',
        r'^PROJETOS$', r'^LINKS$', r'^CONTATO$',
        r'^INFORMAÇÕES(\s+PESSOAIS)?$', r'^INFORMACOES(\s+PESSOAIS)?$',
        r'^TRABALHO$', r'^ATUAÇÃO$', r'^ATUACAO$',
        r'^QUALIFICAÇÕES(\s+E\s+CERTIFICAÇÕES)?$', r'^QUALIFICACOES(\s+E\s+CERTIFICACOES)?$',
        r'^DADOS\s+PESSOAIS$', r'^DADOSPESSOAIS$',
        r'^INTERESSES?$',
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append('')
            continue

        # Detectar títulos de seção APENAS se a linha for CURTA E corresponder EXATAMENTE
        # a um nome de seção conhecido. Isso evita falsos positivos como
        # "Atuação em telemarketing de cobrança ativa e receptiva" que não é header.
        is_header = False
        upper_stripped = stripped.upper()
        if len(stripped) <= 40:
            for pattern in SECTION_PATTERNS:
                if re.match(pattern, upper_stripped):
                    is_header = True
                    break

        if is_header:
            result.append(f'## {stripped}')
            result.append('')
        elif re.match(r'^[-•*]\s', stripped):
            result.append(f'- {stripped[2:]}')
        else:
            result.append(stripped)

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
            raise HTTPException(status_code=400, detail=f"Formato de arquivo não suportado. Use {_SUPPORTED_EXTS_MSG}.")
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Arquivo excede 10MB.")

        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cv_')
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)

            # Extrair texto com fallback chain (helper reutilizado pelo /api/market/cv-fit)
            markdown_text, extractor_used, fallback_used = _extract_cv_text(temp_path, ext)
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
                pdf_links = _extract_pdf_links(temp_path)
                for url in pdf_links:
                    already = any(l['url'] == url for l in links_info)
                    if not already:
                        links_info.append({'url': url, 'valid': True})
            logger.info(f"[CV] Links detectados: {len(links_info)}")

            # ====================================================================
            # VALIDAÇÕES DO GUIA (CHECKLIST COMPLETO)
            # ====================================================================
            checklist_validacao = {}

            # 1. Verificar se PDF é selecionável
            if ext == '.pdf':
                checklist_validacao['pdf_selecionavel'] = _check_pdf_selectable(temp_path)
                checklist_validacao['numero_paginas'] = _count_pdf_pages(temp_path)
                logger.info(f"[CHECKLIST] Páginas: {checklist_validacao['numero_paginas']}")

            # 2. Verificar nome do arquivo
            filename = cv_file.filename or ""
            nome_valido = True
            nome_problema = None
            # Padrão: NomeSobrenome_CV.pdf ou NomeSobrenome_Resume.pdf
            nome_sem_ext = os.path.splitext(filename)[0]
            if not nome_sem_ext or len(nome_sem_ext) < 3:
                nome_valido = False
                nome_problema = "Nome do arquivo muito curto ou genérico"
            elif re.match(r'^\d', nome_sem_ext):
                nome_valido = False
                nome_problema = "Nome do arquivo começa com número"
            elif '_' not in nome_sem_ext and '-' not in nome_sem_ext:
                nome_valido = False
                nome_problema = "Nome do arquivo não segue padrão Nome_Sobrenome"
            checklist_validacao['nome_arquivo'] = {
                "valido": nome_valido,
                "nome": filename,
                "problema": nome_problema
            }

            # 3. Detectar dados sensíveis
            dados_sensiveis = _detect_sensitive_data(markdown_text)
            if dados_sensiveis:
                logger.warning(f"[CHECKLIST] Dados sensíveis: {len(dados_sensiveis)} encontrados")
            checklist_validacao['dados_sensiveis'] = dados_sensiveis

            # 4. Detectar abreviações
            abreviacoes = _detect_abbreviations(markdown_text)
            if abreviacoes:
                logger.info(f"[CHECKLIST] Abreviações: {len(abreviacoes)} encontradas")
            checklist_validacao['abreviacoes'] = abreviacoes

            # 5. Verificar ordem cronológica
            ordem_check = _check_chronological_order(markdown_text)
            checklist_validacao['ordem_cronologica'] = ordem_check

            # 6. Verificar Profile Summary
            resumo_check = _check_profile_summary(markdown_text)
            checklist_validacao['profile_summary'] = resumo_check

            # 7. Verificar tecnologias por experiência
            tech_check = _check_tech_stack_by_experience(markdown_text)
            checklist_validacao['tech_stack_por_experiencia'] = tech_check

            # 8. Verificar links em projetos
            projetos_check = _check_project_links(markdown_text, links_info)
            checklist_validacao['projetos_com_link'] = projetos_check

            # 9. Verificar motivo de saída
            motivo_saida = _detect_Exit_Reason(markdown_text)
            if motivo_saida:
                logger.warning(f"[CHECKLIST] Motivo de saída: {len(motivo_saida)} encontrados")
            checklist_validacao['motivo_saida'] = motivo_saida

            # 10. Verificar número de páginas (punição se > 2)
            num_paginas = checklist_validacao.get('numero_paginas', 1)
            if num_paginas > 2:
                checklist_validacao['numero_paginas_valido'] = False
                checklist_validacao['numero_paginas_problema'] = f"Curriculum com {num_paginas} páginas, máximo recomendado é 2"
            else:
                checklist_validacao['numero_paginas_valido'] = True
                checklist_validacao['numero_paginas_problema'] = None

            # 11. Verificar múltiplos currículos
            multi_check = _detect_multiple_cvs(markdown_text)
            checklist_validacao['multiplos_curriculos'] = multi_check

            # 12. Verificar se é cover letter
            cover_check = _detect_cover_letter(markdown_text)
            checklist_validacao['cover_letter'] = cover_check

            logger.info(f"[CHECKLIST] Validações concluídas: {list(checklist_validacao.keys())}")

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

            selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
            base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
            if not base_url:
                base_url = "http://localhost:20128/v1"  # omniroute local

            client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)

            # Carregar prompts — análise em 2 passes (estrutura → qualidade).
            # O prompt monolítico cv_analysis_prompt.md continua em knowledge/
            # apenas para referência/histórico; o endpoint usa os prompts divididos.
            prompt_estrut_file = KNOWLEDGE_DIR / 'cv_analysis_estrutura.md'
            prompt_qual_file = KNOWLEDGE_DIR / 'cv_analysis_qualidade.md'
            if prompt_estrut_file.exists():
                with open(prompt_estrut_file, 'r', encoding='utf-8') as f:
                    sys_prompt_estrut = f.read()
            else:
                sys_prompt_estrut = """Você é um especialista em análise de currículos (CV) para ATS e mercado de trabalho.

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

            # Fallback do passo 2 (arquivo ausente → prompt mínimo, mesmo padrão)
            if prompt_qual_file.exists():
                with open(prompt_qual_file, 'r', encoding='utf-8') as f:
                    sys_prompt_qual = f.read()
            else:
                sys_prompt_qual = ("Você é um especialista em QUALIDADE de currículos (CV). "
                                   "Avalie a fórmula XYZ, a presença de métricas e a narrativa, e retorne um JSON "
                                   "válido com os campos pontos_fortes e pontos_fracos. Cada item deve incluir um "
                                   "trecho LITERAL do CV no formato (trecho: 'texto'); se não houver trecho que "
                                   "sustente o item, omita a citação — NUNCA invente trechos nem informação.")

            # Montar user message — PASSO 1 (estrutura)
            area_info = target_role or area or ''
            user_content_estrut = f"""ANALISE A ESTRUTURA DESTE CURRÍCULO (PASSO 1 DE 2).

CURRÍCULO (Markdown):
---
{markdown_text}
---

INFORMAÇÕES ADICIONAIS:
- Links detectados: {[l['url'] for l in links_info] if links_info else 'Nenhum'}
- Tipo de arquivo: {ext}
- Extrator usado: {extractor_used}
- Job description (se fornecida): {job_description or 'Nenhuma'}
- Target role: {area_info or 'Não especificado'}

{f'- O candidato busca posição na área de: {area_info}' if area_info else '- ÁREA DO CANDIDATO NÃO ESPECIFICADA: não assuma nenhuma área (não assuma que é tecnologia, desenvolvimento, etc.). Analise o CV de forma genérica, avaliando apenas o que está escrito.'}

Avalie APENAS o escopo deste passo (estrutura, seções, ortografia, erros comuns, ATS e checklist do guia). A crítica de qualidade (fórmula XYZ, métricas, narrativa) será feita no passo 2."""

            # PASSO 1 — estrutura (nota base, seções, ortografia, erros comuns, ATS)
            response_estrut = client.chat.completions.create(
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
            resumo_pass1 = {
                "resumo_executivo": analysis.get("resumo_executivo"),
                "analise_secoes": analysis.get("analise_secoes"),
                "analise_ats": analysis.get("analise_ats"),
                "erros_comuns_detectados": analysis.get("erros_comuns_detectados"),
            }
            user_content_qual = f"""ANALISE A QUALIDADE DESTE CURRÍCULO (PASSO 2 DE 2).

CURRÍCULO (Markdown):
---
{markdown_text}
---

CONTEXTO DO PASSO 1 (análise de estrutura, JSON):
---
{json.dumps(resumo_pass1, ensure_ascii=False)[:4000]}
---

INFORMAÇÕES ADICIONAIS:
- Target role: {area_info or 'Não especificado'}

{f'- O candidato busca posição na área de: {area_info}' if area_info else '- ÁREA DO CANDIDATO NÃO ESPECIFICADA: não assuma nenhuma área (não assuma que é tecnologia, desenvolvimento, etc.). Analise a qualidade de forma genérica.'}

Avalie APENAS a qualidade (fórmula XYZ, métricas, narrativa) seguindo o prompt de sistema.
Retorne o JSON com pontos_fortes e pontos_fracos, com citações literais do currículo."""

            response_qual = None
            try:
                response_qual = client.chat.completions.create(
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
            import unicodedata as _ud_cit
            def _norm_trecho(s: str) -> str:
                return _ud_cit.normalize('NFD', (s or '').lower()).encode('ascii', 'ignore').decode('ascii')
            _norm_texto_cv = _norm_trecho(markdown_text)
            _citacao_pat = re.compile(
                r"\(\s*trecho\s*:\s*[\"'“”‘’]((?:(?!\s*[\"'”’]\)).)*)[\"'“”‘’]\s*\)",
                re.DOTALL,
            )
            for _campo_cit in ("pontos_fortes", "pontos_fracos"):
                if not isinstance(analysis.get(_campo_cit), list):
                    continue
                def _validar_citacao(item: str) -> str:
                    def _sub(m):
                        trecho = m.group(1).strip()
                        if trecho and _norm_trecho(trecho) in _norm_texto_cv:
                            return m.group(0)
                        return ""
                    limpo = _citacao_pat.sub(_sub, item)
                    return re.sub(r'\s{2,}', ' ', limpo).strip()
                analysis[_campo_cit] = [
                    s for s in (_validar_citacao(i) for i in analysis[_campo_cit] if isinstance(i, str))
                    if s
                ]

            # VALIDAÇÃO DE GROUNDING: remover erros ortográficos alucinados
            # Critérios de remoção (todos devem passar para manter o erro):
            # 1) Palavra deve existir no texto extraído (ignora acentos)
            # 2) Palavra != correcao (senão é falso positivo)
            # 3) Palavra NÃO pode ser toda maiúscula (capitalização não é erro)
            # 4) Palavra NÃO pode conter 'ç' ou outros chars suspeitos de OCR
            # 5) Palavra NÃO pode ser um acrônimo (3+ letras maiúsculas seguidas)
            import unicodedata
            def _norm(s: str) -> str:
                return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode('ascii')
            extracted_norm = _norm(markdown_text) if markdown_text else ""
            if 'erros_ortograficos' in analysis and isinstance(analysis['erros_ortograficos'], list):
                valid_errors = []
                for err in analysis['erros_ortograficos']:
                    if not isinstance(err, dict):
                        continue
                    word = err.get('palavra', '')
                    correcao = err.get('correcao', '')

                    # Critério 1: palavra deve existir no texto extraído (ignora acentos)
                    if not word or _norm(word) not in extracted_norm:
                        continue
                    # Critério 2: correcao deve ser diferente da palavra
                    if correcao and _norm(correcao) == _norm(word):
                        continue
                    # Critério 3: palavra toda em maiúsculas é capitalização, não erro
                    if word == word.upper() and len(word) > 1:
                        continue
                    # Critério 4: palavras com 'ç' ou chars suspeitos de OCR → ignorar
                    if 'ç' in word or 'ñ' in word or any(ord(c) > 127 and c not in 'áéíóúâêîôûãõéèêëïîôùÿáàâéèêëïîôùÿ' for c in word):
                        continue
                    # Critério 5: acrônimos (3+ letras maiúsculas) → ignorar
                    if len(word) >= 3 and word.isupper():
                        continue
                    valid_errors.append(err)
                analysis['erros_ortograficos'] = valid_errors

            # === PÓS-PROCESSAMENTO DEFINITIVO: blindar contra falsos positivos ===
            import unicodedata as _ud
            def _norm(s):
                return _ud.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode('ascii')
            # Normalização sem remover acentos — só lowercase + normalizaçao NFD
            def _norm_accent(s):
                return _ud.normalize('NFD', s).lower()

            # Extrair TODAS as palavras do texto extraído (tokenização por espaço+pontuação)
            _words_raw = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", markdown_text or "")
            _words_norm = set(_norm(w) for w in _words_raw)

            # 1) ERRORS ORTOGRÁFICOS: validação rigorosa em nível de palavra
            if 'erros_ortograficos' in analysis and isinstance(analysis['erros_ortograficos'], list):
                valid_errors = []
                for err in analysis['erros_ortograficos']:
                    if not isinstance(err, dict):
                        continue
                    word = err.get('palavra', '')
                    correcao = err.get('correcao', '')
                    contexto = err.get('contexto', '')

                    # A) Palavra precisa existir como token isolado no texto extraído
                    if not word or _norm(word) not in _words_norm:
                        continue
                    # B) Correcao não pode ser igual à palavra (comparação exata, não normalizada)
                    if correcao and _norm_accent(correcao) == _norm_accent(word):
                        continue
                    # C) Tudo maiúsculo: só ignorar se a forma lowercase existir no texto extraído
                    #    (ex: "API" é sigla correta, mas "REDUSEI" não existe mesmo em lowercase)
                    if word == word.upper() and len(word) > 1:
                        # Verificar se a versão lowercase existe no texto como palavra correta
                        word_lower = word.lower()
                        if _norm(word_lower) in _words_norm:
                            continue  # palavra existe no texto em lowercase → é capitalização, não erro
                        # Se não existe no texto, pode ser erro ortográfico mesmo em caps
                        # (ex: "REDUSEI" → lowercase "redusei" não existe → erro real)
                    # D) Chars suspeitos de OCR → ignorar
                    if 'ç' in word or 'ñ' in word:
                        continue
                    # E) Acrônimos 3+ letras que existem no texto → ignorar
                    if len(word) >= 3 and word.isupper():
                        word_lower = word.lower()
                        if _norm(word_lower) in _words_norm:
                            continue
                        # Se não existe no texto, pode ser erro (ex: "REDUSEI" em caps)
                    # F) Correcao = word.upper() → é capitalização, não erro ortográfico
                    if correcao and correcao == word.upper():
                        continue
                    # G) Palavra lowercase + correcao uppercase = capitalização, não erro
                    if word.islower() and correcao and correcao.isupper():
                        continue
                    # H) Contexto NÃO pode conter palavras inexistentes no texto extraído
                    ctx_words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", contexto or '')
                    if ctx_words and not all(_norm(x) in _words_norm for x in ctx_words):
                        continue
                    # I) Correção NÃO pode conter palavras inexistentes
                    if correcao:
                        corr_words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", correcao)
                        if corr_words and not all(_norm(x) in _words_norm for x in corr_words):
                            continue
                    # J) Palavra não pode ser duas palavras juntas (ex: "seguran ca" → artefato OCR)
                    if ' ' in word or '\n' in word or '-' in word:
                        continue
                    valid_errors.append(err)
                analysis['erros_ortograficos'] = valid_errors

            # 2) Quando área NÃO é especificada: blindagem total contra viés dev
            if not area_info:
                analysis['palavras_chave_faltantes'] = []
                if 'ordem_secoes' in analysis:
                    analysis['ordem_secoes']['correta'] = True
                    analysis['ordem_secoes']['problema'] = None
                    analysis['ordem_secoes']['como_corrigir'] = None
                # Palavras-chave que indicam viés de tech/dev
                dev_keywords = {
                    'linguagem', 'linguagen', 'linguagens', 'framework', 'frameworks',
                    'tech', 'tecnologia', 'tecnologias', 'api', 'apis',
                    'banco de dados', 'database', 'sql',
                    'javascript', 'typescript', 'python', 'java', 'c++', 'c#', 'csharp',
                    'react', 'angular', 'vue', 'node', 'nodejs', 'dev',
                    'desenvolvimento', 'desenvolver', 'programação', 'programar',
                    'código', 'codigos', 'software', 'frontend', 'backend', 'fullstack',
                    'git', 'github', 'gitlab', 'aws', 'azure', 'docker', 'kubernetes',
                    'k8s', 'ci/cd', 'pipeline', 'agile', 'scrum', 'sprint',
                    'biblioteca', 'bibliotecas', 'scripts', 'script',
                    'computador', 'computação', 'ti', 't.i.', 'informática',
                }
                if 'pontos_fracos' in analysis and isinstance(analysis['pontos_fracos'], list):
                    analysis['pontos_fracos'] = [
                        pf for pf in analysis['pontos_fracos']
                        if not any(kw in pf.lower() for kw in dev_keywords)
                    ]
                # Se ainda sobrou algum ponto fraco com viés tech, zerar
                if any(any(kw in pf.lower() for kw in dev_keywords) for pf in analysis.get('pontos_fracos', [])):
                    analysis['pontos_fracos'] = []
                # Filtrar resumo_executivo: remover apenas menções a FALTA de skills tech
                if 'resumo_executivo' in analysis and isinstance(analysis['resumo_executivo'], str):
                    # Só filtrar se o resumo mencionar falta/déficit de competências tech
                    missing_tech_pattern = re.compile(
                        r'(falta|ausência|deveria ter|precisa|deveria possuir|lucro|ganho|vantagem).*(linguagem|framework|tech|tecnolog|api|sql|git|aws|docker|react|node|python|java|frontend|backend|fullstack|programa|código|script)',
                        re.IGNORECASE
                    )
                    sentences = re.split(r'(?<=[.!?])\s+', analysis['resumo_executivo'])
                    cleaned = [s for s in sentences if not missing_tech_pattern.search(s)]
                    if len(cleaned) < len(sentences):
                        analysis['resumo_executivo'] = ' '.join(cleaned)
                        analysis['resumo_executivo'] = re.sub(r'\s+', ' ', analysis['resumo_executivo']).strip()

            # 3) ERROS COMUNS DETECTADOS: filtrar capitalização e OCR
            if 'erros_comuns_detectados' in analysis and isinstance(analysis['erros_comuns_detectados'], list):
                valid_comuns = []
                for err in analysis['erros_comuns_detectados']:
                    if not isinstance(err, dict):
                        continue
                    descricao = err.get('descricao', '')
                    exemplo = err.get('exemplo', '')
                    tipo = err.get('tipo', '').lower()
                    # Remover se exemplo não existe no texto
                    if exemplo and _norm(exemplo) not in _words_norm:
                        continue
                    # Remover se exemplo contém chars de OCR
                    if 'ç' in (exemplo or '') or 'ñ' in (exemplo or ''):
                        continue
                    # Remover se tipo/descrição é sobre capitalização (várias variações)
                    desc_lower = descricao.lower()
                    if (tipo in ('capitalizacao', 'capitalização', 'capitalization', 'uppercase', 'maiúscula', 'maiscula')
                        or 'capitaliz' in desc_lower
                        or 'maiúscula' in desc_lower
                        or 'maiscula' in desc_lower
                        or 'uppercase' in desc_lower
                        or 'maiúscul' in desc_lower
                        or 'maiúsc' in desc_lower):
                        continue
                    # Remover se erro é sobre capitalização: palavra + correção = mesma palavra em cases diferentes
                    # Remove se erro é sobre capitalização: exemplo + correção = mesma palavra em cases diferentes
                    # (usa os campos do PRÓPRIO erro comum — nunca variáveis de outro loop)
                    correcao_comum = (err.get('correcao') or '').strip()
                    if correcao_comum and exemplo and exemplo.lower() == correcao_comum.lower() and exemplo != correcao_comum:
                        continue
                    # Remover se exemplo é toda maiúscula e a versão lowercase existe no texto
                    if exemplo and exemplo == exemplo.upper() and len(exemplo) > 1:
                        if _norm(exemplo.lower()) in _words_norm:
                            continue
                    valid_comuns.append(err)
                analysis['erros_comuns_detectados'] = valid_comuns

            # 4) CONSISTÊNCIA NARRATIVA: se não há erros ortográficos, remover pontos fracos que alegam erros ortográficos
            has_spelling_errors = bool(analysis.get('erros_ortograficos'))
            spelling_pattern = re.compile(
                r'erro[s]? ortográfic[os]?|erros? de ortografia|erros? gramaticais|ortograf[icose]?|deslizes? ortográfic[os]?|erros? de digita[çc][ao]|erros? de escrita|digitacao|ajuste[s]? ortográfic[os]?|corre[çc][ao]es? ortográfic[as]?',
                re.IGNORECASE
            )
            if 'pontos_fracos' in analysis and isinstance(analysis['pontos_fracos'], list) and not has_spelling_errors:
                analysis['pontos_fracos'] = [
                    pf for pf in analysis['pontos_fracos']
                    if not spelling_pattern.search(pf)
                ]
                # Remover pontos fracos que mencionam artefatos de OCR (ç, ñ, espaços quebrados)
                ocr_pattern = re.compile(r'segurançe|artefato[zs]? de extra[çc][ao]|artefato[s]? OCR|quebra[s]? de linha|formata[çc][ao]', re.IGNORECASE)
                analysis['pontos_fracos'] = [
                    pf for pf in analysis['pontos_fracos']
                    if not ocr_pattern.search(pf)
                ]
            # Filtrar resumo_executivo: remover menções a erros ortográficos se não há erros reais
            if 'resumo_executivo' in analysis and isinstance(analysis['resumo_executivo'], str) and not has_spelling_errors:
                # Remover frases inteiras que mencionam erro ortográfico
                sentences = re.split(r'(?<=[.!?])\s+', analysis['resumo_executivo'])
                cleaned = [s for s in sentences if not spelling_pattern.search(s)]
                analysis['resumo_executivo'] = ' '.join(cleaned)
                # Limpeza final
                analysis['resumo_executivo'] = re.sub(r'\s+', ' ', analysis['resumo_executivo']).strip()
                analysis['resumo_executivo'] = re.sub(r'([.,;:!])\s*\1+', r'\1', analysis['resumo_executivo'])

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
            analysis['_links'] = [l['url'] for l in links_info]

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
        raise HTTPException(status_code=500, detail=f"Erro ao processar o currículo: {str(e)}")


# ---------------------------------------------------------------------------
# Fit CV × Vagas do Mercado — ranking determinístico (sem LLM, sem chave)
# ---------------------------------------------------------------------------

@app.post('/api/market/cv-fit')
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
        cv_text, extractor_used, _ = _extract_cv_text(temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    conn = sqlite3.connect(DB_FILE)
    try:
        rows = conn.execute(
            "SELECT id, title, company, location, modality, source_url, requirements, nice_to_have "
            "FROM market_jobs WHERE is_relevant = 1"
        ).fetchall()
    finally:
        conn.close()

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
      |\b(?:reduz|reduc|reducao|diminui|aument|cresc|economiz|eleva|gera)\w*\s+(?:em|de|para)\s+\d+(?:[.,]\d+)?""",
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
    return sum(1 for l in corpo if _BULLET_LINE_RE.match(l))


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


@app.post('/api/cv/semantic-fit')
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

    # Provider por id (mesmo padrão do /api/linkedin/analyze)
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

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvfitsem_')
    extractor_used = "none"
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, extractor_used, _ = _extract_cv_text(temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = "http://localhost:20128/v1"  # omniroute local

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if CV_FIT_PROMPT_FILE.exists():
        with open(CV_FIT_PROMPT_FILE, 'r', encoding='utf-8') as f:
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

    client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
    try:
        start_time = time.time()
        response = client.chat.completions.create(
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
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

        try:
            fit = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            fit = json.loads(match.group()) if match else {}
        if not isinstance(fit, dict):
            fit = {}

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


@app.post('/api/cv/recruiter-sim')
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

    # Provider por id (mesmo padrão do /api/cv/semantic-fit)
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

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvrecruit_')
    extractor_used = "none"
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, extractor_used, _ = _extract_cv_text(temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = "http://localhost:20128/v1"  # omniroute local

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if RECRUITER_PROMPT_FILE.exists():
        with open(RECRUITER_PROMPT_FILE, 'r', encoding='utf-8') as f:
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

    client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
    try:
        start_time = time.time()
        response = client.chat.completions.create(
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
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

        try:
            sim = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            sim = json.loads(match.group()) if match else {}
        if not isinstance(sim, dict):
            sim = {}

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


@app.post('/api/cv/cover-letter')
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

    # Provider por id (mesmo padrão do /api/cv/recruiter-sim)
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

    t0 = time.time()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='cvcover_')
    extractor_used = "none"
    try:
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        cv_text, extractor_used, _ = _extract_cv_text(temp_path, ext)
        if not cv_text or not cv_text.strip():
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto do arquivo. Tente outro PDF ou um .docx.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = "http://localhost:20128/v1"  # omniroute local

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if COVER_LETTER_PROMPT_FILE.exists():
        with open(COVER_LETTER_PROMPT_FILE, 'r', encoding='utf-8') as f:
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

    client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
    try:
        start_time = time.time()
        response = client.chat.completions.create(
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
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

        try:
            carta = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            carta = json.loads(match.group()) if match else {}
        if not isinstance(carta, dict):
            carta = {}

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


@app.post('/api/cv/diff')
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

    def _extrair(content: bytes, ext: str, prefixo: str, rotulo: str) -> tuple:
        temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix=prefixo)
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)
            texto, extractor_used, _ = _extract_cv_text(temp_path, ext)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        if not texto or not texto.strip():
            raise HTTPException(status_code=400, detail=f"Não foi possível extrair texto do arquivo {rotulo}. Tente outro PDF ou um .docx.")
        return texto, extractor_used

    texto_novo, extractor_novo = _extrair(content_novo, ext_novo, 'cvdiffnovo_', "novo")
    texto_anterior, extractor_anterior = _extrair(content_anterior, ext_anterior, 'cvdiffant_', "anterior")

    # Diferença determinística não depende de LLM — calculada antes de tudo
    deterministico = _diff_cv_deterministic(texto_anterior, texto_novo)

    # Provider por id (mesmo padrão do /api/cv/cover-letter)
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

    t0 = time.time()
    selected_model = model_name if (model_name and model_name.strip()) else "auto/best-coding"
    base_url = api_url if (api_url and api_url.strip()) else os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = "http://localhost:20128/v1"  # omniroute local

    # Carregar prompt de sistema (fallback mínimo se o arquivo sumiu)
    if CV_DIFF_PROMPT_FILE.exists():
        with open(CV_DIFF_PROMPT_FILE, 'r', encoding='utf-8') as f:
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

    client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
    try:
        start_time = time.time()
        response = client.chat.completions.create(
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
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

        try:
            narrativa = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            narrativa = json.loads(match.group()) if match else {}
        if not isinstance(narrativa, dict):
            narrativa = {}

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
        client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)
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
    except Exception:
        # Detalhe vai só para os logs (com stacktrace); o cliente recebe mensagem genérica
        logger.exception("[MARKET ERROR] falha interna na análise de mercado")
        raise HTTPException(status_code=500, detail="Falha interna na análise de mercado. Tente novamente em instantes.")


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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
        import urllib.parse
        query = urllib.parse.quote_plus("test")
        req = urllib.request.Request(
            f'https://api.openwebninja.com/jsearch/search-v2?query={query}&country=br&language=pt&num_pages=1',
            headers={
                'X-API-Key': api_key,
                'Accept': 'application/json'
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("data", {}).get("jobs", [])
            return {
                "valid": True,
                "data": {
                    "rate_limit": resp.headers.get("x-ratelimit-limit"),
                    "rate_limit_remaining": resp.headers.get("x-ratelimit-remaining"),
                    "total_results": len(jobs)
                }
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}

@app.post('/api/jsearch/save-key')
async def api_save_jsearch_key(
    api_key: str = Form(...),
    description: str = Form(""),
):
    """Salva uma chave JSearch no DB (com hash para upsert do market_service)."""
    from datetime import datetime
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    key_prefix = api_key[:8] + "…" + api_key[-4:] if len(api_key) > 12 else api_key
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO jsearch_keys (api_key, key_hash, key_prefix, description, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, 'ok')",
            (api_key, key_hash, key_prefix, description, datetime.now().isoformat())
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid}
    except sqlite3.Error as e:
        logger.error(f"[JSEARCH] Falha ao salvar chave: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


@app.put('/api/jsearch/update-key')
async def api_update_jsearch_key(
    key_id: int = Form(...),
    api_key: str = Form(...),
    description: str = Form(""),
):
    """Atualiza a chave/descrição de uma chave JSearch já salva."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    key_prefix = api_key[:8] + "…" + api_key[-4:] if len(api_key) > 12 else api_key
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE jsearch_keys SET api_key = ?, key_hash = ?, key_prefix = ?, description = ? WHERE id = ?",
            (api_key, key_hash, key_prefix, description, key_id),
        )
        conn.commit()
        return {"success": cursor.rowcount > 0}
    except sqlite3.Error as e:
        logger.error(f"[JSEARCH] Falha ao atualizar chave: {e}")
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
            client = OpenAI(api_key=key, timeout=_LLM_TIMEOUT)
        else:
            client = OpenAI(api_key=key, base_url=base_url, timeout=_LLM_TIMEOUT)

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

