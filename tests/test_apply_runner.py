"""
Testes do runner do Job Hunter (backend/apply_runner.py) — Nível 3.

Simula um "bot" com um script fake (printa e dorme) num APPLY_DIR
temporário: ciclo de vida completo (start → rodando → log → 409 → kill →
parado) e bot desconhecido. Nenhum bot real é executado.
"""
import json
import os
import signal
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

import apply_runner as ar

FAKE_BOT = """import time
print('oi da automacao')
time.sleep(120)
"""


@pytest.fixture
def fake_apply(tmp_path, monkeypatch):
    apply_dir = tmp_path / 'apply'
    (apply_dir / 'relatorio').mkdir(parents=True)
    # resolve_apply_dir só reconhece o apply se o contrato de dados existir
    (apply_dir / 'relatorio' / 'candidaturas.json').write_text(
        json.dumps({'candidaturas': [], 'ja_candidatado': []}), encoding='utf-8')
    (apply_dir / 'gupy.py').write_text(FAKE_BOT, encoding='utf-8')
    monkeypatch.setenv('APPLY_DIR', str(apply_dir))
    return apply_dir


def test_ciclo_de_vida_completo(fake_apply):
    info = ar.start_bot('gupy')
    pid = info['pid']
    try:
        # sobe de verdade (o fake dorme 2min); o print chega só depois do
        # startup do interpretador filho → poll curto no tail do log
        for _ in range(40):
            if ar.bot_status('gupy')['running']:
                break
            time.sleep(0.25)
        st = ar.bot_status('gupy')
        assert st['running'] is True
        assert st['pid'] == pid
        assert st['started_at']
        for _ in range(40):
            st = ar.bot_status('gupy')
            if st['log_tail']:
                break
            time.sleep(0.25)
        assert any('oi da automacao' in linha for linha in st['log_tail']), st['log_tail']

        # segundo start do mesmo bot → erro "já está em execução" (409 na rota)
        with pytest.raises(ar.ApplyRunError, match='já está em execução'):
            ar.start_bot('gupy')

        # list_bots devolve todos os 5, só o gupy rodando
        allb = ar.list_bots()
        assert set(allb) == set(ar.APPLY_BOTS)
        assert allb['gupy']['running'] and not allb['indeed']['running']
    finally:
        os.kill(pid, signal.SIGTERM)

    for _ in range(20):
        if not ar.bot_status('gupy')['running']:
            break
        time.sleep(0.25)
    assert ar.bot_status('gupy')['running'] is False
    assert ar.bot_status('gupy')['pid'] is None


def test_bot_desconhecido(fake_apply):
    with pytest.raises(ar.ApplyRunError, match='desconhecido'):
        ar.start_bot('xpto')


def test_script_ausente(fake_apply):
    with pytest.raises(ar.ApplyRunError, match='não existe'):
        ar.start_bot('indeed')  # não criei indeed.py no fake apply


def test_stop_bot(fake_apply):
    info = ar.start_bot('gupy')
    pid = info['pid']
    try:
        for _ in range(40):
            if ar.bot_status('gupy')['running']:
                break
            time.sleep(0.25)
        assert ar.bot_status('gupy')['running']
        r = ar.stop_bot('gupy')
        assert r['stopped'] is True and r['pid'] == pid
    finally:
        # cumpre o kill no caso do stop já ter terminado antes
        if ar.is_process_alive(pid):
            os.kill(pid, signal.SIGTERM)

    for _ in range(40):
        if not ar.is_process_alive(pid):
            break
        time.sleep(0.25)
    assert not ar.is_process_alive(pid)
    assert ar.bot_status('gupy')['running'] is False
    # parar de novo → 'não está em execução' (409 na rota)
    with pytest.raises(ar.ApplyRunError, match='não está em execução'):
        ar.stop_bot('gupy')
    with pytest.raises(ar.ApplyRunError, match='desconhecido'):
        ar.stop_bot('xpto')


def test_pidfile_legivel(fake_apply):
    ar.start_bot('gupy')
    time.sleep(1)
    pf = fake_apply / 'relatorio' / 'runs' / 'gupy.json'
    data = json.loads(pf.read_text(encoding='utf-8'))
    assert set(data) >= {'pid', 'started_at', 'script'}
    pid = data['pid']
    assert ar.is_process_alive(pid)
    os.kill(pid, signal.SIGTERM)
    time.sleep(0.5)
    assert not ar.is_process_alive(pid)


# ── Login-só (botão "Logar" da UI) ─────────────────────────────────────────

FAKE_BOT_OK = """import os, time
print('flag=', os.environ.get('TRIVOR_LOGIN_ONLY'))
print('poll=', os.environ.get('TRIVOR_LOGIN_POLL'))
time.sleep(3)
"""
FAKE_BOT_FAIL = "import sys\nprint('login faliu')\nsys.exit(1)\n"


def _esperar_login(bot, espera_s):
    """Dorme o suficiente pra o fake terminar e devolve o estado."""
    time.sleep(espera_s)
    return ar.login_status(bot)


def test_login_ciclo_completo(fake_apply):
    (fake_apply / 'gupy.py').write_text(FAKE_BOT_OK, encoding='utf-8')
    ar.start_login('gupy')
    assert ar.login_status('gupy')['estado'] == 'aguardando'
    try:
        # porta 9333 ocupada: outro bot do grupo fica bloqueado (409 na rota)
        with pytest.raises(ar.ApplyRunError, match='em uso'):
            ar.start_login('infojobs')
        st = _esperar_login('gupy', 4)
        assert st['estado'] == 'concluido' and st['exit_code'] == 0
        # o env TRIVOR_LOGIN_ONLY=1 chegou no subprocess
        log = (fake_apply / 'relatorio' / 'runs' / 'gupy-login.log').read_text()
        assert 'flag= 1' in log
        # TRIVOR_LOGIN_POLL: login-só nunca tem TTY — o bot precisa pola a
        # janela em vez de travar em input()
        assert 'poll= 1' in log
    finally:
        if ar.login_status('gupy')['estado'] == 'aguardando':
            ar.stop_login('gupy')


def test_login_falha_vira_estado(fake_apply):
    (fake_apply / 'gupy.py').write_text(FAKE_BOT_FAIL, encoding='utf-8')
    ar.start_login('gupy')
    st = _esperar_login('gupy', 4)
    assert st['estado'] == 'falhou' and st['exit_code'] == 1


def test_login_sem_pidfile_e_stop_vazio(fake_apply):
    assert ar.login_status('indeed')['estado'] == 'inativo'
    with pytest.raises(ar.ApplyRunError, match='Não há login'):
        ar.stop_login('indeed')
    with pytest.raises(ar.ApplyRunError, match='desconhecido'):
        ar.start_login('xpto')


def test_login_veredito_persiste_no_pidfile(fake_apply):
    """Após 'concluido', o veredito vem do pidfile (o proc em memória é
    descartado no primeiro poll) — os próximos polls não podem degradar
    para 'indeterminado': o cartão usa isso para manter a luz verde."""
    (fake_apply / 'gupy.py').write_text(FAKE_BOT_OK, encoding='utf-8')
    ar.start_login('gupy')
    st = _esperar_login('gupy', 4)
    assert st['estado'] == 'concluido'
    for _ in range(3):
        st = ar.login_status('gupy')
        assert st['estado'] == 'concluido'
        assert st.get('exit_code') == 0


def test_run_completa_bloqueia_login_do_mesmo_bot(fake_apply):
    """Run completa em execução impede login-só do MESMO bot (e do grupo da
    porta 9333) — 409 na rota; o usuário precisa parar a run antes."""
    (fake_apply / 'gupy.py').write_text(FAKE_BOT, encoding='utf-8')
    info = ar.start_bot('gupy')
    try:
        for _ in range(40):
            if ar.bot_status('gupy')['running']:
                break
            time.sleep(0.25)
        with pytest.raises(ar.ApplyRunError, match='pare antes'):
            ar.start_login('gupy')
        with pytest.raises(ar.ApplyRunError, match='em uso'):
            ar.start_login('infojobs')
    finally:
        if ar.is_process_alive(info['pid']):
            os.kill(info['pid'], signal.SIGTERM)


# ── Logs do painel (ler_log / origem_log_ativa) ───────────────────────────
# O endpoint /api/apply/state devolve o log da ORIGEM mais relevante; estes
# testes cobrem as regras de escolha (o endpoint em si é 1 chamada fina).

def _runs(fake_apply):
    d = fake_apply / 'relatorio' / 'runs'
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_ler_log_por_origem(fake_apply):
    runs = _runs(fake_apply)
    (runs / 'gupy.log').write_text('linha exec 1\n\nlinha exec 2\n', encoding='utf-8')
    (runs / 'gupy-login.log').write_text('linha login 1\nlinha login 2\n', encoding='utf-8')
    exec_ = ar.ler_log('gupy', 'execucao', 100)
    login = ar.ler_log('gupy', 'login', 100)
    assert exec_['lines'] == ['linha exec 1', 'linha exec 2']
    assert login['lines'] == ['linha login 1', 'linha login 2']
    assert login['origem'] == 'login'
    # bot_log (rota /api/apply/log) continua lendo só a execução
    assert ar.bot_log('gupy', 100)['lines'] == ['linha exec 1', 'linha exec 2']


def test_ler_log_corta_para_lines_e_sem_arquivo_vazio(fake_apply):
    runs = _runs(fake_apply)
    (runs / 'gupy.log').write_text('\n'.join(f'linha {i}' for i in range(50)), encoding='utf-8')
    r = ar.ler_log('gupy', 'execucao', 5)
    assert r['lines'] == [f'linha {i}' for i in range(45, 50)]
    assert r['total'] == 5
    assert ar.ler_log('indeed', 'execucao', 10)['lines'] == []
    with pytest.raises(ar.ApplyRunError, match='desconhecido'):
        ar.ler_log('xpto')


def test_origem_aguardando_sempre_login(fake_apply):
    runs = _runs(fake_apply)
    (runs / 'gupy.log').write_text('exec', encoding='utf-8')
    (runs / 'gupy-login.log').write_text('login', encoding='utf-8')
    assert ar.origem_log_ativa('gupy', {'estado': 'aguardando'}) == 'login'


def test_origem_ganha_o_mais_recente_por_mtime(fake_apply):
    runs = _runs(fake_apply)
    (runs / 'gupy.log').write_text('exec', encoding='utf-8')
    (runs / 'gupy-login.log').write_text('login', encoding='utf-8')
    agora = time.time()
    os.utime(runs / 'gupy.log', (agora, agora))
    assert ar.origem_log_ativa('gupy', {'estado': 'concluido'}) == 'execucao'
    os.utime(runs / 'gupy-login.log', (agora + 10, agora + 10))
    assert ar.origem_log_ativa('gupy', {'estado': 'concluido'}) == 'login'


def test_origem_somente_um_logou_quem_existe(fake_apply):
    runs = _runs(fake_apply)
    (runs / 'gupy-login.log').write_text('login', encoding='utf-8')
    assert ar.origem_log_ativa('gupy', {'estado': 'inativo'}) == 'login'
    # nada no disco → origem padrão 'execucao' (linhas vazias)
    (runs / 'gupy-login.log').unlink()
    assert ar.origem_log_ativa('gupy', {'estado': 'inativo'}) == 'execucao'
