"""Camada de texto puro da Inteligência de Mercado — sem I/O.

Normalização canônica de skills, detecção de senioridade/nacionalidade,
score de keywords e pré-filtro de vagas: tudo regex sobre texto, sem DB
nem rede (quem faz I/O são market_db e market_jsearch).
"""

import re

from market_log import logger

# Max jobs sent to AI per analysis — pre-filter reduces the pool first
_MAX_JOBS_FOR_ANALYSIS = 3000


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
    r"\b(powerpoint|ms\s*powerpoint|microsoft\s*powerpoint)\b": "PowerPoint",
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
    r"\b(organização|organizacao)\b": "Organização",
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
    r"\bsuporte|suporta|help\s*desk|central\s*de\s+ajuda\b": "Suporte Técnico",
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
    return bool(re.match(r'^[\d\s.,%\-/]+$', t))


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


def extract_mentioned_skills(text: str) -> list[str]:
    """Retorna as skills canônicas mencionadas em QUALQUER parte do texto,
    usando o mapeamento _SKILL_NORMALIZATION (mesma base canônica do market).
    Usa-se no fit determinístico CV × vaga para complementar a extração
    heurística estruturada (que só pega linhas com palavras-chave de requisito)."""
    if not text or not text.strip():
        return []
    text_lower = text.lower()
    mentioned: list[str] = []
    seen = set()
    for pattern, canonical in _SKILL_NORMALIZATION.items():
        if not canonical:
            continue
        if re.search(pattern, text_lower, re.IGNORECASE):
            key = canonical.strip().lower()
            if key and key not in seen:
                seen.add(key)
                mentioned.append(canonical.strip())
    return mentioned


def _parse_br_number(raw: str) -> float:
    """Converte número em formato brasileiro (milhar '.', decimal ',') para float.
    Padrão BR: '.' é milhar e ',' é decimal — '8.000' → 8000.0, '8.000,50' → 8000.5.
    Sem vírgula, só é milhar quando se encaixa no padrão 1.234(.56)?;
    caso contrário é decimal ('8.5' → 8.5)."""
    s = raw.strip()
    if not s:
        raise ValueError("número de salário vazio")
    if ',' in s:
        return float(s.replace('.', '').replace(',', '.'))
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', s):
        return float(s.replace('.', ''))
    return float(s)


# ---------------------------------------------------------------------------
# Detecção: senioridade, janela de datas e nacionalidade da vaga
# ---------------------------------------------------------------------------

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
    """Mapeia time_window do frontend para valor da API JSearch.

    Regra: nunca encolher a janela pedida — usa o valor suportado pela API
    com amplitude MENOR OU IGUAL à janela solicitada ('3days', 'week'=7d,
    'month'=30d, 'all'). Janelas acima de 30 dias viram 'all', o que pode
    incluir vagas mais antigas, mas nunca subestima a recência pedida.
    """
    match = re.search(r'(\d+)\s*dias?', time_window.lower().strip())
    if not match:
        return 'all'
    days = int(match.group(1))
    if days <= 3:
        return '3days'
    if days <= 7:
        return 'week'
    if days <= 30:
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


def _keyword_score(job_text_lower: str, job_title: str, target_stack: list[str], seniority: str, location: str) -> int:
    """Retorna score de relevância permissivo. Nunca zera por falta de palavra exata."""
    if seniority.lower() == "nenhum":
        sen_matches = []
    else:
        sen_matches = _SENIORITY_MATCHES.get(seniority.lower(), [])

    keywords = target_stack or [w for w in job_title.strip().split() if len(w) > 2]

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
    raw_jobs: list[tuple],
    target_stack: list[str],
    seniority: str,
    location: str,
    neg_list: list[str],
    max_jobs: int = _MAX_JOBS_FOR_ANALYSIS,
) -> list[tuple]:
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
            if any(loc in loc_text for loc in _NON_BR_LOCATIONS):
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
