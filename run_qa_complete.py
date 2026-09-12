import os
import requests
import json
import fitz
import time

# Check backend
backend_ok = False
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    backend_ok = r.status_code == 200
except:
    pass

# List PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([p for p in os.listdir(docs_path) if p.endswith('.pdf')])

# Write status
out_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_status.txt"
with open(out_path, "w") as f:
    f.write(f"Backend: {'OK' if backend_ok else 'DOWN'}\n")
    f.write(f"PDFs: {len(pdfs)}\n")
    for p in pdfs:
        f.write(f"  {p}\n")

if not backend_ok:
    print("Backend não está rodando!")
    exit(1)

print(f"Backend: OK")
print(f"PDFs: {len(pdfs)}")

# Analyze each PDF
results = []
for pdf_name in pdfs:
    pdf_path = os.path.join(docs_path, pdf_name)
    print(f"\nTESTANDO: {pdf_name}")

    # Extract text
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        print(f"  Texto: {len(text)} chars")
    except Exception as e:
        print(f"  Erro ao extrair: {e}")
        continue

    # Analyze
    try:
        with open(pdf_path, 'rb') as f:
            files = {'cv_file': ('test.pdf', f, 'application/pdf')}
            resp = requests.post("http://localhost:8000/api/cv/analyze", files=files, timeout=120)
        if resp.status_code != 200:
            print(f"  Erro HTTP: {resp.status_code}")
            continue
        analysis = resp.json()
    except Exception as e:
        print(f"  Erro na análise: {e}")
        continue

    time.sleep(1)

    # Validate grounding
    errors = analysis.get("erros_ortograficos", [])
    extracted_lower = text.lower()
    issues = []
    for err in errors:
        word = err.get("palavra", "") if isinstance(err, dict) else str(err)
        contexto = err.get("contexto", "") if isinstance(err, dict) else ""
        if word and word.lower() not in extracted_lower:
            issues.append(f"ALUCINAÇÃO: '{word}'")
        if contexto and contexto not in text:
            issues.append(f"CONTEXT: '{contexto[:30]}...'")

    score = analysis.get("score", 0)
    score_ats = analysis.get("score_ats", 0)
    bullets = analysis.get("bullet_points", [])
    datas = analysis.get("datas_extraidas", [])

    print(f"  Score: {score}, ATS: {score_ats}")
    print(f"  Erros: {len(errors)}")
    for e in errors:
        print(f"    - {e}")
    print(f"  Bullets: {len(bullets)}, Datas: {len(datas)}")
    print(f"  Grounding issues: {len(issues)}")
    for iss in issues:
        print(f"    ⚠ {iss}")

    results.append({
        "nome": pdf_name,
        "score": score,
        "score_ats": score_ats,
        "erros": errors,
        "issues": issues,
        "status": "OK" if not issues else "ISSUE"
    })

# Summary
print(f"\n\nRESUMO")
print(f"Total: {len(results)}")
errors_api = sum(1 for r in results if not r.get("score"))
grounding = sum(1 for r in results if r.get("issues"))
false_positives = 0
fp_details = []

for r in results:
    for e in r.get("erros", []):
        word = e.get("palavra", "") if isinstance(e, dict) else str(e)
        if word.lower() in ['migração', 'gerenciei', 'otimizei', 'otimizai']:
            false_positives += 1
            fp_details.append(f"{r['nome']}: '{word}'")

print(f"Erros API: {errors_api}")
print(f"Grounding issues: {grounding}")
print(f"Falsos positivos: {false_positives}")
if fp_details:
    print("Falsos positivos:")
    for d in fp_details:
        print(f"  - {d}")

if false_positives == 0 and grounding == 0 and errors_api == 0:
    print("\n✅ TODOS OS TESTES PASSARAM!")
else:
    print("\n❌ PROBLEMAS ENCONTRADOS")

# Save
results_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_results.json"
with open(results_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSalvo em: {results_path}")
