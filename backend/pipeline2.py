import sys, os, time, subprocess

BACKEND_DIR = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend'
PYTHON = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\venv\Scripts\python.exe'
LOG = os.path.join(BACKEND_DIR, 'pipeline_log2.txt')
OUT = os.path.join(BACKEND_DIR, 'result_e2e_full2.txt')

def log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        f.flush()
    print(msg)

def run_py(script, timeout=60):
    r = subprocess.run([PYTHON, script], cwd=BACKEND_DIR,
                       capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout, r.stderr

# Step 1: Test imports
log("Step 1: Testing imports...")
rc, stdout, stderr = run_py('test_main.py', timeout=30)
log(f"  rc={rc} stdout={stdout.strip()[:200]} stderr={stderr.strip()[:500]}")

# Step 2: Start server
log("Step 2: Starting server...")
server_proc = subprocess.Popen(
    [PYTHON, 'start_server.py'],
    cwd=BACKEND_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
log(f"  PID: {server_proc.pid}")

# Step 3: Wait for ready
log("Step 3: Waiting for server...")
ready = False
for i in range(60):
    time.sleep(1)
    try:
        rc2, o2, e2 = run_py('test_health.py', timeout=5)
        if 'OK' in (o2 + e2):
            log(f"  Server ready after {i+1}s")
            ready = True
            break
    except:
        pass
if not ready:
    log("  Server not ready, checking log...")
    try:
        with open(os.path.join(BACKEND_DIR, 'server_log.txt'), 'r', encoding='utf-8') as f:
            log(f"  server_log.txt: {f.read()[:500]}")
    except:
        pass
    log("  Giving up on server startup")
    sys.exit(1)

# Step 4: Run test
log("Step 4: Running E2E test...")
ALL_KEYS = "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom,ak_y05reahqfectpm7959dp9kj1a2n0sz3atu1qbrw5yt17y5g,ak_yqhvsksd061yhjtafzi0l4k4t134mnpz2slwvm45pkpwq0k,ak_w50lspzm38pmj2zdz8v9phbuvai1a1h0df1u0qh1gmx753p,ak_a8plc0spoptyh0o0ug3d4qjrwpxa05gl0qmnsfadpoq2x2r,ak_aaijzj1qg9l0165qb3achtc6gd44nuegre9jcp0wbzu2fim"

data = subprocess.run(
    [PYTHON, 'e2e_test_simple.py', ALL_KEYS],
    cwd=BACKEND_DIR,
    capture_output=True, text=True, timeout=900,
    encoding='utf-8', errors='replace'
)
log(f"  Test exit code: {data.returncode}")
log(f"  Test stdout ({len(data.stdout)} chars): {data.stdout[:1000]}")
log(f"  Test stderr ({len(data.stderr)} chars): {data.stderr[:500]}")

# Check result file
if os.path.exists(OUT):
    with open(OUT, 'r', encoding='utf-8') as f:
        content = f.read()
    log(f"  Result file ({len(content)} chars): {content[:2000]}")
else:
    log("  Result file not found")

# Step 5: Shutdown
log("Step 5: Shutting down...")
server_proc.terminate()
try:
    server_proc.wait(timeout=5)
except:
    server_proc.kill()
log("Done.")
