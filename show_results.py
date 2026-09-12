import json

with open(r"c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\qa_v4_results.json", 'r', encoding='utf-8') as f:
    results = json.load(f)

output = []
for r in results:
    nome = r.get('nome', 'N/A')
    nota = r.get('nota', 'N/A')
    erros = len(r.get('erros_ortograficos', []))
    issues = len(r.get('grounding_issues', []))
    status = "ISSUES!" if issues > 0 else "OK"
    output.append(f"{nome}: nota={nota}, erros={erros}, issues={issues} [{status}]")
output.append(f"\nTotal: {len(results)}")

with open(r"C:\temp\results_summary.txt", 'w', encoding='utf-8') as f:
    f.write("\n".join(output))

print("\n".join(output))
