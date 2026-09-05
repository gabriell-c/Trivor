@echo off
cd /d "c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend"
call venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8008
