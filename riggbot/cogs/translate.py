"""Manual translation triggers.

- React with 🏳️‍⚧️ to translate a message.
- React with a country flag to translate it, treating the text as that country's language
  (see /langflags and the flag map).
- Reply to a message with anything containing "trans" to translate the replied-to message.
"""
import logging

import discord
from discord.ext import commands

from ..bot import RiggBot, describe_location
from ..cooldown import Cooldown
from ..messaging import fetch_reaction_message, is_reply, reaction_count, reply, resolve_reference
from ..translation import TranslationError

log = logging.getLogger(__name__)

TRANSLATE_EMOJI = '\U0001F3F3️‍⚧️'     # 🏳️‍⚧️

# Deliberately loose (creator's requirement): ANY reply containing "trans" -- including
# "transport", "transfer", "transparent"... -- translates the replied-to message. It's funny.
# Don't narrow this.
TRANS_KEYWORD = 'trans'

NOTHING_TO_TRANSLATE = "Sorry, I couldn't find anything to translate in that"
TRANSLATION_DOWN = "Sorry, translation isn't working right now. Try again later."


class Translate(commands.Cog):
    def __init__(self, bot: RiggBot):
        self.bot = bot
        self.reaction_cooldown = Cooldown(lambda: bot.settings.translation.reaction_cooldown_seconds)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.id == self.bot.user.id or message.webhook_id is not None:
            return
        if not (is_reply(message) and message.content):
            return
        if TRANS_KEYWORD not in message.content.lower():
            return

        target = await resolve_reference(message)
        if target is None:
            log.warning('Reply trigger by %s, but the replied-to message is gone', message.author)
            return
        log.info('Translation trigger: reply by %s (id=%s) on msg=%s in %s', message.author, message.author.id,
                 target.id, describe_location(message.guild, message.channel))
        await self.translate_message(target)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == self.bot.user.id or payload.message_author_id == self.bot.user.id:
            return
        emoji = str(payload.emoji)
        if emoji == TRANSLATE_EMOJI:
            source = None
        elif emoji in self.bot.flag_store.data:
            source = self.bot.flag_store.data[emoji]
        else:
            return

        message = await fetch_reaction_message(self.bot, payload)
        if message is None:
            return
        # Only the first reaction of a kind triggers, and not again within the cooldown
        # (so removing and re-adding the reaction doesn't translate twice).
        if reaction_count(message, emoji) > 1:
            return
        if not self.reaction_cooldown.try_acquire((message.id, emoji)):
            log.debug('Reaction %s on msg=%s ignored: cooling down', emoji, message.id)
            return

        log.info('Translation trigger: reaction %s%s by user=%s on msg=%s in %s', emoji,
                 f' (source {source})' if source else '', payload.user_id, message.id,
                 describe_location(message.guild, message.channel))
        await self.translate_message(message, source=source)

    async def translate_message(self, message: discord.Message, *, source: str | None = None) -> None:
        """Translate `message` (its embed's text if it has one, otherwise its content) and reply."""
        service = self.bot.translation
        if not service.enabled:
            await reply(message, TRANSLATION_DOWN)
            return

        description = message.embeds[0].description if message.embeds else None
        try:
            if description:
                result = await service.translate_post(description, manual=True, source=source)
            elif message.content:
                result = await service.translate_text(message.content, manual=True, source=source)
            else:
                result = None
        except TranslationError as e:
            log.warning('Translation of msg=%s failed: %s', message.id, e)
            await reply(message, TRANSLATION_DOWN)
            return

        await reply(message, result or NOTHING_TO_TRANSLATE)


async def setup(bot: RiggBot) -> None:
    await bot.add_cog(Translate(bot))
