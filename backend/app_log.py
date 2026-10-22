"""Logger da aplicação (padrão do main): StreamHandler no stdout com
formatter '%(asctime)s %(levelname)s %(message)s' — SEM %(name)s, para as
linhas de log ficarem idênticas às do main.py original depois que a
aplicação foi dividida em módulos de domínio (*_routes.py, llm_core,
cv_helpers)."""

import logging

_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')


def get_app_logger(name: str) -> logging.Logger:
    """Logger por módulo com o formato de linha padrão do main (guarda
    contra handlers duplicados se o módulo for importado duas vezes)."""
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_formatter)
        log.addHandler(handler)
    return log
