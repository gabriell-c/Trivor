"""Full pipeline: kill old server, start new, run test, save results."""
import sys, os, time, signal, subprocess, urllib.request, urllib.parse, json

BACKEND_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend'
PYTHON = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\venv\Scripts\python.exe'
LOG = os.path.join(BACKEND_DIR, 'pipeline_log.txt')
OUT = os.path.join(BACKEND_DIR, 'result_e2e_full.txt')

def log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        f.flush()
    print(msg)

def run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, cwd=cwd or BACKEND_DIR,
                       capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout, r.stderr

# Step 1: Kill any existing python server
log("Step 1: Killing existing python processes...")
run(f'"{PYTHON}" -c "import subprocess; subprocess.run([\"powershell\",\"-NoProfile\",\"-Command\",\"Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force\"], timeout=10)"')
time.sleep(2)
log("  Done")

# Step 2: Start server in background
log("Step 2: Starting server...")
server_proc = subprocess.Popen(
    [PYTHON, 'start_server.py'],
    cwd=BACKEND_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
log(f"  Server PID: {server_proc.pid}")

# Step 3: Wait for server to be ready
log("Step 3: Waiting for server...")
for i in range(30):
    time.sleep(1)
    try:
        code, stdout, stderr = run(f'"{PYTHON}" -c "import urllib.request; r=urllib.request.urlopen(\"http://127.0.0.1:8000/docs\", timeout=3); print(r.status)"')
        if '200' in stdout:
            log(f"  Server ready after {i+1}s")
            break
    except:
        pass
else:
    log("  ERROR: Server not ready after 30s")
    log(f"  stdout: {server_proc.stdout.read() if server_proc.stdout else 'none'}")
    log(f"  stderr: {server_proc.stderr.read() if server_proc.stderr else 'none'}")
    sys.exit(1)

# Step 4: Run test
log("Step 4: Running E2E test...")
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
    with urllib.request.urlopen(req, timeout=900) as resp:
        raw = resp.read().decode()
        result = json.loads(raw)
        R = result.get('report', result)
        s = R.get('summary', {})

        out_lines = []
        out_lines.append(f"Total jobs scanned: {s.get('total_jobs_scanned')}")
        out_lines.append(f"Pre-filtered: {s.get('pre_filtered_count')}")
        out_lines.append(f"Relevant analyzed: {s.get('relevant_jobs_analyzed')}")
        out_lines.append(f"Discarded: {s.get('discarded_jobs')}")
        out_lines.append(f"JSearch status: {s.get('jsearch_status')}")
        jm = s.get('jsearch_message', '')
        out_lines.append(f"JSearch msg: {str(jm)[:300]}")

        stats = R.get('statistics', {})
        req_techs = stats.get('required_technologies', [])
        soft_skills = stats.get('top_soft_skills', [])
        langs = stats.get('top_languages', [])
        nice = stats.get('nice_to_have_skills', [])
        exp_stats = stats.get('experience_distribution', {})

        out_lines.append(f"\n=== REQUIRED TECH (top 15) ===")
        for t in req_techs[:15]:
            out_lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        out_lines.append(f"\n=== SOFT SKILLS (top 10) ===")
        for t in soft_skills[:10]:
            out_lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        out_lines.append(f"\n=== LANGUAGES (top 10) ===")
        for t in langs[:10]:
            out_lines.append(f"  {t.get('language')}: {t.get('count')} ({t.get('percentage',0)}%)")

        out_lines.append(f"\n=== NICE TO HAVE (top 15) ===")
        for t in nice[:15]:
            out_lines.append(f"  {t.get('skill')}: {t.get('count')} ({t.get('percentage',0)}%)")

        out_lines.append(f"\n=== EXPERIENCE ===")
        out_lines.append(f"  min: {exp_stats.get('min_years')}")
        out_lines.append(f"  max: {exp_stats.get('max_years')}")
        out_lines.append(f"  avg: {exp_stats.get('avg_years')}")
        out_lines.append(f"  dist: {json.dumps(exp_stats.get('distribution', {}), ensure_ascii=False)}")

        out_lines.append(f"\n=== REJECTION SAMPLES ===")
        reasons = s.get('rejected_reasons_sample', [])
        for r in reasons[:10]:
            out_lines.append(f"  {r}")

        out_lines.append(f"\n=== KEY JOBS (first 5 relevant) ===")
        jobs = R.get('jobs', [])
        for j in jobs[:5]:
            out_lines.append(f"  Title: {j.get('title')}")
            out_lines.append(f"    req: {json.dumps(j.get('requirements',[])[:5], ensure_ascii=False)}")
            out_lines.append(f"    soft: {json.dumps(j.get('soft_skills',[])[:3], ensure_ascii=False)}")
            out_lines.append(f"    nice: {json.dumps(j.get('nice_to_have',[])[:3], ensure_ascii=False)}")
            out_lines.append(f"    lang: {j.get('languages',[])}")
            out_lines.append(f"    exp: {j.get('experience_years')}")
            out_lines.append(f"    status: {j.get('status')}")
            out_lines.append("")

        out_lines.append(f"\nTotal jobs in report: {len(jobs)}")
        with open(OUT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out_lines))
        log(f"  Results saved to {OUT}")
        log(f"  Total scanned: {s.get('total_jobs_scanned')}")
        log(f"  Relevant: {s.get('relevant_jobs_analyzed')}")
        log(f"  Discarded: {s.get('discarded_jobs')}")

except Exception as e:
    log(f"  ERROR: {e}")
    import traceback
    log(traceback.format_exc())
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(f"ERROR: {e}\n{traceback.format_exc()}")

# Step 5: Shutdown server
log("Step 5: Shutting down server...")
server_proc.terminate()
try:
    server_proc.wait(timeout=5)
except:
    server_proc.kill()
log("Done.")
