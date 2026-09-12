import requests, json, os

base = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base, 'link_debug2.txt'), 'w', encoding='utf-8') as f:
    for fname in ['Curriculo Gabriel Cardoso.pdf', 'Currículo Milena Cardoso.pdf']:
        path = os.path.join(base, 'docs', fname)
        r = requests.post('http://localhost:8000/api/cv/analyze', files={'cv_file': open(path, 'rb')})
        d = r.json()
        links = d.get('_links', [])
        proj = d.get('checklist_validacao', {}).get('projetos_com_link', {})
        errs = d.get('erros_comuns_detectados', [])
        link_errors = [e for e in errs if 'link' in (e.get('descricao','') + ' ' + e.get('tipo','')).lower()]
        out = {
            'file': fname,
            'status': r.status_code,
            'links': links,
            'proj': proj,
            'link_errors': link_errors,
        }
        f.write(json.dumps(out, indent=2, ensure_ascii=False) + '\n---\n')
        print(f'{fname}: {r.status_code}, links={len(links)}, proj={proj}')
