"""Permission checks for slash commands."""
import discord
from discord import app_commands


def is_owner(bot, user: discord.abc.User) -> bool:
    """Whether `user` is listed in `owner_ids` in config.json."""
    return user.id in bot.settings.owner_ids


def owner_only():
    """Decorator for slash commands only the bot owners (config `owner_ids`) may use.

    Usage, on a command inside a cog:

        @app_commands.command(name='shutdown')
        @owner_only()
        async def shutdown(self, interaction): ...

    When someone else uses the command, it doesn't run. The bot's error handler
    (RiggBot.on_app_command_error) tells them privately that they're not allowed.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        # discord.py calls this before the command runs.
        if is_owner(interaction.client, interaction.user):
            return True
        # Raising CheckFailure stops the command; its message is shown to the user.
        raise app_commands.CheckFailure('Only the bot owners can use this command.')
    return app_commands.check(predicate)
