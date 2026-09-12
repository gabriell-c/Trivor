"""Deep debug: write all results to file to avoid terminal buffer issues."""
import sqlite3, json, sys, requests

out = open(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\debug_all.txt', 'w', encoding='utf-8')

def w(s=''):
    out.write(s + '\n')

# Check recent logs
conn = sqlite3.connect(r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\data\requests.log.db')
rows = conn.execute('SELECT id, timestamp, status_code, response_summary, extracted_text FROM api_logs ORDER BY timestamp DESC LIMIT 5').fetchall()
conn.close()

w(f"{'='*60}")
w(f"TOTAL LOG ENTRIES: {len(rows)}")
w(f"{'='*60}")

for rid, ts, sc, rs, et in rows:
    w(f"\n--- LOG: {ts} (status={sc}, id={rid[:8]}) ---")
    if rs:
        d = json.loads(rs)
        w(f"  erros_ort: {len(d.get('erros_ortograficos',[]))}")
        for e in d.get('erros_ortograficos', []):
            w(f"    - palavra='{e.get('palavra')}' correcao='{e.get('correcao')}' contexto='{e.get('contexto','')[:60]}'")
        w(f"  erros_comuns: {len(d.get('erros_comuns_detectados',[]))}")
        for e in d.get('erros_comuns_detectados', []):
            w(f"    - tipo={e.get('tipo')} exemplo='{e.get('exemplo')}'")
        w(f"  faltantes: {d.get('palavras_chave_faltantes',[])}")
        w(f"  ordem: {json.dumps(d.get('ordem_secoes',{}), ensure_ascii=False)}")
        w(f"  nota: {d.get('nota')}")
        pf = d.get('pontos_fracos',[])
        tech_kw = {'linguagem','framework','tech','api','sql','javascript','python','java','react','git','aws','docker','dev','código','software','frontend','backend','fullstack'}
        tech_pts = [p for p in pf if any(k in p.lower() for k in tech_kw)]
        if tech_pts:
            w(f"  ATENCAO-vies-tech: {tech_pts}")
    if et:
        lines = et.split('\n')
        w(f"  TEXT(Primeiras 30 linhas):")
        for i, l in enumerate(lines[:30]):
            w(f"    {i+1:3}: {l}")

w(f"\n{'='*60}")
w("TESTING PDFs via API...")
w(f"{'='*60}")

BASE = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo'
pdfs = [
    f'{BASE}/docs/Curriculo Gabriel Cardoso.pdf',
    f'{BASE}/docs/Currículo Milena Cardoso.pdf',
    f'{BASE}/docs/test_curriculo.pdf',
    f'{BASE}/docs/test_erro_orho_real.pdf',
    f'{BASE}/docs/test_erros_graves.pdf',
]

for pdf_path in pdfs:
    try:
        fname = pdf_path.split('/')[-1]
        with open(pdf_path, 'rb') as f:
            files = {'cv_file': (fname, f, 'application/pdf')}
            resp = requests.post('http://localhost:8000/api/cv/analyze', files=files, data={'area': ''}, timeout=60)
        data = resp.json()
        w(f"\n--- {fname} (status={resp.status_code}) ---")
        if resp.status_code != 200:
            w(f"  ERROR: {data}")
            continue
        w(f"  nota: {data.get('nota')}")
        w(f"  erros_ort: {len(data.get('erros_ortograficos',[]))}")
        for e in data.get('erros_ortograficos', []):
            w(f"    - palavra='{e.get('palavra')}' correcao='{e.get('correcao')}' contexto='{e.get('contexto','')[:60]}'")
        w(f"  erros_comuns: {len(data.get('erros_comuns_detectados',[]))}")
        for e in data.get('erros_comuns_detectados', []):
            w(f"    - tipo={e.get('tipo')} exemplo='{e.get('exemplo')}'")
        w(f"  faltantes: {data.get('palavras_chave_faltantes',[])}")
        w(f"  ordem: {json.dumps(data.get('ordem_secoes',{}), ensure_ascii=False)}")
        pf = data.get('pontos_fracos',[])
        tech_kw = {'linguagem','framework','tech','api','sql','javascript','python','java','react','git','aws','docker','dev','código','software','frontend','backend','fullstack'}
        tech_pts = [p for p in pf if any(k in p.lower() for k in tech_kw)]
        if tech_pts:
            w(f"  ATENCAO-vies-tech: {tech_pts}")
    except Exception as e:
        w(f"  ERROR {fname}: {e}")
        import traceback; traceback.print_exc(file=out)

w(f"\n{'='*60}")
w("DONE")
out.close()
print("DONE - check debug_all.txt")
