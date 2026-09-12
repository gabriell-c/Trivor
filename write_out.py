import subprocess
import os

workdir = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo"

# Run list_pdfs.py and capture output
result = subprocess.run(
    ['python', 'list_pdfs.py'],
    cwd=workdir,
    capture_output=True,
    text=True
)

output_path = os.path.join(workdir, "output.txt")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write("STDOUT:\n")
    f.write(result.stdout)
    f.write("\nSTDERR:\n")
    f.write(result.stderr)
    f.write("\nRETURNCODE:\n")
    f.write(str(result.returncode))

print("done", result.returncode)
