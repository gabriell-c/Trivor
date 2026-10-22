"""
Market Intelligence Service – módulo completo de Inteligência de Mercado.
Coleta, filtro, extração IA e agregação estatística.

Estrutura (split por responsabilidade — este arquivo é o núcleo + facade):
- market_log.py:      logger compartilhado (backend/market_log.txt)
- market_keywords.py: normalização de skills, score e pré-filtro (texto puro)
- market_db.py:       schema SQLite, migrações e uso do pool de chaves JSearch
- market_jsearch.py:  busca na API JSearch e geração de amostra p/ base vazia

Aqui ficam a heurística de extração, a extração em lote com IA e a
orquestração do pipeline (run_market_analysis). Os reexports no topo
(marcados `noqa: F401`) mantêm o contrato `import market_service` estável
para main.py e a suíte de testes.
"""

import json
import os
import re
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Import logging service for AI call tracking
from logging_service import log_request as log_ai_call
from market_db import (
    _apply_reports_retention as _db_apply_reports_retention,
)
from market_db import (
    _connect_market_db,
    init_market_db,
)
from market_jsearch import (
    _build_jobs_from_raw,  # noqa: F401 (facade de compat — testes/main importam daqui)
    _parse_jsearch_posted_at,  # noqa: F401
    generate_mock_jobs_if_empty,
)
from market_keywords import (
    _MAX_JOBS_FOR_ANALYSIS,
    _detect_job_seniority,  # noqa: F401
    _is_garbage_requirement,  # noqa: F401
    _keyword_score,  # noqa: F401
    _parse_br_number,
    _pre_filter_jobs,
    extract_mentioned_skills,  # noqa: F401
    map_time_window_to_date_posted,
    normalize_skill,
    normalize_term,  # noqa: F401
    sanitize,
)
from market_log import logger
from openai import OpenAI

# Retenção: market_reports guarda no máximo as N análises mais recentes —
# espelho do market_db._REPORTS_KEEP_LAST. O wrapper abaixo lê o valor deste
# módulo para que monkeypatch nos testes (`market_service._REPORTS_KEEP_LAST`)
# continue valendo.
_REPORTS_KEEP_LAST = 30


def _apply_reports_retention(cursor) -> None:
    """Facade da retenção do market_db, injetando o limite deste módulo."""
    _db_apply_reports_retention(cursor, keep=_REPORTS_KEEP_LAST)

# ---------------------------------------------------------------------------
# Fallback heurístico (regex) — extrai dados mesmo quando a IA falha
# ---------------------------------------------------------------------------

# Salário: grupo1 = valor mínimo (formato BR: 8.000 / 8.000,50 / 5k),
# grupo2 = máximo da faixa (opcional, após "a"/"até"). Sufixos mil/k/mês/anual
# só contam se fizerem parte do PRÓPRIO match (não do texto inteiro).
_SALARY_RE = re.compile(
    r'(?:\bde\b|\br\$\s*|\bsalary\b|\bsalário\b|\bremuneração\b)?'
    r'\s*(?:r\$?\s*)?'
    r'(\d[\d\.,]*)'
    r'(?:\s*(?:a|até)\s*(\d[\d\.,]*))?'
    r'\s*(?:mil|k|/\s*month|mês|anual|ao\s*ano)?',
    re.IGNORECASE,
)
# Padrão BR de milhar: 1.234 / 1.234.567 / 1.234,56
_BR_THOUSANDS_RE = re.compile(r'\d{1,3}(\.\d{3})+(,\d{1,2})?')


_LEVEL_KEYWORDS = {
    "júnior": "Júnior", "junior": "Júnior", "estagiário": "Júnior", "estagiario": "Júnior", "estágio": "Júnior", "intern": "Júnior",
    "pleno": "Pleno", "middle": "Pleno",
    "sênior": "Sênior", "senior": "Sênior", "staff": "Sênior", "lead": "Sênior",
    "especialista": "Especialista", "expert": "Especialista", "principal": "Especialista", "architect": "Especialista", "arquiteto": "Especialista",
}


def heuristic_extract(job_text: str) -> dict[str, Any]:
    """Extrai dados estruturados via regex quando a IA falha."""
    if not job_text or not job_text.strip():
        return {"is_relevant": False, "role_level": None, "exp_years_min": None,
                "exp_years_max": None, "requirements": [], "nice_to_have": [],
                "certifications": [], "soft_skills": [], "salary_min": None,
                "salary_max": None, "currency": None}
    text_lower = job_text.lower()
    result: dict[str, Any] = {
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

    # Salário — sufixos (k/mil/anual/ao ano) valem SOMENTE quando parte do
    # próprio segmento do match; no texto inteiro, "keyboard"/"Black" multiplicavam
    # por 1000 e "plano anual de saúde" dividia por 12 (reproduzido no audit).
    for m in _SALARY_RE.finditer(job_text):
        first = m.group(1)
        if not first:
            continue
        segment = m.group(0)
        # Ignora números sem contexto de salário (datas, "12 a 15 anos", etc.)
        has_context = bool(re.search(r'(r\$|salari|salary|remunera)', segment, re.IGNORECASE))
        if not has_context:
            has_context = (
                bool(re.search(r'\d\s*(k|mil)\s*$', segment, re.IGNORECASE))
                or bool(_BR_THOUSANDS_RE.search(segment))
                or len(first) >= 5
            )
        if not has_context:
            continue
        try:
            min_val = _parse_br_number(first)
            if m.group(2):
                max_val = _parse_br_number(m.group(2))
                if max_val < min_val:
                    max_val = min_val
            elif re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d{1,2})?', first.strip()):
                max_val = min_val  # "8.000" / "8.000,50": valor único, não faixa
            else:
                max_val = min_val * 1.5
            if re.search(r'\d\s*(k|mil)\s*$', segment, re.IGNORECASE):
                min_val *= 1000
                max_val *= 1000
            elif re.search(r'\d\s*(anual|ao\s*ano)\s*$', segment, re.IGNORECASE) or \
                    re.search(r'(anual|ao\s*ano)\s*(de\s*)?$', job_text[max(0, m.start() - 15):m.start()], re.IGNORECASE):
                min_val /= 12
                max_val /= 12
            result["salary_min"] = round(min_val, 2)
            result["salary_max"] = round(max_val, 2)
            result["currency"] = "BRL"
            break
        except ValueError:
            continue

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
    lines = [linha.strip() for linha in job_text.split('\n') if linha.strip()]
    for line in lines:
        ll = line.lower()
        if 'requisito' in ll or 'obrigatório' in ll or 'obrigatorio' in ll:
            # Extrai itens após dois-pontos ou vírgulas
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) >= 3 and len(p) < 100:
                    result["requirements"].append(p)
        elif 'diferencial' in ll or 'desejável' in ll or 'nice to have' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) >= 3 and len(p) < 100:
                    result["nice_to_have"].append(p)
        # Formação escolar
        elif 'formação' in ll or 'formacao' in ll or 'escolaridade' in ll or 'ensino' in ll or 'idioma' in ll or 'idiomas' in ll:
            parts = re.split(r'[:,;]', line)
            for p in parts[1:]:
                p = p.strip()
                if len(p) >= 3 and len(p) < 100:
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
# Extração com IA (vaga única)
# ---------------------------------------------------------------------------

def extract_job_with_ai(client: OpenAI, selected_model: str, job_text: str, target_stack: list[str], seniority: str = "Pleno", location: str = "Remoto Nacional") -> dict[str, Any]:
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

Retorne o JSON abaixo com TODOS OS campos preenchidos:
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


def _sanitize_requirements(item: dict[str, Any]) -> dict[str, Any]:
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
        return any(kw in t_lower for kw in [
            "health insurance", "dental insurance", "vision insurance",
            "life insurance", "401k", "retirement",
            "paid time off", "pto", "paid leave",
            "wellness", "gym", "fitness",
            "tuition reimbursement", "education assistance",
            "stock options", "equity", "rsu",
        ])

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


def _ensure_common_skills(item: dict[str, Any], job_text: str) -> dict[str, Any]:
    """Garante que skills administrativos comuns sejam extraídos se presentes no texto.
    Roda após a IA para capturar o que ela perdeu."""
    if not job_text or not item:
        return item

    text_lower = job_text.lower()
    requirements = set(item.get("requirements", []))
    nice_to_have = set(item.get("nice_to_have", []))
    all_existing = requirements | nice_to_have


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


def _extract_languages(item: dict[str, Any]) -> list[dict[str, Any]]:
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


def _parse_batch_response(data: Any, expected: int) -> list[dict[str, Any]]:
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
    data: list[dict[str, Any]],
    expected: int,
    client: OpenAI,
    selected_model: str,
    job_texts: list[str],
    target_stack: list[str],
    seniority: str,
    location: str,
) -> list[dict[str, Any]]:
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
    job_texts: list[str],
    target_stack: list[str],
    seniority: str,
    location: str,
) -> list[dict[str, Any]]:
    """Fallback: tenta IA individual, se falhar usa heurística."""
    results = []
    for job_text in job_texts:
        result = None
        try:
            result = extract_job_with_ai(client, selected_model, job_text, target_stack)
        except Exception as exc:
            logger.warning(f"[MARKET] IA individual falhou p/ esta vaga (fallback heurístico): {exc}")
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
    job_texts: list[str],
    target_stack: list[str],
    seniority: str = "Pleno",
    location: str = "Remoto Nacional",
    neg_list: list[str] | None = None,
) -> list[dict[str, Any]]:
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
        # Timeout dinâmico proporcional ao nº de vagas do lote (15s por vaga, mín 60s, teto 400s;
        # com _BATCH_SIZE=10 o valor prático é ~150s)
        calc_timeout = max(60, min(400, len(job_texts) * 15))
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=calc_timeout,
        )
        content = response.choices[0].message.content or "[]"
        # Remove markdown codeblocks ```json ... ``` se houver
        content = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL).strip()
        # Remove <|thinking|> tags (ASCII pipes)
        content = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', content, flags=re.DOTALL).strip()
        # Remove ｜thinking｜ tags (fullwidth pipes, common in some models)
        content = re.sub(r'｜thinking｜.*?／｜thinking｜', '', content, flags=re.DOTALL).strip()
        # Remove any remaining <thinking>...</thinking>
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

        # Garante que content não seja string vazia ou inválida para o json.loads
        if not content or content == "[]":
            raw = []
        else:
            try:
                raw = json.loads(content)
            except json.JSONDecodeError as err:
                logger.error(f"[MARKET] Erro ao decodificar JSON da IA: {err}. Conteúdo recebido (primeiros 300 caracteres): {content[:300]!r}")
                # Tenta localizar uma estrutura JSON [...] ou {...} dentro do texto retornado pela IA
                match = re.search(r'(\[.*\]|\{.*\})', content, re.DOTALL)
                if match:
                    try:
                        raw = json.loads(match.group(1))
                    except Exception as exc:
                        logger.warning(f"[MARKET] JSON 'rescue' (recorte do texto) falhou, seguindo p/ fallback heurístico: {exc}")
                        raw = []
                else:
                    raw = []
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
        except Exception as exc:
            logger.warning(f"[MARKET] log da chamada IA falhou (ignorado p/ não derrubar o batch): {exc}")

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


def _median(values: list[float]):
    """Mediana clássica: média dos 2 centrais em lista par. Lista vazia → None."""
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


# ---------------------------------------------------------------------------
# Orquestração do pipeline completo
# ---------------------------------------------------------------------------

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
    jsearch_api_keys: list[str] | None = None
) -> dict[str, Any]:
    """Executa o pipeline completo de Inteligência de Mercado."""

    # 1. Garante vagas de amostragem no DB (limpa buscas anteriores para evitar dados de outra área)
    init_market_db(db_file)
    conn = _connect_market_db(db_file)
    conn.execute("DELETE FROM market_raw_jobs")
    conn.execute("DELETE FROM market_jobs")
    conn.commit()
    conn.close()
    date_posted = map_time_window_to_date_posted(time_window)
    generate_mock_jobs_if_empty(db_file, job_title, jsearch_api_keys=jsearch_api_keys, date_posted=date_posted, location=location)

    stack_list = [s.strip() for s in target_stack.split(",") if s.strip()]
    neg_list = [k.strip().lower() for k in negative_keywords.split(",") if k.strip()]

    # 2. Coleta todas as vagas
    conn = _connect_market_db(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, description, location, modality, source, source_url FROM market_raw_jobs")
    raw_jobs = cursor.fetchall()

    total_jobs = len(raw_jobs)
    if total_jobs == 0:
        conn.close()
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
                "exp_years_median": None,
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
    logger.info(f"[MARKET] Pré-filtro: {total_scanned} vagas → {len(pending)} vagas para análise IA")

    # Processa em lotes
    extracted_jobs = []
    relevant_count = 0
    analysis_start = time.time()

    for batch_start in range(0, len(pending), _BATCH_SIZE):
        batch = pending[batch_start:batch_start + _BATCH_SIZE]
        job_texts = [item[8] for item in batch]

        batch_results = extract_jobs_batched(client, selected_model, job_texts, stack_list, seniority=seniority, location=location, neg_list=neg_list)

        batch_rows = []
        for idx, (job_id, title, company, description, loc, mod, source, source_url, _unused) in enumerate(batch):
            extracted = batch_results[idx] if idx < len(batch_results) else {}
            extracted = _sanitize_requirements(extracted)
            # Extração agora é 100% baseada no texto real da vaga pela IA, sem injeção forçada de skills.
            # Extract languages from requirements/nice_to_have
            extracted_languages = _extract_languages(extracted)
            is_rel = extracted.get("is_relevant", False)

            reqs_norm = sorted({normalize_skill(t) for t in extracted.get("requirements", []) if normalize_skill(t)})
            nice_norm = sorted({normalize_skill(t) for t in extracted.get("nice_to_have", []) if normalize_skill(t)})

            # Debug: log first batch results
            if batch_start == 0 and idx < 3:
                logger.debug(f"[DEBUG] Job {idx+1}: title={title[:50]}, is_rel={is_rel}, reqs={reqs_norm[:3]}, nice={nice_norm[:3]}, soft={extracted.get('soft_skills', [])[:3]}, certs={extracted.get('certifications', [])[:3]}")

            if is_rel:
                relevant_count += 1
                batch_rows.append((
                    str(uuid.uuid4()), job_id, title, company, loc, mod, source, source_url or "", 1,
                    extracted.get("rejection_reason"),
                    json.dumps(reqs_norm), json.dumps(nice_norm),
                    extracted.get("role_level"),
                    extracted.get("exp_years_min"), extracted.get("exp_years_max"),
                    json.dumps(extracted.get("soft_skills", [])),
                    json.dumps(extracted.get("certifications", [])),
                    extracted.get("salary_min"), extracted.get("salary_max"),
                    extracted.get("currency"), datetime.now().isoformat()
                ))

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

        # 1 executemany + 1 commit POR LOTE (antes era commit por INSERT relevante)
        if batch_rows:
            cursor.executemany('''
                INSERT INTO market_jobs (id, raw_job_id, title, company, location, modality, source, source_url,
                    is_relevant, rejection_reason, requirements, nice_to_have, role_level, exp_years_min, exp_years_max,
                    soft_skills, certifications, salary_min, salary_max, currency, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', batch_rows)
            conn.commit()

    conn.close()

    elapsed_analysis = time.time() - analysis_start
    logger.info(f"[MARKET] AI analysis complete: {len(extracted_jobs)} jobs processed in {elapsed_analysis:.0f}s ({relevant_count} relevant)")

    # 4. Agregação de métricas
    conn = _connect_market_db(db_file)
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
        top_level_name, _ = max(levels.items(), key=lambda x: x[1])
        language_ranking.append({
            "name": lname,
            "count": sum(levels.values()),
            "top_level": top_level_name,
        })

    # Anos de experiência (Mediana + Distribuição)
    exp_median = _median(exp_years_list)

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
            # Sempre presentes no summary (padrão do contrato; defaults quando não há falha)
            "jsearch_status": "ok",
            "jsearch_message": "Busca JSearch concluída." if (jsearch_api_keys or os.getenv("JSEARCH_API_KEY", "").strip())
                               else "JSearch não utilizada nesta análise (sem chaves informadas).",
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
    report_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO market_reports (id, job_title, target_stack, seniority, location, time_window, total_jobs, relevant_jobs, confidence_score, report_data, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        report_id, job_title, target_stack, seniority, location, time_window,
        total_jobs, relevant_count, confidence, json.dumps(report_result),
        datetime.now().isoformat()
    ))
    # Retenção: mantém apenas as 30 análises mais recentes
    _apply_reports_retention(cursor)
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
    except Exception as exc:
        logger.warning(f"[MARKET] log de conclusão da análise falhou (relatório já retornado): {exc}")

    return report_result
