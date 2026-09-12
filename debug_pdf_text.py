import pymupdf, sys, os

base = os.path.dirname(os.path.abspath(__file__))
for fname in ['Curriculo Gabriel Cardoso.pdf', 'Currículo Milena Cardoso.pdf']:
    path = os.path.join(base, 'docs', fname)
    doc = pymupdf.open(path)
    print(f'\n=== {fname} ===')
    print(f'Pages: {len(doc)}')
    for i, page in enumerate(doc):
        links = page.get_links()
        print(f'Page {i+1}: {len(links)} embedded links')
        for l in links:
            print(f'  {l}')
        text = page.get_text()
        # Check for URLs in text
        import re
        urls = re.findall(r'https?://[^\s<>\)]+', text)
        www = re.findall(r'www\.[^\s<>\)]+', text)
        emails = re.findall(r'[\w.-]+@[\w.-]+\.\w+', text)
        print(f'  Text URLs: {urls}')
        print(f'  Text www:  {www}')
        print(f'  Emails:    {emails}')
    doc.close()
