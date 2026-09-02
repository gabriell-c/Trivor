#!/usr/bin/env python3
"""Testes QA manuais - simulações múltiplas do usuário."""
import json
import requests
import os
import time

BACKEND = 'http://127.0.0.1:8000'
DOCS = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'
RESULTS = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_manual'
os.makedirs(RESULTS, exist_ok=True)

# Verificar health
r = requests.get(f'{BACKEND}/health')
print(f"[HEALTH] {r.json()['status']}")

def run_test(label, filename):
    """Executa uma análise e retorna o resultado."""
    path = os.path.join(DOCS, filename)
    if not os.path.exists(path):
        print(f"[SKIP] {label}: {filename} não encontrado")
        return None
    with open(path, 'rb') as f:
        files = {'cv_file': (filename, f, 'application/pdf')}
        r = requests.post(f'{BACKEND}/api/cv/analyze', files=files, timeout=120)
    if r.status_code == 200:
        result = r.json()
        out = os.path.join(RESULTS, f'{label}_{int(time.time())}.json')
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        return result
    else:
        print(f"  [ERROR] {label}: HTTP {r.status_code} - {r.text[:200]}")
        return None

# ============================================================================
# TESTES COM CURRÍCULOS EXISTENTES
# ============================================================================
print("\n" + "=" * 80)
print("FASE 1: CURRÍCULOS EXISTENTES (/docs)")
print("=" * 80)

existing_cvs = [
    ('GABRIEL', 'Curriculo Gabriel Cardoso.pdf'),
    ('MILENA', 'Currículo Milena Cardoso.pdf'),
    ('TEST', 'test_curriculo.pdf'),
    ('MARIANA', 'test_erro_orho_real.pdf'),
    ('PEDRO', 'test_datas_variadas.pdf'),
    ('LUCAS', 'test_erros_ortograficos.pdf'),
    ('ANA', 'test_erros_graves.pdf'),
    ('EDGE', 'test_edge_cases.pdf'),
]

results = {}
for label, fname in existing_cvs:
    print(f"\n--- {label}: {fname} ---")
    r = run_test(label, fname)
    if r:
        results[label] = r
        print(f"  NOTA: {r.get('nota')} | ATS: {r.get('score_ats')}")
        print(f"  ERROS ORTO: {r.get('erros_ortograficos', [])}")
        print(f"  FOTO: {r.get('foto_detectada')}")
        print(f"  MODELO: {r.get('api_info', {}).get('model')}")
        secoes = r.get('analise_secoes', {})
        for sec, data in secoes.items():
            print(f"    {sec}: {data.get('score')} ({data.get('status')})")
    time.sleep(1)  # evitar rate limit

# ============================================================================
# ANÁLISE DE CONSISTÊNCIA: rodar o mesmo CV 2x e comparar
# ============================================================================
print("\n" + "=" * 80)
print("FASE 2: CONSISTÊNCIA - MESMO CV 2x (Gabriel)")
print("=" * 80)

r1 = run_test('GABRIEL_R1', 'Curriculo Gabriel Cardoso.pdf')
time.sleep(2)
r2 = run_test('GABRIEL_R2', 'Curriculo Gabriel Cardoso.pdf')

if r1 and r2:
    print(f"\n  Rodada 1: nota={r1['nota']} err_ort={r1['erros_ortograficos']}")
    print(f"  Rodada 2: nota={r2['nota']} err_ort={r2['erros_ortograficos']}")
    # Comparar campos críticos
    checks = [
        ('nota', r1['nota'], r2['nota']),
        ('score_ats', r1['score_ats'], r2['score_ats']),
        ('foto_detectada', r1['foto_detectada'], r2['foto_detectada']),
        ('erros_ortograficos', r1['erros_ortograficos'], r2['erros_ortograficos']),
    ]
    all_consistent = True
    for name, v1, v2 in checks:
        match = v1 == v2
        print(f"  {name}: {'CONSISTENTE' if match else 'DIVERGENTE'} ({v1} vs {v2})")
        if not match:
            all_consistent = False
    print(f"\n  {'PASS' if all_consistent else 'CHECK CONSISTÊNCIA'}: Notas podem variar +/- 5 pontos entre rodadas (LLM não determinística)")

# ============================================================================
# TESTES DE VALIDAÇÃO ESPECÍFICA
# ============================================================================
print("\n" + "=" * 80)
print("FASE 3: VALIDAÇÃO ESPECÍFICA POR CRITÉRIO")
print("=" * 80)

def validate(label, result, checks):
    """Valida checks específicos."""
    if not result:
        print(f"  [{label}] FAIL - sem resultado")
        return False
    all_pass = True
    for check_name, condition in checks:
        passed = condition(result)
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{label}] {status}: {check_name}")
    return all_pass

# Validação 1: Nenhuma palavra técnica é flagrada como erro ortográfico
print("\n--- Validação: LLM não inventa erros ortográficos ---")
tech_words = ['React', 'Python', 'JavaScript', 'Node', 'Django', 'AWS', 'Docker',
              'GitHub', 'LinkedIn', 'TypeScript', 'PostgreSQL', 'MongoDB', 'Redis',
              'Jenkins', 'Kafka', 'GraphQL', 'SQL', 'API', 'REST', 'JWT', 'CI/CD',
              'Maria', 'João', 'Silva', 'Santos', 'Oliveira', 'Pedro', 'Lucas']

for label, result in results.items():
    erros = result.get('erros_ortograficos', [])
    inventados = [e for e in erros if any(w.lower() in e.lower() for w in tech_words)]
    if inventados:
        print(f"  [FAIL] {label}: inventou erros: {inventados}")
    else:
        print(f"  [PASS] {label}: {len(erros)} erros, nenhum inventado")

# Validação 2: Notas na escala 0-100
print("\n--- Validação: Escala 0-100 ---")
for label, result in results.items():
    nota = result.get('nota', -1)
    ats = result.get('score_ats', -1)
    if 0 <= nota <= 100 and 0 <= ats <= 100:
        print(f"  [PASS] {label}: nota={nota}, ats={ats}")
    else:
        print(f"  [FAIL] {label}: nota={nota}, ats={ats}")

# Validação 3: Erros ortográficos reais são detectados (Lucas)
print("\n--- Validação: Erros reais detectados (Lucas) ---")
lucas = results.get('LUCAS')
if lucas:
    erros = lucas.get('erros_ortograficos', [])
    # REDUSEI é erro real (verbo "reduzir" no pretérito perfeito = reduzi, não REDUSEI)
    has_real_error = any('REDUSEI' in e.upper() or 'REDUZ' in e.upper() for e in erros)
    if has_real_error:
        print(f"  [PASS] Lucas: erro REAL detectado: {erros}")
    else:
        print(f"  [WARN] Lucas: erros detectados={erros} (esperava REDUSEI ou similar)")

# Validação 4: Dados sensíveis detectados (Ana)
print("\n--- Validação: Dados sensíveis detectados (Ana) ---")
ana = results.get('ANA')
if ana:
    erros_comuns = ana.get('erros_comuns_detectados', [])
    tipos = [e.get('tipo', '') for e in erros_comuns]
    if 'dados_sensiveis' in tipos or 'cpf' in str(tipos).lower():
        print(f"  [PASS] Ana: dados sensíveis detectados: {tipos}")
    else:
        print(f"  [WARN] Ana: tipos detectados={tipos} (esperava dados_sensiveis)")

# Validação 5: Barras de progresso detectadas (Ana)
print("\n--- Validação: Barras de progresso detectadas (Ana) ---")
if ana:
    erros_comuns = ana.get('erros_comuns_detectados', [])
    tipos = [e.get('tipo', '') for e in erros_comuns]
    if any('percentual' in t or 'progresso' in t for t in tipos):
        print(f"  [PASS] Ana: barras de progresso detectadas: {tipos}")
    else:
        print(f"  [WARN] Ana: tipos detectados={tipos}")

# Validação 6: Bullet points entendidos (Gabriel/Milena)
print("\n--- Validação: Bullet points entendidos ---")
for label in ['GABRIEL', 'MILENA', 'MARIANA']:
    r = results.get(label)
    if r:
        exp = r.get('analise_secoes', {}).get('experiencia_profissional', {})
        bullets = exp.get('bullet_points')
        if bullets is not None:
            print(f"  [PASS] {label}: bullet_points={bullets}")
        else:
            print(f"  [WARN] {label}: bullet_points não encontrado na resposta")

# Validação 7: Ordem das seções
print("\n--- Validação: Ordem das seções ---")
for label, r in results.items():
    ordem = r.get('ordem_secoes', {})
    correta = ordem.get('correta', 'N/A')
    problema = ordem.get('problema', 'N/A')
    print(f"  [{label}] ordem_correta={correta} | problema={problema[:60] if problema and problema != 'N/A' else 'N/A'}")

print("\n" + "=" * 80)
print("TESTES MANUAIS CONCLUÍDOS")
print(f"Resultados salvos em: {RESULTS}")
print(f"Total de currículos testados: {len(results)}")
print("=" * 80)
