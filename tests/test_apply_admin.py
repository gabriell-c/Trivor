"""
Testes do admin do Job Hunter (backend/apply_admin.py) — Nível 3.

APPLY_DIR fake em tmp: round-trip do config.yaml, CRUD de provedores de IA
(chaves sempre mascaradas pra fora), teste de conexão "pong" contra um
servidor HTTP fake (OpenAI-compatível e Anthropic) e upload/exclusão de
currículos. Nenhum provedor real é chamado.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

import apply_admin as ad


@pytest.fixture
def fake_apply(tmp_path, monkeypatch):
    apply_dir = tmp_path / 'apply'
    (apply_dir / 'relatorio').mkdir(parents=True)
    (apply_dir / 'relatorio' / 'candidaturas.json').write_text(
        json.dumps({'candidaturas': [], 'ja_candidatado': []}), encoding='utf-8')
    # ia_test importa apply/common/llm.py direto do arquivo — espelha o real
    llm_real = os.path.join(ROOT, 'apply', 'common', 'llm.py')
    (apply_dir / 'common').mkdir()
    with open(llm_real, encoding='utf-8') as f:
        (apply_dir / 'common' / 'llm.py').write_text(f.read(), encoding='utf-8')
    perfil_real = os.path.join(ROOT, 'apply', 'common', 'perfil.py')
    with open(perfil_real, encoding='utf-8') as f:
        (apply_dir / 'common' / 'perfil.py').write_text(f.read(), encoding='utf-8')
    monkeypatch.setenv('APPLY_DIR', str(apply_dir))
    return apply_dir


# ── config ───────────────────────────────────────────────────────────────────

def test_config_roundtrip(fake_apply):
    assert ad.load_config() == {}  # ainda não existe
    cfg = {'candidato': {'nome': 'Gabriel'}, 'busca': {'palavras_excluir': ['sênior']}}
    ad.save_config(cfg)
    assert ad.load_config() == cfg
    assert (fake_apply / 'config.yaml').is_file()
    assert not (fake_apply / 'config.yaml.tmp').exists()  # escrita atômica


def test_save_config_rejeita_nao_dict(fake_apply):
    with pytest.raises(ad.ApplyAdminError):
        ad.save_config(['lista'])


def test_perfil_contexto_secoes_e_senhas(fake_apply):
    """O bloco que a IA dos bots enxerga: config + documentos do .env entram,
    senhas NUNCA entram."""
    cfg = {'candidato': {'nome': 'Ana', 'sobre': 'dev júnior'},
           'busca': {'palavras_excluir': ['java']}}
    ad.save_config(cfg)
    (fake_apply / '.env').write_text(
        'CANDIDATO_CPF="11122233344"\nGUPY_SENHA="segredo"\n', encoding='utf-8')
    out = ad.perfil_contexto()
    texto = out['texto']
    assert 'Ana' in texto
    assert 'dev júnior' in texto          # campo novo (sobre) entra no contexto
    assert 'LISTA DE EXCLUSÕES' in texto
    assert 'java' in texto
    assert '11122233344' in texto          # documento do .env entra
    assert 'segredo' not in texto          # senha nunca entra


# ── IA ───────────────────────────────────────────────────────────────────────

def _novo_provedor(**over):
    p = {
        'nome': 'Groq', 'tipo': 'openai', 'base_url': 'https://api.groq.com/openai/v1',
        'api_key': 'gsk_abcdefghijklmnop', 'modelo': 'llama-3.3-70b-versatile',
        'temperatura': 0.4, 'max_tokens': 500,
    }
    p.update(over)
    return p


def test_ia_crud_e_mascara(fake_apply):
    # criar → vira ativo automaticamente; chave sai só mascarada
    prov = ad.ia_add(_novo_provedor())
    assert prov['id'] == 'groq'
    assert prov['api_key_masked'].startswith('gsk_')
    assert 'api_key' not in prov

    lst = ad.ia_list()
    assert lst['ativo'] == 'groq'
    assert lst['providers'][0]['api_key_masked'] != 'gsk_abcdefghijklmnop'  # nunca em claro

    # editar sem reenviar api_key → a salva é mantida
    ad.ia_update('groq', {'modelo': 'llama-3.1-8b-instant'})
    assert ad.load_config()['ia']['providers'][0]['api_key'] == 'gsk_abcdefghijklmnop'

    # ativar o outro / excluir o ativo
    ad.ia_add(_novo_provedor(nome='Claude', tipo='anthropic', id='claude',
                              base_url='', api_key='sk-ant-123456789'))
    assert ad.ia_list()['ativo'] == 'groq'  # ativo não muda sozinho
    ad.ia_set_active('claude')
    assert ad.ia_list()['ativo'] == 'claude'
    ad.ia_delete('claude')
    assert ad.ia_list()['ativo'] == 'groq'  # volta pro que sobrou


def test_ia_validacoes(fake_apply):
    with pytest.raises(ad.ApplyAdminError, match='modelo'):
        ad.ia_add({'nome': 'x', 'tipo': 'openai', 'base_url': 'http://x', 'api_key': 'k'})
    with pytest.raises(ad.ApplyAdminError, match='base_url'):
        ad.ia_add({'nome': 'x', 'tipo': 'openai', 'api_key': 'k', 'modelo': 'm'})
    with pytest.raises(ad.ApplyAdminError, match='api_key'):
        ad.ia_add({'nome': 'x', 'tipo': 'openai', 'base_url': 'http://x', 'modelo': 'm'})
    ad.ia_add(_novo_provedor())
    with pytest.raises(ad.ApplyAdminError, match='existe um provedor'):
        ad.ia_add(_novo_provedor(id='groq'))  # slug do nome 'Groq' já existe
    with pytest.raises(ad.ApplyAdminError, match='não encontrado'):
        ad.ia_update('inexistente', {'modelo': 'z'})


# ── pong (teste de conexão) ──────────────────────────────────────────────────

def _http_fake(responder):
    """Servidor local 127.0.0.1:porta; responder(caminho, headers) → (status, payload)."""
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            ln = int(self.headers.get('Content-Length', 0))
            self.rfile.read(ln)
            status, payload = responder(self.path, dict(self.headers))
            out = json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass  # silêncio nos testes

    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def _hget(headers: dict, nome: str):
    """headers vêm do http.server com caso de rede ("X-api-key"); procura
    case-insensitive."""
    for k, v in headers.items():
        if k.lower() == nome.lower():
            return v
    return None


def test_pong_openai(fake_apply):
    def responder(path, headers):
        # base_url do provider "openai" é a raiz /v1 (ex.: api.groq.com/openai/v1)
        assert path == '/chat/completions'
        if _hget(headers, 'Authorization') != 'Bearer k-ok':
            return 401, {'error': 'chave inválida'}
        return 200, {'choices': [{'message': {'content': 'pong'}}]}

    srv, base = _http_fake(responder)
    try:
        r = ad.ia_test({'tipo': 'openai', 'base_url': base, 'api_key': 'k-ok', 'modelo': 'm'})
        assert r['ok'] is True
        assert 'pong' in r['resposta']
        r = ad.ia_test({'tipo': 'openai', 'base_url': base, 'api_key': 'k-errada', 'modelo': 'm'})
        assert r['ok'] is False
        assert '401' in r['detalhe']
    finally:
        srv.shutdown()


def test_pong_anthropic(fake_apply):
    def responder(path, headers):
        assert path == '/v1/messages'
        assert _hget(headers, 'anthropic-version'), f'versão ausente: {list(headers)}'
        if _hget(headers, 'x-api-key') != 'sk-ok':
            return 401, {'type': 'error', 'message': 'chave inválida'}
        return 200, {'content': [{'text': 'pong'}]}

    srv, base = _http_fake(responder)
    try:
        r = ad.ia_test({'tipo': 'anthropic', 'base_url': base, 'api_key': 'sk-ok', 'modelo': 'claude-x'})
        assert r['ok'] is True and 'pong' in r['resposta']
    finally:
        srv.shutdown()


def test_pong_por_id_salvo(fake_apply):
    def responder(path, headers):
        return 200, {'choices': [{'message': {'content': 'pong'}}]}

    srv, base = _http_fake(responder)
    try:
        p = ad.ia_add(_novo_provedor(id='groq', base_url=base, api_key='gsk_1234'))
        assert p['id'] == 'groq'
        r = ad.ia_test({'id': 'groq'})  # sem chave no payload → usa a salva
        assert r['ok'] is True
    finally:
        srv.shutdown()


def test_ia_test_sem_modelo(fake_apply):
    with pytest.raises(ad.ApplyAdminError, match='modelo'):
        ad.ia_test({'tipo': 'openai', 'api_key': 'k'})


# ── currículos ───────────────────────────────────────────────────────────────

def test_resumes_upload_lista_edita_exclui(fake_apply):
    pdf = b'%PDF-1.4 fake'
    up = ad.resume_upload(pdf, 'curr.pdf', 'CV Backend', 'Python + FastAPI', 'backend_python')
    assert up['id'] == 'backend_python'

    lst = ad.resumes_list()['resumes']
    assert len(lst) == 1
    assert lst[0]['nome'] == 'CV Backend'
    assert lst[0]['existe'] is True
    assert (fake_apply / 'resumes' / 'backend_python.pdf').read_bytes() == pdf

    cfg = ad.load_config()
    assert cfg['resumes']['backend_python'] == 'resumes/backend_python.pdf'

    atualizado = ad.resume_update('backend_python', {'nome': 'CV Atualizado', 'descricao': 'x'})
    assert atualizado['nome'] == 'CV Atualizado'

    r = ad.resume_delete('backend_python')
    assert r['deleted'] == 'backend_python'
    assert ad.resumes_list()['resumes'] == []
    assert not (fake_apply / 'resumes' / 'backend_python.pdf').exists()
    assert 'backend_python' not in ad.load_config().get('resumes', {})


def test_resume_upload_validacoes(fake_apply):
    with pytest.raises(ad.ApplyAdminError, match='Formato'):
        ad.resume_upload(b'x', 'planilha.xlsx', 'n', '', 'geral')
    with pytest.raises(ad.ApplyAdminError, match='excede'):
        ad.resume_upload(b'0' * (5 * 1024 * 1024 + 1), 'grande.pdf', 'n', '', 'geral')
    with pytest.raises(ad.ApplyAdminError, match='não encontrado'):
        ad.resume_delete('inexistente')
    with pytest.raises(ad.ApplyAdminError, match='não encontrado'):
        ad.resume_update('inexistente', {'nome': 'n'})


# ── env (segredos dos bots em apply/.env) ─────────────────────────────────

def test_env_sem_arquivo_retorna_vazias(fake_apply):
    got = ad.load_env()
    assert set(got) == set(ad.APPLY_ENV_KEYS)
    assert all(v == '' for v in got.values())
    # .env não existe ainda — load não cria arquivo
    assert not (fake_apply / '.env').exists()


def test_env_roundtrip_preserva_linhas_alheias(fake_apply):
    p = fake_apply / '.env'
    p.write_text('GROQ_API_KEY=gsk_segredo_intocavel\nCANDIDATO_CPF=12345678909\n', encoding='utf-8')
    got = ad.load_env()
    assert got['CANDIDATO_CPF'] == '12345678909'
    ad.save_env({**got, 'CANDIDATO_CPF': '99988877766'})
    conteudo = p.read_text(encoding='utf-8')
    assert 'GROQ_API_KEY=gsk_segredo_intocavel' in conteudo  # linha alheia intocada
    assert '99988877766' in conteudo
    assert ad.load_env()['CANDIDATO_CPF'] == '99988877766'


def test_env_senha_mascarada_e_restaurada(fake_apply):
    p = fake_apply / '.env'
    p.write_text('GUPY_SENHA=minhasenha12345\n', encoding='utf-8')
    got = ad.load_env()
    mask = got['GUPY_SENHA']
    assert 'minhasenha' not in mask and mask
    # devolve o mask → backend mantém o valor real (a UI não redigita)
    ad.save_env(got)
    assert 'GUPY_SENHA="minhasenha12345"' in p.read_text(encoding='utf-8')
    # valor novo no mask → vira o valor
    got2 = ad.load_env()
    got2['GUPY_SENHA'] = 'nova-senha-99'
    ad.save_env(got2)
    assert 'nova-senha-99' in p.read_text(encoding='utf-8')


def test_env_valor_vazio_remove_chave(fake_apply):
    p = fake_apply / '.env'
    p.write_text('CANDIDATO_RG=ABC123\nCANDIDATO_CPF=1\n', encoding='utf-8')
    got = ad.load_env()
    got['CANDIDATO_RG'] = ''
    ad.save_env(got)
    conteudo = p.read_text(encoding='utf-8')
    assert 'CANDIDATO_RG' not in conteudo
    assert 'CANDIDATO_CPF' in conteudo


def test_env_chave_nao_liberada_rejeitada(fake_apply):
    got = ad.load_env()
    got['ARBITRARIA_KEY'] = 'x'
    with pytest.raises(ad.ApplyAdminError, match='não permitidas'):
        ad.save_env(got)
