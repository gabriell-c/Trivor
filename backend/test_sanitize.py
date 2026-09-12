"""Test the new _sanitize_requirements."""
import sys
sys.path.insert(0, '.')
from market_service import _sanitize_requirements

# Test cases from the debug output
test_items = [
    {
        "requirements": [
            "2 A 5 Anos De Experiência Profissional Na Área. Conhecimentos Obrigatórios",
            "Adaptabilidade",
            "Auxílio Educação",
            "Capacidade De Análise. Será Considerado Diferencial",
            "Code Review E Pair Programming. Benefícios",
            "Conhecimento Em Lgpd. Ambiente Ágil Com Sprints Quinzenais",
            "Home Office Flexível.",
            "Node.js",
            "Plano De Saúde",
            "Pós-graduação Em Ti",
            "React",
            "Typescript",
            "Vr/va",
        ],
        "soft_skills": ["Adaptabilidade", "Capacidade de análise", "Facilidade de aprendizado"],
    },
    {
        "requirements": [
            "Excel avançado",
            "Word",
            "Inglês avançado",
            "Ensino Médio completo",
            "Das 10h Às 19h. Domingos E Feriados Conforme Escala. Local",
            "Terça A Sábado",
            "R$ 4.612",
            "Pacote Office",
        ],
        "soft_skills": [],
    },
    {
        "requirements": [
            "Experiência na área administrativa de compras ( a partir de 1 ano)",
            "Formação cursando ou concluído em qualquer área",
            "Espanhol avançado",
            "Pacote Office intermediário",
            "SAP",
        ],
        "soft_skills": [],
    },
]

for i, item in enumerate(test_items):
    result = _sanitize_requirements(item)
    print(f"\n=== Test {i+1} ===")
    print(f"  Before: {len(item['requirements'])} reqs, {len(item['soft_skills'])} soft")
    print(f"  After:  {len(result['requirements'])} reqs, {len(result['soft_skills'])} soft")
    print(f"  Req: {result['requirements']}")
    print(f"  Soft: {result['soft_skills']}")
