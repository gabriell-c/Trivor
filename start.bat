REM Start usando o venv da raiz

REM Backend
cd backend
REM Usa o Python do venv da raiz — o python global não tem uvicorn em PC novo.
REM Se venv/ não existir: volte à raiz e rode `python -m venv venv` e
REM `venv\Scripts\pip install -r backend\requirements.txt`.
..\venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
REM Para expor na rede: set TRIVOR_ALLOW_LAN=1

REM Frontend em outra janela
cd frontend
npm run dev