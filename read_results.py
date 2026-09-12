import json

# Read results
with open(r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v4_results.json", 'r', encoding='utf-8') as f:
    results = json.load(f)

print(f"Total results: {len(results)}")
for r in results:
    nome = r.get('nome', 'N/A')
    nota = r.get('nota', 'N/A')
    erros = len(r.get('erros_ortograficos', []))
    issues = len(r.get('grounding_issues', []))
    status = "ISSUES!" if issues > 0 else "OK"
    print(f"{nome}: nota={nota}, erros={erros}, issues={issues} [{status}]")

# Check for new PDFs
import os
docs = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = [f for f in os.listdir(docs) if f.endswith('.pdf')]
print(f"\nPDFs in docs: {len(pdfs)}")
for p in sorted(pdfs):
    print(f"  {p}")
