from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from riggbot import checks
from riggbot.cogs import fun as fun_module
from riggbot.cogs import translate as translate_module
from riggbot.cogs.bots import Bots, approved_bot_ids
from riggbot.cogs.fun import STAR, Fun
from riggbot.cogs.langflags import LangFlags, validate_flag
from riggbot.cogs.translate import NOTHING_TO_TRANSLATE, TRANSLATE_EMOJI, TRANSLATION_DOWN, Translate
from riggbot.cogs.triggers import Trigger, Triggers
from riggbot.storage import GuildStore
from riggbot.translation.service import NoProviderAvailable

from .conftest import BOT_ID, GUILD_ID, make_interaction, make_message, make_user, sent_text


# ---------------------------------------------------------------------------
# Translate cog
# ---------------------------------------------------------------------------

def reaction_payload(emoji, *, user_id=42, message_author_id=7):
    return SimpleNamespace(emoji=emoji, user_id=user_id, message_author_id=message_author_id,
                           channel_id=1, message_id=2)


class TestTranslateCog:
    @pytest.fixture
    def cog(self, bot):
        return Translate(bot)

    @pytest.fixture
    def reacted(self, monkeypatch):
        """The message a reaction points at; its 🏳️‍⚧️ count starts at 1."""
        message = make_message('hola', reactions=[SimpleNamespace(emoji=TRANSLATE_EMOJI, count=1)])
        monkeypatch.setattr(translate_module, 'fetch_reaction_message', AsyncMock(return_value=message))
        return message

    async def test_prefers_embed_description(self, cog, bot):
        target = make_message('link', embeds=[SimpleNamespace(description='post text')])
        await cog.translate_message(target)
        bot.translation.translate_post.assert_awaited_once_with('post text', manual=True, source=None)
        assert sent_text(target.reply) == 'translated post'

    async def test_falls_back_to_content_when_embed_has_no_text(self, cog, bot):
        target = make_message('hola', embeds=[SimpleNamespace(description=None)])
        await cog.translate_message(target)
        bot.translation.translate_text.assert_awaited_once_with('hola', manual=True, source=None)

    async def test_nothing_to_translate(self, cog, bot):
        bot.translation.translate_text.return_value = None
        target = make_message('hello')
        await cog.translate_message(target)
        assert sent_text(target.reply) == NOTHING_TO_TRANSLATE

    async def test_provider_failure_message(self, cog, bot):
        bot.translation.translate_text.side_effect = NoProviderAvailable('all down')
        target = make_message('hola')
        await cog.translate_message(target)
        assert sent_text(target.reply) == TRANSLATION_DOWN

    async def test_translation_disabled(self, cog, bot):
        bot.translation.enabled = False
        target = make_message('hola')
        await cog.translate_message(target)
        assert sent_text(target.reply) == TRANSLATION_DOWN

    async def test_long_result_is_split(self, cog, bot):
        bot.translation.translate_text.return_value = 'x' * 1500 + '\n' + 'y' * 1500
        target = make_message('hola')
        await cog.translate_message(target)
        target.reply.assert_awaited_once()
        target.channel.send.assert_awaited_once()

    async def test_ignores_own_and_webhook_replies(self, cog, bot):
        await cog.on_message(make_message('trans', author=bot.user, reply_to=make_message('x')))
        await cog.on_message(make_message('trans', webhook_id=9, reply_to=make_message('x')))
        bot.translation.translate_text.assert_not_awaited()

    async def test_reaction_translates(self, cog, bot, reacted):
        await cog.on_raw_reaction_add(reaction_payload(TRANSLATE_EMOJI))
        bot.translation.translate_text.assert_awaited_once_with('hola', manual=True, source=None)

    async def test_flag_reaction_passes_source(self, cog, bot, reacted):
        reacted.reactions = [SimpleNamespace(emoji='🇯🇵', count=1)]
        await cog.on_raw_reaction_add(reaction_payload('🇯🇵'))
        bot.translation.translate_text.assert_awaited_once_with('hola', manual=True, source='ja')

    async def test_only_first_reaction_counts(self, cog, bot, reacted):
        reacted.reactions[0].count = 2
        await cog.on_raw_reaction_add(reaction_payload(TRANSLATE_EMOJI))
        bot.translation.translate_text.assert_not_awaited()

    async def test_readding_within_cooldown_is_ignored(self, cog, bot, reacted):
        await cog.on_raw_reaction_add(reaction_payload(TRANSLATE_EMOJI))
        await cog.on_raw_reaction_add(reaction_payload(TRANSLATE_EMOJI))
        assert bot.translation.translate_text.await_count == 1

    async def test_unrelated_emoji_does_not_fetch(self, cog, bot, reacted):
        await cog.on_raw_reaction_add(reaction_payload('😂'))
        translate_module.fetch_reaction_message.assert_not_awaited()

    async def test_reactions_on_riggbot_messages_are_ignored(self, cog, bot, reacted):
        await cog.on_raw_reaction_add(reaction_payload(TRANSLATE_EMOJI, message_author_id=BOT_ID))
        bot.translation.translate_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# Fun cog (is-this-true is covered in test_behavior_lock.py)
# ---------------------------------------------------------------------------

class TestFunCog:
    @pytest.fixture
    def cog(self, bot):
        return Fun(bot)

    async def test_dat_me_banter_by_name(self, cog):
        message = make_message('DAT ME!!', author=make_user(name='LatiBot', is_bot=True))
        await cog.on_message(message)
        assert sent_text(message.reply) == 'latibot→en:\nim a dumb bitch'

    async def test_mock_banter(self, cog):
        message = make_message('"iM rIgGbOt!" lol', author=make_user(name='latibot', is_bot=True))
        await cog.on_message(message)
        assert sent_text(message.channel.send) == 'shut up nerd'

    async def test_banter_uses_configured_id(self, cog, bot):
        bot.settings.latibot.user_id = 77
        impostor = make_message('dat me!!', author=make_user(name='latibot', is_bot=True))
        real = make_message('dat me!!', author=make_user(user_id=77, name='renamed', is_bot=True))
        await cog.on_message(impostor)
        await cog.on_message(real)
        impostor.reply.assert_not_awaited()
        real.reply.assert_awaited_once()

    async def test_banter_ignores_others(self, cog):
        message = make_message('dat me!!')
        await cog.on_message(message)
        message.reply.assert_not_awaited()

    async def test_owner_goodbye(self, cog, bot):
        bot.settings.owner_ids = [11]
        message = make_message('ok riggbot, kys', author=make_user(user_id=11))
        await cog.on_message(message)
        assert sent_text(message.channel.send) in bot.settings.responses.shutdown.farewells
        bot.close.assert_awaited_once()

    async def test_goodbye_from_non_owner_is_ignored(self, cog, bot):
        bot.settings.owner_ids = [11]
        message = make_message('say goodbye riggbot', author=make_user(user_id=12))
        await cog.on_message(message)
        bot.close.assert_not_awaited()

    async def test_star_thanks(self, cog, bot, monkeypatch):
        message = make_message('I am riggbot', author=bot.user, reactions=[SimpleNamespace(emoji=STAR, count=1)])
        monkeypatch.setattr(fun_module, 'fetch_reaction_message', AsyncMock(return_value=message))
        await cog.on_raw_reaction_add(reaction_payload(STAR, message_author_id=BOT_ID))
        message.channel.send.assert_awaited_once_with('omg thank you so much', silent=True)

    async def test_star_on_other_messages_is_ignored(self, cog, monkeypatch):
        fetch = AsyncMock()
        monkeypatch.setattr(fun_module, 'fetch_reaction_message', fetch)
        await cog.on_raw_reaction_add(reaction_payload(STAR, message_author_id=7))
        fetch.assert_not_awaited()


# ---------------------------------------------------------------------------
# Triggers and approved bots
# ---------------------------------------------------------------------------

class TestTriggerMatching:
    @pytest.mark.parametrize('trigger, content, expected', [
        (Trigger('beer', 'r'), 'I love BEERS', True),
        (Trigger('weed', 'r'), 'nice tweed jacket', True),          # contains: inside words too
        (Trigger('weed', 'r', match='word'), 'nice tweed jacket', False),
        (Trigger('weed', 'r', match='word'), 'weed?', True),
        (Trigger('one piece', 'r', match='word'), 'the One Piece is real', True),
        (Trigger('hi', 'r', match='exact'), '  HI ', True),
        (Trigger('hi', 'r', match='exact'), 'hi there', False),
    ])
    def test_modes(self, trigger, content, expected):
        assert trigger.matches(content) is expected


class TestTriggersCog:
    @pytest.fixture
    def cog(self, bot):
        return Triggers(bot)

    async def test_new_server_gets_default_triggers(self, cog):
        phrases = [t.phrase for t in cog.triggers(GUILD_ID)]
        assert phrases[:3] == ['beer', 'weed', 'awaga'] and phrases[-1] == 'riggbot'

    async def test_each_match_sends_a_response_in_order(self, cog):
        message = make_message('beer and weed')
        await cog.on_message(message)
        assert [c.args[0] for c in message.channel.send.await_args_list] == ['mmmmm beer 🍺', 'mmmmm weed 🍃']

    async def test_riggbot_trigger_answers_anyone(self, cog):
        message = make_message('hey riggbot')
        await cog.on_message(message)
        assert sent_text(message.channel.send) == "I'm riggbot! 🤖"

    async def test_no_triggers_in_dms(self, cog):
        message = make_message('beer', guild_id=None)
        await cog.on_message(message)
        message.channel.send.assert_not_awaited()

    async def test_unapproved_bots_are_ignored(self, cog):
        message = make_message('beer', author=make_user(is_bot=True))
        await cog.on_message(message)
        message.channel.send.assert_not_awaited()

    async def test_approved_bot_only_sets_off_include_bots_triggers(self, cog, bot):
        latibot = make_user(user_id=77, name='latibot', is_bot=True)
        approved_bot_ids(bot.guild_store, GUILD_ID).append(77)
        message = make_message('"iM rIgGbOt!" beer', author=latibot)
        await cog.on_message(message)
        # beer allows approved bots; the riggbot trigger doesn't (that would loop with LatiBot's mock)
        assert [c.args[0] for c in message.channel.send.await_args_list] == ['mmmmm beer 🍺']

    async def test_responses_never_ping(self, cog):
        message = make_message('beer')
        await cog.on_message(message)
        mentions = message.channel.send.call_args.kwargs['allowed_mentions']
        assert not (mentions.everyone or mentions.users or mentions.roles)

    async def test_add_update_remove(self, cog, bot, tmp_path):
        interaction = make_interaction()
        await cog.add.callback(cog, interaction, 'Pizza', 'pizza time', 'word', True)
        assert sent_text(interaction.response.send_message).startswith('Added trigger')
        await cog.add.callback(cog, make_interaction(), 'pizza', 'PIZZA TIME')
        pizza = [t for t in cog.triggers(GUILD_ID) if t.phrase.lower() == 'pizza']
        assert pizza == [Trigger('pizza', 'PIZZA TIME', 'contains', False)]

        fresh = Triggers(SimpleNamespace(guild_store=GuildStore(tmp_path / 'guilds'), user=bot.user))
        assert any(t.phrase == 'pizza' for t in fresh.triggers(GUILD_ID))    # saved to disk

        interaction = make_interaction()
        await cog.remove.callback(cog, interaction, 'PIZZA')
        assert all(t.phrase != 'pizza' for t in cog.triggers(GUILD_ID))

    async def test_triggers_are_per_server(self, cog):
        await cog.add.callback(cog, make_interaction(guild_id=1), 'pizza', 'here')
        assert not any(t.phrase == 'pizza' for t in cog.triggers(2))

    async def test_remove_unknown(self, cog):
        interaction = make_interaction()
        await cog.remove.callback(cog, interaction, 'nope')
        assert interaction.response.send_message.call_args.kwargs['ephemeral'] is True

    async def test_list(self, cog):
        interaction = make_interaction()
        await cog.list_triggers.callback(cog, interaction)
        text = sent_text(interaction.response.send_message)
        assert text.startswith('**Triggers** (8)') and '**beer**' in text


class TestBotsCog:
    @pytest.fixture
    def cog(self, bot):
        return Bots(bot)

    async def test_add_and_remove(self, cog, bot):
        latibot = make_user(user_id=77, name='latibot', is_bot=True)
        await cog.add.callback(cog, make_interaction(), latibot)
        assert approved_bot_ids(bot.guild_store, GUILD_ID) == [77]
        await cog.remove.callback(cog, make_interaction(), latibot)
        assert approved_bot_ids(bot.guild_store, GUILD_ID) == []

    async def test_refuses_humans_and_itself(self, cog, bot):
        for user in (make_user(user_id=5), bot.user):
            interaction = make_interaction()
            await cog.add.callback(cog, interaction, user)
            assert interaction.response.send_message.call_args.kwargs['ephemeral'] is True
        assert approved_bot_ids(bot.guild_store, GUILD_ID) == []

    async def test_none_approved_by_default(self, cog, bot):
        interaction = make_interaction()
        await cog.list_bots.callback(cog, interaction)
        assert sent_text(interaction.response.send_message) == 'No bots are approved on this server.'


# ---------------------------------------------------------------------------
# Language flags
# ---------------------------------------------------------------------------

class TestLangFlags:
    @pytest.fixture
    def cog(self, bot):
        return LangFlags(bot)

    @pytest.mark.parametrize('flag, ok', [
        ('🇯🇵', True), ('🏴󠁧󠁢󠁳󠁣󠁴󠁿', True), ('<:custom:123>', True),
        (TRANSLATE_EMOJI, False), ('jp', False), ('', False), ('🇯🇵 🇰🇷', False),
    ])
    def test_validate_flag(self, flag, ok):
        assert (validate_flag(flag) is None) is ok

    async def test_set_normalizes_and_saves(self, cog, bot):
        interaction = make_interaction()
        await cog.set_flag.callback(cog, interaction, '🇲🇴', 'ZH_tw')
        assert bot.flag_store.data['🇲🇴'] == 'zh-TW'
        assert sent_text(interaction.response.send_message) == 'flag: 🇲🇴 assigned to lang_code: zh-TW'
        assert bot.flag_store.path.exists()

    async def test_set_rejects_unknown_language(self, cog, bot):
        interaction = make_interaction()
        await cog.set_flag.callback(cog, interaction, '🇲🇴', 'klingon')
        assert '🇲🇴' not in bot.flag_store.data

    async def test_remove(self, cog, bot):
        await cog.remove_flag.callback(cog, make_interaction(), '🇯🇵')
        assert '🇯🇵' not in bot.flag_store.data


def test_is_owner(bot):
    bot.settings.owner_ids = [1]
    assert checks.is_owner(bot, make_user(user_id=1)) and not checks.is_owner(bot, make_user(user_id=2))
