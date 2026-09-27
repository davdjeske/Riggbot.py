"""googletrans: unofficial scraper of the public Google Translate web endpoint.

Free and needs no key, but Google sometimes blocks or rate-limits it. The service's circuit
breaker keeps a blocked googletrans from slowing down every translation.
"""
from googletrans import Translator

from .base import ProviderUnavailableError, TranslationResult, UnsupportedLanguageError
from .languages import normalize


class GoogletransProvider:
    """Translates through googletrans. See base.TranslationProvider for what each method must do."""

    name = 'googletrans'

    def __init__(self, translator: Translator | None = None):
        # One Translator is kept for the bot's whole run (it holds an open network connection).
        # `translator` can be passed in by tests (a fake).
        self._translator = translator or Translator()

    def supports(self, lang: str) -> bool:
        return True     # googletrans validates codes itself and raises ValueError for unknown ones

    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult:
        try:
            # googletrans wants lowercase codes ('zh-cn'); 'auto' means detect the language.
            result = await self._translator.translate(text, dest=target.lower(), src=source.lower() if source else 'auto')
        except ValueError as e:     # "invalid source/destination language"
            raise UnsupportedLanguageError(str(e)) from e
        except Exception as e:
            # Anything else (blocked, network error, Google changed its page...) counts as "unavailable".
            raise ProviderUnavailableError(f'{type(e).__name__}: {e}') from e
        # result.src is the detected language; in rare cases googletrans returns something odd there.
        detected = result.src if isinstance(result.src, str) else (source or 'auto')
        return TranslationResult(text=result.text, source_lang=normalize(detected),
                                 target_lang=normalize(target), provider=self.name)

    async def aclose(self) -> None:
        await self._translator.client.aclose()
