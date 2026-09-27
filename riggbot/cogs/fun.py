"""Riggbot's personality: "is this true", LatiBot banter, ⭐ thanks, and the owner goodbye phrases.

All texts come from `responses` in config.json; the defaults reproduce the original behavior.
"""
import logging
import random

import discord
from discord.ext import commands

from ..bot import RiggBot, describe_location
from ..checks import is_owner
from ..cooldown import Cooldown
from ..messaging import fetch_reaction_message, is_reply, reaction_count, resolve_reference

log = logging.getLogger(__name__)

STAR = '⭐'     # ⭐


class Fun(commands.Cog):
    """Message and reaction responses that give riggbot its personality."""

    def __init__(self, bot: RiggBot):
        self.bot = bot
        # Stops the ⭐ thank-you from repeating if the star is removed and added again.
        self.star_cooldown = Cooldown(lambda: bot.settings.translation.reaction_cooldown_seconds)

    @property
    def responses(self):
        """The `responses` section of config.json (read fresh each time, so /reload applies)."""
        return self.bot.settings.responses

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Every new message is checked against each of the features below."""
        # Ignore riggbot's own messages and webhook messages.
        if message.author.id == self.bot.user.id or message.webhook_id is not None:
            return
        await self.latibot_banter(message)
        await self.is_this_true(message)
        await self.owner_goodbye(message)

    def is_latibot(self, user: discord.abc.User) -> bool:
        """Is `user` LatiBot? By user ID if one is configured, otherwise by name."""
        settings = self.bot.settings.latibot
        if settings.user_id:
            return user.id == settings.user_id
        return bool(settings.name_fallback) and settings.name_fallback.lower() in user.name.lower()

    async def latibot_banter(self, message: discord.Message) -> None:
        """Riggbot's comebacks to two specific LatiBot messages."""
        if not self.is_latibot(message.author):
            return
        banter = self.responses.latibot_banter
        # LatiBot says exactly "dat me!!" (any capitalization) -> reply with the dat_me_reply.
        if message.content.lower() == banter.dat_me_trigger.lower():
            log.info('LatiBot banter: "%s" in %s', banter.dat_me_trigger, describe_location(message.guild, message.channel))
            await message.reply(banter.dat_me_reply, silent=True)
        # LatiBot mocks riggbot ("iM rIgGbOt!") -> answer in the channel.
        if banter.mock_trigger and banter.mock_trigger in message.content:
            log.info('LatiBot banter: mock in %s', describe_location(message.guild, message.channel))
            await message.channel.send(banter.mock_reply, silent=True)

    async def is_this_true(self, message: discord.Message) -> None:
        """Reply to a reply containing an "is this true" phrase with a random answer.

        Only answers when the replied-to message isn't riggbot's own. Creator requirement: this
        must keep behaving exactly like the original (default phrases and answers in config).
        """
        if not (is_reply(message) and message.content):
            return
        content = message.content.lower()
        # In message text, an @riggbot mention looks like <@1234567890>. Put that in place of
        # {mention} in the configured phrases, then look for any of them in the message.
        mention = f'<@{self.bot.user.id}>'
        phrases = [p.replace('{mention}', mention).lower() for p in self.responses.is_this_true.phrases]
        if not any(phrase in content for phrase in phrases):
            return

        target = await resolve_reference(message)
        if target is None:
            log.warning('"Is this true" from %s, but the replied-to message is gone', message.author)
            return
        # Riggbot doesn't fact-check itself.
        if target.author.id == self.bot.user.id:
            return
        answer = random.choice(self.responses.is_this_true.answers)
        log.info('"Is this true" from %s (id=%s) in %s: answered %s', message.author, message.author.id,
                 describe_location(message.guild, message.channel), answer)
        await message.reply(answer, silent=True)

    async def owner_goodbye(self, message: discord.Message) -> None:
        """Owners can shut the bot down by saying one of the goodbye phrases."""
        shutdown = self.responses.shutdown
        content = message.content.lower()
        if not any(phrase.lower() in content for phrase in shutdown.phrases):
            return
        # Everyone else saying the phrase is ignored, but logged with their ID so a missing or
        # wrong entry in owner_ids is easy to spot.
        if not is_owner(self.bot, message.author):
            log.info('Shutdown phrase from %s (id=%s) ignored: not in owner_ids', message.author, message.author.id)
            return
        log.info('Shutdown requested by %s (id=%s) in %s', message.author, message.author.id,
                 describe_location(message.guild, message.channel))
        await message.channel.send(random.choice(shutdown.farewells), silent=True)
        await self.bot.close()      # disconnects; the program then ends

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Say thanks for the first ⭐ on one of riggbot's messages."""
        # Cheap checks first, using only the IDs in the event: a ⭐, on riggbot's message...
        if str(payload.emoji) != STAR or payload.message_author_id != self.bot.user.id:
            return
        # ...not added by riggbot itself.
        if payload.user_id == self.bot.user.id:
            return
        # Then fetch the message to check this is the first ⭐ on it.
        message = await fetch_reaction_message(self.bot, payload)
        if message is None or reaction_count(message, STAR) > 1:
            return
        if not self.star_cooldown.try_acquire(message.id):
            return
        log.info('Starred by user=%s: msg=%s', payload.user_id, message.id)
        await message.channel.send(self.responses.star_thanks, silent=True)


async def setup(bot: RiggBot) -> None:
    """Called by bot.load_extension() to add this cog to the bot."""
    await bot.add_cog(Fun(bot))
