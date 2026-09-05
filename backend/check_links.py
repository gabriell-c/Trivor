import pymupdf
from pathlib import Path

path = r"C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs\Currículo Milena Cardoso.pdf"
doc = pymupdf.open(path)
print(f"Pages: {doc.page_count}")
for i, page in enumerate(doc):
    links = page.get_links()
    text = page.get_text()
    print(f"Page {i}: links={len(links)}, text_len={len(text)}")
    for lnk in links:
        print(f"  link: {lnk}")
doc.close()
