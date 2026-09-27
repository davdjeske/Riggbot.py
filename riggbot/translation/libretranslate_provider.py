"""LibreTranslate: open-source translation server (https://github.com/LibreTranslate/LibreTranslate).

Self-host it to use it for free (`pip install libretranslate`, then `libretranslate`, or Docker).
The server URL is `translation.libretranslate.url` in config.json; LIBRETRANSLATE_API_KEY in
.env is only needed for servers that require a key (such as libretranslate.com).
"""
import logging

import httpx

from .base import ProviderUnavailableError, TranslationResult, UnsupportedLanguageError
from .languages import normalize

log = logging.getLogger(__name__)

# Codes different LibreTranslate versions use for a canonical code, most likely first.
_CANDIDATES = {
    'zh-cn': ('zh-Hans', 'zh'),
    'zh-tw': ('zh-Hant', 'zt'),
    'no': ('nb', 'no'),
}


class LibreTranslateProvider:
    name = 'libretranslate'

    def __init__(self, url: str, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self._url = url.rstrip('/')
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=30)
        self._server_codes: set[str] | None = None    # fetched from /languages on first use

    def supports(self, lang: str) -> bool:
        if self._server_codes is None:
            return True     # not known yet; find out on first request
        return self._server_code(lang) is not None

    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult:
        await self._load_languages()
        target_code = self._server_code(target)
        source_code = self._server_code(source) if source else 'auto'
        if target_code is None or source_code is None:
            raise UnsupportedLanguageError(f'This LibreTranslate server does not support {source or ""}→{target}')

        payload = {'q': text, 'source': source_code, 'target': target_code, 'format': 'text'}
        if self._api_key:
            payload['api_key'] = self._api_key
        data = await self._request('POST', '/translate', json=payload)

        detected = (data.get('detectedLanguage') or {}).get('language') or source or 'auto'
        return TranslationResult(text=data['translatedText'], source_lang=normalize(detected),
                                 target_lang=normalize(target), provider=self.name)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _load_languages(self) -> None:
        if self._server_codes is None:
            languages = await self._request('GET', '/languages')
            self._server_codes = {entry['code'] for entry in languages}
            log.debug('LibreTranslate at %s supports: %s', self._url, ', '.join(sorted(self._server_codes)))

    def _server_code(self, lang: str) -> str | None:
        key = normalize(lang).lower()
        for candidate in _CANDIDATES.get(key, (key,)):
            if candidate in self._server_codes:
                return candidate
        return None

    async def _request(self, method: str, path: str, **kwargs):
        try:
            response = await self._client.request(method, self._url + path, **kwargs)
        except httpx.HTTPError as e:
            raise ProviderUnavailableError(f'{type(e).__name__} reaching {self._url}: {e}') from e
        if response.status_code == 400:
            raise UnsupportedLanguageError(_error_text(response))
        if response.status_code >= 400:
            raise ProviderUnavailableError(f'HTTP {response.status_code}: {_error_text(response)}')
        return response.json()


def _error_text(response: httpx.Response) -> str:
    try:
        return response.json().get('error', response.text)
    except ValueError:
        return response.text
