import pytest
from unittest.mock import AsyncMock, MagicMock
import riggbot


# ---------------------------------------------------------------------------
# Env Loading Tests
# ---------------------------------------------------------------------------
''' 
Tests for loading configuration from environment variables. These tests ensure that
the env vars are read corrrectly, whitespace is stripped, and defaults are applied when vars are missing.
For BOT_TOKEN, also tests that a FileNotFoundError is raised if the token is missing or empty,
since it's required for the bot to function.
'''


class TestEnvBotToken:
    # can read token from env
    def test_loads_token_from_env(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', 'bot_token')
        assert riggbot.bot_token() == 'bot_token'

    # can strip whitespace from env var
    def test_strips_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', '   padded_token   ')
        assert riggbot.bot_token() == 'padded_token'

    # raises FileNotFoundError if env var is missing
    def test_raises_when_env_var_missing(self, monkeypatch):
        monkeypatch.delenv('RIGGBOT_TOKEN', raising=False)
        with pytest.raises(FileNotFoundError):
            riggbot.bot_token()

    # or empty
    def test_raises_when_env_var_empty(self, monkeypatch):
        monkeypatch.setenv('RIGGBOT_TOKEN', '')
        with pytest.raises(FileNotFoundError):
            riggbot.bot_token()


class TestEnvEmbedBot:
    # can read embed bot name from env
    def test_loads_embed_bot_name_from_env(self, monkeypatch):
        monkeypatch.setenv('EMBED_BOT_NAME', 'EmbedBot')
        riggbot.init_bot()
        assert riggbot.EMBED_BOT_NAME == 'embedbot'

    # can strip whitespace from embed bot name from env
    def test_strips_whitespace_from_embed_bot_name(self, monkeypatch):
        monkeypatch.setenv('EMBED_BOT_NAME', '   EmbedBot   ')
        riggbot.init_bot()
        assert riggbot.EMBED_BOT_NAME == 'embedbot'

    # defaults to '' if env var is missing
    def test_defaults_embed_bot_name(self, monkeypatch):
        monkeypatch.delenv('EMBED_BOT_NAME', raising=False)
        riggbot.init_bot()
        assert riggbot.EMBED_BOT_NAME == ''


class TestEnvDestLang:
    # can read dest lang from env
    def test_loads_dest_lang_from_env(self, monkeypatch):
        monkeypatch.setenv('DEST_LANG', 'de')
        riggbot.init_bot()
        assert riggbot.DEST_LANG == 'de'

    # can strip whitespace from dest lang env var
    def test_strips_whitespace_from_dest_lang(self, monkeypatch):
        monkeypatch.setenv('DEST_LANG', '   de   ')
        riggbot.init_bot()
        assert riggbot.DEST_LANG == 'de'

    # defaults to 'en' if env var is missing
    def test_defaults_dest_lang(self, monkeypatch):
        monkeypatch.delenv('DEST_LANG', raising=False)
        riggbot.init_bot()
        assert riggbot.DEST_LANG == 'en'


class TestEnvManualOverrideLang:
    # can read manual override lang from env
    def test_loads_manual_override_lang_from_env(self, monkeypatch):
        monkeypatch.setenv('MANUAL_OVERRIDE_LANG', 'de')
        riggbot.init_bot()
        assert riggbot.MANUAL_OVERRIDE_LANG == 'de'

    # can strip whitespace from manual override lang env var
    def test_strips_whitespace_from_manual_override_lang(self, monkeypatch):
        monkeypatch.setenv('MANUAL_OVERRIDE_LANG', '   de   ')
        riggbot.init_bot()
        assert riggbot.MANUAL_OVERRIDE_LANG == 'de'

    # defaults to 'zh-CN' if env var is missing
    def test_defaults_manual_override_lang(self, monkeypatch):
        monkeypatch.delenv('MANUAL_OVERRIDE_LANG', raising=False)
        riggbot.init_bot()
        assert riggbot.MANUAL_OVERRIDE_LANG == 'zh-CN'

# ---------------------------------------------------------------------------
# Translation Tests
# ---------------------------------------------------------------------------


class TestTranslateText:
    """
    translate_text decision tree:
      - detected.lang != DEST_LANG, manual or not   → translate, return "lang→dest: text"
      - detected.lang == DEST_LANG, is_manual       → translate to MANUAL_OVERRIDE_LANG, return translated.text
      - detected.lang == DEST_LANG, not manual      → return None
      - exception raised                            → return None
    """

    # before each test, ensures global vars are set correctly
    @pytest.fixture(autouse=True)
    def setup_globals(self):
        riggbot.DEST_LANG = 'en'
        riggbot.MANUAL_OVERRIDE_LANG = 'zh-CN'

    # helper to create a mock translator with specified detect and translate behavior
    def _make_translator(self, detected_lang, translated_text='translated'):
        mock = MagicMock()
        mock.detect.return_value = MagicMock(lang=detected_lang)
        mock.translate.return_value = MagicMock(text=translated_text)
        return mock

    # if already dest lang, returns none when not manual
    async def test_returns_none_when_already_dest_lang_and_auto(self):
        riggbot.translator = self._make_translator('en')
        result = await riggbot.translate_text('hello', is_manual=False)
        assert result is None

    # basic translation of foreign text to dest lang, not manual
    async def test_translates_foreign_text_to_dest_lang(self):
        riggbot.translator = self._make_translator(
            'zh-CN', translated_text='hello')
        result = await riggbot.translate_text('你好', is_manual=False)
        assert result == 'zh-CN→en: hello'

    # basic translation of foreign text to dest lang, manual
    async def test_manual_translates_foreign_text_to_dest_lang(self):
        riggbot.translator = self._make_translator(
            'ja', translated_text='hello')
        result = await riggbot.translate_text('こんにちは', is_manual=True)
        assert result == 'ja→en: hello'

    # if already dest lang, returns manual override translation when manual
    async def test_manual_override_when_already_in_dest_lang(self):
        riggbot.translator = self._make_translator('en', translated_text='你好')
        result = await riggbot.translate_text('hello', is_manual=True)
        assert result == '你好'
        riggbot.translator.translate.assert_called_once_with(
            'hello', dest='zh-CN')

    # if translator raises an exception, just return none
    async def test_returns_none_on_exception(self):
        mock = MagicMock()
        mock.detect.side_effect = Exception('network error')
        riggbot.translator = mock
        result = await riggbot.translate_text('hello', is_manual=False)
        assert result is None

# ---------------------------------------------------------------------------
# process_embed TODO: check these again
# ---------------------------------------------------------------------------


class TestProcessEmbed:

    # before each test, ensures global vars are set correctly and sets up a default translator
    @pytest.fixture(autouse=True)
    def setup_globals(self):
        riggbot.DEST_LANG = 'en'
        riggbot.MANUAL_OVERRIDE_LANG = 'zh-CN'
        # Default translator: always reports zh-CN so a translation is always returned.
        # Must be MagicMock (not AsyncMock) because translate_text calls translator methods
        # via asyncio.to_thread(), which invokes them as plain synchronous callables.
        mock = MagicMock()
        mock.detect.return_value = MagicMock(lang='zh-CN')
        mock.translate.return_value = MagicMock(text='translated text')
        riggbot.translator = mock

    # helper to create a mock embed with specified description
    def _make_embed(self, description):
        embed = MagicMock()
        embed.to_dict.return_value = {
            'description': description} if description is not None else {}
        return embed

    # if no description key in embed, returns none
    async def test_returns_none_when_no_description_key(self):
        embed = self._make_embed(None)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is None

    # description key with empty string should also return none
    async def test_returns_none_when_description_is_empty_string(self):
        embed = self._make_embed('')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is None

    # single blob description is translated and prefixed with page emoji
    async def test_translates_single_blob_description(self):
        embed = self._make_embed('你好世界')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result  # [page emoji] for main text

    # Two-blob description: the regex splits on **[...](...)** style separators.
    # Four cases covering every combination of blobs needing / not needing translation.
    TWO_BLOB_DESC = 'main post text **[quoted/emoji](http://example.com)** quoted reply text'

    # Both blobs already in DEST_LANG → translate_text returns None for both → overall None
    async def test_two_blob_neither_needs_translation(self):
        mock = MagicMock()
        mock.detect.side_effect = [MagicMock(lang='en'), MagicMock(lang='en')]
        riggbot.translator = mock
        embed = self._make_embed(self.TWO_BLOB_DESC)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is None

    # First blob needs translation, second is already in DEST_LANG → only page emoji
    async def test_two_blob_only_first_needs_translation(self):
        mock = MagicMock()
        mock.detect.side_effect = [
            MagicMock(lang='zh-CN'), MagicMock(lang='en')]
        mock.translate.return_value = MagicMock(text='translated text')
        riggbot.translator = mock
        embed = self._make_embed(self.TWO_BLOB_DESC)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result     # [page emoji] first blob translated 
        assert '\U0001F4AC' not in result # [speech balloon] second blob NOT included

    # First blob is already in DEST_LANG, second needs translation → only speech bubble emoji
    async def test_two_blob_only_second_needs_translation(self):
        mock = MagicMock()
        mock.detect.side_effect = [
            MagicMock(lang='en'), MagicMock(lang='zh-CN')]
        mock.translate.return_value = MagicMock(text='translated text')
        riggbot.translator = mock
        embed = self._make_embed(self.TWO_BLOB_DESC)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' not in result # [page emoji] first blob NOT included
        assert '\U0001F4AC' in result     # [speech balloon] second blob translated

    # Both blobs need translation → both emojis present in result
    async def test_two_blob_both_need_translation(self):
        mock = MagicMock()
        mock.detect.side_effect = [
            MagicMock(lang='zh-CN'), MagicMock(lang='zh-CN')]
        mock.translate.return_value = MagicMock(text='translated text')
        riggbot.translator = mock
        embed = self._make_embed(self.TWO_BLOB_DESC)
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result     # [page emoji] first blob translated
        assert '\U0001F4AC' in result     # [speech balloon] second blob translated

    # if is_manual=True, should trigger manual override path in translate_text for both blobs
    async def test_passes_is_manual_flag_through(self):
        mock = MagicMock()
        mock.detect.return_value = MagicMock(lang='en')
        mock.translate.return_value = MagicMock(text='override translation')
        riggbot.translator = mock

        embed = self._make_embed('some english text')
        result = await riggbot.process_embed(embed, is_manual=True)
        assert result is not None
        mock.translate.assert_called_with('some english text', dest='zh-CN')
