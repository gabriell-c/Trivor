import requests, json, sys
r = requests.post('http://localhost:8000/api/cv/analyze', files={'cv_file': open('docs/test_edge_cases.pdf', 'rb')})
d = r.json()
out = {'status': r.status_code, 'links': d.get('_links', []), 'proj': d.get('checklist_validacao', {}).get('projetos_com_link')}
sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False))
