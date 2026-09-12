"""Check JSearch rate limit headers in detail."""
import urllib.request
import urllib.parse
import json

key = "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom"
query = urllib.parse.quote_plus("Assistente Administrativo Brasil")
url = f"https://api.openwebninja.com/jsearch/search-v2?query={query}&country=br&language=pt&num_pages=1&date_posted=all"

req = urllib.request.Request(url, headers={
    "X-API-Key": key,
    "Accept": "application/json",
})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print("Status: OK")
        for k, v in resp.headers.items():
            print(f"  {k}: {v}")
except urllib.error.HTTPError as e:
    print(f"Status: {e.code}")
    for k, v in e.headers.items():
        print(f"  {k}: {v}")
    body = e.read().decode()
    print(f"Body: {body[:300]}")
