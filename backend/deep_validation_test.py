"""
Teste profundo de validação: bullet points, datas, hyperlinks, organização do texto.
Versão corrigida com checks precisos.
"""
import sys, io, json, requests, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8008"
DOCS = Path(__file__).parent.parent / "docs"

import pymupdf

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} -- {detail}")

def get_raw_links(filepath):
    """Extrai URLs únicas de hyperlinks do PDF usando PyMuPDF."""
    doc = pymupdf.open(str(filepath))
    urls = set()
    for page in doc:
        for lnk in page.get_links():
            url = lnk.get("uri", "") or lnk.get("url", "")
            if url:
                urls.add(url)
    doc.close()
    return urls

def get_raw_text(filepath):
    """Extrai todo o texto bruto do PDF."""
    doc = pymupdf.open(str(filepath))
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

def analyze_pdf(pdf_file, pdf_path):
    """Analisa o PDF via API e retorna o parsed response."""
    filepath = DOCS / pdf_path
    if not filepath.exists():
        print(f"  SKIP -- {filepath}")
        return None
    with open(filepath, "rb") as f:
        r = requests.post(
            f"{BASE}/api/cv/analyze",
            files={"cv_file": (pdf_file, f, "application/pdf")},
            data={"model_name": "auto/best-coding"},
            timeout=120,
        )
    if r.status_code != 200:
        print(f"  SKIP -- status {r.status_code}: {r.text[:200]}")
        return None
    return r.json().get("data", r.json())

# ============================================================================
# TESTE 1: Hyperlinks — precisão de detecção
# ============================================================================
print("=" * 60)
print("  TESTE 1: Hyperlinks — Precisão")
print("=" * 60)

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    filepath = DOCS / pdf_path
    if not filepath.exists():
        continue

    print(f"\n  --- {pdf_file} ---")
    raw_links = get_raw_links(filepath)
    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    llm_links = set(parsed.get("_links", []))

    print(f"    Raw links (PyMuPDF): {raw_links}")
    print(f"    LLM links: {llm_links}")

    if raw_links:
        missing = raw_links - llm_links
        check(
            f"{pdf_file}: Nenhum link bruto perdido (LLM detectou todos)",
            len(missing) == 0,
            f"missing={missing}"
        )
        invented = llm_links - raw_links
        check(
            f"{pdf_file}: Nenhum link inventado pelo LLM",
            len(invented) == 0,
            f"invented={invented}"
        )
    else:
        check(
            f"{pdf_file}: Sem links brutos => sem links no LLM também",
            len(llm_links) == 0,
            f"llm_links={llm_links}"
        )

    # Links válidos NÃO devem ser flagrados como erros
    erros = parsed.get("erros_comuns_detectados", [])
    erros_desc = " ".join(e.get("descricao", "") for e in erros).lower()
    for link in llm_links:
        link_lower = link.lower()
        if "wa.me" in link_lower or "whatsapp" in link_lower:
            check(
                f"{pdf_file}: Link WhatsApp não flagrado como erro ortográfico",
                "wa.me" not in erros_desc,
                f"erros_desc contains wa.me"
            )
        if "mailto" in link_lower or ("@" in link and "gmail" in link.lower()):
            check(
                f"{pdf_file}: Link email não flagrado como erro ortográfico",
                "mailto" not in erros_desc,
                f"erros_desc contains mailto"
            )

# ============================================================================
# TESTE 2: Datas — LLM não inventa anos
# ============================================================================
print("\n" + "=" * 60)
print("  TESTE 2: Datas — Preservação")
print("=" * 60)

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    filepath = DOCS / pdf_path
    if not filepath.exists():
        continue

    full_text = get_raw_text(filepath)
    # Busca qualquer ano de 1900-2030 no texto
    years = sorted(set(re.findall(r'\b(19[0-9]\d|20[0-2]\d)\b', full_text)))

    print(f"\n  --- {pdf_file} ---")
    print(f"    Anos no PDF original: {years}")

    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    resumo = parsed.get("resumo_executivo", "")
    resp_years = sorted(set(re.findall(r'\b(19[0-9]\d|20[0-2]\d)\b', resumo)))
    invented = set(resp_years) - set(years)

    check(
        f"{pdf_file}: Anos no resumo existem no original (sem invenção)",
        len(invented) == 0,
        f"invented={invented}, resp={resp_years}, orig={years}"
    )

    # Check years in analise_secoes too
    secoes_text = json.dumps(parsed.get("analise_secoes", {}))
    secao_years = sorted(set(re.findall(r'\b(19[0-9]\d|20[0-2]\d)\b', secoes_text)))
    invented_sec = set(secao_years) - set(years)
    check(
        f"{pdf_file}: Anos nas seções existem no original",
        len(invented_sec) == 0,
        f"invented={invented_sec}"
    )

# ============================================================================
# TESTE 3: Bullet points — LLM identifica corretamente
# ============================================================================
print("\n" + "=" * 60)
print("  TESTE 3: Bullet Points — Identificação")
print("=" * 60)

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    filepath = DOCS / pdf_path
    if not filepath.exists():
        continue

    print(f"\n  --- {pdf_file} ---")
    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    hab = parsed.get("analise_secoes", {}).get("habilidades", {})
    bp = hab.get("bullet_points") if isinstance(hab, dict) else None
    check(
        f"{pdf_file}: bullet_points presente na seção habilidades",
        bp is not None,
        f"bullet_points={bp}"
    )

    # Bullet points no texto extraído (para verificar se o LLM viu bullets)
    full_text = get_raw_text(filepath)
    # Procura por caracteres de bullet ou marcadores
    has_bullets_raw = any(c in full_text for c in ["•", "·", "\u2022", "\u2023"])
    has_dash_bullets = bool(re.search(r'^\s*[-*]\s+\S', full_text, re.MULTILINE))

    # Se o PDF tem bullets, o LLM deve ter detectado
    if has_bullets_raw or has_dash_bullets:
        check(
            f"{pdf_file}: PDF com bullets => LLM analisou bullet_points",
            bp is not None,
            f"has_bullets_raw={has_bullets_raw}, has_dash={has_dash_bullets}"
        )

    # Experiência profissional deve ter score válido
    exp = parsed.get("analise_secoes", {}).get("experiencia_profissional", {})
    if isinstance(exp, dict):
        check(
            f"{pdf_file}: experiencia_profissional tem score 0-100",
            0 <= exp.get("score", -1) <= 100,
            f"score={exp.get('score')}"
        )
        check(
            f"{pdf_file}: experiencia_profissional tem status",
            "status" in exp,
            f"keys={list(exp.keys())}"
        )

# ============================================================================
# TESTE 4: Organização do texto — seções presentes no PDF são analisadas
# ============================================================================
print("\n" + "=" * 60)
print("  TESTE 4: Organização do texto — Seções")
print("=" * 60)

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    filepath = DOCS / pdf_path
    if not filepath.exists():
        continue

    full_text = get_raw_text(filepath).lower()
    print(f"\n  --- {pdf_file} ---")

    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    secoes = parsed.get("analise_secoes", {})

    text_indicators = {
        "dados_pessoais": ["nome", "email", "telefone", "endereço", "localização"],
        "experiencia_profissional": ["experiência", "experiencia", "atuação", "cargo", "empresa"],
        "formacao_academica": ["formação", "formacao", "graduacao", "graduação", "bacharelado", "mestrado"],
        "habilidades": ["habilidades", "competências", "competencias", "skills"],
        "objetivo": ["objetivo"],
    }

    for sec_name, keywords in text_indicators.items():
        in_pdf = any(kw in full_text for kw in keywords)
        in_analysis = sec_name in secoes
        if in_pdf:
            check(
                f"{pdf_file}: Seção '{sec_name}' no PDF => analisada",
                in_analysis,
                f"in_pdf={in_pdf}, in_analysis={in_analysis}"
            )

    # Todas as seções esperadas devem estar presentes na análise
    for sec_name in text_indicators:
        check(
            f"{pdf_file}: Seção '{sec_name}' sempre presente na análise",
            sec_name in secoes,
            f"secoes={list(secoes.keys())}"
        )

    # Score de cada seção deve estar em 0-100
    for sec_name, sec_data in secoes.items():
        if isinstance(sec_data, dict) and "score" in sec_data:
            score = sec_data["score"]
            check(
                f"{pdf_file}: Score '{sec_name}' em 0-100",
                0 <= score <= 100,
                f"score={score}"
            )

# ============================================================================
# TESTE 5: Falsos positivos de erro ortográfico — PALAVRAS SEGURAS
# ============================================================================
print("\n" + "=" * 60)
print("  TESTE 5: Falsos positivos — Palavras seguras")
print("=" * 60)

SAFE_WORDS = [
    "Python", "JavaScript", "SQL", "Git", "AWS", "Docker",
    "React", "Node", "Java", "C++", "TypeScript", "API",
    "Milena", "Cardoso", "Gabriel", "Silva", "Souza",
    "wa.me", "mailto:", "linkedin.com",
    "OCR", "UX", "CI/CD",
]

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    filepath = DOCS / pdf_path
    if not filepath.exists():
        continue

    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    erros = parsed.get("erros_comuns_detectados", [])
    # Checa apenas nas descrições dos erros (não no tipo)
    erros_desc = " ".join(e.get("descricao", "") for e in erros).lower()
    erros_exemplo = " ".join(e.get("exemplo", "") or "" for e in erros).lower()
    erros_tipo = " ".join(e.get("tipo", "") for e in erros).lower()
    erros_texto = erros_desc + " " + erros_exemplo + " " + erros_tipo

    print(f"\n  --- {pdf_file} ---")
    print(f"    Erros detectados: {erros}")

    for word in SAFE_WORDS:
        word_lower = word.lower()
        # Check exact word match (not substring)
        found = bool(re.search(rf'\b{re.escape(word_lower)}\b', erros_texto))
        check(
            f"{pdf_file}: '{word}' NÃO flagrado como erro",
            not found,
            f"error_desc={erros_desc[:100]}" if found else ""
        )

# Also check that wa.me/mailto links are in _links and NOT in errors
for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue
    links = parsed.get("_links", [])
    erros = parsed.get("erros_comuns_detectados", [])
    erros_desc = " ".join(e.get("descricao", "") for e in erros).lower()

    for link in links:
        link_lower = link.lower()
        if "wa.me" in link_lower:
            check(
                f"{pdf_file}: Link wa.me presente em _links e NÃO em erros",
                "wa.me" not in erros_desc,
                f"erros={erros}"
            )
        if "mailto" in link_lower:
            check(
                f"{pdf_file}: Link mailto presente em _links e NÃO em erros",
                "mailto" not in erros_desc,
                f"erros={erros}"
            )

# ============================================================================
# TESTE 6: Estrutura de resposta — todos os campos corretos
# ============================================================================
print("\n" + "=" * 60)
print("  TESTE 6: Estrutura de resposta")
print("=" * 60)

for pdf_file, pdf_path in [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]:
    parsed = analyze_pdf(pdf_file, pdf_path)
    if parsed is None:
        continue

    print(f"\n  --- {pdf_file} ---")

    # Nota 0-100
    nota = parsed.get("nota")
    check(f"{pdf_file}: nota é float em 0-100", isinstance(nota, (int, float)) and 0 <= nota <= 100)

    # Score ATS 0-100
    score_ats = parsed.get("score_ats")
    check(f"{pdf_file}: score_ats é int em 0-100", isinstance(score_ats, int) and 0 <= score_ats <= 100)

    # analise_ats
    ats = parsed.get("analise_ats", {})
    check(f"{pdf_file}: analise_ats é dict", isinstance(ats, dict))
    if isinstance(ats, dict):
        check(f"{pdf_file}: analise_ats.veredito_robos presente", "veredito_robos" in ats)
        check(f"{pdf_file}: analise_ats.score_ats em 0-100", 0 <= ats.get("score_ats", -1) <= 100)
        check(f"{pdf_file}: analise_ats.gargalos_formatacao é lista", isinstance(ats.get("gargalos_formatacao"), list))
        check(f"{pdf_file}: analise_ats.palavras_chave_faltantes é lista", isinstance(ats.get("palavras_chave_faltantes"), list))

    # _extractor_used
    check(f"{pdf_file}: _extractor_used presente", "_extractor_used" in parsed)
    check(f"{pdf_file}: _extractor_used é string", isinstance(parsed.get("_extractor_used"), str))

    # uso_tokens
    tokens = parsed.get("uso_tokens")
    check(f"{pdf_file}: uso_tokens presente", tokens is not None)
    if isinstance(tokens, dict):
        check(f"{pdf_file}: uso_tokens.total_tokens é int", isinstance(tokens.get("total_tokens"), int))

    # foto_detectada / foto_recomendada
    check(f"{pdf_file}: foto_detectada é bool", isinstance(parsed.get("foto_detectada"), bool))
    check(f"{pdf_file}: foto_recomendada é bool", isinstance(parsed.get("foto_recomendada"), bool))

    # ordem_secoes
    ordem = parsed.get("ordem_secoes")
    check(f"{pdf_file}: ordem_secoes é dict", isinstance(ordem, dict))

    # sugestoes
    check(f"{pdf_file}: sugestoes é lista", isinstance(parsed.get("sugestoes"), list))

    # erros_comuns_detectados
    check(f"{pdf_file}: erros_comuns_detectados é lista", isinstance(parsed.get("erros_comuns_detectados"), list))

# ============================================================================
# MAIN
# ============================================================================
print("\n" + "=" * 60)
print(f"  RESULTADO FINAL: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("\n  TODOS OS TESTES PASSARAM!")
    sys.exit(0)
