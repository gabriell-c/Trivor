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

try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        raw = resp.read().decode()
        result = json.loads(raw)
        R = result.get('report', result)
        s = R.get('summary', {})
        out = []
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
        out.append(f"Required techs (top 10): {json.dumps(req_techs[:10], ensure_ascii=False)}")
        out.append(f"Top soft skills: {json.dumps(soft_skills[:5], ensure_ascii=False)}")
        out.append(f"Top languages: {json.dumps(langs[:5], ensure_ascii=False)}")
        sample = R.get('sample_jobs', [])
        out.append(f"Sample jobs: {len(sample)}")
        for j in sample[:5]:
            reqs = j.get('requirements', [])
            soft = j.get('soft_skills', [])
            nice = j.get('nice_to_have', [])
            rel = j.get('is_relevant', False)
            out.append(f"  [{rel}] {j.get('title','')[:50]} reqs={reqs[:3]} soft={soft[:2]} nice={nice[:2]}")
        word_count = sum(1 for j in sample if any('word' in r.lower() for r in j.get('requirements', []) + j.get('nice_to_have', [])))
        excel_count = sum(1 for j in sample if any('excel' in r.lower() for r in j.get('requirements', []) + j.get('nice_to_have', [])))
        out.append(f"Word in {word_count}/{len(sample)} jobs")
        out.append(f"Excel in {excel_count}/{len(sample)} jobs")
        out.append("DONE")
        with open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\result2.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
except Exception as e:
    with open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\result2.txt', 'w', encoding='utf-8') as f:
        f.write(f"ERROR: {e}\n")
        import traceback
        f.write(traceback.format_exc())
