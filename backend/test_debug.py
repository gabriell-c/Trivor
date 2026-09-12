"""Debug E2E - inspect raw response structure."""
import sys
sys.path.insert(0, 'backend')
import urllib.request
import urllib.parse
import json

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

print("Sending request...")
with urllib.request.urlopen(req, timeout=300) as resp:
    raw = resp.read().decode()
    result = json.loads(raw)
    R = result.get('report', result)

    # Print top-level keys
    print("TOP KEYS:", list(R.keys()))

    # Print summary
    s = R.get('summary', {})
    print("\n=== SUMMARY ===")
    print(f"  total_jobs_scanned: {s.get('total_jobs_scanned')}")
    print(f"  pre_filtered_count: {s.get('pre_filtered_count')}")
    print(f"  relevant_jobs_analyzed: {s.get('relevant_jobs_analyzed')}")
    print(f"  discarded_jobs: {s.get('discarded_jobs')}")
    print(f"  rejected_reasons_sample count: {len(s.get('rejected_reasons_sample', []))}")

    # Print statistics
    st = R.get('statistics', {})
    print("\n=== STATISTICS ===")
    print(f"  keys: {list(st.keys())}")

    req_techs = st.get('required_technologies', [])
    print(f"\n  required_technologies ({len(req_techs)} items):")
    for item in req_techs[:10]:
        print(f"    {item}")

    desc_techs = st.get('desirable_technologies', [])
    print(f"\n  desirable_technologies ({len(desc_techs)} items):")
    for item in desc_techs[:10]:
        print(f"    {item}")

    soft = st.get('soft_skills', [])
    print(f"\n  soft_skills ({len(soft)} items):")
    for item in soft[:10]:
        print(f"    {item}")

    # Print jobs
    jobs = R.get('jobs', [])
    print(f"\n=== JOBS ({len(jobs)} total) ===")
    relevant_count = sum(1 for j in jobs if j.get('is_relevant'))
    print(f"  relevant: {relevant_count}")
    if jobs:
        print(f"  First job keys: {list(jobs[0].keys())}")
        print(f"  First job is_relevant: {jobs[0].get('is_relevant')}")
        print(f"  First job title: {jobs[0].get('title')}")
        print(f"  First job requirements: {jobs[0].get('requirements')}")
        print(f"  First job nice_to_have: {jobs[0].get('nice_to_have')}")
        print(f"  First job rejection_reason: {jobs[0].get('rejection_reason')}")

    # Show model and elapsed
    print(f"\n  model: {R.get('model')}")
    print(f"  elapsed_seconds: {R.get('elapsed_seconds')}")
