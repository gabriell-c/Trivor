import requests, json

pdfs = [
    ('docs/Curriculo Gabriel Cardoso.pdf', ''),
    ('docs/Currículo Milena Cardoso.pdf', ''),
    ('docs/test_curriculo.pdf', ''),
    ('docs/test_erros_graves.pdf', ''),
]

results = []
for pdf_path, area in pdfs:
    with open(pdf_path, 'rb') as f:
        files = {'cv_file': (pdf_path.split('/')[-1], f, 'application/pdf')}
        resp = requests.post('http://localhost:8000/api/cv/analyze', files=files, data={'area': area}, timeout=60)
    data = resp.json()
    results.append({
        'file': pdf_path.split('/')[-1],
        'nota': data.get('nota'),
        'erros_ort': len(data.get('erros_ortograficos', [])),
        'erros_comuns': len(data.get('erros_comuns_detectados', [])),
        'faltantes': data.get('palavras_chave_faltantes', []),
        'ordem': data.get('ordem_secoes', {}),
        'pontos_fracos': data.get('pontos_fracos', []),
    })

with open(r'results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("DONE")
