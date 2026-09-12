import requests
import json

# Testar backend
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"Health: {r.status_code} - {r.text}")
except Exception as e:
    print(f"Health error: {e}")

# Listar PDFs
import os
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = [f for f in os.listdir(docs_path) if f.endswith('.pdf')]
print(f"\nPDFs: {pdfs}")

# Testar análise de um PDF
if pdfs:
    pdf_path = os.path.join(docs_path, pdfs[0])
    print(f"\nTestando: {pdfs[0]}")
    try:
        with open(pdf_path, 'rb') as f:
            files = {'cv_file': ('test.pdf', f, 'application/pdf')}
            resp = requests.post("http://localhost:8000/api/cv/analyze", files=files, timeout=120)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Score: {data.get('score')}")
            print(f"Erros: {data.get('erros_ortograficos', [])}")
    except Exception as e:
        print(f"Error: {e}")
