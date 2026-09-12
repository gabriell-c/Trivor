"""Test _ensure_common_skills and _sanitize_requirements."""
import sys
sys.path.insert(0, '.')
from market_service import _ensure_common_skills, _sanitize_requirements, normalize_skill

print("=== Test _ensure_common_skills ===")

# Test 1: vaga administrativa com Word/Excel
job_text = """Título: Assistente Administrativo
Empresa: Teste
Localização: São Paulo
Descrição:
Requisitos:
- Excel intermediário
- Pacote Office
- Word
- Ensino médio completo
- Digitação
- Inglês básico
"""
item = {"requirements": ["Excel intermediário"], "nice_to_have": [], "soft_skills": []}
result = _ensure_common_skills(item, job_text)
print(f"Test 1 - Admin vaga:")
print(f"  Requirements: {result['requirements']}")
print(f"  Nice: {result['nice_to_have']}")

# Test 2: vaga com PowerPoint mencionado
job_text2 = "Vaga para assistente. Necessrio PowerPoint, Word e Excel. Ensino superior."
item2 = {"requirements": ["Excel"], "nice_to_have": [], "soft_skills": []}
result2 = _ensure_common_skills(item2, job_text2)
print(f"Test 2 - PowerPoint:")
print(f"  Requirements: {result2['requirements']}")
print(f"  Nice: {result2['nice_to_have']}")

# Test 3: vaga não-administrativa (tech)
job_text3 = "Desenvolvedor Python. React, Node.js, Docker."
item3 = {"requirements": ["Python", "React"], "nice_to_have": [], "soft_skills": []}
result3 = _ensure_common_skills(item3, job_text3)
print(f"Test 3 - Tech vaga (no admin skills should be added):")
print(f"  Requirements: {result3['requirements']}")

# Test 4: vaga administrativa sem nenhum skill extraído pela IA
job_text4 = """Assistente Administrativo
Requisitos: Word, Excel, Pacote Office, Ensino Médio completo, Digitação, Organização
"""
item4 = {"requirements": [], "nice_to_have": [], "soft_skills": []}
result4 = _ensure_common_skills(item4, job_text4)
print(f"Test 4 - Admin vaga sem skills (safety net):")
print(f"  Requirements: {result4['requirements']}")
print(f"  Nice: {result4['nice_to_have']}")

print("\n=== Test _sanitize_requirements ===")

# Test sanitize with increased max length
item_s1 = {"requirements": ["Formação superior completa em qualquer área"], "soft_skills": []}
result_s1 = _sanitize_requirements(item_s1)
print(f"Sanitize test 1: {result_s1['requirements']}")

item_s2 = {"requirements": ["Excel avançado", "Word", "PowerPoint", "Ensino Médio completo", "Das 10h Às 19h"], "soft_skills": []}
result_s2 = _sanitize_requirements(item_s2)
print(f"Sanitize test 2: {result_s2['requirements']}")

item_s3 = {"requirements": ["Experiência na área administrativa de compras (a partir de 1 ano)"], "soft_skills": []}
result_s3 = _sanitize_requirements(item_s3)
print(f"Sanitize test 3: {result_s3['requirements']}")

print("\n=== Test normalize_skill ===")
tests = ["Word", "Microsoft Word", "PowerPoint", "Pacote Office", "Excel avançado", "Excel básico", "Informática"]
for t in tests:
    print(f"  {repr(t)} -> {repr(normalize_skill(t))}")

print("\nAll tests completed!")
