import requests
import os

# Testar backend
backend_ok = False
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    backend_ok = r.status_code == 200
    print(f"Backend: {'OK' if backend_ok else 'NÃO RESPONDE'}")
except Exception as e:
    print(f"Backend error: {e}")

if not backend_ok:
    print("Backend não está rodando!")
    exit(1)

# Listar PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])
print(f"\nPDFs encontrados: {len(pdfs)}")
for p in pdfs:
    print(f"  {p}")
