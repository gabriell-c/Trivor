import requests
import json
import os
import sys
from pathlib import Path

# 1. Testar se o servidor está rodando
try:
    print('--- Teste 1: Conectividade Servidor ---')
    r = requests.get('http://localhost:8000/openapi.json')
    assert r.status_code == 200
    print('OK: Backend Online')
except Exception as e:
    print(f'ERRO: Backend offline ou indisponível: {e}')

# 2. Testar se a pasta de dados existe e o BD é criado
print('\n--- Teste 2: Integridade de Dados ---')
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(base_dir, 'data')
if not os.path.exists(data_dir):
    print('ERRO: Pasta data ausente')
else:
    print('OK: Pasta data encontrada')

# 3. Testar a estrutura necessária dos arquivos
print('\n--- Teste 3: Arquivos críticos ---')
req_files = [
    os.path.join(base_dir, 'backend', 'main.py'),
    os.path.join(base_dir, 'frontend', 'app', 'layout.tsx'),
    os.path.join(base_dir, 'knowledge', 'system_prompt.md')
]
for f in req_files:
    if os.path.exists(f):
        print(f'OK: {f} encontrado')
    else:
        print(f'ERRO: {f} inexistente')

# 4. Simulação de requisição (sem envio de arquivo)
print('\n--- Teste 4: API Endpoint (Pre-flight simulado) ---')
try:
    r = requests.post('http://localhost:8000/api/analyze', files={'file': ('test.pdf', b'%PDF')}, headers={'api_key': 'teste'})
    print(f'Resposta da API: {r.status_code} - {r.text[:50]}...')
except Exception as e:
    print(f'ERRO: Falha na requisição: {e}')