"""DeepL API (Free or Pro), through the official `deepl` package.

Needs DEEPL_API_KEY in .env. Free-plan keys end in ":fx" and are sent to the free endpoint
automatically. The free plan allows 500,000 characters a month.
"""
import asyncio

import deepl

from .base import ProviderUnavailableError, TranslationResult, UnsupportedLanguageError
from .languages import normalize

# Languages DeepL translates from/into (canonical codes). Kept locally so unsupported languages
# go straight to the next provider without an API call. DeepL adds languages now and then;
# add them here when it does.
SUPPORTED = {
    'ar', 'bg', 'cs', 'da', 'de', 'el', 'en', 'es', 'et', 'fi', 'fr', 'he', 'hu', 'id', 'it', 'ja',
    'ko', 'lt', 'lv', 'no', 'nl', 'pl', 'pt', 'ro', 'ru', 'sk', 'sl', 'sv', 'th', 'tr', 'uk', 'vi',
    'zh-cn', 'zh-tw',
}

# Canonical code -> DeepL code, where they differ. Anything else is just upper-cased.
# DeepL wants a specific variant when translating INTO English/Portuguese/Chinese,
# but only the plain language when translating FROM them.
_TARGET_CODES = {'en': 'EN-US', 'pt': 'PT-BR', 'zh-cn': 'ZH-HANS', 'zh-tw': 'ZH-HANT', 'no': 'NB'}
_SOURCE_CODES = {'zh-cn': 'ZH', 'zh-tw': 'ZH', 'no': 'NB'}


def to_deepl(code: str, *, target: bool) -> str:
    """Convert a canonical code to DeepL's code, e.g. ('en', target=True) -> 'EN-US'."""
    key = normalize(code).lower()
    table = _TARGET_CODES if target else _SOURCE_CODES
    return table.get(key, key.upper())


class DeeplProvider:
    """Translates through the DeepL API. See base.TranslationProvider for what each method must do."""

    name = 'deepl'

    def __init__(self, api_key: str, client: deepl.DeepLClient | None = None):
        # `client` can be passed in by tests (a fake); normally the real client is created here.
        self._client = client or deepl.DeepLClient(api_key, send_platform_info=False)

    def supports(self, lang: str) -> bool:
        return normalize(lang).lower() in SUPPORTED

    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult:
        # Don't spend a request (or quota) on languages DeepL can't do.
        if not self.supports(target) or (source and not self.supports(source)):
            raise UnsupportedLanguageError(f'DeepL does not support {source or ""}→{target}')
        try:
            # The deepl package is not async: run its call in a background thread so the bot
            # keeps responding to Discord while waiting for DeepL.
            result = await asyncio.to_thread(
                self._client.translate_text, text,
                source_lang=to_deepl(source, target=False) if source else None,     # None = auto-detect
                target_lang=to_deepl(target, target=True),
            )
        except (deepl.AuthorizationException, deepl.QuotaExceededException,
                deepl.TooManyRequestsException, deepl.ConnectionException) as e:
            # Bad key, monthly quota used up, too many requests, or no connection.
            raise ProviderUnavailableError(f'{type(e).__name__}: {e}') from e
        except deepl.DeepLException as e:
            if 'not supported' in str(e).lower():
                raise UnsupportedLanguageError(str(e)) from e
            raise ProviderUnavailableError(f'{type(e).__name__}: {e}') from e
        return TranslationResult(text=result.text, source_lang=normalize(result.detected_source_lang),
                                 target_lang=normalize(target), provider=self.name)

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)
