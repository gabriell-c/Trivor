import os
import sys

# Debug info
print(f"CWD: {os.getcwd()}")
print(f"Python: {sys.executable}")

# Test write
test_path = r"C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\test_write.txt"
try:
    with open(test_path, 'w') as f:
        f.write("test")
    print(f"Write OK: {os.path.exists(test_path)}")
except Exception as e:
    print(f"Write error: {e}")

# List docs
docs_path = r"C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = os.listdir(docs_path)
pdfs = [p for p in pdfs if p.endswith('.pdf')]
print(f"PDFs: {len(pdfs)}")
for p in sorted(pdfs):
    print(f"  {p}")
