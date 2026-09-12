"""Check JSearch rate limit headers."""
import urllib.request
import urllib.parse
import json

keys = [
    "ak_5ptli4fp16hlffsrv7mxqgmv7atry4g67sn0uj1ghdg7jom",
    "ak_y05reahqfectpm7959dp9kj1a2n0sz3atu1qbrw5yt17y5g",
    "ak_yqhvsksd061yhjtafzi0l4k4t134mnpz2slwvm45pkpwq0k",
    "ak_w50lspzm38pmj2zdz8v9phbuvai1a1h0df1u0qh1gmx753p",
    "ak_a8plc0spoptyh0o0ug3d4qjrwpxa05gl0qmnsfadpoq2x2r",
    "ak_aaijzj1qg9l0165qb3achtc6gd44nuegre9jcp0wbzu2fim",
]

query = urllib.parse.quote_plus("Assistente Administrativo Brasil")
url = f"https://api.openwebninja.com/jsearch/search-v2?query={query}&country=br&language=pt&num_pages=1&date_posted=all"

for i, key in enumerate(keys):
    print(f"\n--- Key {i+1} ({key[:12]}...) ---")
    req = urllib.request.Request(url, headers={
        "X-API-Key": key,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = dict(resp.headers)
            remaining = headers.get("x-ratelimit-remaining", "?")
            reset = headers.get("x-ratelimit-reset", "?")
            limit = headers.get("x-ratelimit-limit", "?")
            print(f"  remaining: {remaining}/{limit}, reset: {reset}")
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "OK":
            jobs = data.get("data", {}).get("jobs", [])
            print(f"  OK: {len(jobs)} vagas")
        else:
            print(f"  status={data.get('status')}: {json.dumps(data)[:150]}")
    except urllib.error.HTTPError as e:
        headers = dict(e.headers) if e.headers else {}
        remaining = headers.get("x-ratelimit-remaining", "?")
        reset = headers.get("x-ratelimit-reset", "?")
        limit = headers.get("x-ratelimit-limit", "?")
        print(f"  HTTP {e.code}: remaining={remaining}/{limit} reset={reset}")
        body = e.read().decode()[:200]
        print(f"  body: {body}")
    except Exception as e:
        print(f"  Error: {e}")
