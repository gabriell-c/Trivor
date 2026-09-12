"""Quick test: how many jobs per page for admin search."""
import urllib.request, urllib.parse, json

key = "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom"
for pages in [2, 4, 6, 8, 10]:
    query = urllib.parse.quote_plus("Assistente Administrativo remoto nacional Brasil")
    url = f"https://api.openwebninja.com/jsearch/search-v2?query={query}&country=br&language=pt&num_pages={pages}&date_posted=all"
    req = urllib.request.Request(url, headers={"X-API-Key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        jobs = data.get("data", {}).get("jobs", [])
        print(f"  num_pages={pages} → {len(jobs)} jobs")
    except Exception as e:
        print(f"  num_pages={pages} → ERROR: {e}")
