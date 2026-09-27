"""Post the bot's log lines to one Discord channel.

Set `logging.discord_channel_id` in config.json to turn it on, and `logging.discord_level`
for the lowest level to post (e.g. "INFO" posts info, warning, error and critical, but not debug).

Log lines are collected and posted every few seconds as a colored code block, rather than one
message per line, which would quickly hit Discord's rate limits. If lines pile up faster than
they can be posted (or while the bot is still connecting), the oldest are dropped and the next
message says how many were lost.
"""
import asyncio
import contextvars
import logging
from collections import deque

import discord

from .log import RiggFormatter
from .messaging import MESSAGE_LIMIT

log = logging.getLogger(__name__)

# Discord's ansi code blocks: 30 shows as gray there (the console's 90 isn't supported).
DISCORD_GRAY = '\x1b[30m'
_FENCE_START = '```ansi\n'
_FENCE_END = '\n```'
# Room for the lines inside one message, after the code block markers.
_BUDGET = MESSAGE_LIMIT - len(_FENCE_START) - len(_FENCE_END)

# True while this handler is itself sending to Discord. discord.py logs things while sending
# (e.g. rate-limit warnings); forwarding those would send more messages, which log more, and so on.
_sending = contextvars.ContextVar('riggbot_log_channel_sending', default=False)


def pack_lines(lines: list[str]) -> list[str]:
    """Pack log lines into as few Discord messages (code blocks) as possible."""
    messages: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        # ``` inside a line would end the code block early; break it up with zero-width spaces.
        line = line.replace('```', '`​`​`')
        if len(line) > _BUDGET:
            line = line[:_BUDGET - 1] + '…'     # e.g. a very long stack trace
        if current and size + 1 + len(line) > _BUDGET:
            messages.append(_FENCE_START + '\n'.join(current) + _FENCE_END)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        messages.append(_FENCE_START + '\n'.join(current) + _FENCE_END)
    return messages


class DiscordLogHandler(logging.Handler):
    """A logging handler that posts records to a Discord channel, in batches.

    Created and managed by RiggBot (see bot.py). Lifecycle: start() once the event loop runs,
    configure() whenever the settings change, aclose() on shutdown.
    """

    def __init__(self, bot: discord.Client, *, interval: float = 3.0, max_pending: int = 500):
        super().__init__()
        self.bot = bot
        self.interval = interval                        # seconds between posts
        self.channel_id: int | None = None
        self._channel: discord.abc.Messageable | None = None     # found on first send
        self._channel_failed = False                    # stop trying after a clear failure
        # Lines waiting to be posted. A deque with maxlen drops the oldest when it's full.
        self._pending: deque[str] = deque(maxlen=max_pending)
        self._dropped = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._closed = False
        self.setFormatter(RiggFormatter(color=True, timestamp_color=DISCORD_GRAY))

    def configure(self, channel_id: int | None, level: str) -> None:
        """Set (or change) the channel and the lowest level to post. channel_id None = off."""
        self.setLevel(logging.getLevelName(level))
        if channel_id != self.channel_id:
            # A different channel: look it up again on the next send.
            self.channel_id = channel_id
            self._channel = None
            self._channel_failed = False

    def start(self) -> None:
        """Start the background task that posts the collected lines. Needs the running event loop."""
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run(), name='log-channel')

    # region: Collecting lines (called by the logging system)

    def emit(self, record: logging.LogRecord) -> None:
        # Skip our own sending activity (see _sending), and records marked not to be posted.
        if _sending.get() or getattr(record, 'skip_discord', False):
            return
        try:
            line = self.format(record)
        except Exception:
            self.handleError(record)
            return
        loop = self._loop
        if loop is None:
            # Not started yet (the bot is still starting up): just keep the line until it is.
            if not self._closed:
                self._add(line)
            return
        if loop.is_closed():
            return
        # Logging can happen on other threads (e.g. the DeepL provider runs in one). Hand the line
        # over to the bot's event loop thread, which owns the pending list.
        try:
            loop.call_soon_threadsafe(self._add, line)
        except RuntimeError:
            pass    # the loop is shutting down

    def _add(self, line: str) -> None:
        if len(self._pending) == self._pending.maxlen:
            self._dropped += 1      # the deque is about to push out its oldest line
        self._pending.append(line)

    # endregion

    # region: Posting lines (runs on the bot's event loop)

    async def _run(self) -> None:
        """Every `interval` seconds, post whatever has been collected."""
        await self.bot.wait_until_ready()   # can't post before the bot is connected
        while True:
            await asyncio.sleep(self.interval)
            await self.flush_now()

    async def flush_now(self) -> None:
        """Post all collected lines right away."""
        if self.channel_id is None:
            self._pending.clear()   # channel logging is off
            return
        if not self._pending:
            return
        channel = await self._get_channel()
        lines = list(self._pending)
        self._pending.clear()
        if channel is None:
            return      # nowhere to post; the lines are dropped (they're still in the console and file)
        if self._dropped:
            lines.insert(0, f'({self._dropped} earlier log lines were dropped)')
            self._dropped = 0

        token = _sending.set(True)
        try:
            for message in pack_lines(lines):
                await channel.send(message, silent=True, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            log.warning('Could not post logs to the log channel: %s', e, extra={'skip_discord': True})
        finally:
            _sending.reset(token)

    async def _get_channel(self) -> discord.abc.Messageable | None:
        """The configured channel, looked up once. None (with one warning) if it can't be used."""
        if self._channel is not None or self._channel_failed:
            return self._channel
        channel_id = self.channel_id
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        except discord.HTTPException as e:
            return self._fail(f'channel {channel_id} not found or not visible to the bot ({e})')
        # Must be a channel in a server that the bot can post in.
        guild = getattr(channel, 'guild', None)
        if guild is None or not hasattr(channel, 'send'):
            return self._fail(f'channel {channel_id} is not a text channel in a server')
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.send_messages):
            return self._fail(f'the bot is not allowed to post in #{channel.name} ({guild.name})')
        self._channel = channel
        log.info('Posting logs at level %s and above to #%s in %s', logging.getLevelName(self.level).lower(),
                 channel.name, guild.name)
        return channel

    def _fail(self, reason: str) -> None:
        self._channel_failed = True
        log.warning('Log channel disabled: %s. Check logging.discord_channel_id in config.json, then /reload.',
                    reason, extra={'skip_discord': True})
        return None

    async def aclose(self) -> None:
        """Post what's left (on shutdown), then stop the background task."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        try:
            await asyncio.wait_for(self.flush_now(), timeout=5)
        except (asyncio.TimeoutError, discord.HTTPException):
            pass
        self._closed = True
        self._loop = None

    # endregion
