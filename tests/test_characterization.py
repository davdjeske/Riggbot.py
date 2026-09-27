"""Characterization tests that lock in behavior the cleanup must preserve.

- "riggbot is this true" must behave exactly as it always has (creator requirement C1).
- Any reply containing 'trans' anywhere triggers a translation, including words like
  'transport'. This over-triggering is deliberate and must not be "fixed" (C2).
"""
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import riggbot

BOT_ID = 1293252648803237899
IS_THIS_TRUE_ANSWERS = {'Yes', 'No', 'Israel'}


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    client = MagicMock()
    client.user = MagicMock(name='riggbot_user', id=BOT_ID)
    monkeypatch.setattr(riggbot, 'client', client)
    return client


@pytest.fixture
def process_message(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(riggbot, 'process_message', mock)
    return mock


def make_reply(content, ref_author=None):
    ref_msg = MagicMock(name='referenced_message')
    ref_msg.author = ref_author if ref_author is not None else MagicMock(name='someone_else')
    message = MagicMock(name='reply_message')
    message.content = content
    message.author = MagicMock(name='replier')
    message.reference = MagicMock(resolved=ref_msg)
    message.reply = AsyncMock()
    return message, ref_msg


# ---------------------------------------------------------------------------
# "riggbot is this true" (C1)
# ---------------------------------------------------------------------------

class TestIsThisTrue:

    @pytest.mark.parametrize('content', [
        'riggbot is this true',
        'RIGGBOT IS THIS TRUE?',
        'hey riggbot is this true or not',
        f'<@{BOT_ID}> is this true',
    ])
    async def test_answers_trigger_phrases(self, content, process_message):
        message, _ = make_reply(content)
        await riggbot.handle_reply(message)
        message.reply.assert_awaited_once()
        args, kwargs = message.reply.call_args
        assert args[0] in IS_THIS_TRUE_ANSWERS
        assert kwargs.get('silent') is True

    async def test_picks_from_exactly_the_three_answers(self, monkeypatch, process_message):
        offered = []
        monkeypatch.setattr(riggbot.random, 'choice', lambda seq: offered.append(list(seq)) or seq[0])
        message, _ = make_reply('riggbot is this true')
        await riggbot.handle_reply(message)
        assert sorted(offered[0]) == sorted(IS_THIS_TRUE_ANSWERS)

    async def test_no_answer_when_replying_to_riggbot(self, fake_client, process_message):
        message, _ = make_reply('riggbot is this true', ref_author=fake_client.user)
        await riggbot.handle_reply(message)
        message.reply.assert_not_awaited()

    async def test_no_answer_without_phrase(self, process_message):
        message, _ = make_reply('is this true')
        await riggbot.handle_reply(message)
        message.reply.assert_not_awaited()

    async def test_only_replies_reach_the_handler(self, monkeypatch):
        """A plain (non-reply) message with the phrase gets no answer."""
        handle_reply = AsyncMock()
        monkeypatch.setattr(riggbot, 'handle_reply', handle_reply)
        monkeypatch.setattr(riggbot, 'EMBED_BOT_NAME', '')
        message = MagicMock()
        message.author = MagicMock()
        message.author.name = 'someone'
        message.webhook_id = None
        message.type = discord.MessageType.default
        message.content = 'riggbot is this true'
        message.channel.send = AsyncMock()
        await riggbot.on_message(message)
        handle_reply.assert_not_awaited()


# ---------------------------------------------------------------------------
# 'trans' reply trigger (C2)
# ---------------------------------------------------------------------------

class TestTransReplyTrigger:

    @pytest.mark.parametrize('content', [
        'trans',
        'translate pls',
        'TRANS',
        'what a transport',       # deliberate over-trigger
        'transparent tbh',        # deliberate over-trigger
        'nice transfer window',   # deliberate over-trigger
    ])
    async def test_any_trans_substring_translates_referenced_message(self, content, process_message):
        message, ref_msg = make_reply(content)
        await riggbot.handle_reply(message)
        process_message.assert_awaited_once_with(ref_msg, is_manual=True)

    async def test_no_translation_without_trans(self, process_message):
        message, _ = make_reply('what does this say')
        await riggbot.handle_reply(message)
        process_message.assert_not_awaited()
