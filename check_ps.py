import subprocess
import os
r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], capture_output=True, text=True)
with open('ps_check.txt', 'w', encoding='utf-8') as f:
    f.write(r.stdout)
print('done')
