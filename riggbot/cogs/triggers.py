"""Keyword triggers: phrase -> response, managed per server with /trigger.

Each server starts with the triggers in riggbot/defaults/triggers.json. Matching ignores case:
- contains: the phrase appears anywhere (even inside other words)
- word:     the phrase appears as whole word(s)
- exact:    the whole message is the phrase

Messages from other bots only count if the bot is approved (/bots) and the trigger has
include_bots set.
"""
import logging
import re
from dataclasses import asdict, dataclass
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from ..bot import RiggBot, describe_location
from ..storage import read_default
from ..ui.pagination import Paginator, build_pages
from .bots import approved_bot_ids

log = logging.getLogger(__name__)

SECTION = 'triggers'
MatchMode = Literal['contains', 'word', 'exact']
MAX_PHRASE = 100
MAX_RESPONSE = 2000
NO_MENTIONS = discord.AllowedMentions.none()


@dataclass
class Trigger:
    phrase: str
    response: str
    match: MatchMode = 'contains'
    include_bots: bool = False

    def matches(self, content: str) -> bool:
        phrase = self.phrase.lower()
        content = content.lower()
        if self.match == 'exact':
            return content.strip() == phrase
        if self.match == 'word':
            return re.search(rf'(?<!\w){re.escape(phrase)}(?!\w)', content) is not None
        return phrase in content

    def describe(self) -> str:
        bots = ', approved bots too' if self.include_bots else ''
        return f'**{escape_markdown(self.phrase)}** → {self.response}  *({self.match}{bots})*'


def default_triggers() -> list[dict]:
    return read_default('triggers.json', fallback=[])


def _from_dict(data: dict) -> Trigger | None:
    try:
        trigger = Trigger(**data)
    except TypeError:
        log.warning('Ignoring malformed trigger in data: %r', data)
        return None
    return trigger


@app_commands.guild_only()
class Triggers(commands.GroupCog, group_name='trigger', group_description='Automatic responses to phrases'):
    def __init__(self, bot: RiggBot):
        self.bot = bot
        super().__init__()

    def _stored(self, guild_id: int) -> list[dict]:
        return self.bot.guild_store.section(guild_id, SECTION, default_triggers)

    def triggers(self, guild_id: int) -> list[Trigger]:
        return [t for t in map(_from_dict, self._stored(guild_id)) if t is not None]

    def _find(self, guild_id: int, phrase: str) -> int | None:
        wanted = phrase.strip().lower()
        for i, data in enumerate(self._stored(guild_id)):
            if str(data.get('phrase', '')).lower() == wanted:
                return i
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.id == self.bot.user.id or message.webhook_id is not None:
            return
        if not message.content:
            return

        triggers = self.triggers(message.guild.id)
        if message.author.bot:
            if message.author.id not in approved_bot_ids(self.bot.guild_store, message.guild.id):
                return
            triggers = [t for t in triggers if t.include_bots]

        for trigger in triggers:
            if trigger.matches(message.content):
                log.info('Trigger "%s" fired by %s (id=%s) in %s', trigger.phrase, message.author,
                         message.author.id, describe_location(message.guild, message.channel))
                await message.channel.send(trigger.response, silent=True, allowed_mentions=NO_MENTIONS)

    @app_commands.command(name='add', description='Add a trigger, or change an existing one')
    @app_commands.describe(
        phrase='What to look for in messages (not case-sensitive)',
        response='What riggbot says back',
        match='contains (default): anywhere, even inside words · word: whole words · exact: whole message',
        include_bots='Also respond to approved bots (see /bots). Default: no',
    )
    async def add(self, interaction: discord.Interaction, phrase: app_commands.Range[str, 1, MAX_PHRASE],
                  response: app_commands.Range[str, 1, MAX_RESPONSE], match: MatchMode = 'contains',
                  include_bots: bool = False) -> None:
        phrase = phrase.strip()
        if not phrase or not response.strip():
            await interaction.response.send_message('The phrase and response can\'t be blank.', ephemeral=True)
            return
        trigger = Trigger(phrase, response, match, include_bots)
        stored = self._stored(interaction.guild_id)
        index = self._find(interaction.guild_id, phrase)
        if index is None:
            stored.append(asdict(trigger))
            verb = 'Added'
        else:
            stored[index] = asdict(trigger)
            verb = 'Updated'
        await self.bot.guild_store.save(interaction.guild_id)
        log.info('%s trigger "%s" (%s, include_bots=%s) in guild=%s by %s', verb, phrase, match, include_bots,
                 interaction.guild_id, interaction.user)
        await interaction.response.send_message(f'{verb} trigger: {trigger.describe()}', silent=True,
                                                allowed_mentions=NO_MENTIONS)

    @app_commands.command(name='remove', description='Delete a trigger')
    @app_commands.describe(phrase='The trigger phrase to delete')
    async def remove(self, interaction: discord.Interaction, phrase: str) -> None:
        index = self._find(interaction.guild_id, phrase)
        if index is None:
            await interaction.response.send_message(f'There\'s no trigger for "{phrase}".', ephemeral=True,
                                                    allowed_mentions=NO_MENTIONS)
            return
        removed = self._stored(interaction.guild_id).pop(index)
        await self.bot.guild_store.save(interaction.guild_id)
        log.info('Removed trigger "%s" in guild=%s by %s', removed.get('phrase'), interaction.guild_id,
                 interaction.user)
        await interaction.response.send_message(
            f'Removed trigger **{escape_markdown(str(removed.get("phrase")))}**.', silent=True,
            allowed_mentions=NO_MENTIONS)

    @remove.autocomplete('phrase')
    async def _phrase_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        return [app_commands.Choice(name=t.phrase[:100], value=t.phrase)
                for t in self.triggers(interaction.guild_id) if current in t.phrase.lower()][:25]

    @app_commands.command(name='list', description='Show this server\'s triggers')
    async def list_triggers(self, interaction: discord.Interaction) -> None:
        triggers = self.triggers(interaction.guild_id)
        pages = build_pages([t.describe() for t in triggers], title=f'**Triggers** ({len(triggers)})')
        await Paginator.respond(interaction, pages, empty='This server has no triggers.')


async def setup(bot: RiggBot) -> None:
    await bot.add_cog(Triggers(bot))
