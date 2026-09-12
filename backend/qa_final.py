import sys, json, urllib.request, urllib.parse
sys.path.insert(0, r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend")
from market_service import _fetch_jsearch_jobs, map_time_window_to_date_posted, _keyword_score

KEY = "ak_vwsmyrmqvkorl80pkh8oo4pqvf6yxxpgx1hk95tlqfx3pi2"
BASE = "http://127.0.0.1:8000"
FAIL = []

def check(name, cond):
    if not cond:
        FAIL.append(name)
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")

print("=== QA Final: Correções de Mercado ===\n")

# 1. Código
print("1. Verificação do código")
from market_service import _MAX_JOBS_FOR_ANALYSIS
check(f"_MAX_JOBS_FOR_ANALYSIS = {_MAX_JOBS_FOR_ANALYSIS} (esperado 500)", _MAX_JOBS_FOR_ANALYSIS == 500)
check("map_time_window 90 dias -> month", map_time_window_to_date_posted("90 dias") == "month")
check("map_time_window 30 dias -> month", map_time_window_to_date_posted("30 dias") == "month")

score = _keyword_score("assistente administrativo senior remote", "Assistente Administrativo", [], "Júnior", "Remoto Nacional")
check(f"Stack vazio + vaga senior NÃO rejeitada (score={score})", score > 0)

score2 = _keyword_score("engenheiro civil construcao", "Assistente Administrativo", [], "Júnior", "Remoto Nacional")
check(f"Vaga irrelevante rejeitada (score={score2})", score2 == 0)

# 2. Backend responde
print("\n2. Backend responds")
try:
    r = urllib.request.urlopen(f"{BASE}/api/jsearch/keys", timeout=5)
    keys = json.loads(r.read())
    valid = [k for k in keys["keys"] if k["api_key"] != "test-key-12345"]
    check(f"Backend OK, {len(valid)} chave(s) válida(s)", len(valid) > 0)
except Exception as e:
    check(f"Backend response", False)

# 3. Busca JSearch (com fallback de rate limit)
print("\n3. Busca JSearch")
try:
    jobs, rem, tot = _fetch_jsearch_jobs("Assistente Administrativo", date_posted="all", num_pages=8, api_keys=[KEY])
    check(f"date_posted=all: {len(jobs)} vagas", len(jobs) >= 40)
except Exception as e:
    check(f"date_posted=all busca", False)

try:
    jobs2, rem2, tot2 = _fetch_jsearch_jobs("Assistente Administrativo", date_posted="month", num_pages=8, api_keys=[KEY])
    check(f"date_posted=month: {len(jobs2)} vagas", len(jobs2) >= 20)
except Exception as e:
    check(f"date_posted=month busca", False)

# 4. Endpoint de análise
print("\n4. Endpoint /api/market/analyze")
form = urllib.parse.urlencode({
    'job_title': 'Assistente Administrativo',
    'target_stack': '',
    'seniority': 'Júnior',
    'location': 'Remoto Nacional',
    'time_window': '90 dias',
    'negative_keywords': '',
    'jsearch_api_keys': KEY,
    'api_key': 'sk-test',
    'model_name': 'gpt-4o',
}).encode()
try:
    req = urllib.request.Request(f"{BASE}/api/market/analyze", data=form, method='POST')
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
        if result.get("success"):
            summary = result.get("report", {}).get("summary", {})
            scanned = summary.get("total_jobs_scanned", 0)
            check(f"Análise completou, {scanned} vagas escaneadas", scanned > 0)
        else:
            check("Análise success", False)
except Exception as e:
    check(f"Análise endpoint", False)

print(f"\n{'='*50}")
if not FAIL:
    print("RESULTADO: TODOS TESTES PASSARAM")
else:
    print(f"RESULTADO: {len(FAIL)} falha(s): {', '.join(FAIL)}")
print(f"{'='*50}")
