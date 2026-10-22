"""Rate limit compartilhado (slowapi) entre os módulos de rotas.

O Limiter mora aqui (e não no main) porque os decorators @limiter.limit
ficaram nos módulos de domínio (*_routes.py) — main só registra o
app.state.limiter + o exception handler de RateLimitExceeded.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
