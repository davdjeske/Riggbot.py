import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import deepl
import httpx
import pytest

from riggbot.config import Secrets, Settings, TranslationSettings
from riggbot.embed_text import split_description
from riggbot.translation import build_providers
from riggbot.translation.base import (ProviderUnavailableError, TranslationResult, UnsupportedLanguageError)
from riggbot.translation.deepl_provider import DeeplProvider, to_deepl
from riggbot.translation.googletrans_provider import GoogletransProvider
from riggbot.translation.languages import is_known, normalize, same_language
from riggbot.translation.libretranslate_provider import LibreTranslateProvider
from riggbot.translation.service import NoProviderAvailable, TranslationService


class FakeProvider:
    """Detects `detected` (a code, or a dict of text -> code) and returns `output`."""

    def __init__(self, name='fake', detected='zh-CN', output='translated', error=None, supported=None):
        self.name = name
        self.detected = detected
        self.output = output
        self.error = error
        self.supported = supported
        self.calls = []
        self.closed = False

    def supports(self, lang):
        return self.supported is None or lang.lower() in self.supported

    async def translate(self, text, target, source=None):
        self.calls.append((text, target, source))
        if self.error:
            raise self.error
        detected = self.detected.get(text, 'en') if isinstance(self.detected, dict) else self.detected
        return TranslationResult(self.output, source or detected, target, self.name)

    async def aclose(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_service(*providers, settings=None, clock=None):
    settings = settings or TranslationSettings()
    return TranslationService(list(providers), lambda: settings, clock=clock or Clock())


# ---------------------------------------------------------------------------
# Riggbot's translation rules (ported from the old translate_text tests)
# ---------------------------------------------------------------------------

class TestTranslateText:
    async def test_foreign_text_gets_header(self):
        service = make_service(FakeProvider(detected='zh-CN', output='hello'))
        assert await service.translate_text('你好') == 'zh-CN→en:\nhello'

    async def test_foreign_text_manual_gets_header(self):
        service = make_service(FakeProvider(detected='ja', output='hello'))
        assert await service.translate_text('こんにちは', manual=True) == 'ja→en:\nhello'

    async def test_one_request_for_foreign_text(self):
        provider = FakeProvider(detected='ja')
        await make_service(provider).translate_text('こんにちは')
        assert provider.calls == [('こんにちは', 'en', None)]

    async def test_already_dest_lang_automatic_returns_none(self):
        provider = FakeProvider(detected='en')
        assert await make_service(provider).translate_text('hello') is None
        assert len(provider.calls) == 1

    async def test_already_dest_lang_manual_uses_override_lang(self):
        provider = FakeProvider(detected='en', output='你好')
        assert await make_service(provider).translate_text('hello', manual=True) == '你好'
        assert provider.calls[1] == ('hello', 'zh-CN', None)

    async def test_already_dest_lang_manual_with_flag_source(self):
        provider = FakeProvider(detected='en', output='translated from ja')
        result = await make_service(provider).translate_text('text', manual=True, source='JA')
        assert result == 'translated from ja'
        assert provider.calls[1] == ('text', 'en', 'ja')

    async def test_flag_source_ignored_when_detected_foreign(self):
        """Same as before: the flag only matters when the text looks like it's already in dest_lang."""
        provider = FakeProvider(detected='de', output='hi')
        assert await make_service(provider).translate_text('hallo', manual=True, source='ja') == 'de→en:\nhi'

    async def test_dest_lang_comparison_ignores_case(self):
        provider = FakeProvider(detected='en')
        service = make_service(provider, settings=TranslationSettings(dest_lang='EN'))
        assert await service.translate_text('hello') is None

    async def test_double_backticks_become_quotes(self):
        service = make_service(FakeProvider(output='he said ``hi``'))
        assert await service.translate_text('x') == 'zh-CN→en:\nhe said "hi"'

    async def test_markdown_links_are_stripped_first(self):
        provider = FakeProvider()
        await make_service(provider).translate_text('hi [@someone](https://x.com/someone) there')
        assert provider.calls[0][0] == 'hi @someone there'

    async def test_empty_text_is_skipped(self):
        provider = FakeProvider()
        assert await make_service(provider).translate_text('  ') is None
        assert provider.calls == []

    async def test_raises_when_nothing_works(self):
        service = make_service(FakeProvider(error=ProviderUnavailableError('down')))
        with pytest.raises(NoProviderAvailable, match='down'):
            await service.translate_text('x')

    async def test_raises_with_no_providers(self):
        with pytest.raises(NoProviderAvailable):
            await make_service().translate_text('x')


# ---------------------------------------------------------------------------
# Embed posts (ported from the old process_embed tests, plus the parser fixes)
# ---------------------------------------------------------------------------

TWO_BLOB_DESC = 'main post text\n\n> **[Quoting](http://example.com) Author**\n> \n> quoted reply text'


class TestTranslatePost:
    async def test_single_post(self):
        result = await make_service(FakeProvider()).translate_post('你好世界')
        assert result == '\U0001F4C4 zh-CN→en:\ntranslated'

    async def test_empty_description(self):
        assert await make_service(FakeProvider()).translate_post('') is None

    @pytest.mark.parametrize('main_lang, quoted_lang, expect_main, expect_quoted', [
        ('en', 'en', False, False),
        ('zh-CN', 'en', True, False),
        ('en', 'zh-CN', False, True),
        ('zh-CN', 'zh-CN', True, True),
    ])
    async def test_main_and_quoted(self, main_lang, quoted_lang, expect_main, expect_quoted):
        provider = FakeProvider(detected={'main post text': main_lang, 'quoted reply text': quoted_lang})
        result = await make_service(provider).translate_post(TWO_BLOB_DESC)
        if not (expect_main or expect_quoted):
            assert result is None
            return
        assert ('\U0001F4C4' in result) == expect_main
        assert ('\U0001F4AC' in result) == expect_quoted
        assert not result.startswith('\n')

    async def test_manual_flag_passes_through(self):
        provider = FakeProvider(detected='en', output='override translation')
        result = await make_service(provider).translate_post('some english text', manual=True)
        assert result == '\U0001F4C4 override translation'
        assert provider.calls[-1] == ('some english text', 'zh-CN', None)


class TestSplitDescription:
    def test_main_quote_and_stats(self):
        desc = ('main text\n\n**[💬](http://x) 1.2K  [🔁](http://x) 345  [❤️](http://x) 6.7K**\n\n'
                '> **[Quoting](http://x) N (@n)**\n> \n> line one\n> line two')
        assert split_description(desc) == ('main text', 'line one\nline two')

    def test_bold_words_do_not_split_the_post(self):
        """Regression: inline **bold** used to split a post and drop the bold words."""
        text = 'this is **very** important and more text'
        assert split_description(text) == (text, '')

    def test_quote_without_caption_keeps_quoted_text(self):
        """Regression: an empty first part used to throw away the quoted post."""
        assert split_description('\n\n> **[Quoting](http://x) Author**\n> \n> quoted text') == ('', 'quoted text')

    def test_only_stats(self):
        assert split_description('**[💬](http://x) 1**') == ('', '')


# ---------------------------------------------------------------------------
# Provider chain and circuit breaker
# ---------------------------------------------------------------------------

class TestProviderChain:
    async def test_falls_back_to_next_provider(self):
        first = FakeProvider('first', error=ProviderUnavailableError('blocked'))
        second = FakeProvider('second', output='ok')
        result = await make_service(first, second).translate('x', 'en')
        assert result.provider == 'second'

    async def test_unsupported_language_skips_without_calling(self):
        first = FakeProvider('first', supported={'en'})
        second = FakeProvider('second')
        result = await make_service(first, second).translate('x', 'ga')
        assert result.provider == 'second' and first.calls == []

    async def test_unsupported_error_moves_on(self):
        first = FakeProvider('first', error=UnsupportedLanguageError('nope'))
        second = FakeProvider('second')
        assert (await make_service(first, second).translate('x', 'en')).provider == 'second'

    async def test_unexpected_exception_moves_on(self):
        first = FakeProvider('first', error=RuntimeError('bug'))
        second = FakeProvider('second')
        assert (await make_service(first, second).translate('x', 'en')).provider == 'second'

    async def test_breaker_pauses_and_resumes(self):
        clock = Clock()
        flaky = FakeProvider('flaky', error=ProviderUnavailableError('429'))
        backup = FakeProvider('backup')
        settings = TranslationSettings()   # 3 failures, 10 minutes
        service = make_service(flaky, backup, settings=settings, clock=clock)

        for _ in range(3):
            await service.translate('x', 'en')
        assert len(flaky.calls) == 3
        await service.translate('x', 'en')
        assert len(flaky.calls) == 3          # paused: not called

        clock.now += 10 * 60 + 1
        flaky.error = None
        assert (await service.translate('x', 'en')).provider == 'flaky'

    async def test_success_resets_failure_count(self):
        provider = FakeProvider('p', error=ProviderUnavailableError('x'))
        backup = FakeProvider('backup')
        service = make_service(provider, backup)
        for _ in range(2):
            await service.translate('x', 'en')
        provider.error = None
        await service.translate('x', 'en')
        provider.error = ProviderUnavailableError('x')
        for _ in range(2):
            await service.translate('x', 'en')
        assert len(provider.calls) == 5      # never paused

    async def test_replace_providers_closes_old(self):
        old = FakeProvider('old')
        service = make_service(old)
        await service.replace_providers([FakeProvider('new')])
        assert old.closed and service.providers[0].name == 'new'

    async def test_self_test_logs_each_provider(self, caplog):
        good = FakeProvider('good', output='Hello!')
        bad = FakeProvider('bad', error=ProviderUnavailableError('blocked'))
        with caplog.at_level(logging.INFO):
            await make_service(good, bad).self_test()
        assert 'Self-test: good works' in caplog.text
        assert 'Self-test: bad is not working (blocked)' in caplog.text


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

class TestLanguages:
    @pytest.mark.parametrize('code, expected', [
        ('EN', 'en'), ('zh-cn', 'zh-CN'), ('zh_TW', 'zh-TW'), ('ZH-HANS', 'zh-CN'), ('zh', 'zh-CN'),
        ('zt', 'zh-TW'), ('nb', 'no'), ('iw', 'he'), (' ja ', 'ja'), ('ms-arab', 'ms-Arab'),
    ])
    def test_normalize(self, code, expected):
        assert normalize(code) == expected

    def test_same_language(self):
        assert same_language('EN', 'en') and not same_language('zh-CN', 'zh-TW')

    def test_is_known(self):
        assert is_known('zh-CN') and is_known('ga') and not is_known('xx') and not is_known('english')


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class TestDeepl:
    @pytest.mark.parametrize('code, target, expected', [
        ('en', True, 'EN-US'), ('en', False, 'EN'), ('zh-CN', True, 'ZH-HANS'), ('zh-TW', True, 'ZH-HANT'),
        ('zh-TW', False, 'ZH'), ('pt', True, 'PT-BR'), ('no', False, 'NB'), ('ja', True, 'JA'),
    ])
    def test_codes(self, code, target, expected):
        assert to_deepl(code, target=target) == expected

    def make(self, **client_kwargs):
        client = MagicMock()
        client.translate_text = MagicMock(**client_kwargs)
        return DeeplProvider('key', client=client), client

    async def test_translate(self):
        provider, client = self.make(return_value=SimpleNamespace(text='hello', detected_source_lang='ZH'))
        result = await provider.translate('你好', 'en')
        assert result == TranslationResult('hello', 'zh-CN', 'en', 'deepl')
        client.translate_text.assert_called_once_with('你好', source_lang=None, target_lang='EN-US')

    async def test_unsupported_language_raises_without_request(self):
        provider, client = self.make()
        with pytest.raises(UnsupportedLanguageError):
            await provider.translate('x', 'ga')
        client.translate_text.assert_not_called()

    @pytest.mark.parametrize('error', [
        deepl.QuotaExceededException('quota'), deepl.AuthorizationException('bad key'),
        deepl.ConnectionException('offline', should_retry=False),
    ])
    async def test_service_errors_are_unavailable(self, error):
        provider, _ = self.make(side_effect=error)
        with pytest.raises(ProviderUnavailableError):
            await provider.translate('x', 'en')


class TestGoogletrans:
    def make(self, **kwargs):
        translator = MagicMock()
        translator.translate = AsyncMock(**kwargs)
        translator.client.aclose = AsyncMock()
        return GoogletransProvider(translator), translator

    async def test_translate(self):
        provider, translator = self.make(return_value=SimpleNamespace(text='hello', src='zh-cn'))
        result = await provider.translate('你好', 'en')
        assert result == TranslationResult('hello', 'zh-CN', 'en', 'googletrans')
        translator.translate.assert_awaited_once_with('你好', dest='en', src='auto')

    async def test_source_is_passed(self):
        provider, translator = self.make(return_value=SimpleNamespace(text='hi', src='ja'))
        await provider.translate('x', 'zh-CN', source='ja')
        translator.translate.assert_awaited_once_with('x', dest='zh-cn', src='ja')

    async def test_invalid_language(self):
        provider, _ = self.make(side_effect=ValueError('invalid destination language'))
        with pytest.raises(UnsupportedLanguageError):
            await provider.translate('x', 'xx')

    async def test_network_error(self):
        provider, _ = self.make(side_effect=httpx.ConnectError('blocked'))
        with pytest.raises(ProviderUnavailableError, match='ConnectError'):
            await provider.translate('x', 'en')

    async def test_close(self):
        provider, translator = self.make()
        await provider.aclose()
        translator.client.aclose.assert_awaited_once()


class TestLibreTranslate:
    def make(self, handler, codes=('en', 'de', 'ja', 'zh-Hans', 'zh-Hant')):
        requests = []

        def route(request: httpx.Request):
            requests.append(request)
            if request.url.path == '/languages':
                return httpx.Response(200, json=[{'code': c, 'name': c, 'targets': list(codes)} for c in codes])
            return handler(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(route))
        return LibreTranslateProvider('http://libre:5000/', api_key='k', client=client), requests

    async def test_translate_auto(self):
        provider, requests = self.make(lambda r: httpx.Response(200, json={
            'translatedText': 'hello', 'detectedLanguage': {'confidence': 90, 'language': 'zh-Hans'}}))
        result = await provider.translate('你好', 'en')
        assert result == TranslationResult('hello', 'zh-CN', 'en', 'libretranslate')
        body = json.loads(requests[-1].content)
        assert body == {'q': '你好', 'source': 'auto', 'target': 'en', 'format': 'text', 'api_key': 'k'}

    async def test_maps_chinese_codes(self):
        provider, requests = self.make(lambda r: httpx.Response(200, json={'translatedText': '你好'}))
        result = await provider.translate('hello', 'zh-TW', source='en')
        assert json.loads(requests[-1].content)['target'] == 'zh-Hant'
        assert result.source_lang == 'en'

    async def test_language_missing_on_server(self):
        provider, _ = self.make(lambda r: httpx.Response(200, json={}))
        with pytest.raises(UnsupportedLanguageError):
            await provider.translate('x', 'ga')
        assert not provider.supports('ga') and provider.supports('ja')

    async def test_server_error_is_unavailable(self):
        provider, _ = self.make(lambda r: httpx.Response(500, json={'error': 'boom'}))
        with pytest.raises(ProviderUnavailableError, match='HTTP 500: boom'):
            await provider.translate('x', 'en')

    async def test_unreachable_server(self):
        def fail(request):
            raise httpx.ConnectError('refused')
        client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
        provider = LibreTranslateProvider('http://libre:5000', client=client)
        with pytest.raises(ProviderUnavailableError, match='refused'):
            await provider.translate('x', 'en')


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestBuildProviders:
    async def test_skips_deepl_without_key_and_unknown_names(self, caplog):
        settings = Settings()
        settings.translation.providers = ['deepl', 'bogus', 'googletrans', 'libretranslate']
        with caplog.at_level(logging.WARNING):
            providers = build_providers(settings, Secrets(token='t'))
        try:
            assert [p.name for p in providers] == ['googletrans', 'libretranslate']
            assert 'DEEPL_API_KEY' in caplog.text and 'bogus' in caplog.text
        finally:
            for p in providers:
                await p.aclose()

    async def test_deepl_with_key(self):
        settings = Settings()
        settings.translation.providers = ['deepl']
        providers = build_providers(settings, Secrets(token='t', deepl_api_key='abc:fx'))
        assert [p.name for p in providers] == ['deepl']
        await providers[0].aclose()
