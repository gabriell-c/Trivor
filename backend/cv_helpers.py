"""Camada de análise de currículos (sem HTTP): extração de texto de PDF
com fallback chain (PyMuPDF → pypdfium2 → docling_parse → pdfplumber),
validações do guia (checklist), fit determinístico CV × vaga e conversão
para markdown. Usada pelas rotas de cv_routes (análise, cv-fit, diff,
cover letter, simulador de recrutador).

Movida de main.py — corpos das funções intactos; logger no mesmo formato
de linha do original (ver app_log).
"""

import os
import re
import tempfile
from collections import Counter

import pypdfium2 as pdfium
from app_log import get_app_logger
from docling.document_converter import DocumentConverter

logger = get_app_logger(__name__)

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
        # Padrão: a abreviação isolada, não parte de outra palavra.
        # (?<!\.) evita flaggear o "js" de nomes compostos legítimos
        # (Next.js, React.js, Express.js — o ponto é parte do nome oficial).
        pattern = rf'(?<!\.)\b{abrev}\b'
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
    from market_service import extract_mentioned_skills, heuristic_extract
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


def _detect_exit_reason(text: str) -> list[dict]:
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
    distinct_names = list({n.lower() for n in names if len(n) > 5})

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
