"""
Criar CVs de teste com edge cases específicos para QA.
Foca em: capitalização, bullet points, datas variadas, erros ortográficos sutis,
formatação complexa, termos técnicos, nomes próprios.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Registrar fonte Arial para suportar acentos
font_path = r"C:\Windows\Fonts\arial.ttf"
pdfmetrics.registerFont(TTFont('Arial', font_path))

def create_cv(path, name):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Arial', fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName='Arial', fontSize=10, spaceAfter=4)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontName='Arial', fontSize=13, spaceBefore=12, spaceAfter=6)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName='Arial', fontSize=10, spaceAfter=4)
    bullet_style = ParagraphStyle('Bullet', parent=styles['Normal'], fontName='Arial', fontSize=10, leftIndent=20, bulletIndent=10, spaceAfter=2)

    story = []

    if name == "test_capitalizacao":
        # Testa capitalização: palavras em maiúsculas, título, bullets
        story.append(Paragraph("JOSÉ CARLOS MENDES", title_style))
        story.append(Paragraph("jose.mendes@email.com | (11) 98765-4321 | São Paulo, SP", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("PERFIL PROFISSIONAL", heading_style))
        story.append(Paragraph("Desenvolvedor Full Stack Sênior com 10+ anos de experiência em projetos de alta escala. Especialista em arquitetura de microsserviços, integrações REST e Cloud.", normal_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("TechLead — Nubank", bullet_style))
        story.append(Paragraph("• Liderança técnica de equipe com 8 desenvolvedores", bullet_style))
        story.append(Paragraph("• MIGRAÇÃO do monolito para microsserviços, reduzindo deploy time em 70%", bullet_style))
        story.append(Paragraph("• Implementação de PIPELINE CI/CD com Jenkins e Docker", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Desenvolvedor Pleno — Itaú Unibanco", bullet_style))
        story.append(Paragraph("• Desenvolvimento de APIs REST com JAVA e SPRING BOOT", bullet_style))
        story.append(Paragraph("• Otimização de queries SQL que RESULTARAM em 40% de melhoria no performance", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Bacharel em CIÊNCIA DA COMPUTAÇÃO — USP (2015)", normal_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("HABILIDADES TÉCNICAS", heading_style))
        story.append(Paragraph("JAVA, PYTHON, typescript, GO, Kubernetes, AWS, PostgreSQL, Redis, Kafka", normal_style))

    elif name == "test_datas_variadas":
        # Testa diversos formatos de data
        story.append(Paragraph("MARIA FERNANDA OLIVEIRA", title_style))
        story.append(Paragraph("maria.oliveira@email.com | (21) 99988-7766 | Rio de Janeiro, RJ", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("Gerente de Projetos — Petrobras", bullet_style))
        story.append(Paragraph("Jan 2022 – Presente", normal_style))
        story.append(Paragraph("• Gestão de portfolio com 15 projetos simultâneos", bullet_style))
        story.append(Paragraph("• REDUZI custos operacionais em R$ 2M/ano através de melhorias processuais", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Analista de Dados — Google", bullet_style))
        story.append(Paragraph("Março de 2019 – Dezembro 2021", normal_style))
        story.append(Paragraph("• Análise de big data com Python e SQL para tomada de decisão estratégica", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Estagiário — Accenture", bullet_style))
        story.append(Paragraph("Fev/2018 – Jan/2019", normal_style))
        story.append(Paragraph("• Suporte em projetos de transformação digital", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Consultor Freelancer", bullet_style))
        story.append(Paragraph("2017 – 2018", normal_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("MBA em Gestão de Projetos — FGV (2020)", normal_style))
        story.append(Paragraph("Bacharel em Estatística — UFRJ (Cursando – Previsão 2024)", normal_style))

    elif name == "test_bullets_complexos":
        # Testa bullet points complexos com fórmula XYZ
        story.append(Paragraph("CARLOS EDUARDO SANTOS", title_style))
        story.append(Paragraph("carlos.santos@email.com | (31) 98877-6655 | Belo Horizonte, MG", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("Engenheiro de Software — Amazon AWS", bullet_style))
        story.append(Paragraph("• Atingi 99.99% de uptime (Resultado), mensurado por monitoramento com CloudWatch (Métrica), fazendo deploy automatizado com Terraform (Ação)", bullet_style))
        story.append(Paragraph("• OTIMIZAI pipeline de dados processando 50TB/dia, reduzindo latency em 45%", bullet_style))
        story.append(Paragraph("• Desenvolvi microserviço em Go que PROCESSOU 1M requisições/dia sem downtime", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Desenvolvedor Backend — Spotify", bullet_style))
        story.append(Paragraph("• Liderança técnica em projeto de recomendação musical usando ML", bullet_style))
        story.append(Paragraph("• REDUSEI custo de infraestrutura AWS em 30% através de rightsizing de instâncias", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Estagiário — iFood", bullet_style))
        story.append(Paragraph("• Suporte em desenvolvimento de API de pagamentos com Node.js", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Engenharia de Software — UFMG (2021)", normal_style))

    elif name == "test_termos_tecnicos":
        # Testa termos técnicos que NÃO são erros
        story.append(Paragraph("LUCIANA PEREIRA COSTA", title_style))
        story.append(Paragraph("luciana.costa@email.com | (41) 99977-5544 | Curitiba, PR", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("PERFIL PROFISSIONAL", heading_style))
        story.append(Paragraph("Data Scientist com expertise em Machine Learning, Deep Learning e NLP.", normal_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("ML Engineer — Mercado Livre", bullet_style))
        story.append(Paragraph("• Treinei modelos de NLP para análise de sentimento em reviews (BERT, GPT)", bullet_style))
        story.append(Paragraph("• Desenvolvi pipeline de feature engineering com Apache Spark e Airflow", bullet_style))
        story.append(Paragraph("• Implementação de sistema de recomendação usando deep learning (TensorFlow, PyTorch)", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Analista de Dados — Uber", bullet_style))
        story.append(Paragraph("• Análise de dados geoespaciais com PostGIS e Pandas", bullet_style))
        story.append(Paragraph("• Dashboard interativo com Tableau e Power BI para stakeholders", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Mestrado em Inteligência Artificial — UNICAMP (2023)", normal_style))
        story.append(Paragraph("Bacharel em Matemática — USP (2020)", normal_style))

        story.append(Spacer(1, 8))
        story.append(Paragraph("HABILIDADES", heading_style))
        story.append(Paragraph("Python, TensorFlow, PyTorch, Spark, Kafka, Docker, Kubernetes, AWS, GCP, SQL, NoSQL, REST, GraphQL, Git, CI/CD, Agile, Scrum, Jira, Confluence, Tableau, Power BI, Excel, VBA", normal_style))

    elif name == "test_sem_erros":
        # CV perfeito, sem erros ortográficos
        story.append(Paragraph("ANA BEATRIZ SILVA", title_style))
        story.append(Paragraph("ana.silva@email.com | (51) 98866-4433 | Porto Alegre, RS", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("PERFIL PROFISSIONAL", heading_style))
        story.append(Paragraph("Analista de Marketing Digital com 5 anos de experiência em performance marketing e growth hacking.", normal_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("Marketing Manager — Magazine Luiza", bullet_style))
        story.append(Paragraph("• Atingi crescimento de 150% em leads qualificados (Resultado), mensurado por campanhas Google Ads (Métrica), fazendo otimização contínua de funnel (Ação)", bullet_style))
        story.append(Paragraph("• GERENCIEI R$ 500k/mês em mídia paga com ROAS de 4.2x", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Analista de Tráfego Pago — Totvs", bullet_style))
        story.append(Paragraph("• Criação e gestão de campanhas em Google Ads e Meta Ads", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Bacharel em Marketing — PUC-RS (2019)", normal_style))

    elif name == "test_dados_sensiveis":
        # CV com dados sensíveis (CPF, RG, endereço completo)
        story.append(Paragraph("ROBERTO CARLOS FERREIRA", title_style))
        story.append(Paragraph("CPF: 123.456.789-00 | RG: 12.345.678-9", subtitle_style))
        story.append(Paragraph("Endereço: Rua das Flores, 123,apt 45,Bairro Centro,São Paulo-SP,CEP 01001-000", subtitle_style))
        story.append(Paragraph("Telefone: (11) 3333-4444 | email: roberto@email.com", subtitle_style))
        story.append(Paragraph("Data de Nascimento: 15/03/1990 | Estado Civil: Casado", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("OBJETIVO", heading_style))
        story.append(Paragraph("Vaga de Analista Administrativo", normal_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("Analista Financeiro — Banco do Brasil", bullet_style))
        story.append(Paragraph("• conciliação bancária diária de R$ 500mil", bullet_style))
        story.append(Paragraph("• Elaboração de DRE e fluxo de caixa", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Tecnólogo em Gestão Financeira — Anhanguera (2015)", normal_style))

    elif name == "test_erro_sutil":
        # CV com erro sutil de digitação (não óbvio)
        story.append(Paragraph("FERNANDA COSTA LIMA", title_style))
        story.append(Paragraph("fernanda.lima@email.com | (61) 99988-7766 | Brasília, DF", subtitle_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("PERFIL PROFISSIONAL", heading_style))
        story.append(Paragraph("Desenvolvedora Frontend com foco em React e acessibilidade web.", normal_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", heading_style))
        story.append(Paragraph("Frontend Developer — Nubank", bullet_style))
        story.append(Paragraph("• Desenvolvi interface de usuário responsiva com React e TypeScript", bullet_style))
        story.append(Paragraph("• Implementação de testes unitários com Jest e React Testing Library", bullet_style))
        story.append(Paragraph("• OTIMIZAI performance do app reduzindo bundle size em 40%", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("Estagiária — iFood", bullet_style))
        story.append(Paragraph("• Suporte em desenvolvimento de componentes React", bullet_style))
        story.append(Spacer(1, 6))

        story.append(Paragraph("FORMAÇÃO ACADÊMICA", heading_style))
        story.append(Paragraph("Bacharel em Ciência da Computação — UnB (2022)", normal_style))

    doc.build(story)
    print(f"Criado: {path}")

if __name__ == "__main__":
    docs_path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
    os.makedirs(docs_path, exist_ok=True)

    test_cases = [
        ("test_capitalizacao.pdf", "test_capitalizacao"),
        ("test_datas_variadas2.pdf", "test_datas_variadas"),
        ("test_bullets_complexos.pdf", "test_bullets_complexos"),
        ("test_termos_tecnicos.pdf", "test_termos_tecnicos"),
        ("test_sem_erros.pdf", "test_sem_erros"),
        ("test_dados_sensiveis.pdf", "test_dados_sensiveis"),
        ("test_erro_sutil.pdf", "test_erro_sutil"),
    ]

    for filename, name in test_cases:
        path = os.path.join(docs_path, filename)
        create_cv(path, name)

    print("\nTodos os CVs criados com sucesso!")
