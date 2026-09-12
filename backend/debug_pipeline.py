"""Debug: check pre-filter and AI extraction pipeline."""
import sqlite3
import json
import sys
from pathlib import Path
sys.path.insert(0, '.')
from collections import Counter

from market_service import normalize_skill, _is_garbage_requirement

db = Path("backend/market.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# Count raw jobs
c.execute("SELECT COUNT(*) FROM market_raw_jobs")
raw_count = c.fetchone()[0]
print(f"Raw jobs: {raw_count}")

# Count extracted jobs
c.execute("SELECT COUNT(*) FROM market_jobs")
extracted_count = c.fetchone()[0]
print(f"Extracted jobs: {extracted_count}")

# Count relevant vs irrelevant
c.execute("SELECT COUNT(*) FROM market_jobs WHERE is_relevant = 1")
relevant = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM market_jobs WHERE is_relevant = 0")
irrelevant = c.fetchone()[0]
print(f"Relevant: {relevant}, Irrelevant: {irrelevant}")

# Check the requirements extraction quality
print("\n=== REQUIREMENTS QUALITY CHECK ===")
c.execute("SELECT title, requirements, nice_to_have, soft_skills FROM market_jobs LIMIT 20")
for title, reqs, nice, soft in c.fetchall():
    r = json.loads(reqs) if reqs else []
    n = json.loads(nice) if nice else []
    s = json.loads(soft) if soft else []
    total = len(r) + len(n) + len(s)
    print(f"  [{total:2d} skills] {title[:50]}")
    if r:
        print(f"    Req: {r}")
    if n:
        print(f"    Nice: {n}")
    if s:
        print(f"    Soft: {s}")

# Check what's being filtered by normalize_skill
print("\n=== CHECKING NORMALIZATION ===")
test_items = [
    "Word", "Microsoft Word", "Excel", "Pacote Office",
    "Inglês", "Inglês básico", "Ensino Médio", "Superior completo",
    "Experiência na área administrativa", "Gestão de contratos",
    "Espanhol avançado", "Cursando administração",
]
for item in test_items:
    normalized = normalize_skill(item)
    garbage = _is_garbage_requirement(item)
    print(f"  '{item}' → '{normalized}' (garbage={garbage})")

conn.close()
