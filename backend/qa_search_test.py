import sys, json, urllib.request, urllib.parse
sys.path.insert(0, r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend")
from market_service import _fetch_jsearch_jobs

key = "ak_vwsmyrmqvkorl80pkh8oo4pqvf6yxxpgx1hk95tlqfx3pi2"

print("=== Teste: Busca real com código corrigido ===\n")

# Testar com date_posted=all
jobs_all, rem, tot = _fetch_jsearch_jobs(
    "Assistente Administrativo",
    country="br", language="pt", num_pages=8, date_posted="all", api_keys=[key]
)
print(f"date_posted=all, num_pages=8: {len(jobs_all)} vagas")

# Testar com date_posted=month
jobs_month, rem, tot = _fetch_jsearch_jobs(
    "Assistente Administrativo",
    country="br", language="pt", num_pages=8, date_posted="month", api_keys=[key]
)
print(f"date_posted=month, num_pages=8: {len(jobs_month)} vagas")

print(f"\n=== RESULTADO ===")
print(f"Total com all: {len(jobs_all)}")
print(f"Total com month: {len(jobs_month)}")
if len(jobs_all) >= 60 and len(jobs_month) >= 30:
    print("PASS: Busca funciona corretamente")
else:
    print("NEEDS INVESTIGATION")
