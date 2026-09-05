import sys, subprocess
r1 = subprocess.run([sys.executable, r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\final_validation_test.py'],
    capture_output=True, text=True, encoding='utf-8')
r2 = subprocess.run([sys.executable, r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\deep_validation_test.py'],
    capture_output=True, text=True, encoding='utf-8')
open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\final_out.txt','w',encoding='utf-8').write(r1.stdout+r1.stderr)
open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\deep_out.txt','w',encoding='utf-8').write(r2.stdout+r2.stderr)
print(f"FINAL exit={r1.returncode}  DEEP exit={r2.returncode}")
for label, r in [("FINAL", r1), ("DEEP", r2)]:
    for l in (r.stdout+r.stderr).splitlines():
        if 'RESULTADO' in l or 'passed' in l.lower() or 'FAIL' in l or 'TODOS' in l:
            print(f"  [{label}] {l.strip()}")
