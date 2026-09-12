import os
docs = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
files = sorted(os.listdir(docs))
pdfs = [f for f in files if f.endswith('.pdf')]
print(f"Found {len(pdfs)} PDFs:")
for p in pdfs:
    print(f"  {p}")
print(f"\nNew files (test_capitalizacao etc):")
new = [p for p in pdfs if 'capitalizacao' in p or 'bullets' in p or 'sem_erros' in p or 'termos' in p or 'dados_sensiveis' in p or 'erro_sutil' in p]
for p in new:
    print(f"  {p}")
