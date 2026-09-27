"""The bot itself: startup, shared services, and slash-command plumbing.

Features live in cogs (riggbot/cogs/). Each cog module has an `async def setup(bot)` and is
listed in EXTENSIONS. Cogs reach shared services through the bot:

    self.bot.settings       current Settings (replaced on /reload, so don't keep a copy)
    self.bot.guild_store    per-server JSON data
    self.bot.translation    TranslationService
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from . import __version__, config, paths
from .config import ConfigError, Secrets, Settings
from .log import setup_logging
from .messaging import SAFE_MENTIONS
from .storage import GuildStore
from .translation import TranslationService, build_providers

log = logging.getLogger(__name__)

EXTENSIONS: list[str] = []


class RiggBot(commands.Bot):
    def __init__(self, settings: Settings, secrets: Secrets, base_dir: Path):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,   # required by commands.Bot; no prefix commands exist
            intents=intents,
            help_command=None,
            allowed_mentions=SAFE_MENTIONS,
        )
        self.settings = settings
        self.secrets = secrets
        self.base_dir = base_dir
        self.data_dir = base_dir / 'data'
        self.guild_store = GuildStore(self.data_dir / 'guilds')
        self.translation = TranslationService([], lambda: self.settings.translation)
        self._has_been_ready = False

    async def setup_hook(self) -> None:
        await self.translation.replace_providers(build_providers(self.settings, self.secrets))
        if self.settings.translation.startup_self_test and self.translation.enabled:
            # Runs in the background so a slow provider doesn't delay logging in.
            self._self_test_task = asyncio.create_task(self.translation.self_test(), name='translation-self-test')

        self.tree.on_error = self.on_app_command_error
        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.debug('Loaded %s', extension)
        synced = await self.tree.sync()
        log.info('Synced %d slash commands: %s', len(synced), ', '.join(f'/{c.name}' for c in synced) or '(none)')

    async def close(self) -> None:
        await self.translation.aclose()
        await super().close()

    async def on_ready(self) -> None:
        if self._has_been_ready:
            log.info('Reconnected as %s', self.user)
            return
        self._has_been_ready = True
        log.info('Online as %s (id=%s) in %d server(s)', self.user, self.user.id, len(self.guilds))

    async def on_message(self, message: discord.Message) -> None:
        # commands.Bot would try to parse prefix commands here. There are none; cogs handle messages.
        pass

    async def on_app_command_completion(self, interaction: discord.Interaction,
                                        command: app_commands.Command | app_commands.ContextMenu) -> None:
        log.info('/%s used by %s (id=%s) in %s', command.qualified_name, interaction.user, interaction.user.id,
                 describe_location(interaction.guild, interaction.channel))

    async def on_app_command_error(self, interaction: discord.Interaction,
                                   error: app_commands.AppCommandError) -> None:
        name = interaction.command.qualified_name if interaction.command else '?'
        if isinstance(error, app_commands.CheckFailure):
            log.warning('/%s refused for %s (id=%s): %s', name, interaction.user, interaction.user.id, error)
            text = str(error) or "You can't use this command."
        else:
            log.error('/%s failed', name, exc_info=error)
            text = 'Something went wrong running that command.'
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            log.debug('Could not tell the user about the /%s error', name, exc_info=True)

    async def reload_config(self) -> list[str]:
        """Re-read config.json and data/. Returns warnings to show the user.

        Environment variables are the ones from startup; changes to .env need a restart.
        """
        settings = config.load_settings(self.base_dir / 'config.json', os.environ)
        self.settings = settings
        setup_logging(settings.logging, self.base_dir)
        self.guild_store.reload()
        await self.translation.replace_providers(build_providers(settings, self.secrets))
        self.dispatch('riggbot_reload')     # cogs with their own caches listen for this
        for warning in settings.warnings:
            log.warning(warning)
        log.info('Configuration reloaded: %s', config.summary(settings, self.secrets))
        return settings.warnings


def describe_location(guild: discord.Guild | None, channel) -> str:
    """Short 'where did this happen' text for logs."""
    if guild is None:
        return 'DMs'
    channel_name = f'#{channel.name}' if getattr(channel, 'name', None) else f'channel={getattr(channel, "id", "?")}'
    return f'{guild.name} (id={guild.id}) {channel_name}'


def main() -> None:
    base_dir = paths.base_dir()
    load_dotenv(base_dir / '.env')
    try:
        settings = config.load_settings(base_dir / 'config.json', os.environ)
        secrets = config.load_secrets(os.environ)
    except ConfigError as e:
        print(f'Configuration error: {e}', file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.logging, base_dir)
    log.info('Starting riggbot %s (Python %s, discord.py %s)', __version__, sys.version.split()[0],
             discord.__version__)
    log.info('Base directory: %s', base_dir)
    log.info('Config sources: %s', ' < '.join(settings.sources))
    for warning in settings.warnings:
        log.warning(warning)
    log.info('Config: %s', config.summary(settings, secrets))

    # Riggbot never joins voice channels; skip discord.py's warnings about missing voice libraries.
    discord.VoiceClient.warn_nacl = False
    discord.VoiceClient.warn_dave = False

    bot = RiggBot(settings, secrets, base_dir)
    try:
        # log_handler=None: logging is already configured; don't let discord.py add a second handler.
        bot.run(secrets.token, log_handler=None)
    except discord.LoginFailure:
        log.critical('Discord rejected the bot token. Check RIGGBOT_TOKEN in .env.')
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.critical('The Message Content intent is not enabled. Turn it on for this bot in the Discord '
                     'Developer Portal (Bot → Privileged Gateway Intents).')
        sys.exit(1)
