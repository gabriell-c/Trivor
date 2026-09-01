import requests, json

API = "http://localhost:8008/api/cv/analyze"
CRED = {"api_key": "sk-local", "api_url": "http://localhost:20128/v1", "model_name": "auto/best-coding"}
pdfs = [
    r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs\test_curriculo.pdf",
    r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs\Currículo Milena Cardoso.pdf",
]

print("=" * 60)
print("QA FINAL - PyMuPDF Fallback Chain")
print("=" * 60)

for pdf_path in pdfs:
    name = __import__('os').path.basename(pdf_path)
    print(f"\n--- {name} ---")
    with open(pdf_path, "rb") as f:
        r = requests.post(API, data=CRED, files={"cv_file": (name, f, "application/pdf")}, timeout=120)
    if r.status_code != 200:
        print(f"  ERRO: {r.status_code} {r.text[:200]}")
        continue
    d = r.json()
    print(f"  Extractor: {d.get('_extractor_used', 'N/A')}")
    print(f"  Links: {len(d.get('_links', []))} -> {d.get('_links', [])}")
    print(f"  Nota: {d.get('nota', 'N/A')}")
    print(f"  Score ATS: {d.get('score_ats', 'N/A')}")
    print(f"  Resumo exec: {'SIM' if d.get('resumo_executivo') else 'NÃO'}")
    print(f"  Pts fortes: {len(d.get('pontos_fortes', []))}")
    print(f"  Pts fracos: {len(d.get('pontos_fracos', []))}")
    print(f"  Erros ort: {len(d.get('erros_comuns_detectados', []))}")
    print(f"  Analise secoes: {list(d.get('analise_secoes', {}).keys())}")
    ats = d.get('analise_ats', {})
    print(f"  ATS veredito: {ats.get('veredito_robos', 'N/A')} score: {ats.get('score_ats', 'N/A')}")
    print(f"  Tokens: {d.get('uso_tokens', {})}")
    print(f"  Frontend keys present: nota={'nota' in d}, score_ats={'score_ats' in d}, resumo={'resumo_executivo' in d}")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
