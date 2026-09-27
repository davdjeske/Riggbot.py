"""Helpers for sending and looking up messages."""
import logging

import discord

log = logging.getLogger(__name__)

MESSAGE_LIMIT = 2000

# Never ping @everyone, roles or users from bot output; still show the "replying to" highlight.
SAFE_MENTIONS = discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=True)


def split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Split `text` into chunks of at most `limit` characters, breaking between lines where possible."""
    chunks: list[str] = []
    current: str | None = None
    for line in text.split('\n'):
        while len(line) > limit:            # a single line longer than the limit: hard split
            if current is not None:
                chunks.append(current)
                current = None
            chunks.append(line[:limit])
            line = line[limit:]
        if current is None:
            current = line
        elif len(current) + 1 + len(line) <= limit:
            current += '\n' + line
        else:
            chunks.append(current)
            current = line
    if current is not None:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


async def send_chunked(channel: discord.abc.Messageable, text: str, *, reply_to: discord.Message | None = None,
                       silent: bool = True,
                       allowed_mentions: discord.AllowedMentions = SAFE_MENTIONS) -> list[discord.Message]:
    """Send `text` to `channel`, split into as many messages as needed.

    With `reply_to`, the first message is a reply to it and the rest follow in the channel.
    """
    sent = []
    for i, chunk in enumerate(split_message(text)):
        if i == 0 and reply_to is not None:
            sent.append(await reply_to.reply(chunk, silent=silent, allowed_mentions=allowed_mentions))
        else:
            sent.append(await channel.send(chunk, silent=silent, allowed_mentions=allowed_mentions))
    return sent


async def reply(message: discord.Message, text: str, **kwargs) -> list[discord.Message]:
    """Reply to `message` with `text` of any length (see send_chunked)."""
    return await send_chunked(message.channel, text, reply_to=message, **kwargs)


def is_reply(message: discord.Message) -> bool:
    return message.type == discord.MessageType.reply and message.reference is not None


async def resolve_reference(message: discord.Message) -> discord.Message | None:
    """The message `message` replies to, fetching it if needed. None if it's gone or unreachable."""
    reference = message.reference
    if reference is None:
        return None
    resolved = reference.resolved
    if isinstance(resolved, discord.DeletedReferencedMessage):
        return None
    if resolved is not None:
        return resolved
    if reference.message_id is None:
        return None
    try:
        return await message.channel.fetch_message(reference.message_id)
    except discord.HTTPException as e:     # deleted, or no access
        log.debug('Could not fetch replied-to message %s: %s', reference.message_id, e)
        return None


async def fetch_reaction_message(bot: discord.Client,
                                 payload: discord.RawReactionActionEvent) -> discord.Message | None:
    """Fetch the message a raw reaction event is about, with up-to-date reaction counts."""
    try:
        channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
        return await channel.fetch_message(payload.message_id)
    except discord.HTTPException as e:
        log.debug('Could not fetch reacted-to message %s: %s', payload.message_id, e)
        return None


def reaction_count(message: discord.Message, emoji: str) -> int:
    """How many users reacted to `message` with `emoji` (as text, e.g. '⭐')."""
    for reaction in message.reactions:
        if str(reaction.emoji) == emoji:
            return reaction.count
    return 0
