"""Debug: check what the AI is actually extracting vs what's in the raw descriptions."""
import sqlite3
import json
import sys
sys.path.insert(0, '.')
from market_service import normalize_skill

db = Path("backend/market.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# Get a few raw jobs and their descriptions
c.execute("SELECT title, description FROM market_raw_jobs LIMIT 10")
jobs = c.fetchall()
for title, desc in jobs:
    print(f"\n{'='*60}")
    print(f"TITLE: {title}")
    print(f"DESC ({len(desc)} chars): {desc[:500]}...")
    # Search for keywords
    desc_lower = desc.lower()
    keywords = ["excel", "word", "pacote office", "in", "ensino", "superior", "experiência", "experiencia", "idioma", "espanhol", "português", "powerpoint", "digitacao", "organização"]
    found = [k for k in keywords if k in desc_lower]
    print(f"Keywords found in desc: {found}")

# Check extracted jobs
print(f"\n{'='*60}")
print("EXTRACTED JOBS:")
c.execute("SELECT title, requirements, nice_to_have, soft_skills FROM market_jobs LIMIT 10")
for title, reqs, nice, soft in c.fetchall():
    r = json.loads(reqs) if reqs else []
    n = json.loads(nice) if nice else []
    s = json.loads(soft) if soft else []
    print(f"\n  {title}")
    print(f"    Req ({len(r)}): {r}")
    print(f"    Nice ({len(n)}): {n}")
    print(f"    Soft ({len(s)}): {s}")

conn.close()
