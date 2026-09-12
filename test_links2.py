import requests, json

# Test edge cases PDF
r = requests.post('http://localhost:8000/api/cv/analyze', files={'cv_file': open('docs/test_edge_cases.pdf', 'rb')})
d = r.json()
print(f'status: {r.status_code}')
print(f'_links: {d.get("_links")}')
print(f'checklist: {json.dumps(d.get("checklist_validacao",{}), indent=2, ensure_ascii=False)}')

# Also test test_datas_variadas
r2 = requests.post('http://localhost:8000/api/cv/analyze', files={'cv_file': open('docs/test_datas_variadas.pdf', 'rb')})
d2 = r2.json()
print(f'\ntest_datas_variadas _links: {d2.get("_links")}')
print(f'checklist: {json.dumps(d2.get("checklist_validacao",{}), indent=2, ensure_ascii=False)}')
