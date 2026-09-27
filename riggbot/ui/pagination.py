"""Paginated replies for slash commands.

Typical use in a command:

    pages = build_pages([f'`{t.phrase}` → {t.response}' for t in triggers], title='**Triggers**')
    await Paginator.respond(interaction, pages, empty='No triggers yet.')

Only the user who ran the command can flip pages. The buttons switch off after `timeout`.
"""
from typing import Sequence

import discord

from ..messaging import MESSAGE_LIMIT

NO_MENTIONS = discord.AllowedMentions.none()


def build_pages(lines: Sequence[str], *, title: str = '', max_lines: int = 15,
                max_chars: int = MESSAGE_LIMIT - 100) -> list[str]:
    """Pack `lines` into pages of at most `max_lines` lines and `max_chars` characters.

    `title` is repeated at the top of every page. Lines that are too long on their own are truncated.
    """
    header = f'{title}\n' if title else ''
    budget = max_chars - len(header)
    pages: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if len(line) > budget:
            line = line[:budget - 1] + '…'
        if current and (len(current) >= max_lines or size + 1 + len(line) > budget):
            pages.append(header + '\n'.join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        pages.append(header + '\n'.join(current))
    return pages


class Paginator(discord.ui.View):
    def __init__(self, pages: Sequence[str], *, user_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError('Paginator needs at least one page')
        self.pages = list(pages)
        self.user_id = user_id
        self.index = 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    @classmethod
    async def respond(cls, interaction: discord.Interaction, pages: Sequence[str], *,
                      empty: str = 'Nothing to show.', ephemeral: bool = True) -> None:
        """Answer `interaction` with `pages`, adding page buttons only when there's more than one."""
        if not pages:
            await interaction.response.send_message(empty, ephemeral=ephemeral, allowed_mentions=NO_MENTIONS)
            return
        if len(pages) == 1:
            await interaction.response.send_message(pages[0], ephemeral=ephemeral, allowed_mentions=NO_MENTIONS)
            return
        view = cls(pages, user_id=interaction.user.id)
        await interaction.response.send_message(view.render(), view=view, ephemeral=ephemeral,
                                                allowed_mentions=NO_MENTIONS)
        view.message = await interaction.original_response()

    def render(self) -> str:
        return f'{self.pages[self.index]}\n-# Page {self.index + 1}/{len(self.pages)}'

    def _sync_buttons(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message('Only the person who ran the command can change pages.',
                                                ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction, index: int) -> None:
        self.index = max(0, min(index, len(self.pages) - 1))
        self._sync_buttons()
        await interaction.response.edit_message(content=self.render(), view=self, allowed_mentions=NO_MENTIONS)

    @discord.ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._show(interaction, self.index - 1)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._show(interaction, self.index + 1)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass    # message deleted or ephemeral token expired; nothing to update
