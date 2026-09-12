from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

font_path = r"C:\Windows\Fonts\arial.ttf"
pdfmetrics.registerFont(TTFont('Arial', font_path))

docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
os.makedirs(docs_path, exist_ok=True)

def create_cv(filename, title, content):
    path = os.path.join(docs_path, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    title_style = ParagraphStyle('Title', fontName='Arial', fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', fontName='Arial', fontSize=10, spaceAfter=4)
    heading_style = ParagraphStyle('Heading', fontName='Arial', fontSize=13, spaceBefore=12, spaceAfter=6)
    normal_style = ParagraphStyle('Normal', fontName='Arial', fontSize=10, spaceAfter=4)
    bullet_style = ParagraphStyle('Bullet', fontName='Arial', fontSize=10, leftIndent=20, bulletIndent=10, spaceAfter=2)

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(content.get('subtitle', ''), subtitle_style))
    story.append(Spacer(1, 12))

    for section in content.get('sections', []):
        story.append(Paragraph(section['title'], heading_style))
        for para in section['content']:
            if para.startswith('•'):
                story.append(Paragraph(para, bullet_style))
            else:
                story.append(Paragraph(para, normal_style))
        story.append(Spacer(1, 6))

    doc.build(story)
    print(f"Created: {path}")
    return path

# Create test PDFs
paths = []
paths.append(create_cv("test_capitalizacao.pdf", "JOSÉ CARLOS MENDES", {
    "subtitle": "jose.mendes@email.com | (11) 98765-4321",
    "sections": [
        {"title": "PERFIL", "content": ["Desenvolvedor Full Stack Sênior."]},
        {"title": "EXPERIÊNCIA", "content": ["TechLead — Nubank", "• MIGRAÇÃO do monolito para microsserviços", "• PIPELINE CI/CD com Jenkins", "• APIs REST com JAVA e SPRING BOOT"]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — USP"]},
        {"title": "HABILIDADES", "content": ["JAVA, PYTHON, Kubernetes, AWS"]}
    ]
}))

paths.append(create_cv("test_sem_erros.pdf", "ANA BEATRIZ SILVA", {
    "subtitle": "ana.silva@email.com | (21) 99876-5432",
    "sections": [
        {"title": "PERFIL", "content": ["Engenheira de Software Sênior."]},
        {"title": "EXPERIÊNCIA", "content": ["Engenheira — Nubank", "• GERENCIEI uma equipe de 12 desenvolvedores", "• OTIMIZAI o sistema de pagamentos", "• Liderança técnica de microsserviços"]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em ENGENHARIA — UFRJ"]},
        {"title": "HABILIDADES", "content": ["Python, Java, Go, Kubernetes, AWS"]}
    ]
}))

paths.append(create_cv("test_erro_real.pdf", "CARLOS EDUARDO PEREIRA", {
    "subtitle": "carlos.pereira@email.com | (31) 98765-1234",
    "sections": [
        {"title": "PERFIL", "content": ["Desenvolvedor Backend com 5 anos."]},
        {"title": "EXPERIÊNCIA", "content": ["Desenvolvedor — Stone", "• OTIMIZAI o sistema de transações", "• aprenser Python avançado", "• Desenvolvimento de APIs REST"]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — UFMG"]},
        {"title": "HABILIDADES", "content": ["Python, FastAPI, PostgreSQL"]}
    ]
}))

paths.append(create_cv("test_termos_tecnicos.pdf", "MARINA COSTA LIMA", {
    "subtitle": "marina.lima@email.com | (41) 99876-5432",
    "sections": [
        {"title": "PERFIL", "content": ["Cientista de Dados - NLP."]},
        {"title": "EXPERIÊNCIA", "content": ["Cientista — iFood", "• Modelos BERT para análise de sentimento", "• Pipeline com TensorFlow", "• APIs com GPT e LangChain"]},
        {"title": "FORMAÇÃO", "content": ["Mestrado em CIÊNCIA DA COMPUTAÇÃO — UFPR"]},
        {"title": "HABILIDADES", "content": ["Python, TensorFlow, PyTorch, BERT, GPT"]}
    ]
}))

paths.append(create_cv("test_datas_variadas.pdf", "ROBERTO ALMEIDA SANTOS", {
    "subtitle": "roberto.santos@email.com | (51) 98765-4321",
    "sections": [
        {"title": "PERFIL", "content": ["Analista de Sistemas - 15 anos."]},
        {"title": "EXPERIÊNCIA", "content": ["Analista — Banrisul", "• Jan 2022 - Presente: Liderança", "• Março de 2019 - Dez 2021: Dev", "• Fev/2018 - Jan/2019: Estagiário"]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em SISTEMAS — UFRGS (2016)"]},
        {"title": "HABILIDADES", "content": ["Java, Spring, Angular, AWS"]}
    ]
}))

paths.append(create_cv("test_bullets_complexos.pdf", "FERNANDA OLIVEIRA COSTA", {
    "subtitle": "fernanda.costa@email.com | (61) 99876-5432",
    "sections": [
        {"title": "PERFIL", "content": ["Product Manager com 7 anos."]},
        {"title": "EXPERIÊNCIA", "content": ["Product Manager — Loggi", "• Atingi 30% de crescimento em GMV mensurado por receita mensal, fazendo otimização de rota", "• REDUSEI o churn em 25% através de melhorias no onboarding", "• Liderança de produto de A a Z"]},
        {"title": "FORMAÇÃO", "content": ["MBA em GESTÃO DE PRODUTO — FGV (2020)"]},
        {"title": "HABILIDADES", "content": ["Product Strategy, Analytics, Agile, Scrum, SQL"]}
    ]
}))

paths.append(create_cv("test_dados_sensiveis.pdf", "PAULO HENRIQUE SANTOS", {
    "subtitle": "paulo.santos@email.com | CPF: 123.456.789-00",
    "sections": [
        {"title": "ENDEREÇO", "content": ["Rua das Flores, 123, Apt 45 - Centro, São Paulo - SP, 01310-100"]},
        {"title": "PERFIL", "content": ["Desenvolvedor Full Stack com 6 anos."]},
        {"title": "EXPERIÊNCIA", "content": ["Desenvolvedor — Totvs", "• Desenvolvimento de aplicações web com React e Node.js", "• Integração com APIs REST e SOAP", "• Deploy em AWS com CI/CD"]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em ENGENHARIA DE SOFTWARE — USP (2018)"]},
        {"title": "HABILIDADES", "content": ["React, Node.js, Python, AWS, Docker"]}
    ]
}))

print(f"\nCreated {len(paths)} PDFs:")
for p in paths:
    print(f"  {p}")
