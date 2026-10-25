"""Modo "só login" — TRIVOR_LOGIN_ONLY=1.

Cada bot, ao garantir a sessão (login automático ou manual), pode parar ali:
busca e candidatura não rodam. A UI do Trivor usa esse modo no botão
"Logar" — o processo só termina com exit 0 quando a sessão está salva ou
com exit 1 quando falhou; o backend lê o estado e atualiza o cartão.

Mesmo padrão dos outros modos de campo (`dryrun.py`, `TRIVOR_ENGINE`):
sem a variável no ambiente, o bot roda o fluxo completo.
"""
import os


def ativo() -> bool:
    """True quando TRIVOR_LOGIN_ONLY=1 no ambiente."""
    return os.environ.get("TRIVOR_LOGIN_ONLY", "").strip() == "1"
