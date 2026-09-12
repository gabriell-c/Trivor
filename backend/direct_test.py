"""Quick test with long timeout - write to file."""
import sys, urllib.request, urllib.parse, json, os, time

sys.path.insert(0, '.')

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

out_path = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\result_direct.txt'
start = time.time()

try:
    with urllib.request.urlopen(req, timeout=1200) as resp:
        raw = resp.read().decode()
        elapsed = time.time() - start
        result = json.loads(raw)
        R = result.get('report', result)
        s = R.get('summary', {})

        lines = []
        lines.append(f"Total jobs scanned: {s.get('total_jobs_scanned')}")
        lines.append(f"Pre-filtered: {s.get('pre_filtered_count')}")
        lines.append(f"Relevant analyzed: {s.get('relevant_jobs_analyzed')}")
        lines.append(f"Discarded: {s.get('discarded_jobs')}")
        lines.append(f"JSearch status: {s.get('jsearch_status')}")
        jm = s.get('jsearch_message', '')
        lines.append(f"JSearch msg: {str(jm)[:300]}")
        lines.append(f"Elapsed: {elapsed:.1f}s")

        stats = R.get('statistics', {})
        req_techs = stats.get('required_technologies', [])
        soft_skills = stats.get('top_soft_skills', [])
        langs = stats.get('top_languages', [])
        nice = stats.get('nice_to_have_skills', [])
        exp_stats = stats.get('experience_distribution', {})

        lines.append(f"\n=== REQUIRED TECH (top 15) ===")
        for t in req_techs[:15]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== SOFT SKILLS (top 10) ===")
        for t in soft_skills[:10]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== LANGUAGES (top 10) ===")
        for t in langs[:10]:
            lines.append(f"  {t.get('language')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== NICE TO HAVE (top 15) ===")
        for t in nice[:15]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== EXPERIENCE ===")
        lines.append(f"  min: {exp_stats.get('min_years')}")
        lines.append(f"  max: {exp_stats.get('max_years')}")
        lines.append(f"  avg: {exp_stats.get('avg_years')}")
        lines.append(f"  dist: {json.dumps(exp_stats.get('distribution', {}), ensure_ascii=False)}")

        lines.append(f"\n=== REJECTION SAMPLES ===")
        reasons = s.get('rejected_reasons_sample', [])
        for r in reasons[:10]:
            lines.append(f"  {r}")

        lines.append(f"\n=== KEY JOBS (first 10 relevant) ===")
        jobs = R.get('jobs', [])
        for j in jobs[:10]:
            lines.append(f"  Title: {j.get('title')}")
            lines.append(f"    req: {json.dumps(j.get('requirements',[])[:5], ensure_ascii=False)}")
            lines.append(f"    soft: {json.dumps(j.get('soft_skills',[])[:3], ensure_ascii=False)}")
            lines.append(f"    nice: {json.dumps(j.get('nice_to_have',[])[:3], ensure_ascii=False)}")
            lines.append(f"    lang: {j.get('languages',[])}")
            lines.append(f"    exp: {j.get('experience_years')}")
            lines.append(f"    status: {j.get('status')}")
            lines.append("")

        lines.append(f"\nTotal jobs in report: {len(jobs)}")
        lines.append(f"\nWord mentions: {sum(1 for j in jobs[:100] if any('word' in str(r).lower() for r in j.get('requirements',[])))}")

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"Done in {elapsed:.1f}s - saved to {out_path}")
        print(f"Scanned: {s.get('total_jobs_scanned')}, Relevant: {s.get('relevant_jobs_analyzed')}")

except Exception as e:
    elapsed = time.time() - start
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"ERROR after {elapsed:.1f}s: {e}\n")
        import traceback
        f.write(traceback.format_exc())
    print(f"ERROR after {elapsed:.1f}s: {e}")
