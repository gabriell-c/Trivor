import requests
import json
import os
import fitz
import time

BASE_URL = "http://localhost:8000"
DOCS_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
OUT_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v5_results.json"
LOG_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v5_log.txt"

def log(msg):
    print(msg)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

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
        f.write("QA v5 - Testes Completos\n")
        f.write("="*60 + "\n\n")

    if not check_backend():
        log("ERRO: Backend não está rodando!")
        return

    log("Backend OK")

    all_pdfs = sorted([f for f in os.listdir(DOCS_PATH) if f.endswith('.pdf')])
    log(f"PDFs: {len(all_pdfs)}\n")

    results = []
    for pdf_name in all_pdfs:
        pdf_path = os.path.join(DOCS_PATH, pdf_name)
        log(f"\n{'='*60}")
        log(f"TESTANDO: {pdf_name}")
        log(f"{'='*60}")

        pdf_text = extract_pdf_text(pdf_path)
        log(f"Texto: {len(pdf_text)} chars")

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
        log(f"Erros: {len(erros)}")
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

    log(f"\nTotal: {total}")
    log(f"Erros API: {errors}")
    log(f"Grounding issues: {grounding}")
    log(f"Falsos positivos: {false_positives}")

    if false_positives == 0 and grounding == 0 and errors == 0:
        log("\n✅ TODOS OS TESTES PASSARAM!")
    else:
        log("\n❌ PROBLEMAS ENCONTRADOS")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    log(f"\nResultados: {OUT_PATH}")

if __name__ == "__main__":
    run_qa()
