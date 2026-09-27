"""Translation: pluggable providers behind one TranslationService.

Providers are listed by name in config (`translation.providers`) and tried in that order.
To add one, write a provider class (see base.py) and add a factory to PROVIDERS below.
"""
import logging
from typing import Callable

from ..config import Secrets, Settings
from .base import (ProviderNotConfigured, ProviderUnavailableError, TranslationError, TranslationProvider,
                   TranslationResult, UnsupportedLanguageError)
from .service import TranslationService

log = logging.getLogger(__name__)

__all__ = ['PROVIDERS', 'build_providers', 'TranslationService', 'TranslationProvider', 'TranslationResult',
           'TranslationError', 'UnsupportedLanguageError', 'ProviderUnavailableError']


# Factories: each creates one provider from the settings, or raises ProviderNotConfigured if
# something it needs is missing. Provider modules are imported inside the factory, so a provider
# that isn't used doesn't need its package installed.

def _deepl(settings: Settings, secrets: Secrets) -> TranslationProvider:
    if not secrets.deepl_api_key:
        raise ProviderNotConfigured('DEEPL_API_KEY is not set in .env')
    from .deepl_provider import DeeplProvider
    return DeeplProvider(secrets.deepl_api_key)


def _googletrans(settings: Settings, secrets: Secrets) -> TranslationProvider:
    from .googletrans_provider import GoogletransProvider
    return GoogletransProvider()


def _libretranslate(settings: Settings, secrets: Secrets) -> TranslationProvider:
    url = settings.translation.libretranslate.url.strip()
    if not url:
        raise ProviderNotConfigured('translation.libretranslate.url is empty')
    from .libretranslate_provider import LibreTranslateProvider
    return LibreTranslateProvider(url, api_key=secrets.libretranslate_api_key)


# The names usable in config.json's `translation.providers`, and the factory for each.
PROVIDERS: dict[str, Callable[[Settings, Secrets], TranslationProvider]] = {
    'deepl': _deepl,
    'googletrans': _googletrans,
    'libretranslate': _libretranslate,
}


def build_providers(settings: Settings, secrets: Secrets) -> list[TranslationProvider]:
    """Create the providers named in config, in order, skipping ones that can't be used."""
    providers = []
    for name in settings.translation.providers:
        factory = PROVIDERS.get(name)
        if factory is None:
            log.warning('Unknown translation provider "%s" in config; known providers: %s',
                        name, ', '.join(PROVIDERS))
            continue
        # A provider that can't be created is left out with a warning; the others still work.
        try:
            providers.append(factory(settings, secrets))
        except ProviderNotConfigured as e:
            log.warning('Translation provider %s skipped: %s', name, e)
        except ImportError as e:
            log.warning('Translation provider %s skipped: missing package (%s)', name, e)
    if providers:
        log.info('Translation providers, in order: %s', ', '.join(p.name for p in providers))
    else:
        log.warning('No translation provider is usable; translation is turned off')
    return providers
