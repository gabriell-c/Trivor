"""Teste de pós-processamento."""
import unicodedata
def _n(s):
    return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode('ascii')

extracted = 'seguranca trabalho experiencia habilidades exelente resultado'
extracted_n = _n(extracted)

analysis = {
    'erros_ortograficos': [
        {'palavra': 'seguranca', 'correcao': 'seguranca', 'contexto': 'area'},
        {'palavra': 'EXPERIENCIA', 'correcao': 'experiencia', 'contexto': 'minha'},
        {'palavra': 'API', 'correcao': 'aplicacao', 'contexto': 'use a API'},
        {'palavra': 'exelente', 'correcao': 'excelente', 'contexto': 'resultado exelente'},
        {'palavra': 'aws', 'correcao': 'amazon', 'contexto': 'cloud aws'},
    ],
    'ordem_secoes': {'correta': False, 'problema': 'Seções fora de ordem', 'como_corrigir': 'corrigir'},
    'palavras_chave_faltantes': ['Python', 'SQL'],
    'pontos_fracos': ['Faltam linguagens', 'Precisa melhorar comunicacao'],
    'erros_comuns_detectados': [
        {'tipo': 'capitalizacao', 'descricao': 'Palavra em maiuscula', 'exemplo': 'SIGLA'},
        {'tipo': 'data_errada', 'descricao': 'Data inconsistente', 'exemplo': '2025'},
    ],
}

area_info = ''

# Filtro erros ortograficos
ve = []
for err in analysis['erros_ortograficos']:
    w = err.get('palavra', '')
    c = err.get('correcao', '')
    if not w or _n(w) not in extracted_n: continue
    if c and _n(c) == _n(w): continue
    if w == w.upper() and len(w) > 1: continue
    if 'ç' in w or 'n~' in w: continue
    if len(w) >= 3 and w.isupper(): continue
    ve.append(err)
analysis['erros_ortograficos'] = ve

# Pos-processamento
if not area_info:
    analysis['palavras_chave_faltantes'] = []
    analysis['ordem_secoes']['correta'] = True
    analysis['ordem_secoes']['problema'] = None
    dev_kw = {'linguagem','framework','tech','sql','python','java','react','dev',
              'desenvolvimento','programacao','codigo','software','frontend','backend',
              'git','aws','docker','kubernetes','banco','dados'}
    analysis['pontos_fracos'] = [p for p in analysis['pontos_fracos']
                                 if not any(k in p.lower() for k in dev_kw)]

# Filtro erros comuns
en = _n(extracted)
vc = []
for err in analysis['erros_comuns_detectados']:
    desc = err.get('descricao', '')
    expl = err.get('exemplo', '')
    if expl and _n(expl) not in en: continue
    if 'ç' in (expl or ''): continue
    if 'mai ' in desc.lower() or 'capitaliz' in desc.lower(): continue
    vc.append(err)
analysis['erros_comuns_detectados'] = vc

print("Erros:", len(analysis['erros_ortograficos']), '(exp 1)')
assert len(analysis['erros_ortograficos']) == 1 and analysis['erros_ortograficos'][0]['palavra'] == 'exelente'
print("Ordem:", analysis['ordem_secoes']['correta'], '(exp True)')
assert analysis['ordem_secoes']['correta'] == True
print("Keywords:", analysis['palavras_chave_faltantes'], '(exp [])')
assert analysis['palavras_chave_faltantes'] == []
print("Pontos fracos:", analysis['pontos_fracos'])
assert len(analysis['pontos_fracos']) == 1
print("Erros comuns:", len(analysis['erros_comuns_detectados']), '(exp 1)')
assert len(analysis['erros_comuns_detectados']) == 1
print("PASS")
