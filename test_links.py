import requests, json, os, pymupdf

# Check PDF links via PyMuPDF
print("=== PDF links via PyMuPDF ===")
for f in sorted(os.listdir('docs')):
    if f.endswith('.pdf'):
        try:
            doc = pymupdf.open(f'docs/{f}')
            count = 0
            for page in doc:
                for link in page.get_links():
                    count += 1
            doc.close()
            print(f'  {f}: {count} embedded links')
        except Exception as e:
            print(f'  {f}: error {e}')

# Check what the API returns for links
print("\n=== API _links response ===")
for f in sorted(os.listdir('docs')):
    if f.endswith('.pdf'):
        try:
            r = requests.post('http://localhost:8000/api/cv/analyze', files={'cv_file': open(f'docs/{f}', 'rb')})
            d = r.json()
            links = d.get('_links', [])
            print(f'  {f}: {len(links)} links detected - {links[:3]}')
        except Exception as e:
            print(f'  {f}: error {e}')
