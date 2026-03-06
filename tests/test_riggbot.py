"""
Tests for riggbot.py

Covers:
  - bot_token(): env var loading and error handling
  - KEYWORD_RESPONSES: content validation
  - translate_text(): language detection and translation decision logic
  - process_embed(): embed description parsing and translation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import riggbot


# ---------------------------------------------------------------------------
# bot_token
# ---------------------------------------------------------------------------

class TestBotToken:
    def test_loads_token_from_env(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', 'test_token_abc')
        assert riggbot.bot_token() == 'test_token_abc'

    def test_strips_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', '   padded_token   ')
        assert riggbot.bot_token() == 'padded_token'

    def test_raises_when_env_var_missing(self, monkeypatch):
        monkeypatch.delenv('RIGGBOT_TOKEN', raising=False)
        with pytest.raises(FileNotFoundError):
            riggbot.bot_token()

    def test_raises_when_env_var_empty(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', '')
        with pytest.raises(FileNotFoundError):
            riggbot.bot_token()


# ---------------------------------------------------------------------------
# KEYWORD_RESPONSES
# ---------------------------------------------------------------------------

class TestKeywordResponses:
    def test_all_responses_are_non_empty_strings(self):
        for keyword, response in riggbot.KEYWORD_RESPONSES.items():
            assert isinstance(
                response, str), f'Response for "{keyword}" is not a string'
            assert response.strip(), f'Response for "{keyword}" is empty'


# ---------------------------------------------------------------------------
# translate_text
# ---------------------------------------------------------------------------

class TestTranslateText:
    """
    translate_text decision tree:
      - detected.lang != DEST_LANG              → translate, return "lang→dest: text"
      - detected.lang == DEST_LANG, is_manual   → translate to MANUAL_OVERRIDE_LANG, return translated.text
      - detected.lang == DEST_LANG, not manual  → return None
      - exception raised                        → return None
    """

    @pytest.fixture(autouse=True)
    def setup_globals(self):
        riggbot.DEST_LANG = 'en'
        riggbot.MANUAL_OVERRIDE_LANG = 'zh-CN'

    def _make_translator(self, detected_lang, translated_text='translated'):
        mock = AsyncMock()
        mock.detect.return_value = MagicMock(lang=detected_lang)
        mock.translate.return_value = MagicMock(text=translated_text)
        return mock

    async def test_returns_none_when_already_dest_lang_and_auto(self):
        riggbot.translator = self._make_translator('en')
        result = await riggbot.translate_text('hello', is_manual=False)
        assert result is None

    async def test_translates_foreign_text_to_dest_lang(self):
        riggbot.translator = self._make_translator(
            'zh-CN', translated_text='hello')
        result = await riggbot.translate_text('你好', is_manual=False)
        assert result == 'zh-CN→en: hello'

    async def test_manual_override_when_already_in_dest_lang(self):
        riggbot.translator = self._make_translator('en', translated_text='你好')
        result = await riggbot.translate_text('hello', is_manual=True)
        assert result == '你好'
        riggbot.translator.translate.assert_awaited_once_with(
            'hello', dest='zh-CN')

    async def test_manual_translates_foreign_text_to_dest_lang(self):
        # Even with is_manual=True, a non-dest-lang text is translated normally
        riggbot.translator = self._make_translator(
            'ja', translated_text='hello')
        result = await riggbot.translate_text('こんにちは', is_manual=True)
        assert result == 'ja→en: hello'

    async def test_returns_none_on_exception(self):
        mock = AsyncMock()
        mock.detect.side_effect = Exception('network error')
        riggbot.translator = mock
        result = await riggbot.translate_text('hello', is_manual=False)
        assert result is None


# ---------------------------------------------------------------------------
# process_embed
# ---------------------------------------------------------------------------

class TestProcessEmbed:
    @pytest.fixture(autouse=True)
    def setup_globals(self):
        riggbot.DEST_LANG = 'en'
        riggbot.MANUAL_OVERRIDE_LANG = 'zh-CN'
        # Default translator: always reports zh-CN so a translation is returned
        mock = AsyncMock()
        mock.detect.return_value = MagicMock(lang='zh-CN')
        mock.translate.return_value = MagicMock(text='translated text')
        riggbot.translator = mock

    def _make_embed(self, description):
        embed = MagicMock()
        embed.to_dict.return_value = {
            'description': description} if description is not None else {}
        return embed

    async def test_returns_none_when_no_description_key(self):
        embed = self._make_embed(None)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is None

    async def test_returns_none_when_description_is_empty_string(self):
        # An empty blob list causes an early return of None
        embed = self._make_embed('')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is None

    async def test_translates_single_blob_description(self):
        embed = self._make_embed('你好世界')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result  # 📄 prefix for main text

    async def test_translates_two_blob_description(self):
        # The regex splits on **[...](...)** style separators
        embed = self._make_embed(
            'main post text **[via source](http://example.com)** quoted reply text')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result   # 📄 main blob
        assert '\U0001F4AC' in result   # 💬 quoted blob

    async def test_passes_is_manual_flag_through(self):
        """is_manual=True should trigger the manual override path in translate_text."""
        # Set up translator to report lang='en' so manual override kicks in
        mock = AsyncMock()
        mock.detect.return_value = MagicMock(lang='en')
        mock.translate.return_value = MagicMock(text='override translation')
        riggbot.translator = mock

        embed = self._make_embed('some english text')
        result = await riggbot.process_embed(embed, is_manual=True)
        assert result is not None
        mock.translate.assert_awaited_with('some english text', dest='zh-CN')
