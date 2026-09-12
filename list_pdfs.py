import os
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])
print(f"PDFs in docs: {len(pdfs)}")
for p in pdfs:
    print(f"  {p}")
