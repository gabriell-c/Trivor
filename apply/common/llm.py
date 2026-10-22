"""Provedores de LLM configuráveis pela UI — nada de provider hardcoded.

O `config.yaml` do apply ganha um bloco `ia`:

    ia:
      ativo: "groq"
      providers:
        - id: "groq"
          nome: "Groq"
          tipo: "openai"            # "openai" (compatível) ou "anthropic"
          base_url: "https://api.groq.com/openai/v1"
          api_key: "gsk_..."
          modelo: "llama-3.3-70b-versatile"
          temperatura: 0.4
          max_tokens: 500

`tipo: openai` funciona com qualquer API compatível (Groq, OpenAI,
LM Studio, Ollama, vLLM, Together...); `tipo: anthropic` usa
`/v1/messages`. O backend (aba IA do Trivor) grava esse bloco; os bots
lêm por aqui. Sem dependência nova — urllib da stdlib.
"""
import contextlib
import json
import random
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    """Falha definitiva do provedor (após os retries)."""


def _post(url: str, headers: dict, payload: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', **headers}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _openai_chat(prov: dict, prompt: str, temperature: float, max_tokens: int) -> str:
    base = (prov.get('base_url') or '').rstrip('/')
    if not base:
        raise LLMError("Provider openai-compatível precisa de base_url")
    data = _post(base + '/chat/completions',
                 {'Authorization': f"Bearer {prov.get('api_key', '')}"},
                 {'model': prov['modelo'],
                  'messages': [{'role': 'user', 'content': prompt}],
                  'temperature': temperature,
                  'max_tokens': max_tokens})
    return data['choices'][0]['message']['content'].strip()


def _anthropic_chat(prov: dict, prompt: str, temperature: float, max_tokens: int) -> str:
    base = (prov.get('base_url') or 'https://api.anthropic.com').rstrip('/')
    data = _post(base + '/v1/messages',
                 {'x-api-key': prov.get('api_key', ''), 'anthropic-version': '2023-06-01'},
                 {'model': prov['modelo'],
                  'max_tokens': max_tokens,
                  'temperature': temperature,
                  'messages': [{'role': 'user', 'content': prompt}]})
    return data['content'][0]['text'].strip()


def _resumo_err(exc: Exception, prov: dict, tentativas: int) -> str:
    """Traduz a exceção final em PT-BR — o detalhe vai direto pra UI."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} do provedor nas {tentativas} tentativas"
    if isinstance(exc, urllib.error.URLError):
        base = (prov.get('base_url') or prov.get('nome') or 'servidor').rstrip('/')
        motivo = str(getattr(exc, 'reason', exc)).lower()
        if 'timeout' in motivo or 'timed out' in motivo:
            return f'tempo esgotado ao falar com {base}'
        return f'sem conexão com {base} — o serviço está no ar e a URL base está correta?'
    if isinstance(exc, LLMError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def chat(prov: dict, prompt: str, temperature: float = 0.5,
         max_tokens: int = 500, tentativas: int = 3) -> str:
    """Chama o provedor `prov` (dict do bloco ia) com retries e backoff.

    429/5xx → retry progressivo; 401/403/404 → aborta logo (chave/modelo
    errados não melhoram com retry). Levanta LLMError no fim."""
    tipo = prov.get('tipo', 'openai')
    ultimo: Exception | None = None
    for tentativa in range(tentativas):
        try:
            if tipo == 'anthropic':
                return _anthropic_chat(prov, prompt, temperature, max_tokens)
            return _openai_chat(prov, prompt, temperature, max_tokens)
        except urllib.error.HTTPError as e:
            ultimo = e
            corpo = ''
            with contextlib.suppress(Exception):
                corpo = e.read().decode('utf-8', errors='ignore')[:300]
            if e.code in (401, 403, 404):  # credencial/modelo — retry não resolve
                raise LLMError(f"HTTP {e.code} do provedor: {corpo}") from e
            if tentativa < tentativas - 1:
                time.sleep(4 * (tentativa + 1) + random.uniform(0, 1))
        except Exception as exc:
            ultimo = exc
            if tentativa < tentativas - 1:
                time.sleep(2 ** tentativa + random.uniform(0, 1))
    raise LLMError(f"Provedor '{prov.get('id', prov.get('nome', '?'))}' falhou após "
                   f"{tentativas} {'tentativa' if tentativas == 1 else 'tentativas'}: "
                   f"{_resumo_err(ultimo, prov, tentativas)}")


def ping(prov: dict) -> dict:
    """Teste de conexão: pede um "pong" de 16 tokens. Sem custo real.

    Retorna {"ok": True, "resposta": ...} ou {"ok": False, "detalhe": ...} —
    a aba IA do Trivor mostra na hora se a chave/base_url/modelo funcionam."""
    try:
        return {'ok': True, 'resposta': chat(prov, 'Responda apenas: pong',
                                              temperature=0.0, max_tokens=16, tentativas=1)}
    except LLMError as exc:
        return {'ok': False, 'detalhe': str(exc)}
    except Exception as exc:  # rede/timeout — detalhe genérico mas legível
        return {'ok': False, 'detalhe': f'{type(exc).__name__}: {exc}'}


def providers_ativos(config: dict) -> list[dict]:
    """Provedores do bloco `ia` da config (ordem = fallback, ativo em 1º)."""
    ia = config.get('ia') or {}
    pros = [dict(p) for p in (ia.get('providers') or []) if p.get('id')]
    ativo = ia.get('ativo')
    pros.sort(key=lambda p: p.get('id') != ativo)  # ativo primeiro, sem reordenar o resto
    return pros
