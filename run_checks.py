import subprocess
import os

workdir = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo"
os.chdir(workdir)

# Check PDFs
r1 = subprocess.run(['python', 'list_pdfs.py'], capture_output=True, text=True)
with open('pdf_list_out.txt', 'w', encoding='utf-8') as f:
    f.write(r1.stdout)
    f.write(r1.stderr)

# Check processes
r2 = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], capture_output=True, text=True)
with open('ps_out.txt', 'w', encoding='utf-8') as f:
    f.write(r2.stdout)

print('done')
