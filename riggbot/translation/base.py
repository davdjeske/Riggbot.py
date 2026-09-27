"""The interface every translation provider implements.

A provider only translates. Everything user-facing (which language to translate into, the
"ja→en:" header, formatting) lives in TranslationService.

To add a provider: write a class that matches TranslationProvider (see the existing providers
for examples), then register a factory for it in translation/__init__.py.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_lang: str    # canonical code (see languages.py), detected or as given
    target_lang: str    # canonical code
    provider: str


class TranslationError(Exception):
    """Base class for translation failures."""


class UnsupportedLanguageError(TranslationError):
    """The provider can't translate from or into the requested language. The next provider is tried."""


class ProviderUnavailableError(TranslationError):
    """The provider couldn't be reached or refused the request (blocked, rate-limited, bad key, quota...)."""


class ProviderNotConfigured(Exception):
    """Raised by a provider factory when its settings (API key, URL...) are missing."""


class TranslationProvider(Protocol):
    name: str

    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult:
        """Translate `text` into `target`. With `source=None` the provider detects the language.

        Language codes in and out are canonical codes (languages.normalize()).
        Raises UnsupportedLanguageError or ProviderUnavailableError.
        """
        ...

    def supports(self, lang: str) -> bool:
        """Cheap local check whether `lang` (canonical) might be supported. May be optimistic."""
        ...

    async def aclose(self) -> None:
        """Release network resources."""
        ...
