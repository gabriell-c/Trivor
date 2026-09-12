import os
path = r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_test.txt"
with open(path, "w") as f:
    f.write("Test\n")
print(f"Written to {path}")
