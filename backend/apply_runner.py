"""Executor dos bots do Job Hunter — Nível 3: a UI dispara a execução.

Cada bot roda como processo Python separado (mesmo venv do backend, cwd =
diretório do apply) com log em apply/relatorio/runs/<bot>.log e um pidfile
no mesmo lugar. Um processo por bot de cada vez (409 se já estiver rodando).

Os bots usam navegador NÃO-headless (login manual + turnstile), então a
execução só faz sentido na máquina do dono dos credenciais — por isso o
runner não vai para deploy remoto, apenas roda onde o Trivor roda.
"""
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from apply_service import resolve_apply_dir

# Nome da UI → script do bot (mesmo diretório, um por portal)
APPLY_BOTS = {
    'gupy': 'gupy.py',
    'infojobs': 'infojobs.py',
    'nerdin': 'nerdin.py',
    'indeed': 'indeed.py',
    'solides': 'solides.py',
}

LOG_TAIL_LINES = 12


def _runs_dir() -> Path:
    d = Path(resolve_apply_dir() or '') / 'relatorio' / 'runs'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pidfile(bot: str) -> Path:
    return _runs_dir() / f'{bot}.json'


def _logfile(bot: str) -> Path:
    return _runs_dir() / f'{bot}.log'


def is_process_alive(pid: int) -> bool:
    """Checa se `pid` ainda está vivo.

    Windows: os.kill(pid, 0) engana — um PID recém-matado (zumbi não
    colhido) ou reutilizado por outro processo devolve PermissionError,
    que 'rodando'. Então usa OpenProcess + GetExitCodeProcess: só
    STILL_RUNNING (259) conta como vivo. Posix: kill 0 direto."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION (0x0400)
            h = kernel.OpenProcess(0x0400, False, pid)
            if not h:
                # GetLastError 5 (acesso negado) = processo existe, dono outro
                return kernel.GetLastError() == 5
            code = ctypes.wintypes.DWORD()
            kernel.GetExitCodeProcess(h, ctypes.byref(code))
            kernel.CloseHandle(h)
            return code.value == 259  # STILL_RUNNING
        except Exception:
            return True  # sem vereditivo → mantém 'rodando' (próximo poll resolve)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # processo existe mas de outro dono
    except OSError:
        return False


def _read_pidfile(bot: str) -> dict | None:
    p = _pidfile(bot)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def bot_status(bot: str) -> dict:
    """Estado atual de um bot: rodando? pid? início? últimas linhas do log?"""
    info = _read_pidfile(bot)
    running = bool(info and is_process_alive(int(info['pid'])))
    tail = []
    lf = _logfile(bot)
    if lf.is_file():
        try:
            lines = lf.read_text(encoding='utf-8', errors='replace').splitlines()
            tail = [ln for ln in lines[-LOG_TAIL_LINES:] if ln.strip()][-LOG_TAIL_LINES:]
        except OSError:
            pass
    return {
        'bot': bot,
        'running': running,
        'pid': int(info['pid']) if info and running else None,
        'started_at': info.get('started_at') if info else None,
        'log_tail': tail,
    }


def list_bots() -> dict:
    """Todos os bots em uma chamada (a UI faz poll em /api/apply/runs)."""
    return {name: bot_status(name) for name in APPLY_BOTS}


def ler_log(bot: str, origem: str = 'execucao', lines: int = 200) -> dict:
    """Últimas `lines` linhas úteis do log de `origem`:
    'execucao' → <bot>.log | 'login' → <bot>-login.log. Sem arquivo →
    linhas vazias. `total` conta as linhas devolvidas (após o corte)."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    arq = _login_logfile(bot) if origem == 'login' else _logfile(bot)
    out = []
    if arq.is_file():
        out = [ln for ln in arq.read_text(encoding='utf-8', errors='replace').splitlines()
               if ln.strip()][-lines:]
    return {'bot': bot, 'origem': origem, 'lines': out, 'total': len(out)}


def bot_log(bot: str, lines: int = 200) -> dict:
    """Últimas `lines` linhas úteis do log de EXECUÇÃO (rota /api/apply/log
    mantém o escopo de sempre; o painel da aba Executar escolhe a origem)."""
    return ler_log(bot, 'execucao', lines)


def origem_log_ativa(bot: str, estado_login: dict) -> str:
    """Qual log o painel "em tempo real" deve exibir para o bot:
    - login 'aguardando' → o log de LOGIN (ele é o vivo — a run completa
      não roda em paralelo, o mesmo bot está bloqueado);
    - senão, o arquivo MAIS RECENTE entre execução e login — a atividade
      mais nova é a relevante (ex.: depois de um login concluído, o log
      antigo de execução não agrega nada)."""
    if estado_login.get('estado') == 'aguardando':
        return 'login'
    arq_exec, arq_login = _logfile(bot), _login_logfile(bot)
    tem_exec, tem_login = arq_exec.is_file(), arq_login.is_file()
    if not (tem_exec or tem_login):
        return 'execucao'
    if tem_exec != tem_login:
        return 'login' if tem_login else 'execucao'
    return 'login' if arq_login.stat().st_mtime >= arq_exec.stat().st_mtime else 'execucao'


class ApplyRunError(Exception):
    """Erro de execução — a rota vira 4xx com a mensagem."""


def start_bot(bot: str) -> dict:
    """Sobe o bot em background; 409/400/404 viram ApplyRunError."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    apply_dir = resolve_apply_dir()
    if apply_dir is None:
        raise ApplyRunError("Projeto apply não encontrado. Defina APPLY_DIR no .env.")
    if bot_status(bot)['running']:
        raise ApplyRunError(f"Bot {bot} já está em execução.")

    script = apply_dir / APPLY_BOTS[bot]
    if not script.is_file():
        raise ApplyRunError(f"Script {APPLY_BOTS[bot]} não existe no apply.")

    # PYTHONIOENCODING: o bot grava emoji nos logs — sem isso, o redirect
    # de stdout para o arquivo quebra em Windows (locale cp1252).
    # PYTHONUNBUFFERED: sem isso, o print do bot fica no buffer (bloqueio de
    # 4KB quando stdout é arquivo) e a UI não veria o log crescer.
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    # O bloco with fecha o handle do pai após o Popen — o processo mantém
    # o próprio, então nada de handle aberto vazando pro FastAPI.
    with open(_logfile(bot), 'a', encoding='utf-8') as log_f:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(apply_dir),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    now = datetime.now().isoformat(timespec='seconds')
    _pidfile(bot).write_text(
        json.dumps({'pid': proc.pid, 'started_at': now, 'script': APPLY_BOTS[bot]}),
        encoding='utf-8',
    )
    return {'bot': bot, 'pid': proc.pid, 'started_at': now, 'log': str(_logfile(bot))}


STOP_GRACE_SECONDS = 3

# ── Login só (botão "Logar" da UI) ────────────────────────────────────────
# O bot roda com TRIVOR_LOGIN_ONLY=1: garante a sessão e encerra (exit 0),
# ou falha (exit 1). Pidfile/log separados (<bot>-login.*) para não colidir
# com uma execução completa do mesmo bot.

# Quatro bots compartilham a porta CDP 9333 (gupy, infojobs, nerdin,
# solides) — login de um enquanto outro usa a porta é colisão de browser.
# Indeed escolhe a própria porta (UC) e fica de fora da fila.
BOTS_POR_9333 = ('gupy', 'infojobs', 'nerdin', 'solides')

_LOGIN_PROCS: dict[str, subprocess.Popen] = {}


def _login_pidfile(bot: str) -> Path:
    return _runs_dir() / f'{bot}-login.json'


def _login_logfile(bot: str) -> Path:
    return _runs_dir() / f'{bot}-login.log'


def _read_login_pidfile(bot: str) -> dict | None:
    p = _login_pidfile(bot)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def start_login(bot: str) -> dict:
    """Sobe a execução de login-só em background; erros viram ApplyRunError
    (rota vira 409/400). stdin em DEVNULL: o bot não pode travar em input()."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    apply_dir = resolve_apply_dir()
    if apply_dir is None:
        raise ApplyRunError("Projeto apply não encontrado. Defina APPLY_DIR no .env.")
    if bot_status(bot)['running']:
        raise ApplyRunError(f"Bot {bot} já está em execução (run completa) — pare antes.")
    if login_status(bot)['estado'] == 'aguardando':
        raise ApplyRunError(f"Login de {bot} já está em andamento.")

    if bot in BOTS_POR_9333:
        ocupantes = [
            b for b in BOTS_POR_9333
            if b != bot and (bot_status(b)['running'] or login_status(b)['estado'] == 'aguardando')
        ]
        if ocupantes:
            raise ApplyRunError(
                f"Porta CDP 9333 em uso por {', '.join(ocupantes)} — aguarde terminar.")

    script = apply_dir / APPLY_BOTS[bot]
    if not script.is_file():
        raise ApplyRunError(f"Script {APPLY_BOTS[bot]} não existe no apply.")

    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
               TRIVOR_LOGIN_ONLY='1', TRIVOR_LOGIN_POLL='1')
    # TRIVOR_LOGIN_POLL: login-só nunca tem TTY — quando o login precisa de
    # humano (Google do Indeed, sign-in do Sólides), o bot POLA a janela
    # aberta em vez de travar em input().
    with open(_login_logfile(bot), 'a', encoding='utf-8') as log_f:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(apply_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    _LOGIN_PROCS[bot] = proc
    now = datetime.now().isoformat(timespec='seconds')
    _login_pidfile(bot).write_text(
        json.dumps({'pid': proc.pid, 'started_at': now, 'script': APPLY_BOTS[bot]}),
        encoding='utf-8',
    )
    return {'bot': bot, 'pid': proc.pid, 'started_at': now,
            'log': str(_login_logfile(bot))}


def login_status(bot: str) -> dict:
    """estado: aguardando (proc vivo) | concluido (exit 0) | falhou (exit ≠ 0)
    | indeterminado (backend reiniciou no meio) | inativo (nada em andamento).

    O veredito exato só existe enquanto o proc vive em memória — se o
    backend reiniciou, o pidfile reconstrói só o "aguardando"; morto sem
    veredito vira 'indeterminado' (a UI volta a mostrar o botão)."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    proc = _LOGIN_PROCS.get(bot)
    if proc is not None:
        code = proc.poll()
        if code is None:
            return {'bot': bot, 'estado': 'aguardando', 'pid': proc.pid}
        del _LOGIN_PROCS[bot]
        # Persiste o veredito no pidfile: 'indeterminado' fica restrito a
        # processo morto SEM saída registrada (backend reiniciou no meio).
        info = _read_login_pidfile(bot) or {}
        info['exit_code'] = code
        _login_pidfile(bot).write_text(
            json.dumps(info, ensure_ascii=False), encoding='utf-8')
        return {'bot': bot, 'estado': 'concluido' if code == 0 else 'falhou',
                'exit_code': code}
    info = _read_login_pidfile(bot)
    if info is None:
        return {'bot': bot, 'estado': 'inativo'}
    if 'exit_code' in info:
        code = int(info['exit_code'])
        return {'bot': bot, 'estado': 'concluido' if code == 0 else 'falhou',
                'exit_code': code}
    if is_process_alive(int(info['pid'])):
        return {'bot': bot, 'estado': 'aguardando', 'pid': int(info['pid']),
                'reconstruido': True}
    return {'bot': bot, 'estado': 'indeterminado'}


def stop_login(bot: str) -> dict:
    """Para um login-só em andamento (mesma regra do stop_bot: SIGTERM no
    PID específico, nunca matar processo global)."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    st = login_status(bot)
    if st['estado'] != 'aguardando':
        raise ApplyRunError(f"Não há login em andamento para {bot}.")
    pid = int(st['pid'])
    _LOGIN_PROCS.pop(bot, None)
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    while time.monotonic() < deadline and is_process_alive(pid):
        time.sleep(0.2)
    forca = is_process_alive(pid)
    if forca:
        os.kill(pid, signal.SIGTERM)
    _login_pidfile(bot).unlink(missing_ok=True)
    return {'bot': bot, 'pid': pid, 'stopped': not forca, 'forca': forca}


def stop_bot(bot: str) -> dict:
    """Para o bot com SIGTERM (= TerminateProcess no Windows) no PID
    específico — nunca matar processos globalmente por nome.

    Por que não CTRL_BREAK (a alternativa 'graciosa' que deixaria o bot
    rodar o finally e fechar o navegador)? No Windows, os.kill com evento
    de console chama GenerateConsoleCtrlEvent, que vaza pelo console
    compartilhado — num ambiente de teste em sandbox ele derrubou o próprio
    pytest. TerminateProcess é imediato e cirúrgico: o navegador morre junto
    com o processo, o que é o comportamento esperado ao 'parar' uma
    automação. Quem quer encerramento limpo fecha o navegador pela UI do
    bot (cada um tem sua janela)."""
    if bot not in APPLY_BOTS:
        raise ApplyRunError(f"Bot desconhecido '{bot}'. Use: {', '.join(APPLY_BOTS)}.")
    st = bot_status(bot)
    if not st['running']:
        raise ApplyRunError(f"Bot {bot} não está em execução.")
    pid = int(st['pid'])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    while time.monotonic() < deadline and is_process_alive(pid):
        time.sleep(0.2)
    forca = is_process_alive(pid)
    if forca:
        os.kill(pid, signal.SIGTERM)
    return {'bot': bot, 'pid': pid, 'stopped': not forca, 'forca': forca}
