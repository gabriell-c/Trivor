"""
Testes do runner do Job Hunter (backend/apply_runner.py) — Nível 3.

Simula um "bot" com um script fake (printa e dorme) num APPLY_DIR
temporário: ciclo de vida completo (start → rodando → log → 409 → kill →
parado) e bot desconhecido. Nenhum bot real é executado.
"""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

import apply_runner as ar  # noqa: E402

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
        assert any('oi da automacao' in l for l in st['log_tail']), st['log_tail']

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
