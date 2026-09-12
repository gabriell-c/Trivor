import os
import requests

# Check backend
backend_ok = False
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    backend_ok = r.status_code == 200
except:
    pass

# List PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])

# Write results
with open("qa_status.txt", "w", encoding="utf-8") as f:
    f.write(f"Backend OK: {backend_ok}\n")
    f.write(f"PDFs: {len(pdfs)}\n")
    for p in pdfs:
        f.write(f"  {p}\n")

print(f"Backend: {backend_ok}")
print(f"PDFs: {len(pdfs)}")
for p in pdfs:
    print(f"  {p}")
