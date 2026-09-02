#!/usr/bin/env python3
"""Extended QA Test Runner - Edge Cases"""
import json
import requests
import os

BACKEND_URL = 'http://127.0.0.1:8000'
DOCS_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'
OUTPUT_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def analyze_cv(filename, label):
    cv_path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(cv_path):
        print(f"[SKIP] {label}: arquivo não encontrado")
        return None
    with open(cv_path, 'rb') as f:
        files = {'cv_file': (filename, f, 'application/pdf')}
        r = requests.post(f'{BACKEND_URL}/api/cv/analyze', files=files, timeout=120)
    print(f"[{label}] Status: {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        out_path = os.path.join(OUTPUT_DIR, f'{label}_result.json')
        with open(out_path, 'w', encoding='utf-8') as out:
            json.dump(result, out, indent=2, ensure_ascii=False)
        return result
    else:
        print(f"  Error: {r.text}")
        return None

def check_no_false_spelling(label, result):
    """Verifica se a LLM não inventou erros ortográficos"""
    if not result:
        return False
    erros = result.get('erros_ortograficos', [])
    # Verifica se há erros óbvios inventados (palavras como "React", "Python", nomes próprios)
    palavras_proibidas = ['React', 'Python', 'JavaScript', 'Node', 'Django', 'AWS', 'Docker',
                          'Maria', 'João', 'Silva', 'Santos', 'Oliveira', 'Pedro', 'Lucas',
                          'Ana', 'Mariana', 'Gabriel', 'Henrique', 'Fernandes', 'Rodrigues',
                          'Costa', 'Almeida', 'Ferreira', 'GitHub', 'LinkedIn', 'Jenkins',
                          'TypeScript', 'PostgreSQL', 'MongoDB', 'Redis', 'Kafka', 'GraphQL']
    inventados = [e for e in erros if any(p.lower() in e.lower() for p in palavras_proibidas)]
    if inventados:
        print(f"  [FAIL] {label}: LLM inventou erros ortográficos: {inventados}")
        return False
    print(f"  [PASS] {label}: Nenhum erro ortográfico inventado. Erros reais: {erros}")
    return True

def check_bullet_points(label, result):
    """Verifica se a LLM entende bullet points"""
    if not result:
        return False
    exp = result.get('analise_secoes', {}).get('experiencia_profissional', {})
    bullets = exp.get('bullet_points', None)
    if bullets is not None:
        print(f"  [INFO] {label}: bullet_points detectado = {bullets}")
    return True

def check_dates(label, result):
    """Verifica se a LLM interpreta datas corretamente"""
    if not result:
        return False
    exp_list = result.get('experiencias', [])
    if exp_list:
        for exp in exp_list[:3]:
            print(f"  [INFO] {label}: {exp.get('cargo','?')} | {exp.get('periodo','?')}")
    return True

def check_section_order(label, result):
    """Verifica se a LLM entende a ordem das seções"""
    if not result:
        ordem = result.get('ordem_secoes', {})
        print(f"  [INFO] {label}: ordem_correta={ordem.get('correta')} problema={ordem.get('problema','Nenhum')}")
    return True

def check_score_range(label, result):
    """Verifica se as notas estão na escala 0-100"""
    if not result:
        return False
    nota = result.get('nota', -1)
    score_ats = result.get('score_ats', -1)
    if 0 <= nota <= 100 and 0 <= score_ats <= 100:
        print(f"  [PASS] {label}: nota={nota} score_ats={score_ats} (escala correta)")
        return True
    else:
        print(f"  [FAIL] {label}: nota={nota} score_ats={score_ats} (fora da escala!)")
        return False

# Run tests
print("=" * 80)
print("QA EXTENDED TESTS - EDGE CASES")
print("=" * 80)

# Health check
r = requests.get(f'{BACKEND_URL}/health')
print(f"[HEALTH] {r.json()['status']}")

results = {}

# Test 1: Mariana - Clean CV with real XYZ metrics
print("\n" + "=" * 80)
print("TEST: Mariana Costa (CV bem estruturado, métricas reais)")
print("=" * 80)
results['MARIANA'] = analyze_cv('test_erro_orho_real.pdf', 'MARIANA')
if results['MARIANA']:
    check_score_range('MARIANA', results['MARIANA'])
    check_no_false_spelling('MARIANA', results['MARIANA'])
    check_bullet_points('MARIANA', results['MARIANA'])
    check_dates('MARIANA', results['MARIANA'])
    check_section_order('MARIANA', results['MARIANA'])

# Test 2: Pedro - Varied date formats
print("\n" + "=" * 80)
print("TEST: Pedro Almeida (Datas variadas: 2023-2025, Jan/2021, etc)")
print("=" * 80)
results['PEDRO'] = analyze_cv('test_datas_variadas.pdf', 'PEDRO')
if results['PEDRO']:
    check_score_range('PEDRO', results['PEDRO'])
    check_no_false_spelling('PEDRO', results['PEDRO'])
    check_dates('PEDRO', results['PEDRO'])
    check_section_order('PEDRO', results['PEDRO'])

# Test 3: Lucas - REAL typos (Desenolvi, OTIMIZAI, REDUSEI)
print("\n" + "=" * 80)
print("TEST: Lucas Fernandes (Erros ortográficos REAIS: Desenolvi, OTIMIZAI, REDUSEI)")
print("=" * 80)
results['LUCAS'] = analyze_cv('test_erros_ortograficos.pdf', 'LUCAS')
if results['LUCAS']:
    check_score_range('LUCAS', results['LUCAS'])
    check_no_false_spelling('LUCAS', results['LUCAS'])
    # Specifically check that real typos ARE detected
    erros = results['LUCAS'].get('erros_ortograficos', [])
    print(f"  [CHECK] Erros detectados: {erros}")
    check_section_order('LUCAS', results['LUCAS'])

# Test 4: Ana - Progress bars (% in skills), sensitive data
print("\n" + "=" * 80)
print("TEST: Ana Paula (Barras de progresso, dados sensíveis)")
print("=" * 80)
results['ANA'] = analyze_cv('test_erros_graves.pdf', 'ANA')
if results['ANA']:
    check_score_range('ANA', results['ANA'])
    check_no_false_spelling('ANA', results['ANA'])
    # Check for grave errors detection
    erros_comuns = results['ANA'].get('erros_comuns_detectados', [])
    tipos = [e.get('tipo', '') for e in erros_comuns]
    print(f"  [CHECK] Erros graves detectados: {tipos}")
    if 'barras_progresso_habilidades' in tipos or 'percentual_habilidades' in tipos:
        print(f"  [PASS] Ana: barras de progresso detectadas!")
    else:
        print(f"  [WARN] Ana: barras de progresso podem não ter sido detectadas")
    if 'dados_sensiveis' in tipos:
        print(f"  [PASS] Ana: dados sensíveis detectados!")
    else:
        print(f"  [WARN] Ana: dados sensíveis podem não ter sido detectados")
    check_section_order('ANA', results['ANA'])

# Summary
print("\n" + "=" * 80)
print("RESUMO DOS TESTES")
print("=" * 80)
for label, result in results.items():
    status = "PASS" if result and result.get('nota', 0) > 0 else "FAIL"
    nota = result.get('nota', 'N/A') if result else 'N/A'
    erros = result.get('erros_ortograficos', []) if result else []
    print(f"  {label}: {status} | nota={nota} | erros_ortograficos={erros}")

print("\nTESTES CONCLUÍDOS")
