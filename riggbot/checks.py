"""Permission checks for slash commands."""
import discord
from discord import app_commands


def is_owner(bot, user: discord.abc.User) -> bool:
    """Whether `user` is listed in `owner_ids` in config.json."""
    return user.id in bot.settings.owner_ids


def owner_only():
    """Decorator for slash commands only the bot owners (config `owner_ids`) may use."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_owner(interaction.client, interaction.user):
            return True
        raise app_commands.CheckFailure('Only the bot owners can use this command.')
    return app_commands.check(predicate)
