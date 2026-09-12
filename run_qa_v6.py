"""
QA completo: cria CVs de teste, executa análise, valida resultados.
"""
import requests
import json
import os
import fitz
import time
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_URL = "http://localhost:8000"
DOCS_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
OUT_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v6_results.json"
LOG_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v6_log.txt"

def log(msg):
    print(msg)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

# Registrar fonte
font_path = r"C:\Windows\Fonts\arial.ttf"
pdfmetrics.registerFont(TTFont('Arial', font_path))

def create_test_pdf(filename, title, content):
    """Cria um PDF de teste."""
    path = os.path.join(DOCS_PATH, filename)
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
    log(f"  Criado: {filename}")

def check_backend():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False

def extract_pdf_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        return f"ERRO: {e}"

def analyze_cv(pdf_path):
    try:
        with open(pdf_path, 'rb') as f:
            files = {'cv_file': ('test.pdf', f, 'application/pdf')}
            resp = requests.post(f"{BASE_URL}/api/cv/analyze", files=files, timeout=120)
        if resp.status_code != 200:
            return {"erro": f"HTTP {resp.status_code}"}
        return resp.json()
    except Exception as e:
        return {"erro": str(e)}

def validate_grounding(analysis, pdf_text):
    errors = analysis.get("erros_ortograficos", [])
    extracted_lower = pdf_text.lower()
    issues = []
    for err in errors:
        word = err.get("palavra", "") if isinstance(err, dict) else str(err)
        contexto = err.get("contexto", "") if isinstance(err, dict) else ""
        if word and word.lower() not in extracted_lower:
            issues.append(f"ALUCINAÇÃO: '{word}' não existe no PDF")
        if contexto and contexto not in pdf_text:
            issues.append(f"CONTEXT FOI ALTERADO: '{contexto[:40]}...'")
    return issues

def run_qa():
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write("QA v6 - Testes Completos\n")
        f.write("="*60 + "\n\n")

    # Criar PDFs de teste
    log("Criando PDFs de teste...")
    create_test_pdf("test_capitalizacao.pdf", "JOSÉ CARLOS MENDES", {
        "subtitle": "jose.mendes@email.com | (11) 98765-4321 | São Paulo, SP",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Desenvolvedor Full Stack Sênior com 10+ anos de experiência."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "TechLead — Nubank",
                "• MIGRAÇÃO do monolito para microsserviços, reduzindo deploy time em 70%",
                "• Implementação de PIPELINE CI/CD com Jenkins e Docker",
                "• Desenvolvimento de APIs REST com JAVA e SPRING BOOT"
            ]},
            {"title": "FORMAÇÃO", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — USP (2015)"]},
            {"title": "HABILIDADES", "content": ["JAVA, PYTHON, TypeScript, Go, Kubernetes, AWS"]}
        ]
    })

    create_test_pdf("test_sem_erros.pdf", "ANA BEATRIZ SILVA", {
        "subtitle": "ana.silva@email.com | (21) 99876-5432 | Rio de Janeiro, RJ",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Engenheira de Software Sênior com 8 anos de experiência."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "Engenheira de Software — Nubank",
                "• GERENCIEI uma equipe de 12 desenvolvedores",
                "• OTIMIZAI o sistema de pagamentos, reduzindo latency em 35%",
                "• Liderança técnica de microsserviços em AWS"
            ]},
            {"title": "FORMAÇÃO", "content": ["Bacharel em ENGENHARIA DA COMPUTAÇÃO — UFRJ (2016)"]},
            {"title": "HABILIDADES", "content": ["Python, Java, Go, Kubernetes, AWS, PostgreSQL"]}
        ]
    })

    create_test_pdf("test_erro_sutil.pdf", "CARLOS EDUARDO PEREIRA", {
        "subtitle": "carlos.pereira@email.com | (31) 98765-1234 | Belo Horizonte, MG",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Desenvolvedor Backend com 5 anos de experiência."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "Desenvolvedor Backend — Stone",
                "• OTIMIZAI o sistema de processamento de transações",
                "• Desenvolvimento de APIs REST com Python e FastAPI"
            ]},
            {"title": "FORMAÇÃO", "content": ["Bacharel em CIÊNCIA DA COMPUTAÇÃO — UFMG (2019)"]},
            {"title": "HABILIDADES", "content": ["Python, FastAPI, PostgreSQL, Docker, Kubernetes"]}
        ]
    })

    create_test_pdf("test_termos_tecnicos.pdf", "MARINA COSTA LIMA", {
        "subtitle": "marina.lima@email.com | (41) 99876-5432 | Curitiba, PR",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Cientista de Dados com especialização em NLP."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "Cientista de Dados — iFood",
                "• Treinamento de modelos BERT para análise de sentimento",
                "• Implementação de pipeline com TensorFlow",
                "• Desenvolvimento de APIs com GPT e LangChain"
            ]},
            {"title": "FORMAÇÃO", "content": ["Mestrado em CIÊNCIA DA COMPUTAÇÃO — UFPR (2020)"]},
            {"title": "HABILIDADES", "content": ["Python, TensorFlow, PyTorch, BERT, GPT, LangChain, SQL"]}
        ]
    })

    create_test_pdf("test_datas_variadas.pdf", "ROBERTO ALMEIDA SANTOS", {
        "subtitle": "roberto.santos@email.com | (51) 98765-4321 | Porto Alegre, RS",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Analista de Sistemas com 15 anos de experiência."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "Analista Sênior — Banrisul",
                "• Jan 2022 - Presente: Liderança de equipe",
                "• Março de 2019 - Dez 2021: Desenvolvedor Full Stack",
                "• Fev/2018 - Jan/2019: Estagiário"
            ]},
            {"title": "FORMAÇÃO", "content": ["Bacharel em SISTEMAS DE INFORMAÇÃO — UFRGS (2016)"]},
            {"title": "HABILIDADES", "content": ["Java, Spring Boot, Angular, PostgreSQL, AWS"]}
        ]
    })

    create_test_pdf("test_bullets_complexos.pdf", "FERNANDA OLIVEIRA COSTA", {
        "subtitle": "fernanda.costa@email.com | (61) 99876-5432 | Brasília, DF",
        "sections": [
            {"title": "PERFIL PROFISSIONAL", "content": ["Product Manager com 7 anos de experiência."]},
            {"title": "EXPERIÊNCIA PROFISSIONAL", "content": [
                "Product Manager — Loggi",
                "• Atingi 30% de crescimento em GMV mensurado por receita mensal, fazendo otimização de rota",
                "• REDUSEI o churn em 25% através de melhorias no onboarding",
                "• Liderança de produto de A a Z"
            ]},
            {"title": "FORMAÇÃO", "content": ["MBA em GESTÃO DE PRODUTO — FGV (2020)"]},
            {"title": "HABILIDADES", "content": ["Product Strategy, Analytics, Agile, Scrum, SQL"]}
        ]
    })

    log("")

    # Verificar backend
    if not check_backend():
        log("ERRO: Backend não está rodando!")
        return

    log("Backend OK")

    # Listar PDFs
    all_pdfs = sorted([f for f in os.listdir(DOCS_PATH) if f.endswith('.pdf')])
    log(f"PDFs encontrados: {len(all_pdfs)}\n")

    results = []
    for pdf_name in all_pdfs:
        pdf_path = os.path.join(DOCS_PATH, pdf_name)
        log(f"\n{'='*60}")
        log(f"TESTANDO: {pdf_name}")
        log(f"{'='*60}")

        pdf_text = extract_pdf_text(pdf_path)
        log(f"Texto extraído: {len(pdf_text)} caracteres")

        lines = pdf_text.split('\n')[:15]
        log("Preview:\n" + "\n".join(lines))

        analysis = analyze_cv(pdf_path)
        time.sleep(1)

        if "erro" in analysis:
            log(f"ERRO: {analysis['erro']}")
            results.append({"nome": pdf_name, "erro": analysis["erro"]})
            continue

        issues = validate_grounding(analysis, pdf_text)

        score = analysis.get("score", 0)
        score_ats = analysis.get("score_ats", 0)
        erros = analysis.get("erros_ortograficos", [])
        bullets = analysis.get("bullet_points", [])
        datas = analysis.get("datas_extraidas", [])
        secoes = analysis.get("secoes_encontradas", [])

        log(f"\nScore: {score}, ATS: {score_ats}")
        log(f"Erros ortográficos: {len(erros)}")
        for e in erros:
            log(f"  - {e}")
        log(f"Bullets: {len(bullets)}, Datas: {len(datas)}, Seções: {secoes}")
        log(f"Grounding issues: {len(issues)}")
        for iss in issues:
            log(f"  ⚠ {iss}")

        results.append({
            "nome": pdf_name,
            "score": score,
            "score_ats": score_ats,
            "erros_ortograficos": erros,
            "grounding_issues": issues,
            "status": "OK" if not issues else "ISSUE"
        })

    # Resumo
    log(f"\n\n{'='*60}")
    log("RESUMO")
    log(f"{'='*60}")

    total = len(results)
    errors = sum(1 for r in results if r.get("erro"))
    grounding = sum(1 for r in results if r.get("grounding_issues"))
    false_positives = 0

    for r in results:
        if r.get("erro"):
            continue
        for e in r.get("erros_ortograficos", []):
            word = e.get("palavra", "") if isinstance(e, dict) else str(e)
            if word.lower() in ['migração', 'gerenciei', 'otimizei']:
                false_positives += 1
                log(f"  FALSO POSITIVO: {r['nome']} - '{word}'")

    log(f"\nTotal: {total} CVs")
    log(f"Erros API: {errors}")
    log(f"Grounding issues: {grounding}")
    log(f"Falsos positivos: {false_positives}")

    if false_positives == 0 and grounding == 0 and errors == 0:
        log("\n✅ TODOS OS TESTES PASSARAM!")
    else:
        log("\n❌ PROBLEMAS ENCONTRADOS")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    log(f"\nResultados salvos: {OUT_PATH}")

if __name__ == "__main__":
    run_qa()
