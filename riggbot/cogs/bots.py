"""/bots: the per-server list of approved bots.

Messages from other bots are ignored by triggers unless the bot is approved here AND the
trigger allows approved bots (see the triggers cog). No bots are approved by default.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import RiggBot
from ..storage import GuildStore
from ..ui.pagination import Paginator, build_pages

log = logging.getLogger(__name__)

SECTION = 'approved_bots'


def approved_bot_ids(store: GuildStore, guild_id: int) -> list[int]:
    return store.section(guild_id, SECTION, list)


@app_commands.guild_only()
class Bots(commands.GroupCog, group_name='bots', group_description='Bots whose messages can set off triggers'):
    def __init__(self, bot: RiggBot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name='add', description='Let a bot\'s messages set off triggers on this server')
    @app_commands.describe(bot='The bot to approve')
    async def add(self, interaction: discord.Interaction, bot: discord.User) -> None:
        if not bot.bot:
            await interaction.response.send_message(f'{bot.mention} isn\'t a bot.', ephemeral=True)
            return
        if bot.id == self.bot.user.id:
            await interaction.response.send_message('I don\'t need to approve myself.', ephemeral=True)
            return
        approved = approved_bot_ids(self.bot.guild_store, interaction.guild_id)
        if bot.id in approved:
            await interaction.response.send_message(f'{bot.mention} is already approved.', ephemeral=True)
            return
        approved.append(bot.id)
        await self.bot.guild_store.save(interaction.guild_id)
        log.info('Bot %s (id=%s) approved in guild=%s by %s', bot, bot.id, interaction.guild_id, interaction.user)
        await interaction.response.send_message(
            f'Approved {bot.mention}. Triggers that allow approved bots will now respond to it.',
            silent=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name='remove', description='Stop a bot\'s messages from setting off triggers')
    @app_commands.describe(bot='The bot to remove')
    async def remove(self, interaction: discord.Interaction, bot: discord.User) -> None:
        approved = approved_bot_ids(self.bot.guild_store, interaction.guild_id)
        if bot.id not in approved:
            await interaction.response.send_message(f'{bot.mention} isn\'t approved.', ephemeral=True)
            return
        approved.remove(bot.id)
        await self.bot.guild_store.save(interaction.guild_id)
        log.info('Bot %s (id=%s) unapproved in guild=%s by %s', bot, bot.id, interaction.guild_id, interaction.user)
        await interaction.response.send_message(f'Removed {bot.mention} from the approved bots.', silent=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name='list', description='Show the approved bots on this server')
    async def list_bots(self, interaction: discord.Interaction) -> None:
        approved = approved_bot_ids(self.bot.guild_store, interaction.guild_id)
        pages = build_pages([f'<@{bot_id}> (`{bot_id}`)' for bot_id in approved],
                            title=f'**Approved bots** ({len(approved)})')
        await Paginator.respond(interaction, pages, empty='No bots are approved on this server.')


async def setup(bot: RiggBot) -> None:
    await bot.add_cog(Bots(bot))
