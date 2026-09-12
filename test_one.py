import requests, json

with open(r'docs/Curriculo Gabriel Cardoso.pdf', 'rb') as f:
    files = {'cv_file': ('g.pdf', f, 'application/pdf')}
    resp = requests.post('http://localhost:8000/api/cv/analyze', files=files, data={'area': ''}, timeout=60)
data = resp.json()

with open(r'result.txt', 'w', encoding='utf-8') as out:
    out.write(f"nota: {data.get('nota')}\n")
    out.write(f"erros_ort: {len(data.get('erros_ortograficos', []))}\n")
    out.write(f"erros_comuns: {len(data.get('erros_comuns_detectados', []))}\n")
    out.write(f"faltantes: {data.get('palavras_chave_faltantes', [])}\n")
    out.write(f"ordem: {json.dumps(data.get('ordem_secoes', {}), ensure_ascii=False)}\n")
    out.write(f"pontos_fracos ({len(data.get('pontos_fracos', []))}):\n")
    for p in data.get('pontos_fracos', []):
        out.write(f"  - {p}\n")
print("DONE")
