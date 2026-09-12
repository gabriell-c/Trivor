"""
Criar CVs de teste com edge cases.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

font_path = r"C:\Windows\Fonts\arial.ttf"
pdfmetrics.registerFont(TTFont('Arial', font_path))

DOCS_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"

def create_cv(filename, title, content):
    path = os.path.join(DOCS_PATH, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    title_style = ParagraphStyle('Title', fontName='Arial', fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', fontName='Arial', fontSize=10, spaceAfter=4)
    heading_style = ParagraphStyle('Heading', fontName='Arial', fontSize=13, spaceBefore=12, spaceAfter=6)
    normal_style = ParagraphStyle('Normal', fontName='Arial', fontSize=10, spaceAfter=4)
    bullet_style = ParagraphStyle('Bullet', fontName='Arial', fontSize=10, leftIndent=20, bulletIndent=10, spaceAfter=2)

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(content['subtitle'], subtitle_style))
    story.append(Spacer(1, 12))

    for section in content['sections']:
        story.append(Paragraph(section['title'], heading_style))
        for para in section['content']:
            if para.startswith('•'):
                story.append(Paragraph(para, bullet_style))
            else:
                story.append(Paragraph(para, normal_style))
        story.append(Spacer(1, 6))

    doc.build(story)
    print(f"Created: {path}")

# 1. test_capitalizacao.pdf - Testa palavras em maiúsculas
create_cv("test_capitalizacao.pdf", "JOSÉ CARLOS MENDES", {
    "subtitle": "jose.mendes@email.com | (11) 98765-4321 | São Paulo, SP",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Desenvolvedor Full Stack Sênior com 10+ anos de experiência."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "TechLead — Nubank",
            "• MIGRAÇÃO do monolito para microsserviços, reduzindo deploy time em 70%",
            "• Implementação de PIPELINE CI/CD com Jenkins e Docker",
            "• Desenvolvimento de APIs REST com JAVA e SPRING BOOT",
            "• Otimização de queries SQL que RESULTARAM em 40% de melhoria"
        ]},
        {"title": "FORMAÇÃO ACADÊMICA", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — USP (2015)"]},
        {"title": "HABILIDADES", "content": ["JAVA, PYTHON, TypeScript, Go, Kubernetes, AWS"]}
    ]
})

# 2. test_sem_erros.pdf - CV perfeito com GERENCIEI
create_cv("test_sem_erros.pdf", "ANA BEATRIZ SILVA", {
    "subtitle": "ana.silva@email.com | (21) 99876-5432 | Rio de Janeiro, RJ",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Engenheira de Software Sênior com 8 anos de experiência em fintechs."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Engenheira de Software — Nubank",
            "• GERENCIEI uma equipe de 12 desenvolvedores em projetos de alta complexidade",
            "• OTIMIZAI o sistema de pagamentos, reduzindo latency em 35%",
            "• Liderança técnica de microsserviços em AWS",
            "• Code review e mentoria de desenvolvedores júniores"
        ],
        {"title": "FORMAÇÃO ACADÊMICA", "content": ["Bacharel em ENGENHARIA DA COMPUTAÇÃO — UFRJ (2016)"]},
        {"title": "HABILIDADES", "content": ["Python, Java, Go, Kubernetes, AWS, PostgreSQL"]}
    ]
})

# 3. test_erro_sutil.pdf - Testa erro sutil OTIMIZAI
create_cv("test_erro_sutil.pdf", "CARLOS EDUARDO PEREIRA", {
    "subtitle": "carlos.pereira@email.com | (31) 98765-1234 | Belo Horizonte, MG",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Desenvolvedor Backend com 5 anos de experiência."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Desenvolvedor Backend — Stone",
            "• OTIMIZAI o sistema de processamento de transações",
            "• Desenvolvimento de APIs REST com Python e FastAPI",
            "• Implementação de fila de mensagens com RabbitMQ"
        ]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — UFMG (2019)"]},
        {"title": "HABILIDADES", "content": ["Python, FastAPI, PostgreSQL, Docker, Kubernetes"]}
    ]
})

# 4. test_termos_tecnicos.pdf - Testa termos técnicos que NÃO são erros
create_cv("test_termos_tecnicos.pdf", "MARINA COSTA LIMA", {
    "subtitle": "marina.lima@email.com | (41) 99876-5432 | Curitiba, PR",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Cientista de Dados com especialização em NLP e Machine Learning."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Cientista de Dados — iFood",
            "• Treinamento de modelos BERT para análise de sentimento",
            "• Implementação de pipeline de feature engineering com TensorFlow",
            "• Desenvolvimento de APIs de inferência com GPT e LangChain",
            "• Otimização de modelos com ONNX e TensorRT"
        ]},
        {"title": "FORMAÇÃO", "content": ["Mestrado em CIÊNCIA DA COMPUTAÇÃO — UFPR (2020)"]},
        {"title": "HABILIDADES", "content": ["Python, TensorFlow, PyTorch, BERT, GPT, LangChain, SQL"]}
    ]
})

# 5. test_datas_variadas2.pdf - Testa formatos variados de data
create_cv("test_datas_variadas2.pdf", "ROBERTO ALMEIDA SANTOS", {
    "subtitle": "roberto.santos@email.com | (51) 98765-4321 | Porto Alegre, RS",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Analista de Sistemas com 15 anos de experiência."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Analista Sênior — Banrisul",
            "• Jan 2022 - Presente: Liderança de equipe de desenvolvimento",
            "• Março de 2019 - Dez 2021: Desenvolvedor Full Stack",
            "• Fev/2018 - Jan/2019: Estagiário de análise de sistemas",
            "• 2016 - 2018: Suporte técnico"
        ]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em SISTEMAS DE INFORMAÇÃO — UFRGS (2016)"]},
        {"title": "HABILIDADES", "content": ["Java, Spring Boot, Angular, PostgreSQL, AWS"]}
    ]
})

# 6. test_bullets_complexos.pdf - Testa fórmula XYZ e erros
create_cv("test_bullets_complexos.pdf", "FERNANDA OLIVEIRA COSTA", {
    "subtitle": "fernanda.costa@email.com | (61) 99876-5432 | Brasília, DF",
    "sections": [
        {"title": "PERFIL PROFISSIONAL", "content": ["Product Manager com 7 anos de experiência em startups."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Product Manager — Loggi",
            "• Atingi 30% de crescimento em GMV mensurado por receita mensal, fazendo otimização de rota",
            "• REDUSEI o churn em 25% através de melhorias no onboarding",
            "• Liderança de produto de A a Z, desde ideação até launch"
        ]},
        {"title": "FORMAÇÃO", "content": ["MBA em GESTÃO DE PRODUTO — FGV (2020)"]},
        {"title": "HABILIDADES", "content": ["Product Strategy, Analytics, Agile, Scrum, SQL"]}
    ]
})

# 7. test_dados_sensiveis.pdf - Testa dados sensíveis
create_cv("test_dados_sensiveis.pdf", "PAULO HENRIQUE SANTOS", {
    "subtitle": "paulo.santos@email.com | CPF: 123.456.789-00 | RG: 12.345.678-9",
    "sections": [
        {"title": "ENDEREÇO", "content": ["Rua das Flores, 123, Apt 45 - Centro, São Paulo - SP, 01310-100"]},
        {"title": "PERFIL PROFISSIONAL", "content": ["Desenvolvedor Full Stack com 6 anos de experiência."]},
        {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
            "Desenvolvedor Full Stack — Totvs",
            "• Desenvolvimento de aplicações web com React e Node.js",
            "• Integração com APIs REST e SOAP",
            "• Deploy em AWS com CI/CD"
        ]},
        {"title": "FORMAÇÃO", "content": ["Bacharel em ENGENHARIA DE SOFTWARE — USP (2018)"]},
        {"title": "HABILIDADES", "content": ["React, Node.js, Python, AWS, Docker"]}
    ]
})

print("\nTodos os PDFs criados com sucesso!")
