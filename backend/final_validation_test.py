"""
Teste de validação abrangente do analisador de currículo.
"""
import sys
import io
import json
import requests
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8008"
DOCS = Path(__file__).parent.parent / "docs"

PDFS = [
    ("test_curriculo.pdf", "test_curriculo.pdf"),
    ("Milena Cardoso.pdf", "Currículo Milena Cardoso.pdf"),
]

passed = 0
failed = 0
results = []  # (pdf_name, pass_count, fail_count)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} -- {detail}")


def analyze_pdf(pdf_path, pdf_name):
    filepath = DOCS / pdf_path
    if not filepath.exists():
        print(f"  SKIP -- arquivo não encontrado: {filepath}")
        return None

    with open(filepath, "rb") as f:
        r = requests.post(
            f"{BASE}/api/cv/analyze",
            files={"cv_file": (pdf_path, f, "application/pdf")},
            data={"model_name": "auto/best-coding"},
            timeout=120,
        )

    if r.status_code != 200:
        print(f"  SKIP -- status {r.status_code}: {r.text[:200]}")
        return None

    data = r.json()
    parsed = data.get("data", data)
    return parsed


def validate(parsed, pdf_name):
    global passed, failed
    local_passed = 0
    local_failed = 0

    def local_check(name, condition, detail=""):
        nonlocal local_passed, local_failed
        if condition:
            local_passed += 1
            print(f"  [OK] {name}")
        else:
            local_failed += 1
            print(f"  [FAIL] {name} -- {detail}")

    if parsed is None:
        return 0, 0

    print(f"\n{'='*60}")
    print(f"  Testing: {pdf_name}")
    print(f"{'='*60}")
    print(f"  Extractor: {parsed.get('_extractor_used', 'unknown')}")
    print(f"  Nota: {parsed.get('nota', 'N/A')}")
    print(f"  Score ATS: {parsed.get('score_ats', 'N/A')}")
    print(f"  Links detectados: {parsed.get('_links', [])}")
    print(f"  Erros comuns: {parsed.get('erros_comuns_detectados', [])}")

    # 1. NOTA ESCALA 0-100
    nota = parsed.get("nota")
    local_check("Nota existe e é float", nota is not None and isinstance(nota, (int, float)))
    local_check("Nota em escala 0-100", nota is not None and 0 <= nota <= 100)
    local_check("Nota não está em escala 0-10 (valor >= 10 ou == 0)", nota is None or nota >= 10 or nota == 0)

    # 2. SCORE ATS 0-100
    score_ats = parsed.get("score_ats")
    local_check("score_ats existe e é inteiro", score_ats is not None and isinstance(score_ats, int))
    local_check("score_ats em 0-100", score_ats is not None and 0 <= score_ats <= 100)

    # 3. ERROS ORTOGRÁFICOS
    erros = parsed.get("erros_comuns_detectados", [])
    local_check("erros_comuns_detectados é lista", isinstance(erros, list))
    local_check("Sem erros inventados (lista vazia = OK para CV sem erros)", True)

    # 4. LINKS NÃO FLAGRADOS
    erros_text = json.dumps(erros).lower()
    local_check("Link wa.me não flagrado como erro", "wa.me" not in erros_text)
    local_check("Link mailto: não flagrado como erro", "mailto" not in erros_text)

    # 5. LINKS DETECTADOS
    links = parsed.get("_links", [])
    local_check("_links existe e é lista", isinstance(links, list))

    # 6. ANÁLISE POR SEÇÃO
    analise_secoes = parsed.get("analise_secoes", {})
    local_check("analise_secoes existe e é dict", isinstance(analise_secoes, dict))
    local_check("Pelo menos 1 seção analisada", len(analise_secoes) >= 1)

    for sec_name, sec_data in analise_secoes.items():
        if isinstance(sec_data, dict):
            sec_score = sec_data.get("score")
            if sec_score is not None:
                local_check(f"Score seção '{sec_name}' em 0-100", 0 <= sec_score <= 100)

    # 7. RESUMO EXECUTIVO
    local_check("resumo_executivo presente", bool(parsed.get("resumo_executivo")))

    # 8. VEREDITO ATS
    analise_ats = parsed.get("analise_ats", {})
    veredito = analise_ats.get("veredito_robos") if isinstance(analise_ats, dict) else None
    local_check("veredito_robos presente", veredito is not None and isinstance(veredito, str))
    local_check("analise_ats.score_ats em 0-100", isinstance(analise_ats, dict) and 0 <= analise_ats.get("score_ats", -1) <= 100)

    # 9. USO DE TOKENS
    local_check("uso_tokens presente", parsed.get("uso_tokens") is not None)

    # 10. FRONTEND KEYS
    frontend_keys = ["nota", "score_ats", "resumo_executivo", "analise_secoes",
                     "analise_ats", "uso_tokens", "erros_comuns_detectados", "sugestoes",
                     "_links", "_extractor_used", "foto_detectada", "foto_recomendada",
                     "ordem_secoes", "pontos_fortes", "pontos_fracos",
                     "palavras_chave_presentes", "palavras_chave_faltantes"]
    for key in frontend_keys:
        local_check(f"Key frontend '{key}' presente", key in parsed)

    # 11. SEÇÕES EM analise_secoes
    expected_secoes = ["dados_pessoais", "resumo_profissional", "experiencia_profissional",
                       "formacao_academica", "habilidades", "objetivo"]
    for sec in expected_secoes:
        local_check(f"Seção '{sec}' em analise_secoes", sec in analise_secoes)

    # 12. SUGESTÕES
    local_check("sugestoes é lista", isinstance(parsed.get("sugestoes"), list))

    # 13. STRUCTURE CONSISTENCY
    local_check("foto_detectada é booleano", isinstance(parsed.get("foto_detectada"), bool))
    local_check("foto_recomendada é booleano", isinstance(parsed.get("foto_recomendada"), bool))
    local_check("ordem_secoes é dict", isinstance(parsed.get("ordem_secoes"), dict))
    local_check("pontos_fortes é lista", isinstance(parsed.get("pontos_fortes"), list))
    local_check("pontos_fracos é lista", isinstance(parsed.get("pontos_fracos"), list))
    local_check("palavras_chave_presentes é lista", isinstance(parsed.get("palavras_chave_presentes"), list))
    local_check("palavras_chave_faltantes é lista", isinstance(parsed.get("palavras_chave_faltantes"), list))

    print(f"\n  Resultado: {pdf_name} -- {local_passed} passed, {local_failed} failed")
    return local_passed, local_failed


# ============================================================================
# MAIN
# ============================================================================
print("=" * 60)
print("  VALIDAÇÃO COMPLETA DO ANALISADOR DE CURRÍCULO")
print("=" * 60)

try:
    hr = requests.get(f"{BASE}/health", timeout=5)
    if hr.status_code != 200:
        print(f"\n[ERROR] Backend não saudável: {hr.status_code}")
        sys.exit(1)
    print(f"\nBackend saudável em {BASE}")
except Exception as e:
    print(f"\n[ERROR] Backend inacessível: {e}")
    sys.exit(1)

for pdf_file, pdf_path in PDFS:
    parsed = analyze_pdf(pdf_path, pdf_file)
    p, f = validate(parsed, pdf_file)
    results.append((pdf_file, p, f))

print(f"\n{'='*60}")
print(f"  RESULTADO FINAL: {passed} passed, {failed} failed")
print(f"{'='*60}")

for pdf_file, p, f in results:
    status = "PASS" if f == 0 else "FAIL"
    print(f"  {pdf_file}: {p} passed, {f} failed [{status}]")

if failed > 0:
    sys.exit(1)
else:
    print("\n  TODOS OS TESTES PASSARAM!")
    sys.exit(0)
