"""E2E test for market analysis - using OLD working keys."""
import sys
sys.path.insert(0, 'backend')
import urllib.request
import urllib.parse
import json

# OLD keys that were working
ALL_KEYS = "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom,ak_y05reahqfectpm7959dp9kj1a2n0sz3atu1qbrw5yt17y5g,ak_yqhvsksd061yhjtafzi0l4k4t134mnpz2slwvm45pkpwq0k,ak_w50lspzm38pmj2zdz8v9phbuvai1a1h0df1u0qh1gmx753p,ak_a8plc0spoptyh0o0ug3d4qjrwpxa05gl0qmnsfadpoq2x2r,ak_aaijzj1qg9l0165qb3achtc6gd44nuegre9jcp0wbzu2fim"

data = urllib.parse.urlencode({
    'job_title': 'assistente administrativo',
    'target_stack': 'administrativo',
    'seniority': 'Nenhum',
    'location': 'Nacional',
    'time_window': '30 dias',
    'negative_keywords': '',
    'jsearch_api_keys': ALL_KEYS
}).encode()

req = urllib.request.Request(
    'http://localhost:8000/api/market/analyze',
    data=data,
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)

print("Sending request with OLD working keys...")
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        raw = resp.read().decode()
        result = json.loads(raw)
        R = result.get('report', result)

        s = R.get('summary', {})
        print("=== SUMMARY ===")
        print(f"  Total jobs scanned: {s.get('total_jobs_scanned')}")
        print(f"  Pre-filtered: {s.get('pre_filtered_count')}")
        print(f"  Relevant analyzed: {s.get('relevant_jobs_analyzed')}")
        print(f"  Discarded: {s.get('discarded_jobs')}")
        print(f"  JSearch status: {s.get('jsearch_status')}")
        print(f"  JSearch message: {s.get('jsearch_message', '')[:100]}")

        print("\n=== REJECTION REASONS ===")
        reasons = s.get('rejected_reasons_sample', [])
        if reasons:
            print(f"  {len(reasons)} rejeições encontradas:")
            for r in reasons[:15]:
                reason = r.get('reason', 'NO REASON')
                title = r.get('title', '')[:50]
                print(f"  [{reason}] {title}")
        else:
            print("  (nenhuma vaga rejeitada — todas relevantes)")

        print("\n=== TOP REQUIRED TECH (top 15) ===")
        req_techs = R.get('statistics', {}).get('required_technologies', [])
        for item in req_techs[:15]:
            print(f"  {item.get('name', '?')}: {item.get('count', 0)} vagas ({item.get('percentage', 0)}%)")

        print("\n=== TOP DESIRABLE TECH (top 10) ===")
        desc_techs = R.get('statistics', {}).get('desirable_technologies', [])
        for item in desc_techs[:10]:
            print(f"  {item.get('name', '?')}: {item.get('count', 0)} vagas")

        print("\n=== SOFT SKILLS (top 10) ===")
        soft = R.get('statistics', {}).get('top_soft_skills', [])
        for item in soft[:10]:
            print(f"  {item.get('name', '?')}: {item.get('count', 0)}")

        print("\n=== LANGUAGES (top 5) ===")
        langs = R.get('statistics', {}).get('top_languages', [])
        for item in langs[:5]:
            print(f"  {item.get('name', '?')}: {item.get('count', 0)} vagas (nivel: {item.get('top_level', '?')})")

        print("\n=== EXP YEARS ===")
        print(f"  Mediana: {R.get('statistics', {}).get('exp_years_median', '?')}")
        dist = R.get('statistics', {}).get('exp_years_distribution', {})
        if dist:
            for k, v in sorted(dist.items(), key=lambda x: -x[1])[:5]:
                print(f"  {k}: {v} vagas")

        print("\n=== SAMPLE RELEVANT JOBS (first 5) ===")
        sample = R.get('sample_jobs', [])
        relevant = [j for j in sample if j.get('is_relevant')]
        irrelevant = [j for j in sample if not j.get('is_relevant')]
        print(f"  Relevant in sample: {len(relevant)}")
        print(f"  Irrelevant in sample: {len(irrelevant)}")

        for i, j in enumerate(relevant[:5]):
            reqs = j.get('requirements', [])
            nice = j.get('nice_to_have', [])
            soft = j.get('soft_skills', [])
            exp_min = j.get('exp_years_min')
            exp_max = j.get('exp_years_max')
            title = j.get('title', '?')
            print(f"  [{i+1}] {title[:60]}")
            print(f"      reqs: {reqs[:6]}")
            print(f"      nice: {nice[:4]}")
            print(f"      soft: {soft[:4]}")
            print(f"      exp: {exp_min}-{exp_max}")

        if irrelevant:
            print(f"\n=== IRRELEVANT JOBS (first 5) ===")
            for i, j in enumerate(irrelevant[:5]):
                reason = j.get('rejection_reason', 'NO REASON')
                title = j.get('title', '?')
                print(f"  [{i+1}] {title[:60]}")
                print(f"      reason: {reason}")

        print(f"\nModel: {R.get('model', '?')}")
        print(f"Elapsed: {R.get('elapsed_seconds', '?')}s")

except Exception as e:
    print(f"Error: {e}")
