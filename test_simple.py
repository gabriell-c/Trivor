import os
import sys
import requests

# Verificar backend
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    backend_ok = r.status_code == 200
    print(f"Backend: {'OK' if backend_ok else 'NÃO RESPONDE'}")
except Exception as e:
    backend_ok = False
    print(f"Backend error: {e}")

# Listar PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])
print(f"\nPDFs: {len(pdfs)}")
for p in pdfs[:10]:
    print(f"  {p}")

# Salvar resultado
with open("test_output.txt", "w") as f:
    f.write(f"Backend OK: {backend_ok}\n")
    f.write(f"PDFs: {len(pdfs)}\n")
    for p in pdfs:
        f.write(f"  {p}\n")

print("\nResultado salvo em test_output.txt")
