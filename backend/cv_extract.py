"""Extração de texto de CV (PDF/DOCX/TXT) — sem LLM.

Cadeia de fallback do PDF: PyMuPDF → pypdfium2 → docling_parse → pdfplumber;
docx/txt via docling. Constantes de formato aceito + helpers de página/links.
Corte de cv_helpers.py (split do god file).
"""

import os
import re
import tempfile

import pypdfium2 as pdfium
from app_log import get_app_logger

logger = get_app_logger(__name__)

# L11: .doc (binário legacy) exige LibreOffice/docling e dava RuntimeError
# crua → fora da lista; as mensagens de 400 usam _SUPPORTED_EXTS_MSG,
# que é gerado desta lista (se um dia .doc voltar, é só reconstruir).
_ALLOWED_EXTS = {'.pdf', '.docx', '.txt'}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _format_exts(exts: set[str]) -> str:
    """Monta a lista de extensões em PT-BR ('.docx, .pdf ou .txt') a partir do set."""
    ordered = sorted(exts)
    if len(ordered) <= 1:
        return ordered[0] if ordered else ""
    return ", ".join(ordered[:-1]) + " ou " + ordered[-1]


# Fonte única da lista de extensões permitidas para TODAS as mensagens 400
_SUPPORTED_EXTS_MSG = _format_exts(_ALLOWED_EXTS)

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
            x_positions = sorted({int(b[0]) for b in blocks})
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
        # docx/txt via docling. Import tardio: docling é pesado e só o
        # requirements completo o traz — a API headless fica sem ele e
        # este branch devolve texto vazio (a rota levanta 400 claro) em
        # vez de 500 crua no import do módulo.
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            conversion_result = converter.convert(temp_path)
            markdown_text = conversion_result.document.export_to_markdown()
            extractor_used = "docling"
        except Exception as exc:
            logger.warning(f"[CV] docling indisponível ou falhou ({exc.__class__.__name__}): {exc}")
            markdown_text = ""
            extractor_used = "docling"
            fallback_used = True

    if not markdown_text or not markdown_text.strip():
        logger.warning("[CV] Todos os extratores falharam!")
        return "", "none", True
    return markdown_text, extractor_used, fallback_used
