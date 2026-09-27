"""Tests for posting logs to a Discord channel."""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from riggbot.config import ConfigError, load_settings
from riggbot.log_channel import DiscordLogHandler, pack_lines


def make_channel(can_send=True):
    channel = MagicMock(name='log channel')
    channel.name = 'bot-logs'
    channel.guild = SimpleNamespace(name='test guild', me=object())
    channel.permissions_for = MagicMock(return_value=SimpleNamespace(view_channel=True, send_messages=can_send))
    channel.send = AsyncMock()
    return channel


def make_bot(channel):
    return SimpleNamespace(get_channel=MagicMock(return_value=channel), fetch_channel=AsyncMock(),
                           wait_until_ready=AsyncMock())


def record(msg, level=logging.INFO, name='riggbot.test'):
    return logging.LogRecord(name, level, __file__, 1, msg, None, None)


async def flush(handler):
    """Let the event loop hand over logged lines (see emit), then post them."""
    await asyncio.sleep(0)
    await handler.flush_now()


def posted_text(channel) -> str:
    return '\n'.join(call.args[0] for call in channel.send.await_args_list)


@pytest.fixture
async def handler_and_channel():
    channel = make_channel()
    handler = DiscordLogHandler(make_bot(channel), interval=3600)
    handler.configure(123, 'INFO')
    handler.start()
    yield handler, channel
    await handler.aclose()


class TestPackLines:
    def test_one_code_block_per_message(self):
        (message,) = pack_lines(['first', 'second'])
        assert message == '```ansi\nfirst\nsecond\n```'

    def test_splits_under_discord_limit(self):
        messages = pack_lines(['x' * 900] * 5)
        assert len(messages) == 3 and all(len(m) <= 2000 for m in messages)

    def test_truncates_huge_lines(self):
        (message,) = pack_lines(['y' * 5000])
        assert len(message) <= 2000 and '…' in message

    def test_backtick_fences_cannot_break_out(self):
        (message,) = pack_lines(['a ``` b'])
        assert message.count('```') == 2


class TestDiscordLogHandler:
    async def test_posts_collected_lines(self, handler_and_channel):
        handler, channel = handler_and_channel
        handler.handle(record('hello'))
        handler.handle(record('world', logging.WARNING))
        await flush(handler)
        text = posted_text(channel)
        assert '[info]' in text and 'hello' in text and '[warning]' in text and 'world' in text
        assert channel.send.await_args.kwargs['allowed_mentions'].everyone is False

    async def test_level_filter(self, handler_and_channel):
        handler, channel = handler_and_channel
        logger = logging.getLogger('riggbot.test_level_filter')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            logger.debug('too detailed')
            logger.info('worth posting')
        finally:
            logger.removeHandler(handler)
        await flush(handler)
        text = posted_text(channel)
        assert 'worth posting' in text and 'too detailed' not in text

    async def test_lines_before_start_are_kept(self):
        channel = make_channel()
        handler = DiscordLogHandler(make_bot(channel), interval=3600)
        handler.configure(123, 'INFO')
        handler.handle(record('starting up'))       # before start(): the bot isn't running yet
        handler.start()
        await handler.flush_now()
        assert 'starting up' in posted_text(channel)
        await handler.aclose()

    async def test_does_not_forward_its_own_sending(self, handler_and_channel):
        """discord.py logging while riggbot posts logs must not be posted again (endless loop)."""
        handler, channel = handler_and_channel

        async def send_and_log(*args, **kwargs):
            handler.handle(record('rate limited!', logging.WARNING, 'discord.http'))
        channel.send.side_effect = send_and_log

        handler.handle(record('original'))
        await flush(handler)
        assert channel.send.await_count == 1
        await flush(handler)                        # nothing new may have been queued by the send
        assert channel.send.await_count == 1

    async def test_other_logging_during_send_would_be_queued(self, handler_and_channel):
        """Control for the test above: the same record logged outside a send IS posted."""
        handler, channel = handler_and_channel
        handler.handle(record('rate limited!', logging.WARNING, 'discord.http'))
        await flush(handler)
        assert 'rate limited!' in posted_text(channel)

    async def test_drops_oldest_when_too_many(self):
        channel = make_channel()
        handler = DiscordLogHandler(make_bot(channel), interval=3600, max_pending=3)
        handler.configure(123, 'INFO')
        for i in range(5):
            handler.handle(record(f'line {i}'))
        handler.start()
        await handler.flush_now()
        text = posted_text(channel)
        assert '(2 earlier log lines were dropped)' in text and 'line 0' not in text and 'line 4' in text
        await handler.aclose()

    async def test_unusable_channel_disables_posting(self, caplog):
        channel = make_channel(can_send=False)
        handler = DiscordLogHandler(make_bot(channel), interval=3600)
        handler.configure(123, 'INFO')
        handler.start()
        handler.handle(record('x'))
        with caplog.at_level(logging.WARNING):
            await flush(handler)
        channel.send.assert_not_awaited()
        assert 'Log channel disabled' in caplog.text
        await handler.aclose()

    async def test_missing_channel_disables_posting(self, caplog):
        bot = make_bot(None)
        bot.get_channel.return_value = None
        bot.fetch_channel.side_effect = discord.NotFound(MagicMock(status=404), 'Unknown Channel')
        handler = DiscordLogHandler(bot, interval=3600)
        handler.configure(123, 'INFO')
        handler.start()
        handler.handle(record('x'))
        with caplog.at_level(logging.WARNING):
            await flush(handler)
        assert 'not found' in caplog.text
        await handler.aclose()

    async def test_turning_off_discards_lines(self, handler_and_channel):
        handler, channel = handler_and_channel
        handler.handle(record('x'))
        handler.configure(None, 'INFO')
        await flush(handler)
        channel.send.assert_not_awaited()

    async def test_close_posts_whats_left(self):
        channel = make_channel()
        handler = DiscordLogHandler(make_bot(channel), interval=3600)
        handler.configure(123, 'INFO')
        handler.handle(record('goodbye'))
        handler.start()
        await handler.aclose()
        assert 'goodbye' in posted_text(channel)


class TestSettings:
    def test_defaults_off(self, tmp_path):
        settings = load_settings(tmp_path / 'config.json', {})
        assert settings.logging.discord_channel_id is None and settings.logging.discord_level == 'INFO'

    def test_env_overrides(self, tmp_path):
        settings = load_settings(tmp_path / 'config.json',
                                 {'LOG_DISCORD_CHANNEL_ID': '987654321', 'LOG_DISCORD_LEVEL': 'warning'})
        assert settings.logging.discord_channel_id == 987654321 and settings.logging.discord_level == 'WARNING'

    def test_env_can_turn_it_off(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text('{"logging": {"discord_channel_id": 5}}', encoding='utf-8')
        assert load_settings(path, {'LOG_DISCORD_CHANNEL_ID': 'off'}).logging.discord_channel_id is None

    def test_bad_level_rejected(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text('{"logging": {"discord_level": "chatty"}}', encoding='utf-8')
        with pytest.raises(ConfigError, match='discord_level'):
            load_settings(path, {})
