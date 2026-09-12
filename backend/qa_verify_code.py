import sys, json, urllib.request, urllib.parse
sys.path.insert(0, r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend")

print("=== Verificação do código atual ===\n")

# 1. Verificar imports
from market_service import (
    map_time_window_to_date_posted,
    _keyword_score,
    _pre_filter_jobs,
    _fetch_jsearch_jobs,
    _MAX_JOBS_FOR_ANALYSIS,
    run_market_analysis,
)
from openai import OpenAI
from pathlib import Path
import sqlite3

print(f"_MAX_JOBS_FOR_ANALYSIS = {_MAX_JOBS_FOR_ANALYSIS}")

# 2. Testar map_time_window
print("\n=== map_time_window_to_date_posted ===")
for tw in ["30 dias", "60 dias", "90 dias", "outro"]:
    print(f"  {tw!r:12s} -> {map_time_window_to_date_posted(tw)!r}")

# 3. Testar _keyword_score
print("\n=== _keyword_score ===")
# Vaga sênior com stack vazio, seniority Júnior
score = _keyword_score(
    "assistente administrativo sênior remote planejamento",
    "Assistente Administrativo",
    [],  # stack vazio
    "Júnior",
    "Remoto Nacional"
)
print(f"  Sênior + stack vazio + Júnior user: score={score} {'PASS' if score > 0 else 'FAIL'}")

# Vaga irrelevante
score2 = _keyword_score(
    "engenheiro civil construção edifícios",
    "Assistente Administrativo",
    [],
    "Júnior",
    "Remoto Nacional"
)
print(f"  Irrelevante + stack vazio: score={score2} {'PASS' if score2 == 0 else 'FAIL'}")

# 4. Verificar backend está rodando
print("\n=== Backend status ===")
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/api/jsearch/keys', timeout=5)
    keys = json.loads(r.read())
    print(f"  Backend OK - {len(keys['keys'])} chave(s)")
except Exception as e:
    print(f"  Backend NÃO rodando: {e}")

print("\n=== Verificação completa ===")
