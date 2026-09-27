"""Behavior the cleanup must preserve (ported from the original characterization tests).

- "riggbot is this true" must behave exactly as it always has (creator requirement C1).
- Any reply containing 'trans' anywhere triggers a translation, including words like
  'transport'. This over-triggering is deliberate and must not be "fixed" (C2).
"""
import pytest

from riggbot.cogs import fun as fun_module
from riggbot.cogs.fun import Fun
from riggbot.cogs.translate import Translate

from .conftest import BOT_ID, make_message, make_user

IS_THIS_TRUE_ANSWERS = {'Yes', 'No', 'Israel'}


@pytest.fixture
def fun(bot):
    return Fun(bot)


@pytest.fixture
def translate(bot):
    return Translate(bot)


class TestIsThisTrue:

    @pytest.mark.parametrize('content', [
        'riggbot is this true',
        'RIGGBOT IS THIS TRUE?',
        'hey riggbot is this true or not',
        f'<@{BOT_ID}> is this true',
    ])
    async def test_answers_trigger_phrases(self, fun, content):
        message = make_message(content, reply_to=make_message('some claim'))
        await fun.on_message(message)
        message.reply.assert_awaited_once()
        args, kwargs = message.reply.call_args
        assert args[0] in IS_THIS_TRUE_ANSWERS
        assert kwargs.get('silent') is True

    async def test_picks_from_exactly_the_three_answers(self, fun, monkeypatch):
        offered = []
        monkeypatch.setattr(fun_module.random, 'choice', lambda seq: offered.append(list(seq)) or seq[0])
        await fun.on_message(make_message('riggbot is this true', reply_to=make_message('claim')))
        assert sorted(offered[0]) == sorted(IS_THIS_TRUE_ANSWERS)

    async def test_no_answer_when_replying_to_riggbot(self, fun, bot):
        target = make_message('I said this', author=bot.user)
        message = make_message('riggbot is this true', reply_to=target)
        await fun.on_message(message)
        message.reply.assert_not_awaited()

    async def test_no_answer_without_phrase(self, fun):
        message = make_message('is this true', reply_to=make_message('claim'))
        await fun.on_message(message)
        message.reply.assert_not_awaited()

    async def test_only_replies_get_an_answer(self, fun):
        message = make_message('riggbot is this true')
        await fun.on_message(message)
        message.reply.assert_not_awaited()

    async def test_answers_other_bots_too(self, fun):
        message = make_message('riggbot is this true', author=make_user(is_bot=True), reply_to=make_message('x'))
        await fun.on_message(message)
        message.reply.assert_awaited_once()

    async def test_no_answer_when_replied_to_message_is_gone(self, fun):
        message = make_message('riggbot is this true')
        message.type = make_message('', reply_to=make_message('x')).type
        message.reference = type('Ref', (), {'resolved': None, 'message_id': None})()
        await fun.on_message(message)
        message.reply.assert_not_awaited()


class TestTransReplyTrigger:

    @pytest.mark.parametrize('content', [
        'trans',
        'translate pls',
        'TRANS',
        'what a transport',       # deliberate over-trigger
        'transparent tbh',        # deliberate over-trigger
        'nice transfer window',   # deliberate over-trigger
    ])
    async def test_any_trans_substring_translates_referenced_message(self, translate, bot, content):
        target = make_message('bonjour')
        await translate.on_message(make_message(content, reply_to=target))
        bot.translation.translate_text.assert_awaited_once_with('bonjour', manual=True, source=None)
        target.reply.assert_awaited_once()

    async def test_no_translation_without_trans(self, translate, bot):
        await translate.on_message(make_message('what does this say', reply_to=make_message('bonjour')))
        bot.translation.translate_text.assert_not_awaited()
