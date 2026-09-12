"""
QA completo: cria CVs de teste, executa análise, valida resultados.
"""
import requests
import json
import os
import fitz  # PyMuPDF

BASE_URL = "http://localhost:8000"
DOCS_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
OUT_PATH = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v4_results.json"

def extract_pdf_text(pdf_path):
    """Extrai texto do PDF para validação."""
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
    """Analisa um CV via API."""
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
    """Valida se erros ortográficos realmente existem no texto."""
    errors = analysis.get("erros_ortograficos", [])
    extracted_lower = pdf_text.lower()
    issues = []

    for err in errors:
        word = err.get("palavra", "") if isinstance(err, dict) else str(err)
        contexto = err.get("contexto", "") if isinstance(err, dict) else ""

        if word.lower() not in extracted_lower:
            issues.append(f"ALUCINAÇÃO: '{word}' não existe no PDF")
        if contexto and contexto not in pdf_text:
            issues.append(f"CONTEXT FOI ALTERADO: '{contexto[:30]}...'")

    return issues

def main():
    # Lista de PDFs
    all_pdfs = [f for f in os.listdir(DOCS_PATH) if f.endswith('.pdf')]
    print(f"Total PDFs: {len(all_pdfs)}")
    for p in sorted(all_pdfs):
        print(f"  {p}")

    results = []
    for pdf_name in sorted(all_pdfs):
        pdf_path = os.path.join(DOCS_PATH, pdf_name)
        print(f"\n{'='*50}")
        print(f"TESTANDO: {pdf_name}")

        # Extrair texto
        pdf_text = extract_pdf_text(pdf_path)

        # Analisar
        analysis = analyze_cv(pdf_path)

        if "erro" in analysis:
            results.append({"nome": pdf_name, "erro": analysis["erro"]})
            print(f"  ERRO: {analysis['erro']}")
            continue

        # Validar grounding
        issues = validate_grounding(analysis, pdf_text)

        result = {
            "nome": pdf_name,
            "nota": analysis.get("nota"),
            "score_ats": analysis.get("score_ats"),
            "erros_ortograficos": analysis.get("erros_ortograficos", []),
            "grounding_issues": issues,
            "ordem_secoes": analysis.get("ordem_secoes", {}),
            "pontos_fortes": analysis.get("pontos_fortes", []),
            "pontos_fracos": analysis.get("pontos_fracos", []),
        }
        results.append(result)

        print(f"  Nota: {analysis.get('nota')}")
        print(f"  Score ATS: {analysis.get('score_ats')}")
        print(f"  Erros ortográficos: {len(analysis.get('erros_ortograficos', []))}")
        for e in analysis.get('erros_ortograficos', []):
            print(f"    - {e.get('palavra', '')}: {e.get('correcao', '')}")
        if issues:
            print(f"  ISSUES: {issues}")

    # Salvar
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Resumo
    print(f"\n{'='*50}")
    print("RESUMO:")
    total = len([r for r in results if "erro" not in r])
    with_errors = len([r for r in results if r.get("erros_ortograficos")])
    with_issues = len([r for r in results if r.get("grounding_issues")])
    print(f"  Total analisados: {total}")
    print(f"  Com erros ortográficos: {with_errors}")
    print(f"  Com grounding issues: {with_issues}")

    if with_issues > 0:
        print(f"\n  ALUCINAÇÕES ENCONTRADAS:")
        for r in results:
            if r.get("grounding_issues"):
                print(f"    {r['nome']}: {r['grounding_issues']}")
    else:
        print(f"\n  TODOS OS TESTES PASSARAM! 0 alucinações.")

    print(f"\nResultados salvos em: {OUT_PATH}")

if __name__ == "__main__":
    main()
