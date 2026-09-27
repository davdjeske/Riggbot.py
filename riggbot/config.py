"""Bot settings.

Settings are merged in this order, lowest priority first:

    built-in defaults (the dataclasses below)  ->  config.json  ->  environment variables / .env

The bot never writes config.json; it's edited by hand. Secrets (the bot token and API keys)
are only read from the environment, never from config.json.

To add a setting: add a field (with a default) to the relevant dataclass below, and to
config.example.json. Loading and type-checking happen automatically.
"""
import dataclasses
import json
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
COLOR_MODES = ('auto', 'always', 'never')


class ConfigError(Exception):
    """config.json or the environment contains something the bot can't use."""


# region: Settings dataclasses

@dataclass
class LatibotSettings:
    user_id: int | None = None          # preferred way to recognize LatiBot
    name_fallback: str = 'latibot'      # used when user_id isn't set: substring of the username


@dataclass
class IsThisTrueSettings:
    phrases: list[str] = field(default_factory=lambda: ['riggbot is this true'])
    match_mention: bool = True          # also accept "@riggbot is this true"
    answers: list[str] = field(default_factory=lambda: ['Yes', 'No', 'Israel'])


@dataclass
class LatibotBanterSettings:
    dat_me_trigger: str = 'dat me!!'                # whole message, case-insensitive
    dat_me_reply: str = 'latibot→en:\nim a dumb bitch'
    mock_trigger: str = '"iM rIgGbOt!"'             # anywhere in the message, case-sensitive
    mock_reply: str = 'shut up nerd'


@dataclass
class ShutdownSettings:
    phrases: list[str] = field(default_factory=lambda: ['say goodbye riggbot', 'riggbot, kys'])
    farewells: list[str] = field(default_factory=lambda: ['Goodbye! \U0001F44B', "I'm riggbo- oh... okay..."])


@dataclass
class ResponsesSettings:
    is_this_true: IsThisTrueSettings = field(default_factory=IsThisTrueSettings)
    star_thanks: str = 'omg thank you so much'
    latibot_banter: LatibotBanterSettings = field(default_factory=LatibotBanterSettings)
    shutdown: ShutdownSettings = field(default_factory=ShutdownSettings)


@dataclass
class BreakerSettings:
    failures: int = 3                   # consecutive failures before a provider is skipped
    cooldown_minutes: float = 10


@dataclass
class LibreTranslateSettings:
    url: str = 'http://localhost:5000'


@dataclass
class TranslationSettings:
    providers: list[str] = field(default_factory=lambda: ['deepl', 'googletrans', 'libretranslate'])
    dest_lang: str = 'en'
    manual_override_lang: str = 'zh-CN'
    startup_self_test: bool = True
    breaker: BreakerSettings = field(default_factory=BreakerSettings)
    reaction_cooldown_seconds: float = 30
    libretranslate: LibreTranslateSettings = field(default_factory=LibreTranslateSettings)


@dataclass
class LoggingSettings:
    level: str = 'INFO'                 # console
    file_level: str = 'DEBUG'
    library_level: str = 'WARNING'      # discord.py, httpx, ...
    color: str = 'auto'                 # auto | always | never
    file: str = 'logs/riggbot.log'      # relative to the base directory
    max_bytes: int = 1_000_000
    backup_count: int = 3


def _internal(default_factory):
    """A field that is filled in by the loader, not read from config.json."""
    return field(default_factory=default_factory, metadata={'json': False}, compare=False)


@dataclass
class Settings:
    owner_ids: list[int] = field(default_factory=list)
    latibot: LatibotSettings = field(default_factory=LatibotSettings)
    responses: ResponsesSettings = field(default_factory=ResponsesSettings)
    translation: TranslationSettings = field(default_factory=TranslationSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)

    # Filled in by load_settings(); logged once logging is configured.
    sources: list[str] = _internal(list)
    warnings: list[str] = _internal(list)


@dataclass(repr=False)
class Secrets:
    token: str
    deepl_api_key: str | None = None
    libretranslate_api_key: str | None = None

    def __repr__(self) -> str:
        def mask(value):
            return '***' if value else None
        return (f'Secrets(token={mask(self.token)}, deepl_api_key={mask(self.deepl_api_key)}, '
                f'libretranslate_api_key={mask(self.libretranslate_api_key)})')

# endregion

# region: Loading


def load_settings(path: Path, env: Mapping[str, str]) -> Settings:
    """Build Settings from defaults, then `path` (if it exists), then `env`."""
    warnings = []
    sources = ['defaults']
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding='utf-8-sig'))
        except json.JSONDecodeError as e:
            raise ConfigError(f'{path.name} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}') from e
        settings = _build(Settings, raw, '')
        sources.append(str(path))
    else:
        settings = Settings()
        warnings.append(f'{path.name} not found; using built-in defaults (see config.example.json)')

    env_used = _apply_env(settings, env, warnings)
    if env_used:
        sources.append('env: ' + ', '.join(env_used))

    _validate(settings)
    settings.sources = sources
    settings.warnings = warnings
    return settings


def load_secrets(env: Mapping[str, str]) -> Secrets:
    token = _env(env, 'RIGGBOT_TOKEN')
    if not token:
        raise ConfigError('RIGGBOT_TOKEN is not set. Add the line RIGGBOT_TOKEN=your_bot_token to .env '
                          '(see .env.example).')
    return Secrets(
        token=token,
        deepl_api_key=_env(env, 'DEEPL_API_KEY'),
        libretranslate_api_key=_env(env, 'LIBRETRANSLATE_API_KEY'),
    )


def _env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, '').strip()
    return value or None


def _apply_env(settings: Settings, env: Mapping[str, str], warnings: list[str]) -> list[str]:
    """Apply environment overrides in place. Returns the names of the variables used."""
    used = []

    def take(name):
        value = _env(env, name)
        if value is not None:
            used.append(name)
        return value

    if value := take('DEST_LANG'):
        settings.translation.dest_lang = value
    if value := take('MANUAL_OVERRIDE_LANG'):
        settings.translation.manual_override_lang = value
    if value := take('TRANSLATION_PROVIDERS'):
        settings.translation.providers = [p.strip().lower() for p in value.split(',') if p.strip()]
    if value := take('LIBRETRANSLATE_URL'):
        settings.translation.libretranslate.url = value
    if value := take('LOG_LEVEL'):
        settings.logging.level = value.upper()
    if value := take('LOG_FILE_LEVEL'):
        settings.logging.file_level = value.upper()
    if value := take('LOG_COLOR'):
        settings.logging.color = value.lower()

    if _env(env, 'EMBED_BOT_NAME'):
        warnings.append('EMBED_BOT_NAME is set but no longer used: automatic translation of '
                        'embed-bot posts was removed. It can be deleted from .env.')
    return used


def _validate(settings: Settings) -> None:
    log = settings.logging
    for key in ('level', 'file_level', 'library_level'):
        value = getattr(log, key).upper()
        if value not in LOG_LEVELS:
            raise ConfigError(f'logging.{key} must be one of {", ".join(LOG_LEVELS)} (got "{value}")')
        setattr(log, key, value)
    if log.color not in COLOR_MODES:
        raise ConfigError(f'logging.color must be one of {", ".join(COLOR_MODES)} (got "{log.color}")')
    if log.max_bytes < 1 or log.backup_count < 0:
        raise ConfigError('logging.max_bytes must be positive and logging.backup_count not negative')

    tr = settings.translation
    tr.providers = [p.strip().lower() for p in tr.providers if p.strip()]
    if tr.breaker.failures < 1 or tr.breaker.cooldown_minutes < 0:
        raise ConfigError('translation.breaker.failures must be at least 1 and cooldown_minutes not negative')
    if tr.reaction_cooldown_seconds < 0:
        raise ConfigError('translation.reaction_cooldown_seconds must not be negative')
    if not tr.dest_lang.strip() or not tr.manual_override_lang.strip():
        raise ConfigError('translation.dest_lang and translation.manual_override_lang must not be empty')

    itt = settings.responses.is_this_true
    if not itt.answers:
        raise ConfigError('responses.is_this_true.answers must contain at least one answer')
    if not settings.responses.shutdown.farewells:
        raise ConfigError('responses.shutdown.farewells must contain at least one message')


def _build(cls, data: Any, where: str):
    """Create dataclass `cls` from a JSON object, rejecting unknown keys and wrong types."""
    if not isinstance(data, Mapping):
        raise ConfigError(f'{where.rstrip(".") or "config.json"} must be a JSON object')
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls) if f.metadata.get('json', True)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ConfigError(f'Unknown setting "{where}{unknown[0]}"')
    kwargs = {name: _coerce(hints[name], data[name], f'{where}{name}') for name in fields if name in data}
    return cls(**kwargs)


def _coerce(tp, value: Any, where: str):
    if dataclasses.is_dataclass(tp):
        return _build(tp, value, where + '.')

    origin = typing.get_origin(tp)
    if origin in (types.UnionType, typing.Union):   # only `X | None` is used
        if value is None:
            return None
        (inner,) = [arg for arg in typing.get_args(tp) if arg is not type(None)]
        return _coerce(inner, value, where)
    if origin is list:
        (item_type,) = typing.get_args(tp)
        if not isinstance(value, list):
            raise ConfigError(f'{where} must be a list')
        return [_coerce(item_type, item, f'{where}[{i}]') for i, item in enumerate(value)]

    if tp is bool and isinstance(value, bool):
        return value
    if tp is int and not isinstance(value, bool):
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():   # Discord IDs are often pasted as strings
            return int(value)
    if tp is float and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if tp is str and isinstance(value, str):
        return value
    raise ConfigError(f'{where} must be {_type_name(tp)} (got {json.dumps(value)})')


def _type_name(tp) -> str:
    return {bool: 'true/false', int: 'a whole number', float: 'a number', str: 'a string'}.get(tp, str(tp))

# endregion


def summary(settings: Settings, secrets: Secrets) -> str:
    """One-line description of the effective configuration, safe to log."""
    tr = settings.translation
    return (f'providers={",".join(tr.providers) or "(none)"} dest={tr.dest_lang} '
            f'override={tr.manual_override_lang} owners={len(settings.owner_ids)} '
            f'latibot_id={"set" if settings.latibot.user_id else "not set"} '
            f'deepl_key={"set" if secrets.deepl_api_key else "not set"} '
            f'log_level={settings.logging.level}')
