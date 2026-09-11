"""
Market Intelligence Service – módulo completo de Inteligência de Mercado.
Coleta, filtro, extração IA e agregação estatística.
"""

import sqlite3
import json
import re
import time
import traceback
import logging
import urllib.request
import urllib.error
import hashlib
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timedelta

from openai import OpenAI

logger = logging.getLogger(__name__)
_logger_file = logging.FileHandler(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\market_log.txt', encoding='utf-8')
_logger_file.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
logger.addHandler(_logger_file)
logger.setLevel(logging.INFO)

# Max jobs sent to AI per analysis — pre-filter reduces the pool first
_MAX_JOBS_FOR_ANALYSIS = 3000

# Minimum delay between API calls per key (seconds)
_JSEARCH_MIN_DELAY = 0.5

# Delay between parallel batches (seconds)
_BATCH_DELAY = 0.8

# Delay when all keys are rate-limited (seconds)
_RATE_LIMIT_ALL_SLEEP = 15.0

# Max retry attempts for rate-limited queries
_MAX_RETRY = 2
_RETRY_BASE_DELAY = 3.0

# Import logging service for AI call tracking
from logging_service import log_request as log_ai_call


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def sanitize(text: str) -> str:
    """Remove emojis e caracteres surrogates Unicode."""
    return text.encode('utf-8', 'ignore').decode('utf-8')

def normalize_term(term: str) -> str:
    """Normaliza qualquer termo (skill, certificação, idioma, etc) para padronização."""
    t = term.strip()
    return ' '.join(w.capitalize() for w in t.split())


# ---------------------------------------------------------------------------
# Normalização avançada de skills — agrupa variações e remove lixo
# ---------------------------------------------------------------------------

_GARBAGE_PATTERNS = [
    # Salários
    r"r\$\s*\d[\d\s.]*", r"\d{3,}\s*(mil|milhares)",
    # Horários
    r"\d{1,2}\s*h\s*(à|a|até|ate)\s*\d{1,2}\s*h",
    r"\d{1,2}:\d{2}\s*(às?\s*\d{1,2}:\d{2})?",
    r"\d{1,2}h\s*(às?\s*\d{1,2}h)?",
    r"(segunda|terça|quarta|quinta|sexta|sábado|saber|domingo)\s*(à|a)\s*(segunda|terça|quarta|quinta|sexta|sábado|saber|domingo)",
    r"(domingos|feriados|finais?\s+de\s+semana)",
    r"jornada\s+(combinar|flexível|flexivel|integral|reduzida)",
    r"carga\s+horária\s+(combinar|flexível|flexivel|integral)",
    # Localização
    r"\b(bairro|região|regiao|local|região\s+de|próximo|perto)\s+.+",
    r"\b(estado|cidade|município|municipio|região\s+metropolitana)\b",
    # Benefícios e condições
    r"\b(vale|auxílio|auxilio|benefício|beneficio)\s+(transporte|alimentação|refeição|combustível|saúde|saude|creche|festividade|particpação)",
    r"\b(plano\s+(de|de\s+saúde|de\s+saude)|convênio|convenio)\s+\w+",
    # Formatação e lixo
    r"^—+$", r"^—\s*$", r"^\s*$",
    r"\b(abrangência|abrangencia|escopo|alcance)\s+.+",
    r"\b(conforme\s+escala|conforme\s+demand|necessidade\s+do\s+cliente)",
    r"\b(horário\s+(combinar|flexível|flexivel|de\s+acordo|indisponível))",
    # Números soltos que não fazem sentido como skill
    r"^\d{4,}$", r"^\d{2,3}\s*\%?\s*$",
]

# Mapeamento de normalização de skills para agrupar variações
# A ordem importa: padrões mais específicos vêm PRIMEIRO
_SKILL_NORMALIZATION = {
    # ═══════════════════════════════════════════════════════════
    # 1. FERRAMENTAS DE ESCRITÓRIO — MERGE TODAS AS VARIAÇÕES
    # ═══════════════════════════════════════════════════════════
    r"\b(excel\s+vba|vba\s+excel)\b": "Excel VBA",
    r"\b(excel\s+para\s+finanças|excel\s+financeiro)\b": "Excel Financeiro",
    r"\bpacote\s+office\b": "Excel",
    r"\bpacote\s+office\s+(avançado|avanca?do|intermediário|intermediaria|básico|basico)\b": "Excel",
    r"\bms?\s*excel\b": "Excel",
    r"\bmicrosoft\s+excel\b": "Excel",
    r"\bexcel\s+(avançado|avanca?do|intermediário|intermediaria|básico|basico)\b": "Excel",
    r"\bexcel\b": "Excel",
    r"\b(ms\s*word|microsoft\s+word)\b": "Word",
    r"\bword\b": "Word",
    r"\bpp\s*(presentation|pont)?\b": "PowerPoint",
    r"\b(powerpoint|ms\s*powerpoint|microsoft\s+powerpoint)\b": "PowerPoint",
    r"\boutlook\b": "Outlook",
    r"\bmicrosoft\s+outlook\b": "Outlook",
    r"\baccess\b": "Access",
    r"\b(microsoft\s+)?office\s+(suite|365|professional|completo)\b": "Microsoft Office",
    r"\boffice\s+(201[0-9]|202[0-2]|365|professional)\b": "Microsoft Office",
    r"\bgoogle\s+workspace\b": "Google Workspace",
    r"\bgoogle\s+docs\b": "Google Docs",
    r"\bgoogle\s+sheets?\b": "Google Sheets",
    r"\bgoogle\s+slides?\b": "Google Slides",
    r"\bgoogle\s+drive\b": "Google Drive",
    r"\bplanilhas\s+eletrônicas\b": "Planilhas Eletrônicas",
    r"\bplanilha\b": "Planilhas Eletrônicas",

    # ═══════════════════════════════════════════════════════════
    # 2. PROGRAMAÇÃO
    # ═══════════════════════════════════════════════════════════
    r"\bpython\s+(3|\.?\d+|\.?\d+\.\d+)\b": "Python",
    r"\bpython\b": "Python",
    r"\bjavascript\b": "JavaScript",
    r"\bjs\b": "JavaScript",
    r"\btypescript\b": "TypeScript",
    r"\bts\b": "TypeScript",
    r"\bjava\s+(8|11|17|21|ee|se|me)?\b": "Java",
    r"\bjava\b": "Java",
    r"\bc\s*\+\+\b": "C++",
    r"\bc\b": "C",
    r"\bc\s*sharp\b": "C#",
    r"\bphp\s*(7|8)?\b": "PHP",
    r"\bphp\b": "PHP",
    r"\bruby\b": "Ruby",
    r"\bgo\s*(lang)?\b": "Go",
    r"\bswift\b": "Swift",
    r"\bkotlin\b": "Kotlin",
    r"\br\b": "R",
    r"\brust\b": "Rust",
    r"\bdart\b": "Dart",
    r"\b\.?net\b": ".NET",
    r"\basp\.?net\b": "ASP.NET",
    r"\bnode\.?js\b": "Node.js",

    # ═══════════════════════════════════════════════════════════
    # 3. FRAMEWORKS
    # ═══════════════════════════════════════════════════════════
    r"\breact\b": "React",
    r"\breact\s*js\b": "React",
    r"\bnext\.?js\b": "Next.js",
    r"\bnextjs\b": "Next.js",
    r"\bangular\b": "Angular",
    r"\bangularjs\b": "AngularJS",
    r"\bvue\b": "Vue",
    r"\bdjango\b": "Django",
    r"\bflask\b": "Flask",
    r"\bspring\b": "Spring",
    r"\bspring\s*boot\b": "Spring Boot",
    r"\blaravel\b": "Laravel",
    r"\brails\b": "Rails",
    r"\bruby\s*on\s*rails\b": "Rails",
    r"\bexpress\b": "Express",
    r"\bflutter\b": "Flutter",
    r"\bionic\b": "Ionic",
    r"\breact\s*native\b": "React Native",
    r"\bbootstrap\b": "Bootstrap",
    r"\btailwind\b": "Tailwind",
    r"\btailwind\s*css\b": "Tailwind",

    # ═══════════════════════════════════════════════════════════
    # 4. BANCOS DE DADOS
    # ═══════════════════════════════════════════════════════════
    r"\bmysql\b": "MySQL",
    r"\b(postgresql|postgres)\b": "PostgreSQL",
    r"\bsql\s*server\b": "SQL Server",
    r"\bsql\b": "SQL",
    r"\bmongodb\b": "MongoDB",
    r"\bsqlite\b": "SQLite",
    r"\boracle\b": "Oracle",
    r"\bfirebase\b": "Firebase",
    r"\bredis\b": "Redis",
    r"\bdynamodb\b": "DynamoDB",
    r"\bmariadb\b": "MariaDB",
    r"\btransact\s*sql\b": "T-SQL",

    # ═══════════════════════════════════════════════════════════
    # 5. CLOUD & DEVOPS
    # ═══════════════════════════════════════════════════════════
    r"\baws\b": "AWS",
    r"\bamazon\s*web\s*services\b": "AWS",
    r"\bazure\b": "Azure",
    r"\bmicrosoft\s*azure\b": "Azure",
    r"\bgcp\b": "GCP",
    r"\bgoogle\s*cloud\b": "GCP",
    r"\bdocker\b": "Docker",
    r"\bkubernetes\b": "Kubernetes",
    r"\bk8s\b": "Kubernetes",
    r"\bjenkins\b": "Jenkins",
    r"\bgit\b": "Git",
    r"\bterraform\b": "Terraform",
    r"\bazure\s*dev\s*ops\b": "Azure DevOps",
    r"\bgithub\b": "GitHub",
    r"\bgitlab\b": "GitLab",

    # ═══════════════════════════════════════════════════════════
    # 6. FERRAMENTAS GERAIS
    # ═══════════════════════════════════════════════════════════
    r"\bsap\b": "SAP",
    r"\bsalesforce\b": "Salesforce",
    r"\btrello\b": "Trello",
    r"\bslack\b": "Slack",
    r"\bteams\b": "Microsoft Teams",
    r"\bzoom\b": "Zoom",
    r"\bjira\b": "Jira",
    r"\basana\b": "Asana",
    r"\bmonday\b": "Monday",
    r"\bhubspot\b": "HubSpot",
    r"\bpower\s*b\s*iq\b": "Power BI",
    r"\bpower\sbi\b": "Power BI",
    r"\bbi\b": "Business Intelligence",
    r"\bseo\b": "SEO",
    r"\bsem\b": "SEM",
    r"\bgoogle\s*ads\b": "Google Ads",
    r"\bgoogle\s*analytics\b": "Google Analytics",
    r"\berp\b": "ERP",
    r"\bcmr\b": "CRM",
    r"\bsharepoint\b": "SharePoint",
    r"\bone\s*drive\b": "OneDrive",
    r"\bdropbox\b": "Dropbox",
    r"\bautocad\b": "AutoCAD",
    r"\bphotoshop\b": "Photoshop",
    r"\billustrator\b": "Illustrator",
    r"\bpremiere\b": "Premiere Pro",
    r"\bfigma\b": "Figma",
    r"\bcanva\b": "Canva",
    r"\bnotion\b": "Notion",
    r"\bwordpress\b": "WordPress",
    r"\bshopify\b": "Shopify",
    r"\btotvs\b": "TOTVS",
    r"\bms\s*365\b": "Microsoft 365",
    r"\b365\b": "Microsoft 365",

    # ═══════════════════════════════════════════════════════════
    # 7. IDIOMAS
    # ═══════════════════════════════════════════════════════════
    r"\bportuguês\b": "Português",
    r"\bportugues\b": "Português",
    r"\binglês\b": "Inglês",
    r"\binglish\b": "Inglês",
    r"\bespanhol\b": "Espanhol",
    r"\bespanol\b": "Espanhol",
    r"\bfrancês\b": "Francês",
    r"\bfrances\b": "Francês",
    r"\bitaliano\b": "Italiano",
    r"\balemão\b": "Alemão",
    r"\balemao\b": "Alemão",
    r"\bjaponês\b": "Japonês",
    r"\bjapones\b": "Japonês",
    r"\bcoreano\b": "Coreano",
    r"\bchinês\b": "Chinês",
    r"\bchines\b": "Chinês",
    r"\barabe\b": "Árabe",
    r"\bportuguês\s*(brasileiro|br)\b": "Português (BR)",

    # ═══════════════════════════════════════════════════════════
    # 8. FORMAÇÃO ACADÊMICA
    # ═══════════════════════════════════════════════════════════
    r"\b(ensino\s+(médio|médio\s+completo|fundamental|fundamental\s+(completo|incompleto)|superior|superior\s+(completo|em\s+andamento|cursando)))\b": "Ensino Médio",
    r"\b(superior\s+completo|graduação\s+completa|graduado|bacharel)\b": "Ensino Superior Completo",
    r"\b(cursando|em\s+andamento)\s+(ensino\s+)?(superior|administração|contabilidade|tecnologia|engenharia|direito|psicologia|pedagogia|economia)\b": "Cursando Superior",
    r"\b(pós?-graduação|pós\s+graduação|MBA|mba)\b": "Pós-Graduação",
    r"\b(mestrado|mas?tere)\b": "Mestrado",
    r"\b(doutorado|ph\.?d)\b": "Doutorado",
    r"\b(técnico|tecnico)\s*(em\s+(informática|computação|administrativo|contábil|enfermagem|mecânica))?\b": "Técnico",
    r"\bcurso\s+técnico\b": "Técnico",

    # ═══════════════════════════════════════════════════════════
    # 9. SOFT SKILLS
    # ═══════════════════════════════════════════════════════════
    r"\b(proatividade|pró-atividade|pró activo|pro activo)\b": "Proatividade",
    r"\b(iniciativa|inicial)\b": "Iniciativa",
    r"\b(comunicação|comunicação\s+interpessoal)\b": "Comunicação",
    r"\b(trabalho\s+em\s+(equipe|equipo|grupo|time))\b": "Trabalho em Equipe",
    r"\b(organização|organizacao|organizado|organizada)\b": "Organização",
    r"\b(atenção\s+a\s+detalhes|olho\s+ao\s+detalhe)\b": "Atenção a Detalhes",
    r"\b(responsabilidade|responsável)\b": "Responsabilidade",
    r"\b(liderança|liderar|líder)\b": "Liderança",
    r"\b(resolução\s+de\s+problemas|solução\s+de\s+problemas)\b": "Resolução de Problemas",
    r"\b(pontualidade|pontual|tempestividade)\b": "Pontualidade",
    r"\b(criatividade|criativo|inovador)\b": "Criatividade",
    r"\b(adaptabilidade|adaptável|flexibilidade)\b": "Adaptabilidade",
    r"\b(trabalho\s+sob\s+pressão|sob\s+pressão)\b": "Trabalho sob Pressão",
    r"\b(autonomia|autônomo|autônoma|independente)\b": "Autonomia",
    r"\b(análise\s+de\s+dados|analyze\s+de\s+dados)\b": "Análise de Dados",
    r"\b(análise\s+crítica|pensamento\s+crítico)\b": "Análise Crítica",
    r"\b(relacionamento\s+interpessoal)\b": "Relacionamento Interpessoal",
    r"\b(negociação|negociar)\b": "Negociação",
    r"\b(gestão\s+de\s+tempo|gerenciamento\s+de\s+tempo)\b": "Gestão de Tempo",
    r"\b(gestão\s+de\s+(equipe|projetos)|gerenciamento\s+de\s+(equipe|projetos))\b": "Gestão de Projetos",
    r"\b(planejamento|planejar)\b": "Planejamento",
    r"\b(empathy|empatia)\b": "Empatia",
    r"\b(paciência|paciente)\b": "Paciência",
    r"\b(orientação\s+para\s+resultados|orientado\s+a\s+resultados)\b": "Orientação para Resultados",

    # ═══════════════════════════════════════════════════════════
    # 10. CERTIFICAÇÕES
    # ═══════════════════════════════════════════════════════════
    r"\b(oab)\b": "OAB",
    r"\b(pmp|project\s+management\s+professional)\b": "PMP",
    r"\b(pmi)\b": "PMI",
    r"\b(scrum\s+master|psm|psi|scrum)\b": "Scrum Master",
    r"\b(itil)\b": "ITIL",
    r"\b(cisa)\b": "CISA",
    r"\b(cism)\b": "CISM",
    r"\b(ceh|ethical\s*hacker)\b": "CEH",
    r"\b(cissp)\b": "CISSP",

    # ═══════════════════════════════════════════════════════════
    # 11. OUTROS TERMOS COMUNS
    # ═══════════════════════════════════════════════════════════
    r"\bcálculo\b": "Cálculo",
    r"\bcálculos?\b": "Cálculo",
    r"\bdigitação|digitar\b": "Digitação",
    r"\bcontabilidade|contábil|contador\b": "Contabilidade",
    r"\bfinanceiro|finanças?\b": "Financeiro",
    r"\bcomercial|vendas?\b": "Comercial",
    r"\badministrativo|administração|administrar\b": "Administrativo",
    r"\b(rh|recrutamento|seleção|recruta|selecao)\b": "Recrutamento e Seleção",
    r"\blogística|logistica\b": "Logística",
    r"\bmarketing\b": "Marketing",
    r"\bdesign|designer|gráfico|grafico\b": "Design",
    r"\bredação|redator|escrever|escrita\b": "Redação",
    r"\batendimento|atender|SAC\b": "Atendimento ao Cliente",
    r"\bsuporte|suporta|help\s*desk|central\s*de\s*ajuda\b": "Suporte Técnico",
    r"\btelemarketing|teleatendimento\b": "Telemarketing",
    r"\bdata\s*entry|entrada\s*de\s*dados|cadastro\b": "Data Entry",
    r"\barquivamento|organização\s+de\s+arquivos\b": "Organização de Arquivos",
    r"\bemissão\s+de\s+notas?|emissão\s+de\s+nf-e|emissao\s+de\s+notas?\b": "Emissão de NF-e",
    r"\brelatórios?|report|relatorio\b": "Relatórios",
    r"\bformação|formacao|escolaridade|ensino\b": "Formação",
    r"\bidioma|idiomas\b": "Idioma",
    r"\bidioma\s+(português|ingles|espanhol|frances|italiano|alemao)\b": "",
}


def _is_garbage_requirement(text: str) -> bool:
    """Retorna True se o texto for lixo e não deve ser considerado skill."""
    t = text.strip()
    if len(t) < 2:
        return True
    for pattern in _GARBAGE_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    # Verifica se é apenas números/pontuação
    if re.match(r'^[\d\s.,%\-/]+$', t):
        return True
    return False


def normalize_skill(skill: str) -> str:
    """Normaliza um skill: remove lixo e agrupa variações no mesmo termo canônico."""
    # Remove lixo
    if _is_garbage_requirement(skill):
        return ""
    t = skill.strip().lower()
    # Remove parênteses e conteúdo interno
    t = re.sub(r'\s*\([^)]*\)\s*', ' ', t).strip()
    # Remove níveis numéricos (30%, 2 anos, etc.)
    t = re.sub(r'\b\d{1,3}\s*%?\b', '', t).strip()
    t = re.sub(r'\b\d+\s*(ano|anos|horas|h)\b', '', t).strip()
    # Aplica mapeamentos
    for pattern, replacement in _SKILL_NORMALIZATION.items():
        if re.search(pattern, t, re.IGNORECASE):
            return replacement.strip()
    # Normalização final: capitalização padrão
    return ' '.join(w.capitalize() for w in t.split()) if t else ""


# ---------------------------------------------------------------------------
# Banco SQLite
# ---------------------------------------------------------------------------

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_raw_jobs (
    id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    description TEXT,
    location TEXT,
    modality TEXT,
    source TEXT,
    source_url TEXT,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS market_jobs (
    id TEXT PRIMARY KEY,
    raw_job_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    modality TEXT,
    source TEXT,
    source_url TEXT,
    is_relevant INTEGER,
    rejection_reason TEXT,
    requirements TEXT,
    nice_to_have TEXT,
    role_level TEXT,
    exp_years_min REAL,
    exp_years_max REAL,
    soft_skills TEXT,
    certifications TEXT,
    salary_min REAL,
    salary_max REAL,
    currency TEXT,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS market_reports (
    id TEXT PRIMARY KEY,
    job_title TEXT,
    target_stack TEXT,
    seniority TEXT,
    location TEXT,
    time_window TEXT,
    total_jobs INTEGER,
    relevant_jobs INTEGER,
    confidence_score TEXT,
    report_data TEXT,
    created_at TEXT
);
"""


def init_market_db(db_file: Path) -> None:
    """Cria as tabelas do DB de inteligência de mercado."""
    conn = sqlite3.connect(db_file)
    conn.executescript(DB_SCHEMA)
    # Migração: adicionar colunas que podem não existir
    for table, col in [
        ("market_raw_jobs", "source_url"),
        ("market_jobs", "source_url"),
        ("market_jobs", "rejection_reason"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        except Exception:
            pass  # coluna já existe
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Geração de vagas mock (todas as áreas)

# ---------------------------------------------------------------------------
# JSearch API — 获取真实职位（需要 API Key）
# ---------------------------------------------------------------------------

_JSEARCH_API_URL = "https://api.openwebninja.com/jsearch/search-v2"
_JSEARCH_HEADERS = {
    "X-API-Key": "",  # 占位，运行时设置
    "Accept": "application/json",
}


def _fetch_jsearch_jobs(
    query: str,
    country: str = "br",
    language: str = "pt",
    num_pages: int = 4,
    api_keys: List[str] = None,
    date_posted: str = "all",
) -> tuple:
    """Através JSearch API busca vagas reais, agregando resultados de TODAS as chaves."""
    if not api_keys:
        return [], None, None

    params = urllib.parse.quote_plus(query)
    url_template = f"{_JSEARCH_API_URL}?query={params}&country={country}&language={language}&num_pages={num_pages}&date_posted={date_posted}"

    all_raw_jobs = []
    last_remaining = None
    last_total = None
    keys_tried = []
    rate_limited_keys = set()  # chaves que já retornaram 429 nesta sessão

    for api_key in api_keys:
        api_key = api_key.strip()
        if not api_key:
            continue

        if api_key in rate_limited_keys:
            logger.debug(f"[JSearch] Pulando chave {api_key[:8]}... (rate-limited nesta sessão)")
            continue
        keys_tried.append(api_key)
        req = urllib.request.Request(url_template, headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "OK":
                consecutive_429 = 0  # reset counter on success
                raw_jobs = data.get("data", {}).get("jobs", [])
                remaining = resp.headers.get("x-ratelimit-remaining")
                total = resp.headers.get("x-ratelimit-limit")
                logger.info(f"[JSearch] Chave {api_key[:8]}... → {len(raw_jobs)} vagas | rate: {remaining}/{total}")
                # Filtra vagas pelo país esperado — chaves diferentes podem retornar países errados
                expected = country.lower()
                if expected == "br":
                    # Para Brasil: aceita BR explícito, mas rejeita localizações de territórios não-BR
                    # (JSearch marca Puerto Rico como BR, mas localização é PR)
                    # NOTE: não rejeita jobs com job_country vazio — pode ser vaga BR sem país definido
                    _SKIP_LOC_TERMS = {
                        "puerto rico", "puerto ", " pr,", " pr ",
                        "united states", "usa,", "usa ",
                        "united kingdom", "uk,", "uk ", "inglaterra", "londres",
                        "netherlands", "holanda", "mexico", "espanha", "españa",
                        "canadá", "canada", "portugal", "frança", "france",
                        "trøndelag", "snåsa", "san german", "são tomé",
                    }
                    filtered_raw = []
                    for j in raw_jobs:
                        jc = (j.get("job_country") or "").lower()
                        jl = (j.get("job_location") or "").lower()
                        # Aceita se país for BR explícito
                        if jc in ("br", "brazil", "brasil"):
                            filtered_raw.append(j)
                            continue
                        # Rejeita se país for explicitamente não-BR
                        if jc and jc not in ("", "usa", "united states"):
                            continue
                        # Rejeita se localização contém termo de território não-BR
                        if any(t in jl for t in _SKIP_LOC_TERMS):
                            continue
                        # Aceita: país vago ou não-BR mas localização compatível
                        filtered_raw.append(j)
                else:
                    # Para internacional: aceita US explícito ou vago (remoto global)
                    filtered_raw = [
                        j for j in raw_jobs
                        if (j.get("job_country") or "").lower() in (expected, "usa", "united states", "")
                    ]
                skipped = len(raw_jobs) - len(filtered_raw)
                if skipped > 0:
                    logger.warning(f"[JSearch] Chave {api_key[:8]}... filtrou {skipped} vagas de país errado ({expected})")
                all_raw_jobs.extend(filtered_raw)
                last_remaining = int(remaining) if remaining else last_remaining
                last_total = int(total) if total else last_total
            else:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... retornou erro: {data.get('message', 'unknown')}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... 403 (sem créditos ou inválida), tentando próxima...")
                rate_limited_keys.add(api_key)
                continue
            elif e.code == 429:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... 429 (rate limit)")
                rate_limited_keys.add(api_key)
                continue
            else:
                logger.error(f"[JSearch] HTTP erro {e.code}: {e.reason}")
                continue
        except Exception as e:
            logger.error(f"[JSearch] Erro com chave {api_key[:8]}...: {e}")
            continue
        # Throttle between key attempts to avoid IP rate limit
        time.sleep(max(0.5, _JSEARCH_MIN_DELAY))

    # If ALL keys were rate-limited, wait longer before next query
    if len(rate_limited_keys) >= len(api_keys) and api_keys:
        logger.warning(f"[JSearch] Todas as {len(api_keys)} chaves rate-limited. Aguardando {_RATE_LIMIT_ALL_SLEEP}s...")
        time.sleep(_RATE_LIMIT_ALL_SLEEP)

    jobs = _build_jobs_from_raw(all_raw_jobs, country)
    logger.info(f"[JSearch] Query {query!r}: {len(jobs)} vagas agregadas de {len(keys_tried)} chave(s)")
    return jobs, last_remaining, last_total


def _build_jobs_from_raw(raw_jobs: List, default_country: str) -> List[Dict]:
    """Constrói lista de jobs a partir dos dados brutos da API."""
    jobs = []
    for j in raw_jobs:
        # Extrai link de candidatura (prioriza job_apply_link, depois apply_options)
        apply_link = j.get("job_apply_link", "")
        if not apply_link and j.get("apply_options"):
            apply_link = j["apply_options"][0].get("apply_link", "")

        # Extrai informações de salário
        salary = j.get("job_salary", "")

        # Extrai destaques da descrição
        highlights = j.get("job_highlights", {})
        highlights_text = ""
        if isinstance(highlights, dict):
            highlights_text = " ".join(
                f"{k}: {', '.join(v)}" for k, v in highlights.items() if v
            )

        # Monta descrição completa
        desc_parts = []
        if j.get("job_description"):
            desc_parts.append(j["job_description"])
        if highlights_text:
            desc_parts.append(highlights_text)
        if salary:
            desc_parts.append(f"Salário: {salary}")
        description = " ".join(desc_parts)

        # Cidade/Estado/País
        city = j.get("job_city", "")
        state = j.get("job_state", "")
        job_country = j.get("job_country", default_country)
        if city and state:
            location = f"{city}, {state}"
        elif city:
            location = city
        else:
            location = job_country if job_country else default_country

        # Tipo de emprego
        emp_type = j.get("job_employment_type", "")
        if emp_type == "FULLTIME":
            modality = "Presencial"
        elif emp_type == "PARTTIME":
            modality = "Meio período"
        elif j.get("job_city") == "" and j.get("job_state") == "":
            modality = "Remoto"
        else:
            modality = emp_type or "Presencial"

        # Fonte
        publisher = j.get("job_publisher", "JSearch")

        jobs.append({
            "title": j.get("job_title", "Unknown"),
            "company": j.get("employer_name", "Unknown"),
            "description": description,
            "location": location,
            "modality": modality,
            "source": publisher,
            "source_url": apply_link,
            "seniority": "",
            "job_id": j.get("job_id", ""),
            "job_country": job_country,
        })
    return jobs


def _update_jsearch_usage(db_file: Path, key: str, remaining: int):
    """Atualiza o rate limit remaining de uma chave JSearch no DB."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
    key_prefix = key[:8] + "…" + key[-4:] if len(key) > 12 else key
    conn = sqlite3.connect(db_file)
    conn.execute('''
        INSERT INTO jsearch_keys (key_hash, key_prefix, last_tested, rate_limit_total, rate_limit_remaining, status, last_error)
        VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, 'ok', '')
        ON CONFLICT(key_hash) DO UPDATE SET
            key_prefix = excluded.key_prefix,
            last_tested = CURRENT_TIMESTAMP,
            rate_limit_remaining = excluded.rate_limit_remaining
    ''', (key_hash, key_prefix, 200, remaining))
    conn.commit()
    conn.close()


def _get_jsearch_country_language(location: str) -> tuple:
    """Retorna (country, language) baseado na seleção de localização do usuário."""
    loc = location.lower()
    if "internacional" in loc:
        return "us", "en"
    return "br", "pt"


def _get_geo_keywords(location: str) -> List[str]:
    """Retorna palavras-chave geográficas para enriquecer as queries de busca."""
    loc = location.lower()
    if "internacional" in loc:
        return ["Brazil", "Latam", "Latin America", "Brazilian", "remoto Brasil"]
    return ["Brasil", "Brazil", "remoto Brasil", "vaga Brasil"]


_PORT_TRANSLATIONS = {
    "developer": "desenvolvedor", "engineer": "engenheiro",
    "analyst": "analista", "designer": "designer", "manager": "gerente",
    "lead": "líder", "architect": "arquiteto",
    "data": "dados", "scientist": "cientista",
    "product": "produto", "marketing": "marketing",
    "sales": "vendas", "support": "suporte",
    "fullstack": "fullstack", "frontend": "frontend",
    "backend": "backend", "devops": "devops",
    "qa": "qa", "tester": "testador", "writer": "escritor",
    "coordinator": "coordenador", "specialist": "especialista",
    "administrator": "administrador", "director": "diretor",
    "consultant": "consultor", "representative": "representante",
    "coordinator": "coordenador",
}


def _translate_to_portuguese(english_query: str) -> str:
    """Tenta traduzir query em inglês para português palavra por palavra."""
    words = english_query.lower().split()
    translated = []
    for w in words:
        # Remove suffixos comuns
        clean = w.rstrip("s").rstrip("ed").rstrip("ing")
        por = _PORT_TRANSLATIONS.get(clean, w)
        translated.append(por)
    result = " ".join(translated)
    # Se nenhuma palavra foi traduzida, retorna None
    if result == english_query.lower():
        return None
    return result


def generate_mock_jobs_if_empty(db_file: Path, job_title: str = "Desenvolvedor Backend", jsearch_api_keys: List[str] = None, date_posted: str = "all", location: str = "Remoto Nacional"):
    """Gera vagas mock se a base estiver vazia.
    Se jsearch_api_keys (lista) for fornecido, tenta buscar vagas reais primeiro.
    Usa múltiplas queries para maximizar o volume de vagas.
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM market_raw_jobs")
    count = cursor.fetchone()[0]

    if count == 0:
        import uuid
        from datetime import datetime, timedelta

        # Primeiro tenta JSearch com as chaves fornecidas (fallback automático)
        sample_jobs = []
        used_key_remaining = None
        valid_keys = []
        if jsearch_api_keys:
            valid_keys = [k.strip() for k in jsearch_api_keys if k and k.strip()]
            if valid_keys:
                search_query = job_title.strip()
                country, language = _get_jsearch_country_language(location)
                geo_keywords = _get_geo_keywords(location)

                # ATENÇÃO: Queries massivas para maximizar volume → 200+ vagas relevantes
                # Cada query com num_pages=12 retorna ~144 vagas; 30 queries = ~4320 vagas brutas
                queries = []

                # Query principal com geo
                if geo_keywords:
                    queries.append(f"{search_query} {geo_keywords[0]}")
                queries.append(search_query)

                # Termos brasileiros essenciais
                queries.append(f"{search_query} vaga brasil")
                queries.append(f"{search_query} emprego brasil")
                queries.append(f"{search_query} remoto brasil")
                queries.append(f"{search_query} clt")
                queries.append(f"{search_query} contratação")
                queries.append(f"{search_query} home office")
                queries.append(f"{search_query} online")

                # Plataformas (geram vagas diferentes)
                queries.append(f"{search_query} linkedin")
                queries.append(f"{search_query} catho")
                queries.append(f"{search_query} infojobs")
                queries.append(f"{search_query} glassdoor")

                # Níveis de experiência
                queries.append(f"{search_query} junior")
                queries.append(f"{search_query} pleno")
                queries.append(f"{search_query} estagiario")
                queries.append(f"{search_query} entry level")

                # Regiões e indústria
                queries.append(f"{search_query} sao paulo")
                queries.append(f"{search_query} sudeste brasil")
                queries.append(f"{search_query} banca")

                # Parallel queries: 执行在 6 个并发的批次中，每个批次独立分配不同的 key 子集
                all_jobs = {}
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def _fetch_single_query(q, keys_subset=None, date_posted="month"):
                    """执行单个查询，可选传入 key 子集以分散 IP 压力。"""
                    keys = keys_subset if keys_subset else valid_keys
                    return _fetch_jsearch_jobs(q, country=country, language=language,
                                               num_pages=12, api_keys=keys, date_posted=date_posted)

                # 将有效 key 分成 6 个子集，尽量均匀分配
                def _split_keys(keys, n):
                    """将 keys 列表分成 n 个子列表，尽量均匀分布。"""
                    if not keys:
                        return [[] for _ in range(n)]
                    result = [[] for _ in range(n)]
                    for i, k in enumerate(keys):
                        result[i % n].append(k)
                    return result

                key_subsets = _split_keys(valid_keys, 6)

                batch_size = 6
                max_concurrent = min(batch_size, len(valid_keys)) if valid_keys else 1
                total_batches = (len(queries) + batch_size - 1) // batch_size

                # 统计每批次成功/失败的 query 数，用于后续 retry
                failed_queries = []  # 记录返回 0 条结果的 query
                retry_count = 0
                max_retries = _MAX_RETRY

                for batch_idx in range(total_batches):
                    batch_queries = queries[batch_idx * batch_size : (batch_idx + 1) * batch_size]
                    # 为每个 query 分配不同的 key 子集（round-robin 移位）
                    subset_idx = batch_idx % len(key_subsets)
                    batch_key_subset = key_subsets[subset_idx]

                    with ThreadPoolExecutor(max_workers=min(len(batch_queries), max_concurrent)) as executor:
                        futures = {}
                        for i, q in enumerate(batch_queries):
                            # 每个 query 使用不同的 key 子集偏移，进一步分散压力
                            inner_offset = (batch_idx + i) % len(key_subsets)
                            inner_subset = key_subsets[inner_offset]
                            futures[executor.submit(_fetch_single_query, q, inner_subset)] = q

                        for future in as_completed(futures):
                            q = futures[future]
                            try:
                                jobs, rem, tot = future.result()
                            except Exception as e:
                                logger.error(f"[MARKET] Query {q!r} falhou: {e}")
                                jobs = []
                                rem = None
                                tot = None
                            logger.info(f"[MARKET] JSearch query {q!r}: {len(jobs)} vagas")
                            dup_before = len(all_jobs)
                            for j in jobs:
                                # Dedup: prioriza job_id da API, fallback para hash título+empresa+local
                                raw_jid = j.get("job_id", "")
                                if raw_jid:
                                    dedup_key = f"api:{raw_jid}"
                                else:
                                    dedup_key = hashlib.md5(
                                        f"{j.get('title','')}|{j.get('company','')}|{j.get('location','')}"
                                        .encode()).hexdigest()
                                all_jobs[dedup_key] = j
                            logger.info(f"[MARKET] Query {q!r}: {len(jobs)} novas, {len(all_jobs)-dup_before} únicas")
                            if rem is not None and valid_keys:
                                used_key_remaining = rem
                            # 记录失败（0 条结果）的 query 以便后续 retry
                            if len(jobs) == 0:
                                failed_queries.append(q)

                    # 批次间延迟：避免 IP 级 rate limit
                    time.sleep(_BATCH_DELAY)

                # Retry 逻辑：对返回 0 条结果的 query 进行重试，每次用不同 key 子集
                for retry_attempt in range(1, max_retries + 1):
                    if not failed_queries:
                        break
                    logger.info(f"[MARKET] Retry attempt {retry_attempt}: {len(failed_queries)} queries failed, waiting {_RETRY_BASE_DELAY * retry_attempt}s")
                    time.sleep(_RETRY_BASE_DELAY * retry_attempt)
                    still_failed = []
                    for q in failed_queries:
                        subset_offset = (retry_attempt + failed_queries.index(q)) % len(key_subsets)
                        subset = key_subsets[subset_offset]
                        try:
                            jobs, rem, tot = _fetch_jsearch_jobs(q, country=country, language=language,
                                                                  num_pages=6, api_keys=subset, date_posted=date_posted)
                        except Exception as e:
                            logger.error(f"[MARKET] Retry query {q!r} falhou: {e}")
                            jobs = []
                            rem = None
                            tot = None
                        logger.info(f"[MARKET] Retry {retry_attempt} query {q!r}: {len(jobs)} vagas")
                        dup_before = len(all_jobs)
                        for j in jobs:
                            raw_jid = j.get("job_id", "")
                            if raw_jid:
                                dedup_key = f"api:{raw_jid}"
                            else:
                                dedup_key = hashlib.md5(
                                    f"{j.get('title','')}|{j.get('company','')}|{j.get('location','')}"
                                    .encode()).hexdigest()
                            all_jobs[dedup_key] = j
                        logger.info(f"[MARKET] Retry {retry_attempt} query {q!r}: {len(jobs)} novas, {len(all_jobs)-dup_before} únicas")
                        if rem is not None and valid_keys:
                            used_key_remaining = rem
                        if len(jobs) == 0:
                            still_failed.append(q)
                    failed_queries = still_failed
                    if not still_failed:
                        break

                sample_jobs = list(all_jobs.values())
                retry_note = f"com {len(failed_queries)} queries ainda falhas" if failed_queries else "sem retry necessário"
                logger.info(f"[MARKET] JSearch combinou {len(sample_jobs)} vagas únicas de {len(queries)} queries, {retry_note}")
                # Atualiza uso no DB
                if used_key_remaining is not None and valid_keys:
                    _update_jsearch_usage(db_file, valid_keys[0], used_key_remaining)

        # Se JSearch falhou ou não configurado, prossegue com lista vazia (sem dados fabricados)
        if not sample_jobs:
            logger.info("[MARKET] JSearch sem resultados ou não configurado — prosseguindo com 0 vagas reais")

        if sample_jobs:
            now = datetime.now()
            for i, j in enumerate(sample_jobs):
                job_id = str(uuid.uuid4())
                pub_date = now - timedelta(days=i * 3 + 1)
                source_url = j.get("source_url", "")
                job_country = j.get("job_country", "")
                # Anexa país como metadado na descrição para uso posterior no filtro
                if job_country:
                    country_meta = f"\n[PAÍS: {job_country.upper()}]"
                    desc = j["description"] + country_meta
                else:
                    desc = j["description"]
                cursor.execute('''
                    INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (job_id, sanitize(j["title"]), sanitize(j["company"]), sanitize(desc), sanitize(j["location"]), sanitize(j["modality"]), sanitize(j["source"]), source_url, pub_date.isoformat()))

            conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fallback heurístico (regex) — extrai dados mesmo quando a IA falha
# ---------------------------------------------------------------------------

_SALARY_RE = re.compile(r'(?:de|r\$|salary|salário|remuneração)?\s*(?:r\$?\s*)?([\d\.]+)[\.,]\s*(?:a\s*)?([\d\.]+)?[\.,]?\s*(?:mil|k|/\s*month|mês|anual|ao\s*ano)?', re.IGNORECASE)
_LEVEL_KEYWORDS = {
    "júnior": "Júnior", "junior": "Júnior", "estagiário": "Júnior", "estagiario": "Júnior", "estágio": "Júnior", "intern": "Júnior",
    "pleno": "Pleno", "middle": "Pleno",
    "sênior": "Sênior", "senior": "Sênior", "staff": "Sênior", "lead": "Sênior",
    "especialista": "Especialista", "expert": "Especialista", "principal": "Especialista", "architect": "Especialista", "arquiteto": "Especialista",
}


def is_relevant_heuristic(job_text: str, target_stack: List[str], seniority: str, location: str) -> bool:
    """Validação heurística de relevância — funciona mesmo sem IA."""
    text_lower = job_text.lower()

    # 1. Keywords do stack precisam aparecer
    if target_stack:
        stack_hits = sum(1 for s in target_stack if s.lower() in text_lower)
        if stack_hits == 0:
            return False
        # Pelo menos 1 skill do stack deve estar presente
    else:
        # Se não tem stack, considerar qualquer vaga com título razoável
        if len(job_text) < 50:
            return False

    # 2. Senioridade compatível
    seniority_lower = seniority.lower()
    for kw, level in _LEVEL_KEYWORDS.items():
        if kw in text_lower:
            if seniority_lower == "júnior" and level not in ("Júnior",):
                return False
            elif seniority_lower == "sênior" and level not in ("Sênior", "Especialista"):
                return False

    # 3. Remoto ou matching de localização
    if "remoto" in text_lower or "remote" in text_lower:
        return True

    return True  # Se passou pelos filtros acima, é relevante


def heuristic_extract(job_text: str) -> Dict[str, Any]:
    """Extrai dados estruturados via regex quando a IA falha."""
    if not job_text or not job_text.strip():
        return {"is_relevant": False, "role_level": None, "exp_years_min": None,
                "exp_years_max": None, "requirements": [], "nice_to_have": [],
                "certifications": [], "soft_skills": [], "salary_min": None,
                "salary_max": None, "currency": None}
    text_lower = job_text.lower()
    result: Dict[str, Any] = {
        "is_relevant": True,
        "role_level": None,
        "exp_years_min": None,
        "exp_years_max": None,
        "requirements": [],
        "nice_to_have": [],
        "certifications": [],
        "soft_skills": [],
        "salary_min": None,
        "salary_max": None,
        "currency": None,
    }

    # Nível do cargo
    for kw, level in _LEVEL_KEYWORDS.items():
        if kw in text_lower:
            result["role_level"] = level
            break

    # Anos de experiência — múltiplos padrões
    exp_patterns = [
        r'([\d]+)\s*[+\+]?\s*(?:anos?|años?)\s*(?:de\s*)?(?:experiência|experiencia|experiência)?',
        r'([\d]+)\s*[\-–—]\s*([\d]+)\s*(?:anos?|años?)',
        r'mínimo\s*de\s*([\d]+)\s*(?:anos?|años?)',
        r'([\d]+)\s*(?:\+)?\s*anos?\s*(?:\+\s*)?de\s*(?:experiência|experiencia)',
        r'([\d]+)\s*(?:a|até)\s*([\d]+)\s*(?:anos?|años?)',
    ]
    for pat in exp_patterns:
        m = re.search(pat, job_text, re.IGNORECASE)
        if m:
            if m.lastindex == 2:
                result["exp_years_min"] = float(int(m.group(1)))
                result["exp_years_max"] = float(int(m.group(2)))
            else:
                years = int(m.group(1))
                result["exp_years_min"] = float(years)
                result["exp_years_max"] = float(years + 2)
            break

    # Salário
    salary_matches = _SALARY_RE.findall(job_text)
    if salary_matches:
        for m in salary_matches:
            try:
                min_val = float(m[0].replace('.', '').replace(',', '.'))
                if m[1]:
                    max_val = float(m[1].replace('.', '').replace(',', '.'))
                else:
                    max_val = min_val * 1.5
                if 'mil' in job_text.lower() or 'k' in job_text.lower():
                    min_val *= 1000
                    max_val *= 1000
                if 'anual' in job_text.lower() or 'ao ano' in job_text.lower():
                    min_val /= 12
                    max_val /= 12
                result["salary_min"] = round(min_val, 2)
                result["salary_max"] = round(max_val, 2)
                result["currency"] = "BRL"
                break
            except (ValueError, IndexError):
                pass

    # Soft skills — lista expandida
    soft_skill_keywords = [
        "comunicação", "trabalho em equipe", "trabalho em equipa", "liderança",
        "proatividade", "resolução de problemas", "pensamento crítico",
        "flexibilidade", "adaptabilidade", "gestão de tempo",
        "autonomia", "criatividade", "orientação a resultados",
        "capacidade de análise", "facilidade de aprendizado",
        "collaboration", "teamwork", "problem solving",
    ]
    for ss in soft_skill_keywords:
        if ss in text_lower:
            result["soft_skills"].append(ss.capitalize())

    # Certificações expandidas
    cert_patterns = [
        r'\b(CRM|OAB|CREFITO|CRECI|COREN|CFM|OAB)\b',
        r'\b(CEH|CISS|CISM|PMP|ITIL|AWS|Azure|GCP|Kubernetes|Docker)\b',
        r'\b(BCC|BSc|MSc|MBA|PHD|Doutorado|Mestrado|Graduação|graduação|Engenharia)\b',
        r'\b(AWS Cloud|Solutions Architect|DevOps|Full Stack|Data Engineer)\b',
        r'\b(PSM|CSM|Scrum Master|Kanban)\b',
        r'\b(React|Angular|Vue|Node\.js|Python|Java|C#\b|C\+\+|Go|Ruby|PHP)\b\s+(Certified|Professional|Developer)',
    ]
    for pat in cert_patterns:
        for m in re.finditer(pat, job_text, re.IGNORECASE):
            result["certifications"].append(m.group(0).capitalize())

    # Requirements e nice_to_have por heurística
    lines = [l.strip() for l in job_text.split('\n') if l.strip()]
    for line in lines:
        ll = line.lower()
        if 'requisito' in ll or 'obrigatório' in ll or 'obrigatorio' in ll:
            # Extrai itens após dois-pontos ou vírgulas
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 3 and len(p) < 100:
                    result["requirements"].append(p)
        elif 'diferencial' in ll or 'desejável' in ll or 'nice to have' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 3 and len(p) < 100:
                    result["nice_to_have"].append(p)
        # Formação escolar
        elif 'formação' in ll or 'formacao' in ll or 'escolaridade' in ll or 'ensino' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 3 and len(p) < 100:
                    result["requirements"].append(p)
        # Idiomas
        elif 'idioma' in ll or 'idiomas' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 3 and len(p) < 100:
                    result["requirements"].append(p)
        # Experiência específica
        elif ('experiência' in ll or 'experiencia' in ll) and ('anos' not in ll):
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 5 and len(p) < 100 and 'anos' not in p:
                    result["requirements"].append(p)
        # Atribuições/como bônus
        elif 'atribuição' in ll or 'atribuicao' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) > 5 and len(p) < 100:
                    result["nice_to_have"].append(p)

    return result



# ---------------------------------------------------------------------------
# Pré-filtro por keywords — reduz o pool antes de enviar para IA
# ---------------------------------------------------------------------------

_LOCATION_MATCHES = {
    'remoto': ['remoto', 'remote', 'home office', 'trabalho remoto'],
    'nacional': ['nacional', 'brasil', 'todo o brasil'],
    'internacional': ['internacional', 'estrangeiro', 'foreign'],
    'sp': ['são paulo', 'sp', 'sampa'],
    'rj': ['rio de janeiro', 'rj'],
    'bh': ['belo horizonte', 'bh'],
    'curitiba': ['curitiba', 'ctba'],
    'porto alegre': ['porto alegre', 'poa'],
    'salvador': ['salvador', 'ba'],
    'fortaleza': ['fortaleza', 'ce'],
    'brasilia': ['brasília', 'brasil ia', 'df'],
    'manaus': ['manaus', 'am'],
    'recife': ['recife', 'pe'],
    'belém': ['belém', 'pa'],
}

_SENIORITY_MATCHES = {
    'júnior': ['júnior', 'junior', 'estagiário', 'estagiario', 'intern', 'trainee'],
    'pleno': ['pleno', 'middle', 'meio'],
    'sênior': ['sênior', 'senior', 'staff', 'lead', 'principal', 'arquiteto', 'architect'],
}

# Senioridades que DEVEM ser REJEITADAS quando o usuário selecionou outro nível
_SENIORITY_REJECTS = {
    'júnior': ['sênior', 'senior', 'staff', 'lead', 'principal', 'arquiteto', 'architect', 'especialista'],
    'pleno': ['sênior', 'senior', 'staff', 'lead', 'principal', 'arquiteto', 'architect', 'especialista'],
    'sênior': ['júnior', 'junior', 'estagiário', 'estagiario', 'intern', 'trainee'],
}


def _detect_job_seniority(job_text_lower: str) -> str:
    """Detecta a senioridade da vaga pelo texto. Retorna 'júnior', 'pleno', 'sênior' ou ''."""
    # Check in reverse priority: senior first, then junior
    for kw in ['sênior', 'senior', 'staff', 'lead', 'principal', 'arquiteto', 'architect', 'especialista']:
        if kw in job_text_lower:
            return 'sênior'
    for kw in ['pleno', 'middle']:
        if kw in job_text_lower:
            return 'pleno'
    for kw in ['júnior', 'junior', 'estagiário', 'estagiario', 'intern', 'trainee']:
        if kw in job_text_lower:
            return 'júnior'
    return ''


def map_time_window_to_date_posted(time_window: str) -> str:
    """Mapeia time_window do frontend para valor da API JSearch."""
    tw = time_window.lower().strip()
    if '7' in tw:
        return '3days'
    if '15' in tw:
        return 'week'
    if '30' in tw or '60' in tw or '90' in tw:
        return 'month'
    return 'all'


def detect_job_nationality(job_text: str, job_country: str = "", salary: str = "") -> str:
    """Detecta se uma vaga é nacional (BR) ou internacional.
    Rigoroso: mesmo com job_country='br', verifica sinais de internacional no texto."""
    text_lower = job_text.lower()
    salary_lower = salary.lower()

    # Sinais fortes de internacional NO TEXTO → rejeita mesmo com country=br
    # Check each individually
    for sig in ["usd", "dollar", "us dollar", "remote international",
                "work remotely abroad", "english required", "bilingual",
                "native english", "gbp", "€", "euro", "contractor us"]:
        if sig in text_lower:
            return "internacional"

    # Moeda indica internacional — verificar R$ PRIMEIRO para não confundir com dólar
    if "r$" in salary_lower or "real" in salary_lower or "brl" in salary_lower:
        return "nacional"
    if any(c in salary_lower for c in ["$", "usd", "euro", "€", "us dollar", "gbp", "£"]):
        return "internacional"

    # Idioma do texto — verificar idiomas estrangeiros ANTES de português,
    # pois palavras como "vaga", "remoto", "home office" existem em AMBOS os idiomas.
    # Só consideramos "nacional" se tivermos sinais fortes de português E NENHUM de espanhol.

    # --- Espanhol (verificar PRIMEIRO) ---
    # USAR APENAS palavras exclusivas do espanhol, evitar falsos positivos com português
    spanish_strong = [
        "español", "espanol", "trabajo", "atención",
        "representante", "servicio", "ventas", "seguros", "licencia",
        "otorgada", "llamamos", "sueldo", "contratación",
        "contratacion", "experiencia", "requerimientos", "responsabilidades",
        "remoto 100%", "concesiones", "resiliencia",
        # "jornada" REMOVIDO — bate com "jornadas" (português comum)
        # "operativa" REMOVIDO — existe em português também
        # "oportunidad" REMOVIDO — bate com "oportunidade" (PT)
        # "buscamos" REMOVIDO — existe em português também
        # "salario" REMOVIDO — ambíguo (PT também usa sem acento)
        # "auxiliar" REMOVIDO — existe em português também
    ]
    if any(s in text_lower for s in spanish_strong):
        return "internacional"

    # --- Holandês / Norueguês ---
    nordic_patterns = [
        "raadgever", "alreial", "miljø", "natur", "vilt", "kulturskolerådet",
        "innen", "stilling", "søker", "arbeid",
    ]
    if any(s in text_lower for s in nordic_patterns):
        return "internacional"

    # --- Francês ---
    # Usar delimitadores de espaço para evitar falsos positivos por substring
    french_patterns = [
        " français ", " française ", " francais ", " française ",
        " franco ", " emploi ", " requis ", " salaire ", " poste ",
        " experience ", "competitif", "candidate",
    ]
    if any(s in text_lower for s in french_patterns):
        return "internacional"

    # --- Inglês ---
    english_patterns = [
        "native english", "english required", "bilingual",
        "fluency", "required", "fluent", "salary in usd",
    ]
    if any(s in text_lower for s in english_patterns):
        return "internacional"

    # --- Geografia/localização — verificar ANTES de idioma, pois lugar vence palavra ---
    loc_country_signals = [
        "puerto rico", "puerto", " pr,", " pr ",
        "united states", "usa,", "usa ",
        "united kingdom", "uk,", "uk ", "londres", "inglaterra",
        "netherlands", "holanda", "mexico", "espanha",
        "canadá", "canada", "portugal", "frança",
        "trøndelag", "snåsa", "san german", "são tomé",
    ]
    for sig in loc_country_signals:
        if sig in text_lower:
            return "internacional"

    # --- Português (só agora — depois de descartar espanhol/idiomas estrangeiros e geografia) ---
    # Agora podemos usar "vaga" e "emprego" com segurança porque espanhol e geografia já foram descartados
    pt_brazilian_patterns = [
        "vaga", "emprego", "home office",
        "salário", "salario", "brasileiro", "brasileira", "clt", "pj",
        "híbrido", "hibrido", "remuneracao",
        "requisitos", "atribuições", "benefícios",
        "vínculo", "cnpj", "fgts", "13º", "13o",
        "vt", "vr", "vale transporte", "vale refeição",
        "carteira assinada", "regime clt",
    ]
    if any(p in text_lower for p in pt_brazilian_patterns):
        return "nacional"

    # Check de país como último recurso (só se não houve sinais de idioma no texto)
    if job_country:
        c = job_country.lower().strip()
        if c in ("br", "brazil", "brasil"):
            return "nacional"
        if c not in ("", None):
            return "internacional"

    # Default: se não tem sinais claros de nenhum lado, assume nacional (mais seguro)
    return "nacional"


def _keyword_score(job_text_lower: str, job_title: str, target_stack: List[str], seniority: str, location: str) -> int:
    """Retorna score de relevância permissivo. Nunca zera por falta de palavra exata."""
    if seniority.lower() == "nenhum":
        sen_matches = []
    else:
        sen_matches = _SENIORITY_MATCHES.get(seniority.lower(), [])

    if target_stack:
        keywords = target_stack
    else:
        keywords = [w for w in job_title.strip().split() if len(w) > 2]

    # Base score permissivo (1): Deixa todas as vagas capturadas irem para a IA decidir relevância
    score = 1

    if target_stack:
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', job_text_lower):
                score += 3
    else:
        for kw in keywords:
            if kw.lower() in job_text_lower:
                score += 2

    # SENIORITY — bônus se bater, mas NUNCA rejeita
    for sm in sen_matches:
        if sm in job_text_lower:
            score += 2
            break

    # Localização
    loc_matches = _LOCATION_MATCHES.get(location.lower().strip(), [])
    if loc_matches:
        for lm in loc_matches:
            if lm in job_text_lower:
                score += 2
                break
    elif 'remoto' in job_text_lower:
        score += 1

    return score


def _pre_filter_jobs(
    raw_jobs: List[tuple],
    target_stack: List[str],
    seniority: str,
    location: str,
    neg_list: List[str],
    max_jobs: int = _MAX_JOBS_FOR_ANALYSIS,
) -> List[tuple]:
    """Filtra vagas por keywords e modalidade antes de enviar para IA."""
    filtered = []

    selected_loc_lower = location.lower().strip()
    is_nacional = 'nacional' in selected_loc_lower and 'internacional' not in selected_loc_lower
    is_internacional = 'internacional' in selected_loc_lower
    modality_restriction = None
    if is_nacional or is_internacional:
        modality_restriction = 'remote'
    elif 'presencial' in selected_loc_lower:
        modality_restriction = 'onsite'
    elif 'híbrido' in selected_loc_lower or 'hibrido' in selected_loc_lower:
        modality_restriction = 'hybrid'

    for j in raw_jobs:
        job_id, title, company, description, loc, mod, source, source_url = j
        job_text_lower = (title + " " + description).lower()
        mod_lower = mod.lower()

        # Extrai job_country do metadado anexado na descrição
        _country_match = re.search(r'\[PAÍS:\s*(\w+)\]', description)
        job_country_val = _country_match.group(1) if _country_match else ""

        # Remove negative keywords (word boundary match)
        if neg_list:
            skip = False
            for nk in neg_list:
                if re.search(r'\b' + re.escape(nk.lower()) + r'\b', job_text_lower):
                    skip = True
                    break
            if skip:
                continue

        # NACIONALIDADE — rejeita vagas que não correspondem ao escopo
        if is_nacional or is_internacional:
            job_nationality = detect_job_nationality(description, job_country_val, "")
            if is_nacional and job_nationality == "internacional":
                continue
            if is_internacional and job_nationality == "nacional":
                continue

        # LOCALIZAÇÃO — rejeita vagas com localização física fora do Brasil
        if is_nacional:
            loc_text = (loc + " " + description).lower()
            _NON_BR_LOCATIONS = [
                "puerto rico", "puerto ", " pr,", " pr ",
                "united states", "usa,", "usa ",
                "united kingdom", "uk,", "uk ", "londres", "inglaterra",
                "netherlands", "holanda", "mexico", "espanha",
                "canadá", "canada", "portugal", "frança",
                "trøndelag", "snåsa", "san german",
            ]
            if any(l in loc_text for l in _NON_BR_LOCATIONS):
                continue

        # MODALIDADE — ativada para filtrar vagas irrelevantes
        if modality_restriction == 'remote':
            if 'presencial' in job_text_lower or 'no local' in job_text_lower:
                continue
        elif modality_restriction == 'onsite':
            if 'remoto' in job_text_lower or 'home office' in job_text_lower:
                continue
        elif modality_restriction == 'hybrid':
            if ('exclusivamente remoto' in job_text_lower) or ('exclusivamente presencial' in job_text_lower):
                continue

        score = _keyword_score(job_text_lower, title, target_stack, seniority, location)
        if score > 0:
            job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"
            filtered.append((score, job_id, title, company, description, loc, mod, source, source_url, job_text))

    # Fallback: Se o pré-filtro descartou tudo (0 vagas) mas existem vagas brutas,
    # aplica fallback COM filtro de localização (não adiciona vagas de países errados)
    if not filtered and raw_jobs:
        logger.warning(f"[MARKET] Pré-filtro descartou todas as {len(raw_jobs)} vagas — aplicando fallback com filtro de localização")
        for j in raw_jobs[:max_jobs]:
            job_id, title, company, description, loc, mod, source, source_url = j
            job_text_lower = (title + " " + description).lower()
            # Re-aplica filtro básico de localização/idioma no fallback
            skip = False
            _FALLBACK_SKIP = [
                "puerto rico", "puerto ", " pr,", " pr ",
                "united states", "usa,", "usa ",
                "united kingdom", "uk,", "uk ", "londres", "inglaterra",
                "netherlands", "holanda", "mexico", "espanha",
                "canadá", "canada", "portugal", "frança",
                "trøndelag", "snåsa", "san german",
                "español", "espanol", "trabajo", "agendador", "servicio",
            ]
            for s in _FALLBACK_SKIP:
                if s in job_text_lower:
                    skip = True
                    break
            if skip:
                continue
            job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"
            filtered.append((1, job_id, title, company, description, loc, mod, source, source_url, job_text))

    filtered.sort(key=lambda x: -x[0])
    return [(f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9]) for f in filtered[:max_jobs]]


# ---------------------------------------------------------------------------
# Extração com IA (vaga única)
# ---------------------------------------------------------------------------

def extract_job_with_ai(client: OpenAI, selected_model: str, job_text: str, target_stack: List[str], seniority: str = "Pleno", location: str = "Remoto Nacional") -> Dict[str, Any]:
    """Usa IA para extrair dados estruturados de uma vaga de forma rigorosa."""
    job_title_context = target_stack[0] if target_stack else "diversas áreas"
    prompt = f"""EXTRAIA TODOS OS DADOS POSSÍVEIS desta vaga.
Seja O MAIS COMPLETO POSSÍVEL — extraia TUDO que a vaga menciona como requisito, qualificação ou competência.

CATEGORIAS E O QUE INCLUIR (Seja 100% AGNÓSTICO a área):
- requirements: Exatamente o que a vaga pede como requisito obrigatório ou qualificação.
  * Se for TI: linguagens de programação, frameworks, bancos de dados, ferramentas (Git, Docker, AWS).
  * Se for Mecânica: tipos de motores, ferramentas, sistemas (VE, elétrico, hidráulico), certificações (ANECA, cinto vermelho).
  * Se for outra área: extraia especificamente o que for obrigatório mencionado no texto.
- soft_skills: traços comportamentais e habilidades interpessoais (comunicação, liderança, teamwork, adaptabilidade).
- certifications: certificações formais ou títulos profissionais da área específica da vaga.
- nice_to_have: diferenciais mencionados como desejáveis mas não obrigatórios na descrição.
- languages: idiomas mencionados com nível de fluência se presente.

O QUE NÃO INCLUIR:
- Benefícios da empresa: vale transporte, vale alimentação, plano de saúde, Gympass
- Modalidade: remoto, híbrido, presencial, home office
- Processos/rotina: code review, standup, reunião, troubleshooting
- Responsabilidades do cargo: o que a pessoa faz no dia a dia

O QUE NÃO INCLUIR:
- Benefícios da empresa: vale transporte, vale alimentação, plano de saúde, Gympass
- Modalidade: remoto, híbrido, presencial, home office
- Processos/rotina: code review, standup, reunião
- Responsabilidades do cargo: o que a pessoa faz no dia a dia
- Anos de experiência: vá para exp_years_min/exp_years_max

RELEVÂNCIA: is_relevant=TRUE se o cargo for compatível com o perfil do usuário.

Perfil: cargo={job_title_context}, stack={", ".join(target_stack)}, seniority={seniority}, location={location}

Descrição da vaga:
{job_text}

Retorne o JSON abaixo com TODOS os campos preenchidos:
{{
  "is_relevant": true|false,
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "requirements": ["Excel intermediário", "Pacote Office", "Inglês básico"],
  "nice_to_have": ["Conhecimento em SAP"],
  "certifications": ["OAB"],
  "soft_skills": ["organização", "proatividade"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}}"""
    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=120,
        )
        content = response.choices[0].message.content or "{}"

        # Strip thinking tag se houver
        content = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', content, flags=re.DOTALL).strip()
        content = re.sub(r'｜thinking｜.*?／｜thinking｜', '', content, flags=re.DOTALL).strip()
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

        data = json.loads(content)
        return data
    except Exception as e:
        logger.warning(f"[WARN] extract_job_with_ai falhou, vaga ignorada: {e}")
        return {}


# ---------------------------------------------------------------------------
# Extração em lote (múltiplas vagas por chamada — muito mais rápido)
# ---------------------------------------------------------------------------


def _sanitize_requirements(item: Dict[str, Any]) -> Dict[str, Any]:
    """Safety net: remove obvious non-skills from requirements and soft_skills."""
    import re as _re

    _SKILL_MAX_LEN = 80  # itens muito longos são frases, não skills

    # === REGRAS DE FILTRAGEM ===

    def _is_garbage(term: str) -> bool:
        """Retorna True se o termo for lixo (não skill)."""
        t = term.strip()
        if len(t) < 2 or len(t) > _SKILL_MAX_LEN:
            return True

        t_lower = t.lower()

        # Benefícios da empresa
        if any(kw in t_lower for kw in [
            "auxílio educação", "auxilio educacao", "auxilio", "vale ", "vr/va", "va/vr",
            "plano de saúde", "plano de saude", "plano odontológico", "plano odontologico",
            "refeição", "alimentação", "alimentacao", "vale transporte", "vale combustível",
            "vale alimentação", "vale refeição",
            "bônus", "bonus", "profit share", "stock options", "stock option",
            "seguro de vida", "previdência", "previdencia",
            "participação nos lucros", "participacao nos lucros",
            "gympass", "gypass", "goldpass", "santander student",
            "carteira refeição", "carteira alimentação",
            "reembolso", "day off", "psychological support",
            "ferias", "férias", "13º", "13o", "decimo terceiro",
            "fgts", "ctps",
        ]):
            return True

        # Modalidade / local
        if any(kw in t_lower for kw in [
            "remoto", "hibrido", "híbrido", "home office", "presencial",
            "flexível", "flexivel", "flexibilidade",
            "modelo híbrido", "modelo hibrido",
            "trabalho remoto", "trabalho hibrido", "trabalho híbrido",
            "escritório híbrido", "escritorio hibrido",
            "local: ", "localidade", "região metropolitana", "regiao metropolitana",
        ]):
            return True

        # Processos / rotina
        if any(kw in t_lower for kw in [
            "code review", "pair programming", "pair program", "standup", "retro",
            "reuniões semanais", "reuniões diárias", "reuniões de equipe",
            "cerimônia", "cerimonia", "sprint",
            "ambiente ágil", "ambiente agil",
        ]):
            return True

        # Anos de experiência (vai para exp_years, não requirements)
        if _re.search(r'[\d]+\s*(?:a\s+[\d]+)?\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)', t_lower):
            return True
        if _re.search(r'[\d]+\s*[\+]\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)', t_lower):
            return True
        if _re.search(r'experiência\s+(?:de\s+)?[\d]+\s*anos?', t_lower):
            return True
        if _re.search(r'mínimo\s*de\s*[\d]+\s*anos?', t_lower):
            return True

        # Frases longas / compostas (múltiplos conceitos)
        # Itens com "." (ponto final) são provavelmente frases
        if '.' in t and t.count('.') > 1:
            return True
        # Itens com "; " ou "- " no meio são listas
        if '; ' in t or ('- ' in t and len(t) > 30):
            return True
        # Itens com "ambiente", "será considerado", "diferencial" no contexto de benefício
        if any(kw in t_lower for kw in [
            "ambiente ágil", "ambiente agil", "sprints", "sprint",
            "será considerado", "considerado diferencial",
            "conhecimentos obrigatórios", "conhecimentos obrigatorios",
            "graduação completa", "graduação", "formação completa",
            "certificações na área", "certificacoes na area",
            "pós-graduação", "pós graduação", "pós-grad", "pósgrad",
        ]):
            return True

        # Benefícios em inglês
        if any(kw in t_lower for kw in [
            "health insurance", "dental insurance", "vision insurance",
            "life insurance", "401k", "retirement",
            "paid time off", "pto", "paid leave",
            "wellness", "gym", "fitness",
            "tuition reimbursement", "education assistance",
            "stock options", "equity", "rsu",
        ]):
            return True

        return False

    for field in ("requirements", "soft_skills", "nice_to_have"):
        if field not in item or not isinstance(item[field], list):
            continue
        original = item[field]
        cleaned = [term for term in original if not _is_garbage(term)]
        item[field] = cleaned
    return item


# ---------------------------------------------------------------------------
# Safety net: garante que skills administrativos comuns não sejam perdidos
# ---------------------------------------------------------------------------

# Palavras-chave que indicam vaga administrativa
_ADMIN_KEYWORDS = [
    "administrativo", "administrativa", "assistente", "escritório", "escritorio",
    "clerical", "secretário", "secretaria", "recepcionista", "analista",
    "vaga", "emprego", "contratação", "contratacao", "departamento",
    "cartório", "financeiro", "contábil", "comercial", "operacional",
    "atendimento", "protokol", "arquiv", "escritur", "bancário", "bancaria",
]

# Skills administrativos comuns mapeados para termos canônicos
_ADMIN_COMMON_SKILLS = [
    (r"\bword\b", "Word"),
    (r"\bpower\s*point\b", "PowerPoint"),
    (r"\bpacote\s+office\b", "Excel"),
    (r"\bexcel\b", "Excel"),
    (r"\binformática\b", "Informática"),
    (r"\binformático\b", "Informática"),
    (r"\bdigitação\b", "Digitação"),
    (r"\bredação\b", "Redação"),
    (r"\bportuguês\s+(escrito|escrita|fluente|avançado|avancado)\b", "Português"),
    (r"\binglês\b", "Inglês"),
    (r"\benglish\b", "Inglês"),
    (r"\bensino\s+médio\b", "Ensino Médio"),
    (r"\bensino\s+superior\b", "Ensino Superior"),
    (r"\bsuperior\s+completo\b", "Ensino Superior Completo"),
    (r"\bformação\s+superior\b", "Ensino Superior"),
    (r"\bgraduação\b", "Ensino Superior"),
    (r"\bexperiência\s+(?:de\s+)?(?:\d+\s*(?:e|até)\s*)?\d*\s*(?:anos?|años?)?\b", "Experiência na Área"),
    (r"\bexperiencia\s+(?:na)?\s*area\b", "Experiência na Área"),
    (r"\batenção\s+a\s+detalhes\b", "Atenção a Detalhes"),
    (r"\bolho\s+ao\s+detalhe\b", "Atenção a Detalhes"),
    (r"\banálise\s+de\s+dados\b", "Análise de Dados"),
    (r"\banalise\s+de\s+dados\b", "Análise de Dados"),
    (r"\borganiza(?:ção|ao)\b", "Organização"),
    (r"\bcomunicação\s+(?:efetiva|interpessoal|escrita|oral)\b", "Comunicação"),
    (r"\bcomunicação\b", "Comunicação"),
    (r"\bproatividade\b", "Proatividade"),
    (r"\btrabalho\s+em\s+equipe\b", "Trabalho em Equipe"),
    (r"\batendimento\s+ao\s+público\b", "Atendimento ao Público"),
    (r"\batendimento\s+telefrônico\b", "Atendimento Telefônico"),
    (r"\bprotocolo\b", "Protocolo"),
    (r"\barquiv\b", "Arquivamento"),
    (r"\bmicrosoft\s+outlook\b", "Outlook"),
    (r"\boutlook\b", "Outlook"),
    (r"\bgoogle\s+docs\b", "Google Docs"),
    (r"\bgoogle\s+sheets\b", "Google Sheets"),
    (r"\bgoogle\s+suite\b", "Google Workspace"),
    (r"\bflexibilidade\b", "Flexibilidade"),
    (r"\bgestão\s+de\s+tempo\b", "Gestão de Tempo"),
    (r"\bgestao\s+de\s+tempo\b", "Gestão de Tempo"),
    (r"\bbilingue\b", "Bilíngue"),
    (r"\binglês\s+(básico|basico|intermediário|intermediario|avançado|avancado|fluenta|nativo)\b", "Inglês"),
]


def _ensure_common_skills(item: Dict[str, Any], job_text: str) -> Dict[str, Any]:
    """Garante que skills administrativos comuns sejam extraídos se presentes no texto.
    Roda após a IA para capturar o que ela perdeu."""
    if not job_text or not item:
        return item

    text_lower = job_text.lower()
    requirements = set(item.get("requirements", []))
    nice_to_have = set(item.get("nice_to_have", []))
    all_existing = requirements | nice_to_have

    # Verifica se é vaga administrativa
    is_admin = any(kw in text_lower for kw in _ADMIN_KEYWORDS)

    for pattern, canonical in _ADMIN_COMMON_SKILLS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            # Normaliza o canônico para comparação
            canon_lower = canonical.lower()
            # Verifica se já existe algo similar nos requisitos
            already_has = False
            for existing in all_existing:
                if canon_lower in existing.lower() or existing.lower() in canon_lower:
                    already_has = True
                    break
            if not already_has:
                # Adiciona ao requirements se for um skill básico, senão nice_to_have
                req_skills = {"Word", "Excel", "Pacote Office", "PowerPoint", "Informática", "Digitação",
                              "Ensino Médio", "Ensino Superior", "Ensino Superior Completo",
                              "Inglês", "Português", "Atenção a Detalhes", "Redação",
                              "Análise de Dados", "Organização", "Comunicação",
                              "Trabalho em Equipe", "Proatividade", "Flexibilidade",
                              "Gestão de Tempo", "Protocolo", "Arquivamento",
                              "Outlook", "Google Workspace"}
                if canonical in req_skills:
                    requirements.add(canonical)
                else:
                    nice_to_have.add(canonical)

    item["requirements"] = sorted(requirements)
    item["nice_to_have"] = sorted(nice_to_have)
    return item


def _extract_languages(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detecta idiomas nos requirements/nice_to_have e os separa para o campo languages."""
    import re as _re

    # Padrões de idioma: nome do idioma + nível (opcional)
    # Aceita: "Inglês Avançado", "Inglês C1", "B2 Inglês", "Português (Nativo)", "Intermediate Spanish", etc.
    language_name_pattern = _re.compile(
        r'''(?:inglês|english|espanhol|spanish|português|portuguese|francês|french|alemão|german|
 italiano|italian|holandês|dutch|japonês|japanese|chinês|chinese|coreano|korean|
 árabe|arabic|russo|russian|italiano| italian|mandarim|mandarin|turco|turkish|
 polonês|polish|hindi|hebra|hebrew|sueco|swedish|norueguês|norwegian|
 grego|greek|tâmil|tamil|tailandês|thai|vietnamita|vietnamese)''',
        _re.IGNORECASE
    )

    # Padrões de nível
    cefr_levels = _re.compile(
        r'\b(a1|a2|b1|b2|c1|c2)\b',
        _re.IGNORECASE
    )
    level_words = _re.compile(
        r'''\b(básico|basico|intermediário|intermediario|avançado|avancado|
 avançado|avançada|fluente|nativo|nativa|elementar|proficiente|
 native|fluent|advanced|intermediate|beginner|basic|upper|upper.?intermediate)\b''',
        _re.IGNORECASE
    )

    languages = []
    for field in ("requirements", "nice_to_have"):
        if field not in item or not isinstance(item[field], list):
            continue
        original = item[field]
        cleaned = []
        for term in original:
            term_stripped = term.strip()
            if language_name_pattern.search(term_stripped):
                # Extrai nome do idioma
                lang_match = language_name_pattern.search(term_stripped)
                lang_name = lang_match.group(0)
                # Normaliza nome
                lang_name_lower = lang_name.lower().strip()
                name_map = {
                    "inglês": "Inglês", "english": "Inglês",
                    "espanhol": "Espanhol", "spanish": "Espanhol",
                    "português": "Português", "portuguese": "Português",
                    "francês": "Francês", "french": "Francês",
                    "alemão": "Alemão", "german": "Alemão",
                    "italiano": "Italiano", "italian": "Italiano",
                    "holandês": "Holandês", "dutch": "Holandês",
                    "japonês": "Japonês", "japanese": "Japonês",
                    "chinês": "Chinês", "chinese": "Chinês",
                }
                display_name = name_map.get(lang_name_lower, lang_name.capitalize())

                # Extrai nível
                level = None
                cefr = cefr_levels.search(term_stripped)
                if cefr:
                    level = cefr.group(1).upper()
                else:
                    lvl_match = level_words.search(term_stripped)
                    if lvl_match:
                        lvl_lower = lvl_match.group(1).lower()
                        level_map = {
                            "básico": "Básico", "basico": "Básico", "beginner": "Básico", "basic": "Básico",
                            "intermediário": "Intermediário", "intermediario": "Intermediário", "intermediate": "Intermediário",
                            "avançado": "Avançado", "avancado": "Avançado", "advanced": "Avançado",
                            "fluente": "Fluente", "fluent": "Fluente",
                            "nativo": "Nativo", "nativa": "Nativo", "native": "Nativo",
                            "elementar": "Elementar", "proficiente": "Proficiente",
                        }
                        level = level_map.get(lvl_lower, lvl_match.group(1).capitalize())

                languages.append({
                    "name": display_name,
                    "level": level,
                    "raw": term_stripped,
                })
            else:
                cleaned.append(term)
        item[field] = cleaned

    return languages


_BATCH_SIZE = 10  # reduzido de 25 para 10 para evitar APITimeoutError da OpenAI com 25 descrições longas

# Controla se o warning de batch mismatch já foi logado na execução atual
_batch_mismatch_warned = False


def _parse_batch_response(data: Any, expected: int) -> List[Dict[str, Any]]:
    """Tenta extrair a lista de jobs da resposta da IA, lidando com formatos variados."""
    # Caso 1: resposta já é uma lista
    if isinstance(data, list):
        valid = [item for item in data if isinstance(item, dict)]
        return valid
    # Caso 2: resposta é um dict — tenta extrair array de chaves conhecidas
    if isinstance(data, dict):
        for key in ("results", "data", "jobs", "extraction", "vagas"):
            if key in data and isinstance(data[key], list):
                return [item for item in data[key] if isinstance(item, dict)]
        # Se o dict parece um job individual, retorna como lista de 1
        # O chamador deve lidar com a discrepância de tamanho
        if "requirements" in data or "soft_skills" in data:
            return [data]
    # Caso 3: não consegue extrair nada
    return []


def _pad_missing_jobs(
    data: List[Dict[str, Any]],
    expected: int,
    client: OpenAI,
    selected_model: str,
    job_texts: List[str],
    target_stack: List[str],
    seniority: str,
    location: str,
) -> List[Dict[str, Any]]:
    """Retorna apenas os jobs que a IA retornou — sem fabricar dados."""
    result = data[:expected]
    if len(result) < expected:
        logger.warning(
            f"[INFO] Batch retornou {len(result)} jobs de {expected} esperados. "
            f"Somente dados reais serão usados."
        )
    return result


def _fallback_extract_jobs(
    client: OpenAI,
    selected_model: str,
    job_texts: List[str],
    target_stack: List[str],
    seniority: str,
    location: str,
) -> List[Dict[str, Any]]:
    """Fallback: tenta IA individual, se falhar usa heurística."""
    results = []
    for job_text in job_texts:
        result = None
        try:
            result = extract_job_with_ai(client, selected_model, job_text, target_stack)
        except Exception:
            pass
        # Se IA falhou, usou poucos requisitos, ou é vaga administrativa com poucos skills
        reqs_count = len(result.get("requirements", [])) if result else 0
        text_lower = job_text.lower()
        is_admin_job = any(kw in text_lower for kw in _ADMIN_KEYWORDS)
        should_fallback = (
            not result or
            reqs_count < 2 or
            (is_admin_job and reqs_count < 5)
        )
        if should_fallback:
            result = heuristic_extract(job_text)
        if result:
            results.append(result)
    return results


def extract_jobs_batched(
    client: OpenAI,
    selected_model: str,
    job_texts: List[str],
    target_stack: List[str],
    seniority: str = "Pleno",
    location: str = "Remoto Nacional",
    neg_list: List[str] = None,
) -> List[Dict[str, Any]]:
    """Chama a IA UMA vez com N vagas e devolve uma lista de resultados."""
    if not job_texts:
        return []

    job_title_context = target_stack[0] if target_stack else "diversas áreas"
    stack_str = ", ".join(target_stack) if target_stack else "diversas áreas"
    neg_list_str = ", ".join(neg_list) if neg_list else "nenhuma"

    jobs_section = "\n\n".join(
        f"--- VAGA {i+1} ---\n{txt}" for i, txt in enumerate(job_texts)
    )

    start_time = time.time()

    prompt = f"""EXTRAIA TODOS OS DADOS POSSÍVEIS de CADA vaga abaixo.
Seja O MAIS COMPLETO POSSÍVEL — extraia TUDO que a vaga menciona como requisito, qualificação ou competência.

CATEGORIAS E O QUE INCLUIR:
- requirements: QUALQUER coisa que a vaga pede como requisito ou qualificação. Inclua:
  * Ferramentas/software: Excel, Word, PowerPoint, Pacote Office, SAP, Salesforce, Outlook, etc.
  * Idiomas: Inglês, Espanhol, Francês, etc. (com nível se mencionado: básico, intermediário, avançado)
  * Formação: Ensino Médio, Ensino Superior completo, Cursando faculdade, Graduação, etc.
  * Conhecimento técnico: SQL, Python, Power BI, Google Analytics, etc.
  * Habilidades técnicas: Digitação, Redação, Análise de dados, Contabilidade, Protocolo, etc.
  * Experiência específica: Gestão de contratos, elaboração de editais, atendimento ao público, etc.
  * Para vagas administrativas/assistenciais: SEMPRE inclua os skills que a vaga menciona —
    Word, Excel, PowerPoint, Pacote Office, Digitação, Informática, Organização, Redação,
    Atendimento, Protocolo, Arquivamento, etc.
  * Anos de experiência: SE a vaga pedir "X anos de experiência", coloque em exp_years_min/exp_years_max ABAIXO, NÃO em requirements.
- soft_skills: Traços comportamentais e habilidades interpessoais QUE A VAGA MENZIONIAR.
  * Exemplos: proatividade, comunicação, trabalho em equipe, liderança, organização,
    atenção a detalhes, iniciativa, flexibilidade, resolução de problemas, ética.
  * Se a vaga diz "precisamos de alguém proativo", inclua "Proatividade" nos soft_skills.
  * NUNCA coloque soft_skills em requirements — soft_skills vão APENAS no campo soft_skills.
- certifications: Certificações formais e títulos profissionais MENCIONADOS NA VAGA.
  * Exemplos: OAB, CREFITO, PMP, AWS, Scrum Master, CEH, Excel Expert, etc.
  * Se a vaga diz "desejável certificação PMP", coloque em certifications.
- nice_to_have: Diferenciais mencionados como desejáveis mas NÃO obrigatórios.
  * Palavras-chave que indicam nice_to_have: "desejável", "diferencial", "vantajoso",
    "não obrigatório", "não será considerado", "será um diferencial", "ter como diferencial".
  * Exemplos: "desejável conhecimento em SAP", "diferencial ter inglês avançado"
  * SEMPRE que possível, separe requisitos obrigatórios (requirements) dos desejáveis (nice_to_have).

O QUE NÃO INCLUIR (NUNCA coloque nos campos acima):
- Benefícios da empresa: vale transporte, vale alimentação, plano de saúde, Gympass, bônus
- Modalidade: remoto, híbrido, presencial, home office
- Processos/rotina: code review, standup, reunião, pair programming
- Responsabilidades do cargo: o que a pessoa faz no dia a dia (atender telefone, organizar arquivos)
- Anos de experiência: vá para exp_years_min/exp_years_max
- Salário: vá para salary_min/salary_max

IMPORTANTE: Quanto mais itens extrair, melhor. Não seja seletivo — se a vaga menciona, extraia.

IMPORTANTE: AGRUPE variações do mesmo skill nos arrays. Exemplos:
- "Excel avançado", "Excel básico" → inclua apenas "Excel"
- "Pacote Office", "MS Excel" → inclua apenas "Excel"  
- "Inglês avançado", "Inglês básico" → inclua apenas "Inglês"
- "Proatividade", "Pró-atividade" → inclua apenas "Proatividade"
- "Word", "Microsoft Word" → inclua apenas "Word"
- "MySQL", "MySQL Server" → inclua apenas "MySQL"
- "Python 3", "Python 3.10" → inclua apenas "Python"
NÃO inclua variações duplicadas: use apenas o termo canônico.

RELEVÂNCIA — is_relevant=TRUE para TODAS as vagas que:
- Correspondem ao cargo buscado (mesma função ou similar)
- São do Brasil (nacionais)
- NÃO contêm palavras negativas na descrição

is_relevant=FALSE APENAS se:
- A vaga for de outro país/idioma
- O cargo for completamente diferente do buscado
- Houver termo negativo na descrição
- A vaga ser claramente spam/fraude

IMPORTANTE: Se o pré-filtro já manteve a vaga, ela É relevante. A IA só deve rejeitar vagas claramente fora do perfil.

Perfil: cargo={job_title_context}, stack={stack_str}, seniority={seniority}, location={location}
Palavras negativas: {neg_list_str if neg_list else "nenhuma"}

{jobs_section}

Retorne EXATAMENTE {len(job_texts)} objetos em um array JSON. Formato de cada objeto:
[{{
  "is_relevant": true|false,
  "rejection_reason": "string|null",
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "requirements": ["Extraia a stack técnica real", "Ferramentas específicas", "Conhecimentos obrigatórios"],
  "nice_to_have": ["Diferenciais reais da vaga"],
  "certifications": ["Certificações específicas"],
  "soft_skills": ["Habilidades comportamentais"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}}]

REGRAS OBRIGATÓRIAS:
1. Extraia EXATAMENTE o que está no texto. Se for vaga de TI, extraia linguagens, frameworks e bancos de dados. Se for Mecânico, extraia ferramentas e tipos de motores.
2. NUNCA invente "Excel" ou "Informática" se não estiver explicitamente no texto.
3. Identifique se a vaga é REALMENTE relevante para o cargo e stack solicitados.
4. Se a vaga pedir anos de experiência, extraia os números para exp_years_min/max.
}}]"""
    try:
        # Define timeout dinâmico proporcional ao número de vagas no lote (15s por vaga, min 60s, max 300s)
        calc_timeout = max(60, min(400, len(job_texts) * 15))  # Aumentado timeout máximo
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=calc_timeout,
        )
        content = response.choices[0].message.content or "[]"
        # Remove <|thinking|> tags (ASCII pipes)
        content = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', content, flags=re.DOTALL).strip()
        # Remove ｜thinking｜ tags (fullwidth pipes, common in some models)
        content = re.sub(r'｜thinking｜.*?／｜thinking｜', '', content, flags=re.DOTALL).strip()
        # Remove any remaining <thinking>...</thinking>
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()
        raw = json.loads(content)
        data = _parse_batch_response(raw, len(job_texts))
        elapsed = (time.time() - start_time) * 1000

        # Log raw response for first batch (debug level)
        if len(job_texts) <= 12:
            logger.debug(f"[DEBUG] AI response parsed {len(data)} items, expected {len(job_texts)}. Preview: {content[:500]}...")

        # Se a IA retornou menos jobs que o esperado, truncar — sem fabricar dados
        if len(data) < len(job_texts):
            logger.warning(
                f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. "
                f"Jobs ausentes serão ignorados (sem dados fabricados)."
            )
            data = _pad_missing_jobs(data, len(job_texts), client, selected_model, job_texts, target_stack, seniority, location)
        elif len(data) > len(job_texts):
            # IA retornou mais jobs que o esperado — truncar
            logger.warning(
                f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. Truncating to {len(job_texts)}."
            )
            data = data[:len(job_texts)]

        # Log AI call
        try:
            log_ai_call(
                endpoint="/api/market/analyze (AI batch)",
                method="POST",
                status_code=200,
                duration_ms=round(elapsed, 1),
                model=selected_model,
                api_key_preview="ia_call...",
                request_body={"batch_size": len(job_texts), "model": selected_model},
                response_summary=f"Extracted {len(data)} jobs",
            )
        except Exception:
            pass

        if len(data) == len(job_texts):
            return data
        # Se ainda houver discrepância após padding, fazer fallback heurístico completo
        global _batch_mismatch_warned
        if not _batch_mismatch_warned:
            logger.warning(
                f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. "
                f"Falling back to per-job extraction."
            )
            _batch_mismatch_warned = True
        return _fallback_extract_jobs(client, selected_model, job_texts, target_stack, seniority, location)
    except Exception as e:
        logger.warning(f"[WARN] batch extraction failed: {e}")
        traceback.print_exc()
        return _fallback_extract_jobs(client, selected_model, job_texts, target_stack, seniority, location)


def run_market_analysis(
    db_file: Path,
    client: OpenAI,
    selected_model: str,
    job_title: str,
    target_stack: str,
    seniority: str,
    location: str,
    time_window: str,
    negative_keywords: str = "",
    jsearch_api_keys: List[str] = None
) -> Dict[str, Any]:
    """Executa o pipeline completo de Inteligência de Mercado."""

    # 1. Garante vagas de amostragem no DB (limpa buscas anteriores para evitar dados de outra área)
    init_market_db(db_file)
    conn = sqlite3.connect(db_file)
    conn.cursor().execute("DELETE FROM market_raw_jobs")
    conn.cursor().execute("DELETE FROM market_jobs")
    conn.commit()
    date_posted = map_time_window_to_date_posted(time_window)
    generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys, date_posted=date_posted, location=location)

    stack_list = [s.strip() for s in target_stack.split(",") if s.strip()]
    neg_list = [k.strip().lower() for k in negative_keywords.split(",") if k.strip()]

    # 2. Coleta todas as vagas
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, description, location, modality, source, source_url FROM market_raw_jobs")
    raw_jobs = cursor.fetchall()

    total_jobs = len(raw_jobs)
    if total_jobs == 0:
        return {
            "summary": {
                "job_title": job_title,
                "total_jobs_scanned": 0,
                "relevant_jobs_analyzed": 0,
                "jsearch_status": "no_jobs_found",
                "jsearch_message": "Nenhuma vaga encontrada na busca. Verifique as chaves da JSearch ou amplie os filtros.",
            },
            "statistics": {
                "required_technologies": [],
                "desirable_technologies": [],
                "exp_years_median": 0,
                "exp_years_distribution": {},
                "modalities": [],
                "top_soft_skills": [],
                "top_certifications": [],
                "top_languages": [],
            },
            "sample_jobs": [],
        }

    # 3. Pré-filtro por keywords — reduz o pool antes de enviar para IA
    pending = _pre_filter_jobs(raw_jobs, stack_list, seniority, location, neg_list, max_jobs=_MAX_JOBS_FOR_ANALYSIS)
    total_scanned = len(raw_jobs)
    print(f"[MARKET] Pré-filtro: {total_scanned} vagas → {len(pending)} vagas para análise IA")

    # Processa em lotes
    extracted_jobs = []
    relevant_count = 0
    import uuid
    analysis_start = time.time()

    for batch_start in range(0, len(pending), _BATCH_SIZE):
        batch = pending[batch_start:batch_start + _BATCH_SIZE]
        job_texts = [item[8] for item in batch]

        batch_results = extract_jobs_batched(client, selected_model, job_texts, stack_list, seniority=seniority, location=location, neg_list=neg_list)

        for idx, (job_id, title, company, description, loc, mod, source, source_url, job_text) in enumerate(batch):
            extracted = batch_results[idx] if idx < len(batch_results) else {}
            extracted = _sanitize_requirements(extracted)
            # Extração agora é 100% baseada no texto real da vaga pela IA, sem injeção forçada de skills.
            # Extract languages from requirements/nice_to_have
            extracted_languages = _extract_languages(extracted)
            is_rel = extracted.get("is_relevant", False)

            reqs_norm = sorted(set(normalize_skill(t) for t in extracted.get("requirements", []) if normalize_skill(t)))
            nice_norm = sorted(set(normalize_skill(t) for t in extracted.get("nice_to_have", []) if normalize_skill(t)))

            # Debug: log first batch results
            if batch_start == 0 and idx < 3:
                logger.debug(f"[DEBUG] Job {idx+1}: title={title[:50]}, is_rel={is_rel}, reqs={reqs_norm[:3]}, nice={nice_norm[:3]}, soft={extracted.get('soft_skills', [])[:3]}, certs={extracted.get('certifications', [])[:3]}")

            if is_rel:
                relevant_count += 1
                new_id = str(uuid.uuid4())
                now_str = datetime.now().isoformat()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO market_jobs (id, raw_job_id, title, company, location, modality, source, source_url,
                        is_relevant, rejection_reason, requirements, nice_to_have, role_level, exp_years_min, exp_years_max,
                        soft_skills, certifications, salary_min, salary_max, currency, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_id, job_id, title, company, loc, mod, source, source_url or "", 1,
                    extracted.get("rejection_reason"),
                    json.dumps(reqs_norm), json.dumps(nice_norm),
                    extracted.get("role_level"),
                    extracted.get("exp_years_min"), extracted.get("exp_years_max"),
                    json.dumps(extracted.get("soft_skills", [])),
                    json.dumps(extracted.get("certifications", [])),
                    extracted.get("salary_min"), extracted.get("salary_max"),
                    extracted.get("currency"), now_str
                ))
                conn.commit()

            rejection_reason = extracted.get("rejection_reason") if not is_rel else None
            extracted_jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": loc,
                "modality": mod,
                "source": source,
                "source_url": source_url or "",
                "is_relevant": is_rel,
                "rejection_reason": rejection_reason,
                "requirements": reqs_norm,
                "nice_to_have": nice_norm,
                "role_level": extracted.get("role_level"),
                "exp_years_min": extracted.get("exp_years_min"),
                "exp_years_max": extracted.get("exp_years_max"),
                "soft_skills": extracted.get("soft_skills", []),
                "certifications": extracted.get("certifications", []),
                "languages": extracted_languages,
                "salary_min": extracted.get("salary_min"),
                "salary_max": extracted.get("salary_max"),
                "currency": extracted.get("currency"),
                "raw_description": description
            })

    conn.close()

    elapsed_analysis = time.time() - analysis_start
    logger.info(f"[MARKET] AI analysis complete: {len(extracted_jobs)} jobs processed in {elapsed_analysis:.0f}s ({relevant_count} relevant)")

    # 4. Agregação de métricas
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    rel_total = max(relevant_count, 1)

    tech_counts_req = {}
    tech_counts_desirable = {}
    soft_skills_counts = {}
    cert_counts = {}
    modality_counts = {}
    exp_years_list = []
    language_level_counts = {}  # {"Inglês": {"B2": 5, "C1": 3}}

    for ej in extracted_jobs:
        if not ej["is_relevant"]:
            continue
        for t in ej["requirements"]:
            tech_counts_req[t] = tech_counts_req.get(t, 0) + 1
        for t in ej["nice_to_have"]:
            tech_counts_desirable[t] = tech_counts_desirable.get(t, 0) + 1
        for ss in ej["soft_skills"]:
            ss_norm = ss.strip().capitalize()
            soft_skills_counts[ss_norm] = soft_skills_counts.get(ss_norm, 0) + 1
        for c in ej["certifications"]:
            c_norm = c.strip()
            cert_counts[c_norm] = cert_counts.get(c_norm, 0) + 1
        mod = sanitize(ej["modality"])
        modality_counts[mod] = modality_counts.get(mod, 0) + 1
        if ej["exp_years_min"] is not None:
            exp_years_list.append(ej["exp_years_min"])
        for lang in ej.get("languages", []):
            lname = lang.get("name", "Desconhecido")
            llevel = lang.get("level") or "Não especificado"
            if lname not in language_level_counts:
                language_level_counts[lname] = {}
            language_level_counts[lname][llevel] = language_level_counts[lname].get(llevel, 0) + 1

    # Ranking Technologies
    req_ranking = [
        {"name": tech, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for tech, count in sorted(tech_counts_req.items(), key=lambda x: x[1], reverse=True)
    ]
    desirable_ranking = [
        {"name": tech, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for tech, count in sorted(tech_counts_desirable.items(), key=lambda x: x[1], reverse=True)
    ]

    # Modalidade Ranking
    modality_ranking = [
        {"name": mod, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for mod, count in sorted(modality_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # Idiomas Ranking (nome + nível mais citado)
    language_ranking = []
    for lname, levels in sorted(language_level_counts.items(), key=lambda x: sum(x[1].values()), reverse=True):
        top_level_name, top_level_count = max(levels.items(), key=lambda x: x[1])
        language_ranking.append({
            "name": lname,
            "count": sum(levels.values()),
            "top_level": top_level_name,
        })

    # Anos de experiência (Mediana + Distribuição)
    exp_years_sorted = sorted(exp_years_list)
    if exp_years_sorted:
        mid = len(exp_years_sorted) // 2
        exp_median = exp_years_sorted[mid]
    else:
        exp_median = 3

    # Score de Confiança
    if rel_total >= 10:
        confidence = "Alta"
        confidence_reason = f"Foram analisadas {rel_total} vagas relevantes, suficiente para uma análise confiável."
    elif rel_total >= 5:
        confidence = "Média"
        confidence_reason = f"Análise baseada em {rel_total} vagas relevantes. Considere ampliar o escopo para mais confiança."
    else:
        confidence = "Baixa"
        confidence_reason = f"Poucas vagas relevantes ({rel_total}). Tente ajustar os filtros ou escopo geográfico."

    # Exp distribution buckets
    exp_dist = {
        "0-1 ano": len([e for e in exp_years_list if e <= 1]),
        "1-3 anos": len([e for e in exp_years_list if 1 < e <= 3]),
        "3-5 anos": len([e for e in exp_years_list if 3 < e <= 5]),
        "5+ anos": len([e for e in exp_years_list if e > 5]),
    }

    report_result = {
        "summary": {
            "job_title": job_title,
            "target_stack": stack_list,
            "seniority": seniority,
            "location": location,
            "time_window": time_window,
            "total_jobs_scanned": total_jobs,
            "pre_filtered_count": len(pending),
            "relevant_jobs_analyzed": relevant_count,
            "discarded_jobs": len(pending) - relevant_count,
            "rejected_reasons_sample": [
                {"title": j["title"][:60], "reason": j["rejection_reason"]}
                for j in extracted_jobs if j.get("rejection_reason")
            ][:20],
            "confidence_score": confidence,
            "confidence_reason": confidence_reason,
            "generated_at": datetime.now().isoformat(),
        },
        "statistics": {
            "required_technologies": req_ranking,
            "desirable_technologies": desirable_ranking,
            "exp_years_median": exp_median,
            "exp_years_distribution": exp_dist,
            "modalities": modality_ranking,
            "top_soft_skills": [
                {"name": k, "count": v} for k, v in sorted(soft_skills_counts.items(), key=lambda x: x[1], reverse=True)[:15]
            ],
            "top_certifications": [
                {"name": k, "count": v} for k, v in sorted(cert_counts.items(), key=lambda x: x[1], reverse=True)[:15]
            ],
            "top_languages": [
                {"name": r["name"], "count": r["count"], "top_level": r["top_level"]}
                for r in language_ranking[:15]
            ]
        },
        "sample_jobs": extracted_jobs[:100]
    }

    # Persiste o relatório gerado
    import uuid
    report_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO market_reports (id, job_title, target_stack, seniority, location, time_window, total_jobs, relevant_jobs, confidence_score, report_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        report_id, job_title, target_stack, seniority, location, time_window,
        total_jobs, relevant_count, confidence, json.dumps(report_result)
    ))
    conn.commit()
    conn.close()

    # Log analysis completion
    try:
        log_ai_call(
            endpoint="/api/market/analyze (complete)",
            method="POST",
            status_code=200,
            duration_ms=0,
            model=selected_model,
            api_key_preview="ia_call...",
            request_body={"job_title": job_title, "total_jobs": total_jobs, "relevant": relevant_count},
            response_summary=f"Report generated: {relevant_count} relevant, {total_jobs - relevant_count} discarded",
        )
    except Exception:
        pass

    return report_result

