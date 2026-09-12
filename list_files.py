import os

workdir = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo"
os.chdir(workdir)

# List files
txt_files = [f for f in os.listdir('.') if f.endswith('.txt')]
with open('file_list.txt', 'w', encoding='utf-8') as f:
    f.write("TXT files:\n")
    for f in txt_files:
        f.write(f"  {f}\n")
    f.write(f"\nPDFs in docs/ ({len([p for p in os.listdir('docs') if p.endswith('.pdf')])}):\n")
    for p in sorted([p for p in os.listdir('docs') if p.endswith('.pdf')]):
        f.write(f"  {p}\n")

print("done")
