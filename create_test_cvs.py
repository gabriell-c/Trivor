#!/usr/bin/env python3
"""Cria currículos PDF com reportlab (UTF-8 correto)."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import glob

DOCS_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'

# Registrar fonte Unicode
font_paths = glob.glob(r'C:\Windows\Fonts\*.ttf') + glob.glob(r'C:\Windows\Fonts\*.TTF')
utf_font = None
for fp in font_paths:
    fname = os.path.basename(fp)
    if 'arial' in fname.lower() and 'bd' in fname.lower():
        try:
            pdfmetrics.registerFont(TTFont('ArialBD', fp))
            utf_font = 'ArialBD'
            print(f"  Using font: {fname}")
            break
        except:
            pass
    if 'arial' in fname.lower() and utf_font is None:
        try:
            pdfmetrics.registerFont(TTFont('Arial', fp))
            utf_font = 'Arial'
            print(f"  Using font: {fname}")
            break
        except:
            pass

if not utf_font:
    # Fallback: try any ttf
    for fp in font_paths:
        try:
            pdfmetrics.registerFont(TTFont('CustomFont', fp))
            utf_font = 'CustomFont'
            print(f"  Fallback font: {os.path.basename(fp)}")
            break
        except:
            pass

if not utf_font:
    print("ERROR: No Unicode font found!")
    exit(1)

def create_cv(filename, lines):
    """lines = list of (text, y, font_size, bold)"""
    path = os.path.join(DOCS_DIR, filename)
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    for text, y, fs, bold in lines:
        font = utf_font + "BD" if bold else utf_font
        c.setFont(font, fs)
        c.drawString(72, y, text)
    c.save()
    print(f"  Created: {path}")

print("Creating test PDFs with ReportLab...")

# CV 1: MARIANA
create_cv("test_erro_orho_real.pdf", [
    ("MARIANA COSTA OLIVEIRA", 740, 14, True),
    ("mariana.costa@email.com | (21) 98888-7777 | Rio de Janeiro, RJ", 720, 10, False),
    ("ANALISTA DE SISTEMAS", 695, 11, True),
    ("Analista de Sistemas com 8 anos de experiência em desenvolvimento web e mobile.", 675, 9, False),
    ("Especializada em React, Node.js e arquitetura de microsserviços.", 662, 9, False),
    ("EXPERIÊNCIA PROFISSIONAL", 635, 11, True),
    ("BancoTech SA | Analista de Sistemas Sênior | Fev. De 2022 – Presente", 615, 9, False),
    ("- Liderança de equipe com 5 desenvolvedores, entregando 100% dos sprints no prazo", 600, 9, False),
    ("- Reduzi o tempo de deploy em 55% implementando pipeline CI/CD com Jenkins e Docker", 588, 9, False),
    ("- Migrei sistema monolítico para microsserviços, reduzindo tempo de resposta em 40%", 576, 9, False),
    ("Fintech Solutions | Desenvolvedora Fullstack | Jan 2019 – Jan 2022", 554, 9, False),
    ("- Desenvolvi plataforma de pagamentos atendendo 50k usuários, processando R$ 2M/dia", 539, 9, False),
    ("- Criei API REST com Node.js e Express, integrando com 3 gateways de pagamento", 526, 9, False),
    ("- Implementei testes automatizados (Jest), aumentando cobertura de 30% para 85%", 513, 9, False),
    ("TechStart | Desenvolvedora Júnior | Mar 2018 – Dez 2018", 491, 9, False),
    ("- Desenvolvi interfaces em React para app de gestão financeira pessoal", 476, 9, False),
    ("- Participei de redesign completo do dashboard, aumentando engagement em 25%", 463, 9, False),
    ("FORMAÇÃO ACADÊMICA", 437, 11, True),
    ("Universidade Federal do Rio de Janeiro | Engenharia da Computação | 2014 – 2018", 417, 9, False),
    ("TCC: Aplicações de Machine Learning em Detecção de Fraudes em Transações Financeiras", 404, 9, False),
    ("CURSOS E CERTIFICAÇÕES", 378, 11, True),
    ("Scrum Master Certified (SMC) | Scrum Alliance | 2021", 358, 9, False),
    ("AWS Certified Solutions Architect – Associate | Amazon | 2020", 345, 9, False),
    ("Fullstack JavaScript – Alura | 2019", 332, 9, False),
    ("HABILIDADES", 308, 11, True),
    ("Linguagens: Python, JavaScript, TypeScript, Java", 288, 9, False),
    ("Frameworks: React, Node.js, Express, Django, Spring Boot", 275, 9, False),
    ("Banco de dados: PostgreSQL, MongoDB, Redis", 262, 9, False),
    ("DevOps: Docker, Kubernetes, Jenkins, AWS, Git", 249, 9, False),
    ("Metodologias: Scrum, Kanban, TDD, BDD", 236, 9, False),
    ("LINKS", 212, 11, True),
    ("https://github.com/marianacosta | https://linkedin.com/in/marianacosta | marianacosta.dev", 192, 9, False),
])

# CV 2: PEDRO
create_cv("test_datas_variadas.pdf", [
    ("PEDRO HENRIQUE ALMEIDA", 740, 14, True),
    ("pedro.almeida@email.com | (31) 97777-6666 | Belo Horizonte, MG", 720, 10, False),
    ("DESIGNER UX/UI", 695, 11, True),
    ("Designer UX/UI com 4 anos de experiência em produtos digitais.", 675, 9, False),
    ("Especializado em design systems, prototipagem e pesquisa com usuários.", 662, 9, False),
    ("EXPERIÊNCIA PROFISSIONAL", 635, 11, True),
    ("Nomad Digital | Designer UX/UI Sênior | 2023 – Previsão 2025", 615, 9, False),
    ("- Reduzi em 45% o tempo de onboarding de novos usuários redesignando o fluxo de cadastro", 600, 9, False),
    ("- Criei design system completo com 120+ componentes, padronizando interface em 4 produtos", 587, 9, False),
    ("- Realizei 30+ entrevistas com usuários, identificando 15 pontos críticos de atrito", 574, 9, False),
    ("Studio Criativo | Designer UX/UI | Jan/2021 – Dez/2022", 552, 9, False),
    ("- Prototipei MVP para startup de saúde, validando conceito com 200+ usuários", 537, 9, False),
    ("- Desenhei interface de app mobile que atingiu 4.8 estrelas na App Store", 524, 9, False),
    ("- Colaborei com equipe de desenvolvimento usando Figma e Zeplin", 511, 9, False),
    ("Freelancer | Designer Gráfico | 2019 – 2020", 489, 9, False),
    ("- Criei identidade visual para 15+ empresas de pequeno e médio porte", 474, 9, False),
    ("FORMAÇÃO ACADÊMICA", 448, 11, True),
    ("Faculdade de Artes Visuais | Design Digital | 2015 – 2019", 428, 9, False),
    ("Bootcamp UX/UI – Rock Content | 2019", 415, 9, False),
    ("HABILIDADES", 390, 11, True),
    ("Figma, Adobe XD, Sketch, Photoshop, Illustrator, After Effects", 370, 9, False),
    ("User Research, Wireframing, Prototipagem, Design System, Usabilidade", 357, 9, False),
    ("HTML/CSS, JavaScript básico, Framer Motion", 344, 9, False),
    ("Inglês: Avançado | Espanhol: Intermediário", 331, 9, False),
    ("PORTFÓLIO", 305, 11, True),
    ("https://dribbble.com/pedroalmeida | https://behance.net/pedroalmeida", 285, 9, False),
])

# CV 3: LUCAS - ERROS ORTOGRÁFICOS REAIS
create_cv("test_erros_ortograficos.pdf", [
    ("LUCAS FERNANDES", 740, 14, True),
    ("lucas.fernandes@email.com | (41) 95555-4444 | Curitiba, PR", 720, 10, False),
    ("ENGENHEIRO DE SOFTWARE", 695, 11, True),
    ("Engenheiro de Software com 6 anos de experiência em sistemas distribuídos.", 675, 9, False),
    ("Especializado em Go, Kubernetes e arquitetura de microsserviços.", 662, 9, False),
    ("EXPERIÊNCIA PROFISSIONAL", 635, 11, True),
    ("CloudBase Inc | Engenheiro de Software Pleno | 2022 - 2024", 615, 9, False),
    ("- Desenvolvi microsserviços em Go para processamento de 1M+ requisições/dia", 600, 9, False),
    ("- OTIMIZAI queries SQL reduzindo tempo de resposta em 60%", 587, 9, False),
    ("- Implementei sistema de mensageria com Kafka, aumentando confiabilidade em 99.9%", 574, 9, False),
    ("DataSoft | Desenvolvedor Backend | 2020 - 2022", 552, 9, False),
    ("- Desenvolvi APIs REST em Node.js para plataforma de e-commerce", 537, 9, False),
    ("- REDUSEI o tempo de carga das páginas em 35% através de caching com Redis", 524, 9, False),
    ("- Participei de code reviews e mentoria de 3 desenvolvedores júniores", 511, 9, False),
    ("WebApps LTDA | Desenvolvedor Júnior | 2018 - 2020", 489, 9, False),
    ("- Construí aplicações web com React e Node.js para clientes diversos", 474, 9, False),
    ("FORMAÇÃO ACADÊMICA", 448, 11, True),
    ("Pontifícia Universidade Católica do Paraná | Engenharia de Software | 2014 - 2018", 428, 9, False),
    ("HABILIDADES", 402, 11, True),
    ("Go, Python, JavaScript, TypeScript, Node.js, React, PostgreSQL, MongoDB", 382, 9, False),
    ("Kubernetes, Docker, AWS, GCP, Terraform, CI/CD", 369, 9, False),
    ("Git, Linux, Kafka, Redis, GraphQL", 356, 9, False),
    ("LINKS", 332, 11, True),
    ("https://github.com/lucasfernandes | linkedin.com/in/lucasfernandes", 312, 9, False),
])

# CV 4: ANA - BARRAS DE PROGRESSO + DADOS SENSÍVEIS
create_cv("test_erros_graves.pdf", [
    ("ANA PAULA RODRIGUES", 740, 14, True),
    ("ana.rodrigues@email.com | (11) 93333-2222 | São Paulo, SP", 720, 10, False),
    ("ADMINISTRADORA", 695, 11, True),
    ("Administradora com 3 anos de experiência em gestão de equipes e processos.", 675, 9, False),
    ("EXPERIÊNCIA PROFISSIONAL", 648, 11, True),
    ("Moura Empresas | Assistente Administrativa | 2022 - Presente", 628, 9, False),
    ("- Controle de fluxo de caixa e conciliação bancária diária", 613, 9, False),
    ("- Elaboração de relatórios gerenciais para diretoria", 600, 9, False),
    ("- Gestão de fornecedores e negociações de contratos", 587, 9, False),
    ("Silva Comércio | Estagiária Administrativa | 2021 - 2022", 565, 9, False),
    ("- Atendimento ao cliente e gestão de reclamações", 550, 9, False),
    ("- Controle de estoque e reposição de mercadorias", 537, 9, False),
    ("FORMAÇÃO ACADÊMICA", 511, 11, True),
    ("Faculdade Anhanguera | Administração de Empresas | 2019 – 2022", 491, 9, False),
    ("HABILIDADES", 465, 11, True),
    ("Excel: 80%", 445, 9, False),
    ("Power BI: 70%", 432, 9, False),
    ("SAP: 60%", 419, 9, False),
    ("Inglês: 90%", 406, 9, False),
    ("Gestão de equipes: 100%", 393, 9, False),
    ("DADOS PESSOAIS", 367, 11, True),
    ("Nome: Ana Paula Rodrigues | CPF: 123.456.789-00 | RG: 12.345.678-9", 347, 9, False),
    ("Endereço: Rua das Flores, 123, Ap 45 - São Paulo, SP | Tel: (11) 93333-2222", 334, 9, False),
    ("Data de nascimento: 15/03/1998 | Estado civil: Solteira", 321, 9, False),
])

print("\nDone! All PDFs created with proper UTF-8 encoding.")
