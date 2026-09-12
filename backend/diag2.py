import sys
import os

out = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\diag2.txt'

lines = []
lines.append(f"Python: {sys.executable}")
lines.append(f"CWD: {os.getcwd()}")
lines.append(f"Path: {sys.path}")
lines.append("---")

mods = ['docling', 'pypdfium2', 'export_utils', 'market_export', 'logging_service', 'uvicorn', 'fastapi', 'openai', 'main']
for m in mods:
    try:
        mod = __import__(m)
        lines.append(f"OK: {m}")
    except Exception as e:
        lines.append(f"FAIL {m}: {e}")

try:
    import main
    lines.append(f"main.app: {type(main.app)}")
    lines.append("SUCCESS: main imported")
except Exception as e:
    lines.append(f"FAIL main: {e}")
    import traceback
    lines.append(traceback.format_exc())

with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
