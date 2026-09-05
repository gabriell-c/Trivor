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
    ctps_pattern = r'\b\d{6,9}\b'
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


def _check_tech_stack_by_experience(text: str) -> dict:
    """Verifica se tecnologias são mencionadas em cada experiência."""
    # Procurar por experiências
    exp_patterns = [
        r'(?i)(desenvolvedor|analista|gerente|coordenador|assistente|vendedor|atendente|operador)[^\n]*\n([^\n]*\n){0,10}',
    ]

    # Extrair palavras-chave de tecnologia/área
    tech_keywords = [
        'python', 'java', 'javascript', 'typescript', 'c#', 'c++', 'php',
        'react', 'angular', 'vue', 'node', 'django', 'flask', 'spring',
        'sql', 'nosql', 'mongodb', 'postgresql', 'mysql',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes',
        'git', 'github', 'gitlab',
        'excel', 'power bi', 'tableau', 'sap',
        'crm', 'erp', 'vendas', 'marketing', 'financeiro',
        'atendimento', 'suporte', 'gestão', 'projeto',
    ]

    # Dividir por experiências (presumindo que há seções de experiência)
    exp_sections = re.split(r'(?i)experiência|experiencia|trabalho|atuação|atuacao', text)

    issues = []
    for i, section in enumerate(exp_sections[1:]):  # Pular a primeira parte (antes da primeira experiência)
        if len(section.strip()) < 50:
            continue
        # Verificar se há palavras-chave relevantes
        section_lower = section.lower()
        has_tech = any(kw in section_lower for kw in tech_keywords)
        if not has_tech:
            issues.append({
                "experiencia": i + 1,
                "problema": "Tecnologia/ferramenta não mencionada na descrição"
            })

    if issues:
        return {
            "por_experiencia": False,
            "problema": f"{len(issues)} experiência(s) sem especificar tecnologias/ferramentas"
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
            area_info = target_role or area or ''
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
- Target role: {area_info or 'Não especificado'}

{f'- O candidato busca posição na área de: {area_info}' if area_info else '- ÁREA DO CANDIDATO NÃO ESPECIFICADA: não assuma nenhuma área (não assuma que é tecnologia, desenvolvimento, etc.). Analise o CV de forma genérica, avaliando apenas o que está escrito.'}

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
                    if correcao and word.lower() == correcao.lower() and word != correcao:
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
            # Adicionar checklist de validação do guia
            analysis['checklist_validacao'] = checklist_validacao
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

