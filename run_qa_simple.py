import requests
import json
import os
import fitz
import time

BASE_URL = "http://localhost:8000"
DOCS_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"

def extract_pdf_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        return f"ERRO: {e}"

def analyze_cv(pdf_path):
    try:
        with open(pdf_path, 'rb') as f:
            files = {'cv_file': ('test.pdf', f, 'application/pdf')}
            resp = requests.post(f"{BASE_URL}/api/cv/analyze", files=files, timeout=120)
        if resp.status_code != 200:
            return {"erro": f"HTTP {resp.status_code}"}
        return resp.json()
    except Exception as e:
        return {"erro": str(e)}

def validate_grounding(analysis, pdf_text):
    errors = analysis.get("erros_ortograficos", [])
    extracted_lower = pdf_text.lower()
    issues = []
    for err in errors:
        word = err.get("palavra", "") if isinstance(err, dict) else str(err)
        contexto = err.get("contexto", "") if isinstance(err, dict) else ""
        if word and word.lower() not in extracted_lower:
            issues.append(f"ALUCINAÇÃO: '{word}'")
        if contexto and contexto not in pdf_text:
            issues.append(f"CONTEXT ALTERADO")
    return issues

# List PDFs
pdfs = sorted([f for f in os.listdir(DOCS_PATH) if f.endswith('.pdf')])
print(f"Testing {len(pdfs)} PDFs...")

results = []
for pdf_name in pdfs:
    pdf_path = os.path.join(DOCS_PATH, pdf_name)
    print(f"\n=== {pdf_name} ===")

    pdf_text = extract_pdf_text(pdf_path)
    print(f"Text: {len(pdf_text)} chars")

    analysis = analyze_cv(pdf_path)
    time.sleep(0.5)

    if "erro" in analysis:
        print(f"Error: {analysis['erro']}")
        results.append({"nome": pdf_name, "erro": analysis["erro"]})
        continue

    issues = validate_grounding(analysis, pdf_text)
    score = analysis.get("score", 0)
    erros = analysis.get("erros_ortograficos", [])
    bullets = analysis.get("bullet_points", [])
    datas = analysis.get("datas_extraidas", [])

    print(f"Score: {score}, Erros: {len(erros)}, Bullets: {len(bullets)}, Datas: {len(datas)}")
    for e in erros:
        print(f"  Erro: {e}")
    for iss in issues:
        print(f"  ⚠ {iss}")

    results.append({
        "nome": pdf_name,
        "score": score,
        "erros": erros,
        "issues": issues,
        "status": "OK" if not issues else "ISSUE"
    })

# Summary
print(f"\n\n{'='*60}")
print("RESUMO")
print(f"{'='*60}")

total = len(results)
errors_api = sum(1 for r in results if r.get("erro"))
grounding = sum(1 for r in results if r.get("issues"))
false_positives = 0

for r in results:
    if r.get("erro"):
        continue
    for e in r.get("erros", []):
        word = e.get("palavra", "") if isinstance(e, dict) else str(e)
        if word.lower() in ['migração', 'gerenciei', 'otimizei', 'otimizai']:
            false_positives += 1
            print(f"  FALSO POSITIVO: {r['nome']} - '{word}'")

print(f"Total: {total}")
print(f"Erros API: {errors_api}")
print(f"Grounding issues: {grounding}")
print(f"Falsos positivos: {false_positives}")

if false_positives == 0 and grounding == 0 and errors_api == 0:
    print("\n✅ TODOS OS TESTES PASSARAM!")
else:
    print("\n❌ PROBLEMAS ENCONTRADOS")
