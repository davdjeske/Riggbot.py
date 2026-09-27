"""Fakes for testing cogs without connecting to Discord."""
import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from riggbot.config import Settings
from riggbot.storage import GuildStore, JsonStore, read_default

BOT_ID = 1293252648803237899
GUILD_ID = 555
_ids = itertools.count(1000)


@pytest.fixture
def bot(tmp_path):
    fake = SimpleNamespace()
    fake.user = SimpleNamespace(id=BOT_ID, name='riggbot', bot=True)
    fake.settings = Settings()
    fake.guild_store = GuildStore(tmp_path / 'guilds')
    fake.flag_store = JsonStore(tmp_path / 'flag_lang_map.json', initial=lambda: read_default('flag_lang_map.json'))
    fake.translation = MagicMock(enabled=True)
    fake.translation.translate_text = AsyncMock(return_value='translated')
    fake.translation.translate_post = AsyncMock(return_value='translated post')
    fake.close = AsyncMock()
    fake.latency = 0.042
    return fake


def make_user(user_id=None, name='someone', is_bot=False):
    return SimpleNamespace(id=user_id or next(_ids), name=name, bot=is_bot, mention=f'<@{user_id}>')


def make_message(content='', *, author=None, guild_id=GUILD_ID, reply_to=None, embeds=(), webhook_id=None,
                 reactions=()):
    message = MagicMock(name='message')
    message.id = next(_ids)
    message.content = content
    message.author = author or make_user()
    message.webhook_id = webhook_id
    message.guild = SimpleNamespace(id=guild_id, name='test guild') if guild_id else None
    message.channel = MagicMock(name='channel')
    message.channel.name = 'general'
    message.channel.send = AsyncMock()
    message.reply = AsyncMock()
    message.embeds = list(embeds)
    message.reactions = list(reactions)
    if reply_to is not None:
        message.type = discord.MessageType.reply
        message.reference = SimpleNamespace(resolved=reply_to, message_id=getattr(reply_to, 'id', None))
    else:
        message.type = discord.MessageType.default
        message.reference = None
    return message


def make_interaction(user=None, guild_id=GUILD_ID):
    interaction = MagicMock(name='interaction')
    interaction.user = user or make_user(name='commander')
    interaction.guild_id = guild_id
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def sent_text(mock: AsyncMock) -> str:
    """The text of the last send/reply call on `mock`."""
    return mock.call_args.args[0] if mock.call_args.args else mock.call_args.kwargs.get('content')
