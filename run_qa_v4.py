import requests
import json
import os
import fitz

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
        if word.lower() not in extracted_lower:
            issues.append(f"ALUCINACAO: '{word}' não existe no PDF")
        if contexto and contexto not in pdf_text:
            issues.append(f"CONTEXT ALTERADO: '{contexto[:30]}...'")
    return issues

all_pdfs = sorted([f for f in os.listdir(DOCS_PATH) if f.endswith('.pdf')])
print(f"Total PDFs: {len(all_pdfs)}")

results = []
for pdf_name in all_pdfs:
    pdf_path = os.path.join(DOCS_PATH, pdf_name)
    pdf_text = extract_pdf_text(pdf_path)
    analysis = analyze_cv(pdf_path)
    issues = validate_grounding(analysis, pdf_text)
    result = {
        "nome": pdf_name,
        "nota": analysis.get("nota"),
        "score_ats": analysis.get("score_ats"),
        "erros_ortograficos": analysis.get("erros_ortograficos", []),
        "grounding_issues": issues,
    }
    results.append(result)
    print(f"{pdf_name}: nota={analysis.get('nota')}, erros={len(analysis.get('erros_ortograficos', []))}, issues={len(issues)}")

# Save to C:\\temp
output_path = r"C:\\temp\\qa_results.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nSaved to: {output_path}")

total = len([r for r in results if "erro" not in r])
with_errors = len([r for r in results if r.get("erros_ortograficos")])
with_issues = len([r for r in results if r.get("grounding_issues")])
print(f"Total: {total}, Com erros: {with_errors}, Com issues: {with_issues}")
if with_issues > 0:
    print("ALUCINACOES ENCONTRADAS!")
    for r in results:
        if r.get("grounding_issues"):
            print(f"  {r['nome']}: {r['grounding_issues']}")
else:
    print("TODOS PASSARAM - 0 alucinações!")
