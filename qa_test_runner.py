#!/usr/bin/env python3
"""QA Test Runner for CV Analysis System - Full Output"""
import sys
import json
import requests
import os

BACKEND_URL = 'http://127.0.0.1:8000'
DOCS_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'
OUTPUT_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("QA TESTES - SISTEMA DE ANÁLISE DE CURRÍCULOS")
print("=" * 80)

# Health check
r = requests.get(f'{BACKEND_URL}/health')
health = r.json()
print(f"\n[HEALTH] status={health['status']}, knowledge={health['checks']['knowledge']['status']}")

# Read prompt file
with open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\knowledge\cv_analysis_prompt.md', 'r', encoding='utf-8') as f:
    prompt_content = f.read()
print(f"\n[PROMPT FILE] {len(prompt_content)} caracteres, {len(prompt_content.splitlines())} linhas")

# List docs
print(f"\n[DOCS] Files in {DOCS_DIR}:")
for f in os.listdir(DOCS_DIR):
    print(f"  - {f}")

def analyze_cv(filename, label):
    cv_path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(cv_path):
        print(f"\n[SKIP] {label}: arquivo não encontrado {cv_path}")
        return None
    with open(cv_path, 'rb') as f:
        files = {'cv_file': (filename, f, 'application/pdf')}
        r = requests.post(f'{BACKEND_URL}/api/cv/analyze', files=files)
    print(f"\n[{label}] Status: {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        # Save full result
        out_path = os.path.join(OUTPUT_DIR, f'{label}_result.json')
        with open(out_path, 'w', encoding='utf-8') as out:
            json.dump(result, out, indent=2, ensure_ascii=False)
        print(f"  Result saved to {out_path}")
        return result
    else:
        print(f"  Error: {r.text}")
        return None

def print_summary(label, result):
    if not result:
        print(f"[{label}] FAILED - no result")
        return
    print(f"\n[{label}] NOTA: {result.get('nota', 'N/A')} | SCORE ATS: {result.get('score_ats', 'N/A')}")
    print(f"  Erros ortográficos: {result.get('erros_ortograficos', [])}")
    print(f"  Foto detectada: {result.get('foto_detectada', False)}")
    print(f"  Ordem seções: {result.get('ordem_secoes', {})}")
    print(f"  Pontos fortes: {len(result.get('pontos_fortes', []))}")
    print(f"  Pontos fracos: {len(result.get('pontos_fracos', []))}")
    print(f"  Erros comuns: {len(result.get('erros_comuns_detectados', []))}")
    print(f"  Modelo usado: {result.get('api_info', {}).get('model', 'N/A')}")
    # Check section scores
    secoes = result.get('analise_secoes', {})
    for sec, data in secoes.items():
        print(f"    {sec}: score={data.get('score','?')} status={data.get('status','?')}")

# TEST 1: Gabriel CV
print("\n" + "=" * 80)
print("TESTE 1: CV Gabriel Cardoso")
print("=" * 80)
result1 = analyze_cv('Curriculo Gabriel Cardoso.pdf', 'GABRIEL')
print_summary('GABRIEL', result1)

# TEST 2: Milena CV
print("\n" + "=" * 80)
print("TESTE 2: CV Milena Cardoso")
print("=" * 80)
result2 = analyze_cv('Currículo Milena Cardoso.pdf', 'MILENA')
print_summary('MILENA', result2)

# TEST 3: test_curriculo.pdf
print("\n" + "=" * 80)
print("TESTE 3: CV test_curriculo")
print("=" * 80)
result3 = analyze_cv('test_curriculo.pdf', 'TEST')
print_summary('TEST', result3)

print("\n" + "=" * 80)
print("TESTES CONCLUÍDOS")
print("=" * 80)
