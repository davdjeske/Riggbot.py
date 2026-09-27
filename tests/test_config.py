import json
from pathlib import Path

import pytest

from riggbot.config import ConfigError, Settings, load_secrets, load_settings

EXAMPLE = Path(__file__).resolve().parent.parent / 'config.example.json'


def write_config(tmp_path, data) -> Path:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


class TestDefaults:
    def test_missing_file_uses_defaults_with_warning(self, tmp_path):
        settings = load_settings(tmp_path / 'config.json', {})
        assert settings == Settings()
        assert any('not found' in w for w in settings.warnings)

    def test_example_file_matches_defaults(self):
        """config.example.json documents the defaults; keep them in sync."""
        assert load_settings(EXAMPLE, {}) == Settings()

    def test_is_this_true_defaults_are_unchanged(self):
        itt = Settings().responses.is_this_true
        assert itt.phrases == ['riggbot is this true']
        assert itt.match_mention is True
        assert itt.answers == ['Yes', 'No', 'Israel']


class TestMergeOrder:
    def test_file_overrides_defaults(self, tmp_path):
        path = write_config(tmp_path, {'translation': {'dest_lang': 'de'}})
        settings = load_settings(path, {})
        assert settings.translation.dest_lang == 'de'
        assert settings.translation.manual_override_lang == 'zh-CN'   # untouched default

    def test_env_overrides_file(self, tmp_path):
        path = write_config(tmp_path, {'translation': {'dest_lang': 'de'}, 'logging': {'level': 'INFO'}})
        env = {'DEST_LANG': ' fr ', 'LOG_LEVEL': 'debug', 'TRANSLATION_PROVIDERS': 'GoogleTrans, deepl,'}
        settings = load_settings(path, env)
        assert settings.translation.dest_lang == 'fr'
        assert settings.logging.level == 'DEBUG'
        assert settings.translation.providers == ['googletrans', 'deepl']
        assert 'env: DEST_LANG, TRANSLATION_PROVIDERS, LOG_LEVEL' in settings.sources

    def test_blank_env_values_are_ignored(self, tmp_path):
        settings = load_settings(tmp_path / 'config.json', {'DEST_LANG': '   '})
        assert settings.translation.dest_lang == 'en'

    def test_embed_bot_name_is_deprecated(self, tmp_path):
        settings = load_settings(tmp_path / 'config.json', {'EMBED_BOT_NAME': 'latibot'})
        assert any('EMBED_BOT_NAME' in w for w in settings.warnings)


class TestValidation:
    @pytest.mark.parametrize('data, message', [
        ({'nope': 1}, 'Unknown setting "nope"'),
        ({'translation': {'dest_langg': 'en'}}, 'Unknown setting "translation.dest_langg"'),
        ({'owner_ids': 'me'}, 'owner_ids must be a list'),
        ({'owner_ids': [True]}, 'owner_ids[0] must be a whole number'),
        ({'logging': {'level': 'LOUD'}}, 'logging.level must be one of'),
        ({'logging': {'color': 'rainbow'}}, 'logging.color must be one of'),
        ({'responses': {'is_this_true': {'answers': []}}}, 'answers must contain at least one'),
        ({'translation': {'breaker': {'failures': 0}}}, 'breaker.failures'),
        ([], 'must be a JSON object'),
    ])
    def test_rejects_bad_values(self, tmp_path, data, message):
        with pytest.raises(ConfigError, match=message.replace('[', r'\[').replace(']', r'\]')):
            load_settings(write_config(tmp_path, data), {})

    def test_invalid_json_names_the_line(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text('{\n  "owner_ids": [1,]\n}', encoding='utf-8')
        with pytest.raises(ConfigError, match='line 2'):
            load_settings(path, {})

    def test_ids_may_be_strings(self, tmp_path):
        path = write_config(tmp_path, {'owner_ids': ['123456789012345678'], 'latibot': {'user_id': '42'}})
        settings = load_settings(path, {})
        assert settings.owner_ids == [123456789012345678]
        assert settings.latibot.user_id == 42

    def test_utf8_bom_is_accepted(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text('{"owner_ids": [1]}', encoding='utf-8-sig')
        assert load_settings(path, {}).owner_ids == [1]


class TestSecrets:
    def test_token_required(self):
        with pytest.raises(ConfigError, match='RIGGBOT_TOKEN'):
            load_secrets({'RIGGBOT_TOKEN': '  '})

    def test_loads_and_strips(self):
        secrets = load_secrets({'RIGGBOT_TOKEN': ' tok ', 'DEEPL_API_KEY': 'key:fx'})
        assert secrets.token == 'tok'
        assert secrets.deepl_api_key == 'key:fx'
        assert secrets.libretranslate_api_key is None

    def test_repr_hides_values(self):
        secrets = load_secrets({'RIGGBOT_TOKEN': 'supersecret', 'DEEPL_API_KEY': 'alsosecret'})
        assert 'secret' not in repr(secrets)
