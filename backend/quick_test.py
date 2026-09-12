"""Quick E2E test for volume check - writes output to file."""
import sys, urllib.request, urllib.parse, json, os
sys.path.insert(0, 'backend')

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

out = []
out.append("Sending request...")
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        raw = resp.read().decode()
        result = json.loads(raw)
        R = result.get('report', result)
        s = R.get('summary', {})
        out.append(f"Total scanned: {s.get('total_jobs_scanned')}")
        out.append(f"Pre-filtered: {s.get('pre_filtered_count')}")
        out.append(f"Relevant: {s.get('relevant_jobs_analyzed')}")
        out.append(f"Discarded: {s.get('discarded_jobs')}")
        out.append(f"JSearch status: {s.get('jsearch_status')}")
        jm = s.get('jsearch_message', '')
        out.append(f"JSearch msg: {str(jm)[:200]}")

        stats = R.get('statistics', {})
        req_techs = stats.get('required_technologies', [])
        soft_skills = stats.get('top_soft_skills', [])
        langs = stats.get('top_languages', [])
        out.append("=== SKILLS ===")
        out.append(f"Required techs (top 10): {json.dumps(req_techs[:10], ensure_ascii=False)}")
        out.append(f"Top soft skills: {json.dumps(soft_skills[:5], ensure_ascii=False)}")
        out.append(f"Top languages: {json.dumps(langs[:5], ensure_ascii=False)}")

        sample = R.get('sample_jobs', [])
        out.append(f"=== SAMPLE JOBS ({len(sample)}) ===")
        for j in sample[:10]:
            reqs = j.get('requirements', [])
            soft = j.get('soft_skills', [])
            nice = j.get('nice_to_have', [])
            langs_j = j.get('languages', [])
            exp = j.get('exp_years_min', None)
            rel = j.get('is_relevant', False)
            out.append(f"  [{rel}] {j.get('title','')[:50]} | reqs={reqs[:5]} | soft={soft[:2]} | nice={nice[:2]} | langs={langs_j} | exp={exp}")

        # Word/Excel count
        word_count = sum(1 for j in sample if any('word' in r.lower() for r in j.get('requirements', []) + j.get('nice_to_have', [])))
        excel_count = sum(1 for j in sample if any('excel' in r.lower() for r in j.get('requirements', []) + j.get('nice_to_have', [])))
        ppt_count = sum(1 for j in sample if any('powerpoint' in r.lower() or 'power point' in r.lower() for r in j.get('requirements', []) + j.get('nice_to_have', [])))
        out.append("=== SKILL COVERAGE ===")
        out.append(f"Vagas com Word: {word_count}/{len(sample)}")
        out.append(f"Vagas com Excel: {excel_count}/{len(sample)}")
        out.append(f"Vagas com PowerPoint: {ppt_count}/{len(sample)}")
        out.append("DONE")

except Exception as e:
    out.append(f"ERROR: {e}")
    import traceback
    out.append(traceback.format_exc())

outfile = os.path.join(os.path.dirname(__file__), 'quick_test_result.txt')
with open(outfile, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print("Test completed, results written to quick_test_result.txt")
