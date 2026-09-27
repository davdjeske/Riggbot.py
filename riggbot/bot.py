"""The bot itself: startup, shared services, and slash-command plumbing.

Features live in cogs (riggbot/cogs/). Each cog module has an `async def setup(bot)` and is
listed in EXTENSIONS. Cogs reach shared services through the bot:

    self.bot.settings       current Settings (replaced on /reload, so don't keep a copy)
    self.bot.guild_store    per-server JSON data
    self.bot.flag_store     flag emoji -> language code map
    self.bot.translation    TranslationService

How a run goes: main() loads settings and sets up logging, then starts RiggBot. discord.py
logs in, calls setup_hook() once (load cogs, register slash commands), connects, and from
then on calls the cogs' listeners (on_message, on_raw_reaction_add, ...) as events arrive.
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
from .log_channel import DiscordLogHandler
from .messaging import SAFE_MENTIONS
from .storage import GuildStore, JsonStore, read_default
from .translation import TranslationService, build_providers

log = logging.getLogger(__name__)

# The cog modules to load at startup. A new feature's module gets added here.
EXTENSIONS = [
    'riggbot.cogs.admin',
    'riggbot.cogs.bots',
    'riggbot.cogs.fun',
    'riggbot.cogs.langflags',
    'riggbot.cogs.translate',
    'riggbot.cogs.triggers',
]


class RiggBot(commands.Bot):
    """The Discord client, plus the services the cogs share."""

    def __init__(self, settings: Settings, secrets: Secrets, base_dir: Path):
        # Intents tell Discord which kinds of events to send the bot. Reading message text
        # ("message content") must also be switched on for the bot in the Developer Portal.
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,   # required by commands.Bot; no prefix commands exist
            intents=intents,
            help_command=None,
            allowed_mentions=SAFE_MENTIONS,           # never ping @everyone/roles/users by accident
        )
        self.settings = settings
        self.secrets = secrets
        self.base_dir = base_dir
        self.data_dir = base_dir / 'data'
        # Shared services (see the module docstring above).
        self.guild_store = GuildStore(self.data_dir / 'guilds')
        self.flag_store = JsonStore(self.data_dir / 'flag_lang_map.json',
                                    initial=lambda: read_default('flag_lang_map.json', fallback={}))
        # Starts with no providers; setup_hook() creates them. The lambda means the service always
        # sees the *current* settings, even after /reload replaces them.
        self.translation = TranslationService([], lambda: self.settings.translation)
        # Posts logs to a Discord channel if config.json sets one. Lines logged before the bot
        # connects are kept and posted once it has.
        self.log_channel = DiscordLogHandler(self)
        self.apply_logging_settings()
        self._has_been_ready = False    # to tell the first on_ready apart from reconnects

    def apply_logging_settings(self) -> None:
        """(Re)configure logging from the current settings, including the Discord log channel."""
        settings = self.settings.logging
        self.log_channel.configure(settings.discord_channel_id, settings.discord_level)
        extra = [self.log_channel] if settings.discord_channel_id else []
        setup_logging(settings, self.base_dir, extra)

    async def setup_hook(self) -> None:
        """Runs once, after logging in and before connecting. discord.py calls it for us."""
        # 0. Start posting to the log channel (it waits until the bot is connected).
        self.log_channel.start()

        # 1. Translation providers (DeepL, googletrans, ...) as listed in config.
        await self.translation.replace_providers(build_providers(self.settings, self.secrets))
        if self.settings.translation.startup_self_test and self.translation.enabled:
            # Runs in the background so a slow provider doesn't delay logging in.
            self._self_test_task = asyncio.create_task(self.translation.self_test(), name='translation-self-test')

        # 2. Our own error handler for slash commands (below), then all the cogs.
        self.tree.on_error = self.on_app_command_error
        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.debug('Loaded %s', extension)
        # 3. Tell Discord which slash commands exist, so they show up in the / menu.
        synced = await self.tree.sync()
        log.info('Synced %d slash commands: %s', len(synced), ', '.join(f'/{c.name}' for c in synced) or '(none)')

    async def close(self) -> None:
        """Shut down: post the last log lines, close translation connections, then disconnect."""
        await self.log_channel.aclose()
        await self.translation.aclose()
        await super().close()

    async def on_ready(self) -> None:
        # Discord fires this after connecting, and again after every reconnect.
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
        """Called after any slash command finishes successfully: log who used what, where."""
        log.info('/%s used by %s (id=%s) in %s', command.qualified_name, interaction.user, interaction.user.id,
                 describe_location(interaction.guild, interaction.channel))

    async def on_app_command_error(self, interaction: discord.Interaction,
                                   error: app_commands.AppCommandError) -> None:
        """Called when a slash command fails or isn't allowed. Logs it and tells the user privately."""
        name = interaction.command.qualified_name if interaction.command else '?'
        if isinstance(error, app_commands.CheckFailure):
            # Not allowed (e.g. an owner-only command): expected, so just a warning.
            log.warning('/%s refused for %s (id=%s): %s', name, interaction.user, interaction.user.id, error)
            text = str(error) or "You can't use this command."
        else:
            # A real bug or outage: log the full stack trace.
            log.error('/%s failed', name, exc_info=error)
            text = 'Something went wrong running that command.'
        try:
            # A command can only "respond" once; if it already did, send a follow-up instead.
            # ephemeral=True means only the user who ran the command sees the message.
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
        # If config.json is invalid this raises ConfigError before anything is changed.
        settings = config.load_settings(self.base_dir / 'config.json', os.environ)
        self.settings = settings
        self.apply_logging_settings()
        self.guild_store.reload()
        self.flag_store.reload()
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
    """Entry point (main.py and `python -m riggbot`): load settings, set up logging, run the bot."""
    # Load .env into the environment (existing environment variables take priority).
    base_dir = paths.base_dir()
    load_dotenv(base_dir / '.env')
    try:
        settings = config.load_settings(base_dir / 'config.json', os.environ)
        secrets = config.load_secrets(os.environ)
    except ConfigError as e:
        # Logging isn't set up yet (it needs the settings), so print the problem directly.
        print(f'Configuration error: {e}', file=sys.stderr)
        sys.exit(1)

    # Riggbot never joins voice channels; skip discord.py's warnings about missing voice libraries.
    discord.VoiceClient.warn_nacl = False
    discord.VoiceClient.warn_dave = False

    # Creating the bot also sets up logging (console, file, and the Discord log channel if set).
    bot = RiggBot(settings, secrets, base_dir)

    # From here on, use the log. Start with a summary of what the bot is running with.
    log.info('Starting riggbot %s (Python %s, discord.py %s)', __version__, sys.version.split()[0],
             discord.__version__)
    log.info('Base directory: %s', base_dir)
    log.info('Config sources: %s', ' < '.join(settings.sources))
    for warning in settings.warnings:
        log.warning(warning)
    log.info('Config: %s', config.summary(settings, secrets))

    try:
        # Connects to Discord and keeps running until the bot is shut down.
        # log_handler=None: logging is already configured; don't let discord.py add a second handler.
        bot.run(secrets.token, log_handler=None)
    except discord.LoginFailure:
        log.critical('Discord rejected the bot token. Check RIGGBOT_TOKEN in .env.')
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.critical('The Message Content intent is not enabled. Turn it on for this bot in the Discord '
                     'Developer Portal (Bot → Privileged Gateway Intents).')
        sys.exit(1)
