import urllib.request, urllib.parse, json

API = "http://localhost:8000"

def post(path, data):
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{API}{path}", data=encoded)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

# Testar cadastro de uma chave nova
print("=== Testando cadastro de chave nova ===")
result = post("/api/jsearch/save-key", {
    "api_key": "ak_test_key_123",
    "description": "test key"
})
print(f"Cadastro: {result}")

# Verificar status do backend
health = json.loads(urllib.request.urlopen(f"{API}/health", timeout=5).read())
print(f"Backend: {health['status']}")

# Listar todas as chaves
keys = post("/api/jsearch/keys", {})
print(f"\nTotal keys no DB: {len(keys['keys'])}")
for k in keys["keys"]:
    print(f"  [{k['id']}] {k['api_key'][:35]}... status={k['status']}")
