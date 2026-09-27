"""/langflags: which flag reaction means which source language (used by the translate cog)."""
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import RiggBot
from ..translation.languages import is_known, normalize
from ..ui.pagination import Paginator, build_pages
from .translate import TRANSLATE_EMOJI

log = logging.getLogger(__name__)

_CUSTOM_EMOJI = re.compile(r'^<a?:\w+:\d+>$')
_PLAIN_TEXT = re.compile(r'[\sA-Za-z0-9]')


def validate_flag(flag: str) -> str | None:
    """Returns a problem description, or None if `flag` can be used."""
    if flag == TRANSLATE_EMOJI:
        return f'{TRANSLATE_EMOJI} is reserved for plain translation.'
    if _CUSTOM_EMOJI.match(flag):
        return None
    if not flag or len(flag) > 16 or _PLAIN_TEXT.search(flag):
        return 'That doesn\'t look like a single emoji. Paste the flag emoji itself, e.g. 🇯🇵.'
    return None


class LangFlags(commands.Cog):
    langflags = app_commands.Group(name='langflags', description='Flag reactions that translate from a language')

    def __init__(self, bot: RiggBot):
        self.bot = bot

    @property
    def flags(self) -> dict[str, str]:
        return self.bot.flag_store.data

    @langflags.command(name='set', description='Make reacting with a flag translate from a language')
    @app_commands.describe(flag='The flag emoji, e.g. 🇯🇵', lang_code='Language code, e.g. ja, zh-CN, pt')
    async def set_flag(self, interaction: discord.Interaction, flag: str, lang_code: str) -> None:
        flag = flag.strip()
        if problem := validate_flag(flag):
            await interaction.response.send_message(problem, ephemeral=True)
            return
        if not is_known(lang_code):
            await interaction.response.send_message(
                f'`{lang_code}` isn\'t a language code I know. Use codes like `ja`, `de`, `zh-CN` or `zh-TW`.',
                ephemeral=True)
            return

        code = normalize(lang_code)
        previous = self.flags.get(flag)
        self.flags[flag] = code
        await self.bot.flag_store.save()
        log.info('Flag %s set to %s (was %s) by %s', flag, code, previous, interaction.user)
        changed = f' (was `{previous}`)' if previous and previous != code else ''
        await interaction.response.send_message(f'flag: {flag} assigned to lang_code: {code}{changed}', silent=True)

    @langflags.command(name='remove', description='Stop a flag reaction from translating')
    @app_commands.describe(flag='The flag emoji to remove')
    async def remove_flag(self, interaction: discord.Interaction, flag: str) -> None:
        flag = flag.strip()
        code = self.flags.pop(flag, None)
        if code is None:
            await interaction.response.send_message(f'{flag} isn\'t set up as a language flag.', ephemeral=True)
            return
        await self.bot.flag_store.save()
        log.info('Flag %s (%s) removed by %s', flag, code, interaction.user)
        await interaction.response.send_message(f'flag: {flag} no longer translates from {code}', silent=True)

    @remove_flag.autocomplete('flag')
    async def _flag_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=f'{flag} {code}', value=flag)
                for flag, code in self.flags.items() if current in flag or current.lower() in code.lower()][:25]

    @langflags.command(name='list', description='Show which flags translate from which language')
    async def list_flags(self, interaction: discord.Interaction) -> None:
        lines = [f'{flag} → `{code}`' for flag, code in sorted(self.flags.items(), key=lambda item: item[1])]
        pages = build_pages(lines, title=f'**Language flags** ({len(lines)})', max_lines=20)
        await Paginator.respond(interaction, pages, empty='No language flags are set up.')


async def setup(bot: RiggBot) -> None:
    await bot.add_cog(LangFlags(bot))
