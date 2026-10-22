"""Logger compartilhado do pipeline de Inteligência de Mercado.

Um único objeto logger (nome histórico "market_service") com FileHandler em
backend/market_log.txt. Os submódulos (market_db / market_jsearch /
market_keywords / market_service) importam `logger` daqui — assim todas as
mensagens do pipeline caem no MESMO arquivo, exatamente como caíam antes da
quebra em módulos (linhas de log com prefixo %(name)s idênticas ao original).
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("market_service")
# Log de mercado em arquivo configurável — nunca hardcoded (roda em qualquer máquina/Docker).
# Padrão: backend/market_log.txt (gitignored); override via TRIVOR_MARKET_LOG.
_MARKET_LOG_PATH = os.getenv('TRIVOR_MARKET_LOG') or str(Path(__file__).resolve().parent / 'market_log.txt')
try:
    _logger_file = logging.FileHandler(_MARKET_LOG_PATH, encoding='utf-8')
    _logger_file.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger.addHandler(_logger_file)
    logger.setLevel(logging.INFO)
except OSError as exc:
    # Caminho não gravável — segue só com log de console sem derrubar o import
    logger.addHandler(logging.NullHandler())
    logger.warning(f"Sem log de mercado em arquivo ({_MARKET_LOG_PATH}): {exc}")
