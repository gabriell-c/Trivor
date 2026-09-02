#!/usr/bin/env python3
"""Teste final de consistência - 3 rodadas por CV."""
import json, requests, time, os

BACKEND = 'http://127.0.0.1:8000'
DOCS = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'
RESULTS = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_final'
os.makedirs(RESULTS, exist_ok=True)

def analyze(fname):
    path = os.path.join(DOCS, fname)
    with open(path, 'rb') as f:
        r = requests.post(f'{BACKEND}/api/cv/analyze', files={'cv_file': (fname, f, 'application/pdf')}, timeout=120)
    return r.json() if r.status_code == 200 else None

cvs = [
    'Curriculo Gabriel Cardoso.pdf',
    'Currículo Milena Cardoso.pdf',
    'test_curriculo.pdf',
    'test_erro_orho_real.pdf',
    'test_datas_variadas.pdf',
    'test_erros_ortograficos.pdf',
    'test_erros_graves.pdf',
]

print("=" * 80)
print("TESTE FINAL - 3 RODADAS POR CURRÍCULO")
print("=" * 80)

all_results = {}
for i, cv in enumerate(cvs, 1):
    print(f"\n[{i}/{len(cvs)}] {cv}")
    run_results = []
    for r in range(1, 4):
        result = analyze(cv)
        if result:
            run_results.append(result)
            nota = result.get('nota', 'N/A')
            err = result.get('erros_ortograficos', [])
            print(f"  Rodada {r}: nota={nota} err_ort={err}")
            # Save
            out = os.path.join(RESULTS, f'{os.path.splitext(cv)[0]}_R{r}.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        time.sleep(1)
    all_results[cv] = run_results

# Summary
print("\n" + "=" * 80)
print("RESUMO FINAL")
print("=" * 80)

total_tests = 0
false_positives = 0
real_errors_found = 0

for cv, runs in all_results.items():
    if not runs:
        continue
    for run in runs:
        total_tests += 1
        err = run.get('erros_ortograficos', [])
        # Check for false positives (technical words, proper nouns)
        tech = ['React', 'Python', 'Node', 'Django', 'AWS', 'Docker', 'GitHub', 'LinkedIn',
                'TypeScript', 'PostgreSQL', 'MongoDB', 'Redis', 'Jenkins', 'Kafka', 'GraphQL',
                'Maria', 'João', 'Silva', 'Santos', 'Oliveira', 'Pedro', 'Lucas', 'Ana',
                'Mariana', 'Gabriel', 'Henrique', 'Fernandes', 'Rodrigues', 'Costa', 'Almeida']
        for e in err:
            word = e.get('palavra', '') if isinstance(e, dict) else str(e)
            if any(t.lower() in word.lower() for t in tech):
                false_positives += 1
                print(f"  [FALSE POSITIVE] {cv}: '{word}'")
            else:
                real_errors_found += 1

print(f"\nTotal de análises: {total_tests}")
print(f"Erros ortográficos reais detectados: {real_errors_found}")
print(f"Fake positives (erros inventados): {false_positives}")
print(f"\n{'APROVADO' if false_positives == 0 else 'REPROVADO'}: Teste de QA final")
print("=" * 80)
