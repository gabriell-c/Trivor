import subprocess, sys
r = subprocess.run(
    [sys.executable, r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\deep_validation_test.py'],
    capture_output=True, text=True, encoding='utf-8'
)
with open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\deep_out.txt', 'w', encoding='utf-8') as f:
    f.write(r.stdout + r.stderr)
print(f"exit={r.returncode} stdout_len={len(r.stdout)} stderr_len={len(r.stderr)}")
if r.stderr:
    print("STDERR:", r.stderr[:500])
