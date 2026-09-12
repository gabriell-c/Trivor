import requests
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"Backend: {r.status_code}")
except Exception as e:
    print(f"Backend error: {e}")
