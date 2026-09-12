import json
import os

results = []
for f in sorted(os.listdir('.')):
    if f.startswith('qa_') and f.endswith('_v3.json'):
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
        results.append({
            "nome": f.replace('qa_', '').replace('_v3.json', ''),
            "nota": data.get("nota"),
            "score_ats": data.get("score_ats"),
            "erros": [e.get("palavra") for e in data.get("erros_ortograficos", [])]
        })

output = []
output.append("QA v3 Results Summary")
output.append("="*60)
for r in results:
    output.append(f"{r['nome']}: Nota={r['nota']}, ATS={r['score_ats']}, Erros={r['erros']}")

false_positives = []
for r in results:
    for e in r['erros']:
        if e.lower() in ['migração', 'gerenciei', 'otimizei', 'otimizai']:
            false_positives.append(f"{r['nome']}: '{e}'")

output.append(f"\nFalsos positivos: {len(false_positives)}")
for fp in false_positives:
    output.append(f"  WARNING: {fp}")

if not false_positives:
    output.append("\nPASS - No false positives!")
else:
    output.append("\nFAIL - False positives detected!")

with open("qa_final_summary.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Done")
