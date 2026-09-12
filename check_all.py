import os, requests, json, fitz, time

# Check backend
backend_ok = False
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    backend_ok = r.status_code == 200
except:
    pass

with open("qa_status.txt", "w") as f:
    f.write(f"Backend: {'OK' if backend_ok else 'DOWN'}\n")
    if not backend_ok:
        f.write("ERROR: Backend not running\n")
        exit(1)

# List PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([p for p in os.listdir(docs_path) if p.endswith('.pdf')])
with open("qa_status.txt", "a") as f:
    f.write(f"PDFs: {len(pdfs)}\n")
    for p in pdfs:
        f.write(f"  {p}\n")

print(f"Backend: {'OK' if backend_ok else 'DOWN'}")
print(f"PDFs: {len(pdfs)}")
for p in pdfs:
    print(f"  {p}")
