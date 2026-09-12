import sys
sys.path.insert(0, '.')

log_file = r'C:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\server_log.txt'

def log(msg):
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
        f.flush()

try:
    log("Step 1: importing uvicorn")
    import uvicorn
    log(f"uvicorn {uvicorn.__version__} OK")

    log("Step 2: importing main")
    import main
    log(f"app type: {type(main.app)} OK")

    log("Step 3: starting server on port 8000")
    uvicorn.run(main.app, host="127.0.0.1", port=8000, reload=False, log_level="info")
    log("Server stopped")
except Exception as e:
    log(f"ERROR: {e}")
    import traceback
    log(traceback.format_exc())
    sys.exit(1)
