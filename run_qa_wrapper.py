import subprocess
import os

workdir = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo"
result = subprocess.run(['python', 'run_qa_simple.py'], cwd=workdir, capture_output=True, text=True)
with open(r"C:\temp\qa_output.txt", "w", encoding="utf-8") as f:
    f.write("STDOUT:\n" + result.stdout)
    f.write("\nSTDERR:\n" + result.stderr)
    f.write("\nRETURN CODE:\n" + str(result.returncode))
print("done")
