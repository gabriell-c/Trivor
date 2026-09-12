import subprocess
import os
r = subprocess.run(['python', 'list_pdfs.py'], capture_output=True, text=True)
with open('pdf_list.txt', 'w', encoding='utf-8') as f:
    f.write(r.stdout)
    f.write(r.stderr)
print('done')
