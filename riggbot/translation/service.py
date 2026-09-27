"""TranslationService: the provider chain plus riggbot's translation rules.

Providers are tried in order. One that fails `breaker.failures` times in a row is paused for
`breaker.cooldown_minutes`, so a blocked provider doesn't slow down every request.
(This pattern is called a "circuit breaker", like the one in a fuse box.)
"""
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from ..config import TranslationSettings
from ..embed_text import split_description
from .base import ProviderUnavailableError, TranslationError, TranslationProvider, TranslationResult, \
    UnsupportedLanguageError
from .languages import normalize, same_language

log = logging.getLogger(__name__)

# Put in front of translated embed text: the main post and a quoted post.
MAIN_POST_ICON = '\U0001F4C4'      # 📄
QUOTED_POST_ICON = '\U0001F4AC'    # 💬

# Matches markdown links: [label](url)
_MARKDOWN_LINK = re.compile(r'\[(.*?)\]\(.*?\)')


class NoProviderAvailable(TranslationError):
    """Every provider failed, was paused, or doesn't support the languages involved."""


def strip_markdown_links(text: str) -> str:
    """Replace [label](url) with the label, so translations don't create link embeds or pings."""
    return _MARKDOWN_LINK.sub(r'\1', text)


@dataclass
class _Breaker:
    """Failure bookkeeping for one provider."""
    failures: int = 0               # failures in a row so far
    paused_until: float = 0.0       # clock time until which the provider is skipped


class TranslationService:
    """What the rest of the bot uses to translate. Cogs reach it as `self.bot.translation`."""

    def __init__(self, providers: Sequence[TranslationProvider], settings: Callable[[], TranslationSettings],
                 clock: Callable[[], float] = time.monotonic):
        """`settings` returns the current TranslationSettings (it changes on /reload)."""
        self._settings = settings
        self._clock = clock             # replaceable so tests can fake the passing of time
        self.providers: list[TranslationProvider] = []
        self._breakers: dict[str, _Breaker] = {}    # provider name -> its failure bookkeeping
        self._set_providers(providers)

    @property
    def enabled(self) -> bool:
        """False when no provider is usable at all (translation is effectively off)."""
        return bool(self.providers)

    def _set_providers(self, providers: Sequence[TranslationProvider]) -> None:
        self.providers = list(providers)
        self._breakers = {p.name: _Breaker() for p in self.providers}

    async def replace_providers(self, providers: Sequence[TranslationProvider]) -> None:
        """Switch to a new list of providers (at startup and on /reload), closing the old ones."""
        old = self.providers
        self._set_providers(providers)
        await _close_all(old)

    async def aclose(self) -> None:
        """Close all providers' network connections (on shutdown)."""
        await _close_all(self.providers)

    # region: Provider chain

    async def translate(self, text: str, target: str, source: str | None = None) -> TranslationResult:
        """Translate with the first provider that can. Raises NoProviderAvailable if none can."""
        problems = []       # why each provider was skipped, for the error message if all fail
        for provider in self.providers:
            # Skip providers that are paused after failing repeatedly.
            breaker = self._breakers[provider.name]
            remaining = breaker.paused_until - self._clock()
            if remaining > 0:
                log.debug('Skipping %s: paused for another %.0f s', provider.name, remaining)
                problems.append(f'{provider.name}: paused')
                continue
            # Skip providers that already know they can't handle these languages (no request needed).
            if not provider.supports(target) or (source and not provider.supports(source)):
                log.debug('Skipping %s: does not support %s→%s', provider.name, source or 'auto', target)
                problems.append(f'{provider.name}: unsupported language')
                continue

            started = self._clock()
            try:
                result = await provider.translate(text, target, source)
            except UnsupportedLanguageError as e:
                # Not the provider's fault: move on, but don't count it as a failure.
                log.debug('%s cannot translate %s→%s: %s', provider.name, source or 'auto', target, e)
                problems.append(f'{provider.name}: unsupported language')
                continue
            except ProviderUnavailableError as e:
                # Blocked, rate-limited, offline...: counts toward pausing the provider.
                self._record_failure(provider.name, str(e))
                problems.append(f'{provider.name}: {e}')
                continue
            except Exception as e:     # a provider bug shouldn't break the whole chain
                log.exception('%s raised an unexpected error', provider.name)
                self._record_failure(provider.name, f'{type(e).__name__}: {e}')
                problems.append(f'{provider.name}: {type(e).__name__}')
                continue

            # Success: reset the failure count and hand back the result.
            breaker.failures = 0
            log.info('Translated %s→%s via %s (%d chars, %.0f ms)', result.source_lang, result.target_lang,
                     provider.name, len(text), (self._clock() - started) * 1000)
            return result

        raise NoProviderAvailable('; '.join(problems) or 'no translation provider is configured')

    def _record_failure(self, name: str, error: str) -> None:
        """Count a failure; pause the provider once it has failed too many times in a row."""
        config = self._settings().breaker
        breaker = self._breakers[name]
        breaker.failures += 1
        if breaker.failures >= config.failures:
            breaker.failures = 0
            breaker.paused_until = self._clock() + config.cooldown_minutes * 60
            log.warning('%s failed %d times in a row (%s); pausing it for %g minutes',
                        name, config.failures, error, config.cooldown_minutes)
        else:
            log.warning('%s failed (%s)', name, error)

    # endregion

    # region: Riggbot's translation rules

    async def translate_text(self, text: str, *, manual: bool = False, source: str | None = None) -> str | None:
        """Translate one piece of text the riggbot way. Returns what to post, or None.

        - Not in dest_lang:                 "<src>→<dest>:\\n<translation>"
        - Already in dest_lang, manual:     the text translated into manual_override_lang, or, with
                                            `source` (from a flag reaction), from `source` into dest_lang
        - Already in dest_lang, automatic:  None

        Raises TranslationError if no provider could translate.
        """
        config = self._settings()
        text = strip_markdown_links(text).strip()
        if not text:
            return None
        log.debug('Translating (manual=%s, source=%s): %r', manual, source, text)

        # Step 1: translate into dest_lang. The provider also tells us what language the text was in.
        dest = normalize(config.dest_lang)
        result = await self.translate(text, dest)
        if not same_language(result.source_lang, dest):
            # Foreign text: show the translation with a "ja→en:" header.
            output = f'{result.source_lang}→{dest}:\n{result.text}'
        elif not manual:
            # Already in dest_lang and nobody asked: nothing to say.
            log.debug('Already in %s; nothing to do', dest)
            return None
        elif source:
            # Already "in dest_lang" according to detection, but a flag reaction says it's really
            # `source`: translate again, telling the provider the source language.
            output = (await self.translate(text, dest, source=normalize(source))).text
        else:
            # Someone asked to translate text that's already in dest_lang: use the override language.
            output = (await self.translate(text, normalize(config.manual_override_lang))).text

        # googletrans sometimes renders quotation marks as ``, which breaks Discord markdown.
        return output.replace('``', '"')

    async def translate_post(self, description: str, *, manual: bool = False,
                             source: str | None = None) -> str | None:
        """Translate an embed description: the main post (📄) and a quoted post (💬), if any."""
        main, quoted = split_description(description)
        parts = []
        # (`:=` assigns and tests in one go: only add a part when there's a translation.)
        if main and (translated := await self.translate_text(main, manual=manual, source=source)):
            parts.append(f'{MAIN_POST_ICON} {translated}')
        if quoted and (translated := await self.translate_text(quoted, manual=manual, source=source)):
            parts.append(f'{QUOTED_POST_ICON} {translated}')
        return '\n\n'.join(parts) or None

    async def self_test(self) -> None:
        """Try each provider once and log whether it works. Doesn't affect the circuit breaker."""
        for provider in list(self.providers):
            started = self._clock()
            try:
                # Ask each provider directly (not through the chain) to translate German "hallo".
                result = await provider.translate('hallo', 'en', source='de')
            except TranslationError as e:
                log.warning('Self-test: %s is not working (%s)', provider.name, e)
                continue
            except Exception as e:
                log.warning('Self-test: %s raised %s: %s', provider.name, type(e).__name__, e)
                continue
            elapsed = (self._clock() - started) * 1000
            # Accept "Hello", "hello!", "Hello." ...
            if result.text.strip().strip('!.').lower() == 'hello':
                log.info('Self-test: %s works (%.0f ms)', provider.name, elapsed)
            else:
                log.warning('Self-test: %s answered %r instead of "hello"', provider.name, result.text)

    # endregion


async def _close_all(providers: Sequence[TranslationProvider]) -> None:
    """Close each provider, ignoring errors (we're done with them either way)."""
    for provider in providers:
        try:
            await provider.aclose()
        except Exception:
            log.debug('Error closing %s', provider.name, exc_info=True)
