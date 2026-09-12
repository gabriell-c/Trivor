"""Run E2E test - output to file with progress tracking."""
import sys, urllib.request, urllib.parse, json, os, time

sys.path.insert(0, '.')

ALL_KEYS = "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom,ak_y05reahqfectpm7959dp9kj1a2n0sz3atu1qbrw5yt17y5g,ak_yqhvsksd061yhjtafzi0l4k4t134mnpz2slwvm45pkpwq0k,ak_w50lspzm38pmj2zdz8v9phbuvai1a1h0df1u0qh1gmx753p,ak_a8plc0spoptyh0o0ug3d4qjrwpxa05gl0qmnsfadpoq2x2r,ak_aaijzj1qg9l0165qb3achtc6gd44nuegre9jcp0wbzu2fim"

OUT = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\result_e2e_v2.txt'
prog = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\progress_e2e.txt'

def progress(msg):
    t = time.strftime('%H:%M:%S')
    line = f"[{t}] {msg}"
    print(line)
    with open(prog, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

progress("Starting E2E test...")
progress(f"Keys: {len(ALL_KEYS.split(','))} keys")

start = time.time()

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

progress("Sending request (timeout 1800s)...")
try:
    with urllib.request.urlopen(req, timeout=1800) as resp:
        raw = resp.read().decode()
        elapsed = time.time() - start
        result = json.loads(raw)
        R = result.get('report', result)
        s = R.get('summary', {})

        progress(f"Response received in {elapsed:.0f}s")
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

        lines.append(f"\n=== REQUIRED TECH (top 20) ===")
        for t in req_techs[:20]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== SOFT SKILLS (top 10) ===")
        for t in soft_skills[:10]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== LANGUAGES (top 10) ===")
        for t in langs[:10]:
            lines.append(f"  {t.get('language')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== NICE TO HAVE (top 20) ===")
        for t in nice[:20]:
            lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        lines.append(f"\n=== EXPERIENCE ===")
        lines.append(f"  min: {exp_stats.get('min_years')}")
        lines.append(f"  max: {exp_stats.get('max_years')}")
        lines.append(f"  avg: {exp_stats.get('avg_years')}")
        lines.append(f"  dist: {json.dumps(exp_stats.get('distribution', {}), ensure_ascii=False)}")

        lines.append(f"\n=== REJECTION SAMPLES (first 10) ===")
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

        # Count Word/Excel mentions in requirements
        word_count = sum(1 for j in jobs if any('word' in str(r).lower() for r in j.get('requirements',[])))
        excel_count = sum(1 for j in jobs if any('excel' in str(r).lower() for r in j.get('requirements',[])))
        ppt_count = sum(1 for j in jobs if any('powerpoint' in str(r).lower() or 'ppt' in str(r).lower() for r in j.get('requirements',[])))
        lines.append(f"Word mentions: {word_count}/{len(jobs)}")
        lines.append(f"Excel mentions: {excel_count}/{len(jobs)}")
        lines.append(f"PPT mentions: {ppt_count}/{len(jobs)}")

        with open(OUT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        progress(f"Results saved to {OUT}")
        progress(f"Scanned: {s.get('total_jobs_scanned')}, Relevant: {s.get('relevant_jobs_analyzed')}, Discarded: {s.get('discarded_jobs')}")

except Exception as e:
    elapsed = time.time() - start
    progress(f"ERROR after {elapsed:.0f}s: {e}")
    import traceback
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(f"ERROR after {elapsed:.0f}s: {e}\n")
        f.write(traceback.format_exc())
    progress(traceback.format_exc()[:500])
