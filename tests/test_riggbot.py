import pytest
from unittest.mock import AsyncMock, MagicMock
import riggbot


# ---------------------------------------------------------------------------
# region Env Loading Tests
# ---------------------------------------------------------------------------
''' 
Tests for loading configuration from environment variables. These tests ensure that
the env vars are read corrrectly, whitespace is stripped, and defaults are applied when vars are missing.
For BOT_TOKEN, also tests that a FileNotFoundError is raised if the token is missing or empty,
since it's required for the bot to function.
'''
class TestBotToken:
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


class TestEmbedBot:
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


class TestDestLang:
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


class TestManualOverrideLang:
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
# endregion

# ---------------------------------------------------------------------------
# region Translation Tests TODO: check these again
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
# endregion

# ---------------------------------------------------------------------------
# process_embed TODO: check these again
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
        assert '\U0001F4C4' in result  # [page emoji] prefix for main text

    async def test_translates_two_blob_description(self):
        # The regex splits on **[...](...)** style separators
        embed = self._make_embed(
            'main post text **[quoted/emoji](http://example.com)** quoted reply text')
        result = await riggbot.process_embed(embed, is_manual=False)
        assert result is not None
        assert '\U0001F4C4' in result   # [page emoji] main blob
        assert '\U0001F4AC' in result   # [speech balloon emoji] quoted blob       

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
