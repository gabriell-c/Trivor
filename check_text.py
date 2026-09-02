#!/usr/bin/env python3
import pymupdf
import os

DOCS = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'

# Check Gabriel
print("=== GABRIEL PDF text check ===")
doc = pymupdf.open(os.path.join(DOCS, 'Curriculo Gabriel Cardoso.pdf'))
for i in range(len(doc)):
    t = doc[i].get_text()
    idx = t.find('seguran')
    if idx >= 0:
        print(f"Page {i}: {repr(t[max(0,idx-10):idx+25])}")
doc.close()

# Check Mariana
print("\n=== MARIANA PDF text check ===")
doc = pymupdf.open(os.path.join(DOCS, 'test_erro_orho_real.pdf'))
t = doc[0].get_text()
idx = t.find('Lider')
if idx >= 0:
    print(f"Mariana: {repr(t[max(0,idx-5):idx+25])}")
idx2 = t.find('lider')
if idx2 >= 0:
    print(f"Mariana lower: {repr(t[max(0,idx2-5):idx2+25])}")
doc.close()

# Check if "segurançe" appears ANYWHERE in Gabriel
print("\n=== Searching for 'segurançe' ===")
doc = pymupdf.open(os.path.join(DOCS, 'Curriculo Gabriel Cardoso.pdf'))
found = False
for i in range(len(doc)):
    t = doc[i].get_text()
    if 'segurançe' in t:
        print(f"FOUND on page {i}")
        found = True
if not found:
    print("NOT FOUND - LLM is hallucinating this word")
doc.close()
