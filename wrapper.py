import subprocess
result = subprocess.run(['python', 'run_qa_simple.py'], capture_output=True, text=True, shell=True)
with open(r"C:\temp\qa_out.txt", "w", encoding="utf-8") as f:
    f.write(result.stdout)
    f.write("\n---STDERR---\n")
    f.write(result.stderr)
print("done")
