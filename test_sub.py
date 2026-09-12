import unicodedata
def _n(s):
    return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode('ascii')

# Test substring matching
pf = 'Faltam linguagens'
kw = 'linguagem'
print(f'{kw!r} in {pf.lower()!r} = {kw in pf.lower()}')

# Test the full filter
dev_kw = {'linguagem','framework','tech','sql','python','java','react','dev',
          'desenvolvimento','programacao','codigo','software','frontend','backend',
          'git','aws','docker','kubernetes','banco','dados'}
pontos = ['Faltam linguagens', 'Precisa melhorar comunicacao']
result = [p for p in pontos if not any(k in p.lower() for k in dev_kw)]
print(f'Result: {result}')
