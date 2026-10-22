"""Camada comum dos bots do Job Hunter (browser, seletores adaptativos, delays, LLM)."""
from .browser import ENGINES, Browser, BrowserUnavailable, find_adaptive, human
from .llm import LLMError, chat, ping, providers_ativos

__all__ = [
           'ENGINES',
           'Browser',
           'BrowserUnavailable',
           'LLMError',
           'chat',
           'find_adaptive',
           'human',
           'ping',
           'providers_ativos',
]
