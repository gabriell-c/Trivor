import os
import sys

# Verificar se o backend está rodando
import requests
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"Backend OK: {r.status_code}")
except Exception as e:
    print(f"Backend NÃO responde: {e}")
    sys.exit(1)

# Listar PDFs
docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
pdfs = sorted([f for f in os.listdir(docs_path) if f.endswith('.pdf')])
print(f"\nPDFs em {docs_path}: {len(pdfs)}")
for p in pdfs:
    print(f"  - {p}")

# Criar teste simples
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

font_path = r"C:\Windows\Fonts\arial.ttf"
pdfmetrics.registerFont(TTFont('Arial', font_path))

path = os.path.join(docs_path, "test_simple.pdf")
doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
title_style = ParagraphStyle('Title', fontName='Arial', fontSize=18, spaceAfter=6)
heading_style = ParagraphStyle('Heading', fontName='Arial', fontSize=13, spaceBefore=12, spaceAfter=6)
normal_style = ParagraphStyle('Normal', fontName='Arial', fontSize=10, spaceAfter=4)
bullet_style = ParagraphStyle('Bullet', fontName='Arial', fontSize=10, leftIndent=20, bulletIndent=10, spaceAfter=2)

story = []
story.append(Paragraph("TESTE SIMPLES", title_style))
story.append(Spacer(1, 12))
story.append(Paragraph("EXPERIÊNCIA", heading_style))
story.append(Paragraph("• MIGRAÇÃO do sistema legado", bullet_style))
story.append(Paragraph("• GERENCIEI a equipe técnica", bullet_style))
story.append(Paragraph("• OTIMIZAI os processos", bullet_style))

doc.build(story)
print(f"\nPDF criado: {path}")
