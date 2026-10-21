"""Camada comum dos bots do Job Hunter (browser, seletores adaptativos, delays)."""
from .browser import Browser, BrowserUnavailable, ENGINES, find_adaptive, human

__all__ = ['Browser', 'BrowserUnavailable', 'ENGINES', 'find_adaptive', 'human']
