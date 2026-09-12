import urllib.request, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

url = 'http://localhost:8000/api/cv/analyze'
base = r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs'

pdf = os.path.join(base, 'Curriculo Gabriel Cardoso.pdf')
with open(pdf, 'rb') as f:
    fc = f.read()
body = (f'------TB\r\nContent-Disposition: form-data; name="cv_file"; filename="test.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode() + fc + b'\r\n------TB--\r\n'
req = urllib.request.Request(url, data=body, method='POST')
req.add_header('Content-Type', 'multipart/form-data; boundary=----TB')
resp = urllib.request.urlopen(req, timeout=90)
r = json.loads(resp.read())

print(json.dumps(r, ensure_ascii=False, indent=2))
