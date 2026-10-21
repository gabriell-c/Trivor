"""Camada comum dos bots do Job Hunter (browser, seletores adaptativos, delays, LLM)."""
from .browser import Browser, BrowserUnavailable, ENGINES, find_adaptive, human
from .llm import LLMError, chat, ping, providers_ativos

__all__ = ['Browser', 'BrowserUnavailable', 'ENGINES', 'find_adaptive', 'human',
           'LLMError', 'chat', 'ping', 'providers_ativos']
