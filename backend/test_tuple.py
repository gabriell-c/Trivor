"""Test tuple structure - standalone."""
import re

# Simulating _pre_filter_jobs behavior
def test():
    score = 5
    job_id = 'id1'
    title = 'assistente administrativo'
    company = 'company'
    description = 'descricao vaga assistente'
    loc = 'sao paulo'
    mod = 'remoto'
    source = 'src'
    source_url = 'url'
    job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"

    t = (score, job_id, title, company, description, loc, mod, source, source_url, job_text)
    print(f'Tuple length: {len(t)}')
    print(f'Elements: {list(range(len(t)))}')

    # Try unpacking as 9 elements (current code)
    try:
        job_id2, title2, company2, description2, loc2, mod2, source2, source_url2, job_text2 = t
        print('9-unpack: OK')
    except ValueError as e:
        print(f'9-unpack: FAILED - {e}')

    # Try unpacking as 10 elements
    try:
        sc, job_id2, title2, company2, description2, loc2, mod2, source2, source_url2, job_text2 = t
        print(f'10-unpack: OK, job_text starts with: {job_text2[:40]}')
    except ValueError as e:
        print(f'10-unpack: FAILED - {e}')

if __name__ == '__main__':
    test()
