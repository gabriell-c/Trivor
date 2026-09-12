"""Simple health check."""
import urllib.request
try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=3)
    print("OK")
except Exception as e:
    print(f"FAIL: {e}")
