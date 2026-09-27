"""/ping, plus owner-only /shutdown, /sync and /reload."""
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import RiggBot
from ..checks import owner_only
from ..config import ConfigError

log = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot: RiggBot):
        self.bot = bot

    @app_commands.command(name='ping', description='Check bot latency')
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f'Pong! {round(self.bot.latency * 1000)}ms')

    @app_commands.command(name='shutdown', description='Shut riggbot down (owners only)')
    @owner_only()
    async def shutdown(self, interaction: discord.Interaction) -> None:
        log.info('Shutdown requested by %s (id=%s) via /shutdown', interaction.user, interaction.user.id)
        await interaction.response.send_message(random.choice(self.bot.settings.responses.shutdown.farewells))
        await self.bot.close()

    @app_commands.command(name='sync', description='Re-register slash commands with Discord (owners only)')
    @owner_only()
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        log.info('Synced %d slash commands (requested by %s)', len(synced), interaction.user)
        await interaction.followup.send(f'Synced {len(synced)} commands.', ephemeral=True)

    @app_commands.command(name='reload', description='Re-read config.json and saved data (owners only)')
    @owner_only()
    async def reload(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            warnings = await self.bot.reload_config()
        except ConfigError as e:
            log.error('Reload failed, keeping the old configuration: %s', e)
            await interaction.followup.send(f'config.json has a problem, nothing was changed:\n{e}', ephemeral=True)
            return
        text = 'Reloaded.'
        if warnings:
            text += '\n' + '\n'.join(f'⚠️ {w}' for w in warnings)
        await interaction.followup.send(text, ephemeral=True)


async def setup(bot: RiggBot) -> None:
    await bot.add_cog(Admin(bot))
