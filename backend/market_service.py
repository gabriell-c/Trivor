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

# Max jobs sent to AI per analysis — pre-filter reduces the pool first
_MAX_JOBS_FOR_ANALYSIS = 300

# Import logging service for AI call tracking
from logging_service import log_request as log_ai_call


# ---------------------------------------------------------------------------
# Normalização de termos
# ---------------------------------------------------------------------------

def normalize_term(term: str) -> str:
    """Normaliza qualquer termo (skill, certificação, idioma, etc) para padronização."""
    t = term.strip()
    return ' '.join(w.capitalize() for w in t.split())


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
    # Migração: adicionar source_url se não existir
    for table in ("market_raw_jobs", "market_jobs"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN source_url TEXT")
        except Exception:
            pass  # coluna já existe
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Geração de vagas mock (todas as áreas)
# ---------------------------------------------------------------------------

def _generate_sample_jobs(job_title: str) -> List[Dict]:
    """Gera vagas mock ricas com soft skills, certificações, diferenciais, URLs e senioridade balanceada."""
    import random
    import uuid
    jt = job_title.strip().lower()

    # --- Keywords técnicas do cargo alvo ---
    tech_keywords = []
    if 'python' in jt: tech_keywords += ['python', 'fastapi', 'django', 'flask', 'sqlalchemy', 'postgres', 'redis', 'celery']
    if 'backend' in jt: tech_keywords += ['api rest', 'microserviços', 'docker', 'kubernetes', 'aws', 'azure', 'git', 'jira']
    if 'frontend' in jt: tech_keywords += ['react', 'typescript', 'next.js', 'vue', 'angular', 'tailwind', 'css', 'html5']
    if 'fullstack' in jt: tech_keywords += ['python', 'react', 'typescript', 'node.js', 'docker', 'postgres', 'aws', 'git']
    if 'java' in jt: tech_keywords += ['spring boot', 'java', 'microserviços', 'docker', 'kubernetes', 'aws', 'maven']
    if 'javascript' in jt: tech_keywords += ['javascript', 'node.js', 'react', 'typescript', 'express', 'mongo']
    if 'data' in jt or 'cientista' in jt: tech_keywords += ['python', 'sql', 'machine learning', 'pandas', 'aws', 'docker', 'spark']
    if 'devops' in jt: tech_keywords += ['docker', 'kubernetes', 'jenkins', 'aws', 'terraform', 'ci/cd', 'linux']
    if 'mobile' in jt: tech_keywords += ['react native', 'flutter', 'kotlin', 'swift', 'ios', 'android']
    if 'qa' in jt or 'test' in jt: tech_keywords += ['selenium', 'cypress', 'jest', 'pytest', 'automação', 'ci/cd']
    if 'analista' in jt: tech_keywords += ['sql', 'excel', 'power bi', 'tableau', 'análise de dados']
    if 'go' in jt or 'golang' in jt: tech_keywords += ['go', 'golang', 'grpc', 'docker', 'kubernetes', 'postgres']
    if 'ruby' in jt or 'rails' in jt: tech_keywords += ['ruby', 'rails', 'postgres', 'redis', 'docker']
    if 'dotnet' in jt or '.net' in jt: tech_keywords += ['c#', '.net', 'asp.net', 'sql server', 'azure', 'docker']
    if 'php' in jt: tech_keywords += ['php', 'laravel', 'symfony', 'mysql', 'docker', 'aws']
    if 'scrum' in jt: tech_keywords += ['scrum', 'kanban', 'agile', 'jira', 'sprint']
    if 'estagiário' in jt or 'estagiario' in jt or 'estágio' in jt or 'estagio' in jt: tech_keywords += ['git', 'python', 'sql', 'docker']

    # --- Senioridade balanceada: 40% Júnior, 40% Pleno, 20% Sênior ---
    seniority_weights = (
        [("Júnior", "1 a 2 anos", "3-5k", "4-6k")] * 8
        + [("Pleno", "2 a 5 anos", "6-9k", "8-12k")] * 8
        + [("Sênior", "5+ anos", "12-18k", "15-22k")] * 4
    )
    random.shuffle(seniority_weights)

    # --- Soft skills comuns para enriquecer descrições ---
    soft_skills_pool = [
        "comunicação eficaz", "trabalho em equipe", "proatividade", "resolução de problemas",
        "pensamento crítico", "liderança", "adaptabilidade", "gestão de tempo",
        "capacidade de análise", "criatividade", "facilidade de aprendizado",
        "orientação a resultados", "colaboração multidisciplinar", "autonomia",
    ]
    # --- Certificações ---
    certs_pool = [
        "AWS Cloud Practitioner", "AWS Solutions Architect", "Azure Fundamentals",
        "Google Cloud Professional", "PMP", "ITIL Foundation",
        "Certificação Kubernetes (CKA)", "Scrum Master (PSM/CSM)",
        "Terraform Associate", "MongoDB Developer", "PostgreSQL Professional",
    ]
    # --- Diferenciais ---
    diff_pool = [
        "inglês avançado", "inglês intermediário", "espanhol",
        "pós-graduação em TI", "mestrado", "graduação completa em Engenharia",
        "experiência com startups", "experiência em ambientes ágeis",
        "conhecimento em LGPD", "certificações na área",
    ]

    locations = ["São Paulo, SP", "Rio de Janeiro, RJ", "Remoto Nacional", "Belo Horizonte, MG", "Curitiba, PR", "Porto Alegre, RS"]
    modalities = ["Remoto", "Híbrido", "Presencial", "Remoto Nacional"]
    sources = ["LinkedIn", "Catho", "InfoJobs", "Gupy", "Glassdoor"]
    companies = ["TechCorp Brasil", "DataFlow S.A.", "InovaSoft", "NexGen Digital", "CloudBase", "Fintech X", "StartupHub", "Consultoria Tech", "Software House Brasil", "Agile Labs"]

    def _make_desc(level, exp_range, salary_min, salary_max):
        """Gera uma descrição rica e realista."""
        n_tech = random.randint(3, min(6, max(1, len(tech_keywords)))) if tech_keywords else 3
        n_tech = min(n_tech, len(tech_keywords))
        skills = random.sample(tech_keywords, n_tech)
        n_soft = random.randint(2, min(8, len(soft_skills_pool)))
        soft = random.sample(soft_skills_pool, n_soft)
        n_cert = min(random.randint(0, 2) if level != "Júnior" else 0, len(certs_pool))
        certs = random.sample(certs_pool, n_cert)
        n_diff = random.randint(1, min(3, len(diff_pool)))
        diffs = random.sample(diff_pool, n_diff)

        lines = [
            f"Estamos contratando {job_title} {level} para integrar nossa equipe de tecnologia.",
            f"Requisitos mínimos: {exp_range} de experiência profissional na área.",
            f"Conhecimentos obrigatórios: {', '.join(skills)}.",
            f"Oferecemos remuneração entre R$ {salary_min} e R$ {salary_max}.",
        ]
        if soft:
            lines.append(f"Buscamos profissional com {', '.join(soft)}.")
        if certs:
            lines.append(f"Diferencial: {', '.join(certs)}.")
        if diffs:
            lines.append(f"Será considerado diferencial: {', '.join(diffs)}.")
        lines.append("Ambiente ágil com sprints quinzenais, code review e pair programming.")
        lines.append("Benefícios: VR/VA, plano de saúde, auxílio educação, home office flexível.")
        return " ".join(lines)

    jobs = []
    seen_keys = set()

    for sen in seniority_weights:
        level, exp_range, salary_min, salary_max = sen
        for _ in range(8):  # 8 vagas por nível de senioridade
            mod = random.choice(modalities)
            loc = random.choice(locations)
            src = random.choice(sources)
            company = random.choice(companies)
            title = f"{job_title.title()} {level}"
            key = f"{title}|{company}|{loc}|{mod}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            desc = _make_desc(level, exp_range, salary_min, salary_max)
            src_url = ""  # mock jobs não têm link real

            jobs.append({
                "title": title,
                "company": company,
                "description": desc,
                "location": loc,
                "modality": mod,
                "source": src,
                "source_url": src_url,
                "seniority": level,
            })

    # Garante pelo menos 200 vagas
    while len(jobs) < 200:
        level = random.choice(["Júnior", "Pleno", "Sênior"])
        exp_range = {"Júnior": "1 a 2 anos", "Pleno": "2 a 5 anos", "Sênior": "5+ anos"}[level]
        sal = {"Júnior": ("3-5k", "4-6k"), "Pleno": ("6-9k", "8-12k"), "Sênior": ("12-18k", "15-22k")}[level]
        mod = random.choice(modalities)
        loc = random.choice(locations)
        src = random.choice(sources)
        company = random.choice(companies)
        title = f"{job_title.title()} {level}"
        key = f"{title}|{company}|{loc}|{mod}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        desc = _make_desc(level, exp_range, sal[0], sal[1])
        src_url = ""  # mock jobs não têm link real
        jobs.append({
            "title": title,
            "company": company,
            "description": desc,
            "location": loc,
            "modality": mod,
            "source": src,
            "source_url": src_url,
            "seniority": level,
        })

    return jobs


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
    country: str = "cn",
    language: str = "zh",
    num_pages: int = 2,
    api_keys: List[str] = None,
) -> List[Dict]:
    """Através JSearch API busca vagas reais, com fallback entre múltiplas chaves."""
    if not api_keys:
        return []

    params = urllib.parse.quote_plus(query)
    url_template = f"{_JSEARCH_API_URL}?query={params}&country={country}&language={language}&num_pages={num_pages}&date_posted=all"

    keys_tried = []
    for api_key in api_keys:
        api_key = api_key.strip()
        if not api_key:
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
                raw_jobs = data.get("data", [])
                jobs = _build_jobs_from_raw(raw_jobs, country)
                remaining = resp.headers.get("x-ratelimit-remaining")
                total = resp.headers.get("x-ratelimit-limit")
                logger.info(f"[JSearch] Chave {api_key[:8]}... → {len(jobs)} vagas | rate: {remaining}/{total}")
                return jobs, int(remaining) if remaining else None, int(total) if total else None
            else:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... retornou erro: {data.get('message', 'unknown')}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... 403 (sem créditos ou inválida), tentando próxima...")
                continue
            elif e.code == 429:
                logger.warning(f"[JSearch] Chave {api_key[:8]}... 429 (rate limit), aguardando e tentando próxima...")
                time.sleep(1)
                continue
            else:
                logger.error(f"[JSearch] HTTP erro {e.code}: {e.reason}")
                continue
        except Exception as e:
            logger.error(f"[JSearch] Erro com chave {api_key[:8]}...: {e}")
            continue

    logger.warning(f"[JSearch] Nenhuma das {len(keys_tried)} chave(s) retornou resultados")
    return [], None, None


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


def generate_mock_jobs_if_empty(db_file: Path, job_title: str = "Desenvolvedor Backend", jsearch_api_keys: List[str] = None):
    """Gera vagas mock se a base estiver vazia.
    Se jsearch_api_keys (lista) for fornecido, tenta buscar vagas reais primeiro.
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
                search_query = f"{job_title} desenvolvedor python"
                sample_jobs, used_key_remaining, _ = _fetch_jsearch_jobs(search_query, country="br", language="pt", num_pages=2, api_keys=valid_keys)
                logger.info(f"[MARKET] JSearch retornou {len(sample_jobs)} vagas reais")
                # Atualiza uso no DB
                if used_key_remaining is not None and valid_keys:
                    _update_jsearch_usage(db_file, valid_keys[0], used_key_remaining)

        # Se JSearch falhou ou não configurado, usa mock
        if not sample_jobs:
            if valid_keys:
                logger.info("[MARKET] JSearch sem resultados, usando dados simulados")
            sample_jobs = _generate_sample_jobs(job_title)

        now = datetime.now()
        for i, j in enumerate(sample_jobs):
            job_id = str(uuid.uuid4())
            pub_date = now - timedelta(days=i * 3 + 1)
            source_url = j.get("source_url", "")
            cursor.execute('''
                INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, j["title"], j["company"], j["description"], j["location"], j["modality"], j["source"], source_url, pub_date.isoformat()))

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

    # Se nada foi extraído mas o texto é substancial, marcar como relevante com dados mínimos
    if len(job_text) > 100 and not result["requirements"] and not result["role_level"]:
        result["is_relevant"] = True

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


def _keyword_score(job_text_lower: str, job_title: str, target_stack: List[str], seniority: str, location: str) -> int:
    """Retorna score de relevância. Score == 0 = rejeitado no pré-filtro."""
    # Se não tem stack definido, usa o job_title como fallback
    keywords = target_stack if target_stack else [job_title.strip()]
    job_title_kw = [w for w in job_title.strip().split() if len(w) > 3]

    # REGRA OBRIGATÓRIA: pelo menos 1 keyword deve estar no texto
    stack_hits = sum(1 for kw in keywords if kw.lower() in job_text_lower)
    title_hits = sum(1 for kw in job_title_kw if kw.lower() in job_text_lower)
    if stack_hits == 0 and title_hits == 0:
        return 0  # Nenhuma keyword encontrada → vaga irrelevante

    # REJEIÇÃO RÍGIDA DE SENIORIDADE INCOMPATÍVEL
    job_sen = _detect_job_seniority(job_text_lower)
    if job_sen:
        user_sen = seniority.lower()
        rejects = _SENIORITY_REJECTS.get(user_sen, [])
        for r in rejects:
            if r in job_text_lower:
                # Verifica se é a mesma palavra (não parte de outra)
                if re.search(r'\b' + re.escape(r) + r'\b', job_text_lower, re.IGNORECASE):
                    return 0  # Senioridade incompatível → rejeita

    score = 0

    # Stack keywords
    for kw in keywords:
        if kw.lower() in job_text_lower:
            score += 3

    # Senioridade — bônus se bater
    sen_matches = _SENIORITY_MATCHES.get(seniority.lower(), [])
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

    # Mapeamento rígido de modalidade — se usuário selecionou um tipo, só aceita vagas desse tipo
    # "remoto" ou "remoto nacional" → aceita vagas com "remoto" ou "remoto nacional"
    # "presencial" → aceita apenas vagas presenciais
    # "híbrido" → aceita apenas vagas híbridas
    # outras (cidades) → não restringe modalidade
    selected_loc_lower = location.lower().strip()
    modality_restriction = None
    if 'remoto' in selected_loc_lower and ('nacional' in selected_loc_lower or 'internacional' in selected_loc_lower):
        modality_restriction = 'remote'  # aceita "remoto", "remoto nacional", "remoto internacional"
    elif 'remoto' in selected_loc_lower:
        modality_restriction = 'remote'
    elif 'presencial' in selected_loc_lower:
        modality_restriction = 'onsite'
    elif 'híbrido' in selected_loc_lower or 'hibrido' in selected_loc_lower:
        modality_restriction = 'hybrid'
    # se for cidade específica, modality_restriction = None (não filtra modalidade)

    for j in raw_jobs:
        job_id, title, company, description, loc, mod, source, source_url = j
        job_text_lower = (title + " " + description).lower()
        mod_lower = mod.lower()

        # Remove negative keywords
        if neg_list and any(nk in job_text_lower for nk in neg_list):
            continue

        # MODALIDADE — suavizada para aumentar cobertura
        # Para remoto: não rejeita vagas que não mencionam "remoto" explicitamente
        if modality_restriction == 'remote':
            pass  # permite todas, score será menor se não mencionar remoto
        elif modality_restriction == 'onsite':
            if 'remoto' in job_text_lower or 'home office' in job_text_lower:
                continue
        elif modality_restriction == 'hybrid':
            if 'remoto' in job_text_lower or 'home office' in job_text_lower:
                continue
            # vagas sem menção de modalidade são permitidas (podem ser híbridas)

        score = _keyword_score(job_text_lower, title, target_stack, seniority, location)
        if score > 0:
            job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"
            filtered.append((score, job_id, title, company, description, loc, mod, source, source_url, job_text))

    # Ordena por score decrescente e limita
    filtered.sort(key=lambda x: -x[0])
    return [(f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9]) for f in filtered[:max_jobs]]


# ---------------------------------------------------------------------------
# Extração com IA (vaga única)
# ---------------------------------------------------------------------------

def extract_job_with_ai(client: OpenAI, selected_model: str, job_text: str, target_stack: List[str], seniority: str = "Pleno", location: str = "Remoto Nacional") -> Dict[str, Any]:
    """Usa IA para extrair dados estruturados de uma vaga de forma rigorosa."""
    job_title_context = target_stack[0] if target_stack else "diversas áreas"
    prompt = f"""Analise esta vaga e extraia dados estruturados.

CLASSIFICAÇÃO — pergunte a si mesma para CADA item:
1. É um CONHECIMENTO/FERRAMENTA que a pessoa PRECISA TER? -> requirements
2. É um TRAÇO COMPORTAMENTAL (atitude, forma de agir)? -> soft_skills
3. É um TÍTULO OFICIAL de certificação? -> certifications
4. É Desejável mas não Obrigatório? -> nice_to_have
5. Se NÃO se encaixa em 1-4 -> NÃO é skill. Ignore.

CATEGORIAS:
- requirements: só conhecimento técnico, ferramentas, linguagens, idiomas, formação acadêmica
- soft_skills: só traços comportamentais (proatividade, liderança, comunicação, etc)
- certifications: só certificações formais (AWS, PMP, OAB, etc)
- nice_to_have: diferenciais técnicos não obrigatórios

RELEVÂNCIA: is_relevant=TRUE se o cargo for compatível com o perfil do usuário.

Perfil: cargo={job_title_context}, stack={", ".join(target_stack)}, seniority={seniority}, location={location}

Descrição da vaga:
{job_text}

*** VERIFICAÇÃO FINAL (leia ANTES de gerar o JSON) ***
PARA CADA ITEM nos campos requirements e soft_skills, responda:
"Isso é conhecimento/traço da PESSOA, ou algo que a EMPRESA oferece/processa?"
- EMPRESA PAGA (auxílio, vale, plano, bônus, refeição, Gympass) -> NÃO é skill
- EMPRESA ORGANIZA (remoto, híbrido, home office, flexível) -> NÃO é skill
- PROCESSO/ROTINA (code review, standup, pair programming, reunião) -> NÃO é skill
- RESPONSABILIDADE DO CARGO (o que a pessoa faz no dia a dia) -> NÃO é skill
- ANOS DE EXPERIÊNCIA (X anos, 2-5 anos, mínimo X anos) -> vai para exp_years_min/exp_years_max, NÃO é skill
- SOMENTE se a PESSOA PRECISA SABER/TER -> é skill.

Apenas depois dessa verificação, retorne o JSON abaixo:
{
  "is_relevant": true|false,
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "requirements": ["Python", "React"],
  "nice_to_have": ["AWS"],
  "certifications": ["PMP"],
  "soft_skills": ["proatividade", "trabalho em equipe"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}"""
    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=60,
        )
        content = response.choices[0].message.content or "{}"

        # Strip thinking tag se houver
        content = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', content, flags=re.DOTALL).strip()
        content = re.sub(r'｜thinking｜.*?／｜thinking｜', '', content, flags=re.DOTALL).strip()
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

        data = json.loads(content)
        return data
    except Exception as e:
        # Fallback heurístico quando a IA falha completamente
        logger.warning(f"[WARN] extract_job_with_ai fallback to heuristic: {e}")
        return heuristic_extract(job_text)


# ---------------------------------------------------------------------------
# Extração em lote (múltiplas vagas por chamada — muito mais rápido)
# ---------------------------------------------------------------------------


def _sanitize_requirements(item: Dict[str, Any]) -> Dict[str, Any]:
    """Safety net: remove obvious non-skills from requirements and soft_skills."""
    import re as _re
    # Each pattern matches a SUBSTRING of the term — if found, the term is NOT a skill
    benefit_patterns = [
        r"auxílio", r"auxilio", r"vale\s+\w+", r"vr[/\-]\s*va", r"va[/\-]\s*vr",
        r"plano\s+de\s+saúde", r"plano\s+de\s+saude",
        r"refeição", r"alimentação", r"alimentacao", r"transporte\b", r"bônus", r"bonus",
        r"profit\s*share", r"stock\s*(options?|option)", r"seguro\s+de\s+vida",
        r"previdência", r"previdencia", r"participação\s+nos\s+lucros",
        r"vaga\s+de\s+férias", r"day\s+off", r"psychological\s+support",
        r"\bgympass\b", r"\bgypass\b", r"\bgoldpass\b",
        r"carteira\s+(refeição|alimentação|alimentacao)",
        r"reembolso",
    ]
    modality_patterns = [
        r"\bremoto\b", r"\bhíbrido\b", r"\bhibrido\b", r"\bhome\s+office\b",
        r"\bflexível\b", r"\bflexivel\b", r"\bpresencial\b",
        r"modelo\s+(híbrido|hibrido)\b", r"\btrabalho\s+(remoto|hibrido|híbrido)\b",
        r"\bescritório\s+(híbrido|hibrido)\b",
    ]
    process_patterns = [
        r"\bcode\s+review\b", r"\bpair\s+(programming|program)\b", r"\bstandup\b",
        r"\bretro\b", r"\breunião?\b", r"\bcerimônia?\b", r"\bcerimonia?\b",
    ]
    experience_patterns = [
        r"[\d]+\s*(?:a\s+[\d]+)?\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
        r"[\d]+\s*[\+]\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
        r"experiência\s+(?:de\s+)?[\d]+\s*anos?",
        r"[\d]+\s*(?:a|até)\s*[\d]+\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
        r"mínimo\s*de\s*[\d]+\s*anos?\s*(?:de\s*)?(?:experiência|experiencia)",
    ]

    combined = "|".join(benefit_patterns + modality_patterns + process_patterns + experience_patterns)
    term_pattern = _re.compile(combined, _re.IGNORECASE)

    for field in ("requirements", "soft_skills"):
        if field not in item or not isinstance(item[field], list):
            continue
        original = item[field]
        cleaned = [term for term in original if not term_pattern.search(term.strip())]
        item[field] = cleaned
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


_BATCH_SIZE = 6  # vagas por chamada IA — menor para maior confiabilidade

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
    """Completa jobs faltantes usando heurística quando a IA não retorna todos."""
    if len(data) >= expected:
        return data

    # Limita aos primeiros N jobs que a IA retornou
    jobs_from_ai = data[:expected]

    # Para os jobs faltantes, usa heurística
    missing_count = expected - len(jobs_from_ai)
    for i in range(missing_count):
        if i < len(job_texts):
            heuristic_result = heuristic_extract(job_texts[i])
            jobs_from_ai.append(heuristic_result)
        else:
            jobs_from_ai.append({
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
            })

    return jobs_from_ai


def _fallback_extract_jobs(
    client: OpenAI,
    selected_model: str,
    job_texts: List[str],
    target_stack: List[str],
    seniority: str,
    location: str,
) -> List[Dict[str, Any]]:
    """Fallback: extrai cada vaga individualmente com IA + heurística."""
    results = []
    for job_text in job_texts:
        try:
            result = extract_job_with_ai(client, selected_model, job_text, target_stack)
            # Se a IA falhou e retornou dados vazios, aplica heurística
            if not result.get("requirements") and not result.get("role_level"):
                result = heuristic_extract(job_text)
        except Exception:
            result = heuristic_extract(job_text)

        # Aplica validação heurística de relevância como backup
        if not result.get("is_relevant"):
            result["is_relevant"] = is_relevant_heuristic(
                job_text, target_stack, seniority, location
            )
        results.append(result)
    return results


def extract_jobs_batched(
    client: OpenAI,
    selected_model: str,
    job_texts: List[str],
    target_stack: List[str],
    seniority: str = "Pleno",
    location: str = "Remoto Nacional",
) -> List[Dict[str, Any]]:
    """Chama a IA UMA vez com N vagas e devolve uma lista de resultados."""
    if not job_texts:
        return []

    job_title_context = target_stack[0] if target_stack else "diversas áreas"
    stack_str = ", ".join(target_stack) if target_stack else "diversas áreas"

    jobs_section = "\n\n".join(
        f"--- VAGA {i+1} ---\n{txt}" for i, txt in enumerate(job_texts)
    )

    start_time = time.time()

    prompt = f"""Analise CADA vaga abaixo e extraia dados estruturados.

CLASSIFICAÇÃO — pergunte a si mesma para CADA item de CADA vaga:
1. É um CONHECIMENTO/FERRAMENTA que a pessoa PRECISA TER? -> requirements
2. É um TRAÇO COMPORTAMENTAL (atitude, forma de agir)? -> soft_skills
3. É um TÍTULO OFICIAL de certificação? -> certifications
4. É Desejável mas não Obrigatório? -> nice_to_have
5. Se NÃO se encaixa em 1-4 -> NÃO é skill. Ignore.

CATEGORIAS:
- requirements: só conhecimento técnico, ferramentas, linguagens, idiomas, formação acadêmica
- soft_skills: só traços comportamentais (proatividade, liderança, comunicação, etc)
- certifications: só certificações formais (AWS, PMP, OAB, etc)
- nice_to_have: diferenciais técnicos não obrigatórios

RELEVÂNCIA: is_relevant=TRUE se o cargo for compatível com o perfil do usuário. Vagas remotas são SEMPRE relevantes.

Perfil: cargo={job_title_context}, stack={stack_str}, seniority={seniority}, location={location}

{jobs_section}

*** VERIFICAÇÃO FINAL (leia ANTES de gerar o JSON) ***
PARA CADA ITEM nos campos requirements e soft_skills de CADA vaga, responda:
"Isso é conhecimento/traço da PESSOA, ou algo que a EMPRESA oferece/processa?"
- EMPRESA PAGA (auxílio, vale, plano, bônus, refeição, Gympass) -> NÃO é skill
- EMPRESA ORGANIZA (remoto, híbrido, home office, flexível) -> NÃO é skill
- PROCESSO/ROTINA (code review, standup, pair programming, reunião) -> NÃO é skill
- RESPONSABILIDADE DO CARGO (o que a pessoa faz no dia a dia) -> NÃO é skill
- ANOS DE EXPERIÊNCIA (X anos, 2-5 anos, mínimo X anos) -> vai para exp_years_min/exp_years_max, NÃO é skill
- SOMENTE se a PESSOA PRECISA SABER/TER -> é skill.

Apenas depois dessa verificação, retorne um JSON array com EXATAMENTE {len(job_texts)} objetos:
Formato de cada objeto:
[{{
  "is_relevant": true|false,
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "requirements": ["Python", "React"],
  "nice_to_have": ["AWS"],
  "certifications": ["PMP"],
  "soft_skills": ["proatividade", "trabalho em equipe"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}}]"""
    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=60,
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

        # Se a IA retornou menos jobs que o esperado, tenta completar com heurística
        if len(data) < len(job_texts):
            logger.warning(
                f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. "
                f"Completing missing jobs with heuristics."
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

    # 1. Garante vagas de amostragem no DB
    init_market_db(db_file)
    generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys)

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
            "summary": {"job_title": job_title, "total_jobs_scanned": 0, "relevant_jobs_analyzed": 0},
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

    for batch_start in range(0, len(pending), _BATCH_SIZE):
        batch = pending[batch_start:batch_start + _BATCH_SIZE]
        job_texts = [item[8] for item in batch]

        batch_results = extract_jobs_batched(client, selected_model, job_texts, stack_list, seniority=seniority, location=location)

        for idx, (job_id, title, company, description, loc, mod, source, source_url, job_text) in enumerate(batch):
            extracted = batch_results[idx] if idx < len(batch_results) else {}
            extracted = _sanitize_requirements(extracted)
            # Extract languages from requirements/nice_to_have
            extracted_languages = _extract_languages(extracted)
            is_rel = extracted.get("is_relevant", False)

            # Se a IA marcou como irrelevante mas a heurística diz o contrário, confia na heurística
            if not is_rel and extracted.get("requirements"):
                is_rel = is_relevant_heuristic(job_text, stack_list, seniority, location)
                if is_rel:
                    extracted["is_relevant"] = True

            reqs_norm = sorted(set(normalize_term(t) for t in extracted.get("requirements", [])))
            nice_norm = sorted(set(normalize_term(t) for t in extracted.get("nice_to_have", [])))

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
                        is_relevant, requirements, nice_to_have, role_level, exp_years_min, exp_years_max,
                        soft_skills, certifications, salary_min, salary_max, currency, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_id, job_id, title, company, loc, mod, source, source_url or "", 1,
                    json.dumps(reqs_norm), json.dumps(nice_norm),
                    extracted.get("role_level"),
                    extracted.get("exp_years_min"), extracted.get("exp_years_max"),
                    json.dumps(extracted.get("soft_skills", [])),
                    json.dumps(extracted.get("certifications", [])),
                    extracted.get("salary_min"), extracted.get("salary_max"),
                    extracted.get("currency"), now_str
                ))
                conn.commit()

            extracted_jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": loc,
                "modality": mod,
                "source": source,
                "source_url": source_url or "",
                "is_relevant": is_rel,
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
        mod = ej["modality"]
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
