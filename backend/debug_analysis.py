"""Debug: check what's in the DB and test extraction on sample data."""
import sqlite3
import json
from pathlib import Path
from collections import Counter

db = Path("backend/market.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# Raw jobs count
c.execute("SELECT COUNT(*) FROM market_raw_jobs")
raw_count = c.fetchone()[0]
print(f"Raw jobs in DB: {raw_count}")

if raw_count > 0:
    # Sample a few raw jobs
    c.execute("SELECT title, description FROM market_raw_jobs LIMIT 5")
    for i, (title, desc) in enumerate(c.fetchall()):
        print(f"\n--- Job {i+1} ---")
        print(f"Title: {title}")
        print(f"Desc length: {len(desc)}")
        # Show first 300 chars of description
        print(f"Desc preview: {desc[:300]}...")

# Market jobs (extracted)
c.execute("SELECT COUNT(*) FROM market_jobs")
market_count = c.fetchone()[0]
print(f"\nExtracted jobs: {market_count}")

if market_count > 0:
    c.execute("SELECT title, requirements, nice_to_have, soft_skills, certifications FROM market_jobs LIMIT 5")
    for i, (title, reqs, nice, soft, certs) in enumerate(c.fetchall()):
        print(f"\n--- Job {i+1}: {title} ---")
        print(f"  Req: {reqs}")
        print(f"  Nice: {nice}")
        print(f"  Soft: {soft}")
        print(f"  Certs: {certs}")

# Aggregate stats
c.execute("SELECT requirements, nice_to_have, soft_skills, certifications FROM market_jobs WHERE is_relevant = 1")
all_reqs = Counter()
all_nice = Counter()
all_soft = Counter()
all_certs = Counter()
total_req_items = 0
total_nice_items = 0
total_soft_items = 0
total_cert_items = 0

for reqs, nice, soft, certs in c.fetchall():
    r = json.loads(reqs) if reqs else []
    n = json.loads(nice) if nice else []
    s = json.loads(soft) if soft else []
    ct = json.loads(certs) if certs else []
    all_reqs.update(r)
    all_nice.update(n)
    all_soft.update(s)
    all_certs.update(ct)
    total_req_items += len(r)
    total_nice_items += len(n)
    total_soft_items += len(s)
    total_cert_items += len(ct)

print(f"\n=== AGGREGATE STATS ({market_count} relevant jobs) ===")
print(f"Total req items: {total_req_items} (avg {total_req_items/max(market_count,1):.1f}/job)")
print(f"Total nice items: {total_nice_items} (avg {total_nice_items/max(market_count,1):.1f}/job)")
print(f"Total soft items: {total_soft_items} (avg {total_soft_items/max(market_count,1):.1f}/job)")
print(f"Total cert items: {total_cert_items} (avg {total_cert_items/max(market_count,1):.1f}/job)")

print(f"\nTop Requirements:")
for req, count in all_reqs.most_common(15):
    print(f"  {count:3d}x  {req}")

print(f"\nTop Nice to Have:")
for nice, count in all_nice.most_common(15):
    print(f"  {count:3d}x  {nice}")

print(f"\nTop Soft Skills:")
for soft, count in all_soft.most_common(15):
    print(f"  {count:3d}x  {soft}")

print(f"\nTop Certifications:")
for cert, count in all_certs.most_common(10):
    print(f"  {count:3d}x  {cert}")

conn.close()
