"""Test de conexão com o backend."""
import requests
import os

# Verificar backend
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"Backend: {r.status_code} - {r.text}")
except Exception as e:
    print(f"Backend não responde: {e}")

# Listar PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])
print(f"\nPDFs encontrados ({len(pdfs)}):")
for p in pdfs:
    print(f"  - {p}")
