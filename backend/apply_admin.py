"""Admin do apply (Job Hunter) — Nível 3: o painel do Trivor gerencia
config, provedores de IA, currículos e segredos do .env. O config.yaml e
o .env continuam sendo a fonte de verdade: os bots leem deles direto, o
backend apenas lê/grava.

Regras de segurança:
- api_key nunca sai do backend mascarada (4 primeiros + 4 últimos).
- escrita atômica do config.yaml (tmp + rename).
- upload de currículo: só extensões .pdf/.docx, tamanho limitado.
- .env: só as chaves de APPLY_ENV_KEYS podem ser lidas/gravadas pela UI;
  as demais linhas do arquivo (GROQ_API_KEY etc.) são preservadas tal
  como estão. Senhas saem mascaradas; PUT com o mask original mantém o
  valor (mesmo padrão de restauração da api_key de IA).
"""
import importlib.util
import re
from pathlib import Path

import yaml
from apply_service import resolve_apply_dir
from dotenv import dotenv_values


# ── Erros que as rotas convertem em 4xx ─────────────────────────────────────
class ApplyAdminError(Exception):
    """Erro de admin — mensagem vai direto pro usuário (nada sensível)."""


class ApplyNotFound(ApplyAdminError):
    """Diretório do apply não resolve — vira 404."""


def _apply_dir() -> Path:
    d = resolve_apply_dir()
    if d is None:
        raise ApplyNotFound("Projeto apply não encontrado. Defina APPLY_DIR no .env ou mova apply para ../apply.")
    return d


def _config_path() -> Path:
    return _apply_dir() / 'config.yaml'


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG (leitura/escrita atômica do config.yaml)
# ════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    p = _config_path()
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding='utf-8'))
    return data or {}


def save_config(cfg: dict) -> dict:
    """Grava config.yaml inteiro de forma atômica. Só dicts bem formados."""
    if not isinstance(cfg, dict):
        raise ApplyAdminError("Config inválida: esperado um objeto (dict).")
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.yaml.tmp')
    tmp.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding='utf-8')
    tmp.replace(p)
    return cfg



#  ENV — segredos dos bots (apply/.env)
# ════════════════════════════════════════════════════════════════════════

# Só o que os bots efetivamente leem — a UI não toca nas demais chaves
# do .env (GROQ_API_KEY, HF_API_KEY etc. continuam fora do alcance dela).
APPLY_ENV_KEYS = (
    # Documentos — Indeed/Gupy/Solides preenchem o formulário com isso
    'CANDIDATO_CPF', 'CANDIDATO_RG', 'CANDIDATO_CNH',
    # Filiação — os portais perguntam nome do pai/mãe
    'CANDIDATO_NOME_PAI', 'CANDIDATO_NOME_MAE',
    # Nacionalidade — perguntada nos formulários (Indeed/Gupy)
    'CANDIDATO_NACIONALIDADE',
    # Endereço — tem prioridade sobre o config.yaml nos bots
    'ENDERECO_LOGRADOURO', 'ENDERECO_NUMERO', 'ENDERECO_COMPLEMENTO',
    'ENDERECO_BAIRRO', 'ENDERECO_CEP', 'ENDERECO_CIDADE', 'ENDERECO_ESTADO',
    # Credenciais dos portais
    'GUPY_EMAIL', 'GUPY_SENHA',
    'INFOJOBS_EMAIL', 'INFOJOBS_SENHA',
    'NERDIN_EMAIL', 'NERDIN_SENHA',
    'SOLIDES_EMAIL', 'SOLIDES_SENHA',
)
_APPLY_ENV_SENSITIVE = frozenset(k for k in APPLY_ENV_KEYS if k.endswith('_SENHA'))


def _env_path() -> Path:
    return _apply_dir() / '.env'


def _env_atual() -> dict:
    p = _env_path()
    vals = dotenv_values(p) if p.is_file() else {}
    return {k: (vals.get(k) or '') for k in APPLY_ENV_KEYS}


def load_env() -> dict:
    """Só as chaves liberadas; *_SENHA saem mascaradas (mesma regra de api_key)."""
    out = _env_atual()
    for k in _APPLY_ENV_SENSITIVE:
        out[k] = _mask(out[k])
    return out


def save_env(payload: dict) -> dict:
    """Mescla APENAS as chaves liberadas em apply/.env, preservando as
    demais linhas do arquivo tal como estão (chaves de IA etc.).

    - valor vazio → a chave sai do arquivo
    - valor igual ao mask do que está salvo → mantém o real
      (a UI não digita a senha de novo só para salvar outra coisa)
    """
    if not isinstance(payload, dict):
        raise ApplyAdminError('Env inválido: esperado um objeto (dict).')
    unknown = sorted(k for k in payload if k not in APPLY_ENV_KEYS)
    if unknown:
        raise ApplyAdminError(f"Chaves não permitidas no .env do apply: {', '.join(unknown)}.")

    atual = _env_atual()
    merge: dict[str, str] = {}
    for k in APPLY_ENV_KEYS:
        valor = payload.get(k, '')
        if not isinstance(valor, str):
            raise ApplyAdminError(f"O valor de {k} deve ser texto.")
        valor = valor.strip()
        if valor == '':
            merge[k] = ''
        elif k in _APPLY_ENV_SENSITIVE and atual[k] and valor == _mask(atual[k]):
            merge[k] = atual[k]
        else:
            merge[k] = valor

    lines = []
    p = _env_path()
    if p.is_file():
        lines = p.read_text(encoding='utf-8').splitlines()
    kept: list[str] = []
    for linha in lines:
        chave = None
        if linha.strip() and not linha.lstrip().startswith('#'):
            head, sep, _resto = linha.partition('=')
            if sep and head.strip() in APPLY_ENV_KEYS:
                chave = head.strip()
        if chave is None:
            kept.append(linha)

    texto = '\n'.join(kept).rstrip('\n')
    for k in APPLY_ENV_KEYS:
        v = merge.get(k, '')
        if v:
            v_esc = v.replace('\\', '\\\\').replace('"', '\\"')
            texto = f'{texto}\n{k}="{v_esc}"' if texto else f'{k}="{v_esc}"'
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.env.tmp')
    tmp.write_text(texto + '\n', encoding='utf-8')
    tmp.replace(p)
    return load_env()


#  PERFIL — o contexto que a IA dos bots enxerga (apply/common/perfil.py)

def _perfil_module():
    """Carrega apply/common/perfil.py direto do arquivo: o __init__ do
    pacote `common` puxa a camada de browser e não cabe no backend."""
    spec = importlib.util.spec_from_file_location(
        'apply_perfil', _apply_dir() / 'common' / 'perfil.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def perfil_contexto() -> dict:
    """O exato bloco de texto que os 5 bots injetam nos prompts dos LLMs.

    Deixa o usuário conferir no Trivor o que a IA enxerga (aba Perfil →
    "Ver o contexto da IA"). .env entra só com as chaves liberadas,
    excluindo segredos; o módulo `perfil` ignora qualquer outra chave."""
    mod = _perfil_module()
    cfg = load_config()
    env = {k: v for k, v in _env_atual().items()
           if k in mod.ENV_DOC_KEYS or k.startswith('ENDERECO_')}
    return {'texto': mod.contexto_perfil(cfg, env=env)}


#  IA — provedores (config.yaml → ia)

def _ia() -> dict:
    cfg = load_config()
    ia = cfg.get('ia')
    if not isinstance(ia, dict):
        ia = {}
        cfg['ia'] = ia
    ia.setdefault('providers', [])
    return cfg, ia


def _slug(nome: str, existing: set[str]) -> str:
    base = re.sub(r'[^a-z0-9]+', '-', nome.lower()).strip('-') or 'provedor'
    s, i = base, 2
    while s in existing:
        s = f'{base}-{i}'
        i += 1
    return s


def _mask(key: str) -> str:
    key = key or ''
    return (key[:4] + '…' + key[-4:]) if len(key) > 8 else ('…' if key else '')


def _publicar(prov: dict) -> dict:
    """Provider sem api_key em claro — a UI só recebe a máscara."""
    out = dict(prov)
    out['api_key_masked'] = _mask(str(prov.get('api_key', '')))
    out.pop('api_key', None)
    return out


def ia_list() -> dict:
    _, ia = _ia()
    return {'ativo': ia.get('ativo'),
            'providers': [_publicar(p) for p in ia['providers']]}


def _buscar(ia: dict, pid: str) -> dict:
    for p in ia['providers']:
        if p.get('id') == pid:
            return p
    raise ApplyAdminError(f"Provedor '{pid}' não encontrado.")


def _num(valor, caster, rotulo: str):
    """Converte com mensagem clara — nunca 500 com traceback no usuário."""
    try:
        return caster(valor)
    except (TypeError, ValueError):
        raise ApplyAdminError(f"'{rotulo}' precisa ser um número (recebido: {valor!r}).")


def ia_add(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ApplyAdminError("Payload inválido: esperado o corpo do provedor.")
    if not payload.get('modelo'):
        raise ApplyAdminError("O campo 'modelo' é obrigatório.")
    if payload.get('tipo', 'openai') == 'openai' and not payload.get('base_url'):
        raise ApplyAdminError("Provedores openai-compatíveis precisam de base_url.")
    cfg, ia = _ia()
    prov = {
        'id': payload.get('id') or _slug(payload.get('nome', 'provedor'),
                                         {p.get('id') for p in ia['providers']}),
        'nome': payload.get('nome') or payload.get('id') or 'Provedor',
        'tipo': payload.get('tipo', 'openai'),
        'base_url': (payload.get('base_url') or '').strip(),
        'api_key': str(payload.get('api_key') or ''),
        'modelo': str(payload['modelo']),
        'temperatura': _num(payload.get('temperatura', 0.5), float, 'temperatura'),
        'max_tokens': _num(payload.get('max_tokens', 500), int, 'max_tokens'),
    }
    if not prov['api_key']:
        raise ApplyAdminError("O campo 'api_key' é obrigatório ao criar.")
    if prov['id'] in {p.get('id') for p in ia['providers']}:
        raise ApplyAdminError(f"Já existe um provedor com o id '{prov['id']}'.")
    ia['providers'].append(prov)
    if not ia.get('ativo'):
        ia['ativo'] = prov['id']
    save_config(cfg)
    return _publicar(prov)


def ia_update(pid: str, payload: dict) -> dict:
    cfg, ia = _ia()
    prov = _buscar(ia, pid)
    base_url = payload.get('base_url')
    if base_url is None or (isinstance(base_url, str) and not base_url.strip()):
        base_url = prov.get('base_url', '')
    nova = {
        'id': prov['id'],
        'nome': payload.get('nome', prov.get('nome', pid)),
        'tipo': payload.get('tipo', prov.get('tipo', 'openai')),
        'base_url': str(base_url).strip(),
        'modelo': str(payload.get('modelo', prov.get('modelo', ''))),
        'temperatura': _num(payload.get('temperatura', prov.get('temperatura', 0.5)), float, 'temperatura'),
        'max_tokens': _num(payload.get('max_tokens', prov.get('max_tokens', 500)), int, 'max_tokens'),
    }
    # api_key: ausente ou vazio no payload → mantém a salva (a UI só envia
    # a nova quando o usuário digita um novo valor).
    nova['api_key'] = str(payload.get('api_key') or prov.get('api_key', ''))
    prov.clear()
    prov.update(nova)
    save_config(cfg)
    return _publicar(prov)


def ia_delete(pid: str) -> dict:
    cfg, ia = _ia()
    _buscar(ia, pid)  # existe?
    ia['providers'] = [p for p in ia['providers'] if p.get('id') != pid]
    if ia.get('ativo') == pid:
        ia['ativo'] = (ia['providers'][0]['id'] if ia['providers'] else None)
    save_config(cfg)
    return {'deleted': pid, 'ativo': ia.get('ativo')}


def ia_set_active(pid: str) -> dict:
    cfg, ia = _ia()
    _buscar(ia, pid)
    ia['ativo'] = pid
    save_config(cfg)
    return {'ativo': pid}


def _resolver_payload_ou_id(payload: dict) -> dict:
    """POST /ia/test recebe o corpo do form ainda não salvo, ou {id} salvo."""
    if payload.get('id') and not payload.get('api_key') and not payload.get('modelo'):
        _, ia = _ia()
        return _buscar(ia, str(payload['id']))
    return {
        'id': payload.get('id') or payload.get('nome') or 'teste',
        'tipo': payload.get('tipo', 'openai'),
        'base_url': payload.get('base_url') or '',
        'api_key': payload.get('api_key') or '',
        'modelo': payload.get('modelo') or '',
    }


def ia_test(payload: dict) -> dict:
    """Pong: uma chamada de 16 tokens no provedor (barato, valida tudo).

    Importa `apply/common/llm.py` direto do arquivo: o `__init__` do pacote
    `common` puxa a camada de browser (camoufox/playwright) e não cabe no
    processo do backend.
    """
    prov = _resolver_payload_ou_id(payload)
    if not prov.get('modelo'):
        raise ApplyAdminError("Nada para testar: informe o modelo.")
    spec = importlib.util.spec_from_file_location(
        'apply_llm', _apply_dir() / 'common' / 'llm.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ping(prov)


# ════════════════════════════════════════════════════════════════════════════
#  CURRÍCULOS (apply/resumes/ + metadados em config.yaml → resumes/resumes_info)
# ════════════════════════════════════════════════════════════════════════════

_RESUME_EXT = {'.pdf', '.docx'}
_RESUME_MAX = 5 * 1024 * 1024  # 5 MB


def _meta(cfg: dict) -> dict:
    info = cfg.get('resumes_info')
    if not isinstance(info, dict):
        info = {}
        cfg['resumes_info'] = info
    return info


def resumes_list() -> dict:
    cfg = load_config()
    meta = cfg.get('resumes_info') or {}
    up_dir = _apply_dir() / 'resumes'
    out = []
    # o bot lê cfg['resumes'] (perfil → arquivo); a UI gerencia o mesmo mapeamento
    for rid, rel in (cfg.get('resumes') or {}).items():
        if rid == 'mapeamento':
            continue
        m = meta.get(rid) or {}
        out.append({
            'id': rid,
            'nome': m.get('nome', rid),
            'descricao': m.get('descricao', ''),
            'arquivo': str(rel),
            'existe': (up_dir.parent / rel).is_file() if rel else False,
        })
    return {'resumes': out}


def resume_upload(data: bytes, filename: str, nome: str, descricao: str,
                  perfil: str) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in _RESUME_EXT:
        raise ApplyAdminError(f"Formato inválido '{ext}'. Use .pdf ou .docx.")
    if len(data) > _RESUME_MAX:
        raise ApplyAdminError(f"Arquivo excede 5MB ({len(data) // 1024}KB).")
    cfg = load_config()
    existentes = {k: v for k, v in (cfg.get('resumes') or {}).items() if k != 'mapeamento'}
    rid = re.sub(r'[^a-z0-9_]+', '_', perfil.strip().lower())
    if rid:
        # id de perfil já usado com outro arquivo → mantém o perfil, troca o arquivo
        pass
    else:
        base = f'resume_{len(existentes) + 1}'
        rid, i = base, 2
        # perfil vazio: nunca atropelar um id existente com outro arquivo
        while rid in existentes:
            rid = f'{base}_{i}'
            i += 1
    up_dir = _apply_dir() / 'resumes'
    up_dir.mkdir(parents=True, exist_ok=True)
    destino = up_dir / f'{rid}{ext}'
    destino.write_bytes(data)
    cfg.setdefault('resumes', {})[rid] = f'resumes/{destino.name}'
    _meta(cfg)[rid] = {'nome': nome.strip() or rid, 'descricao': (descricao or '').strip(),
                       'atualizado_em': 'agora'}
    save_config(cfg)
    return {'id': rid, 'arquivo': str(destino.name)}


def resume_delete(rid: str) -> dict:
    cfg = load_config()
    rel = (cfg.get('resumes') or {}).get(rid)
    if not rel:
        raise ApplyAdminError(f"Currículo '{rid}' não encontrado.")
    cfg['resumes'].pop(rid, None)
    (cfg.get('resumes_info') or {}).pop(rid, None)
    save_config(cfg)
    alvo = _apply_dir() / rel
    if alvo.is_file():
        alvo.unlink()
    return {'deleted': rid}


def resume_update(rid: str, payload: dict) -> dict:
    cfg = load_config()
    if rid not in (cfg.get('resumes') or {}):
        raise ApplyAdminError(f"Currículo '{rid}' não encontrado.")
    _meta(cfg)[rid] = {
        'nome': (payload.get('nome') or rid).strip(),
        'descricao': (payload.get('descricao') or '').strip(),
    }
    save_config(cfg)
    return _publicar_meta(rid, cfg)


def _publicar_meta(rid: str, cfg: dict) -> dict:
    m = (cfg.get('resumes_info') or {}).get(rid) or {}
    return {'id': rid, 'nome': m.get('nome', rid), 'descricao': m.get('descricao', ''),
            'arquivo': str((cfg.get('resumes') or {}).get(rid, ''))}
