"""Paginated replies for slash commands.

Typical use in a command:

    pages = build_pages([f'`{t.phrase}` → {t.response}' for t in triggers], title='**Triggers**')
    await Paginator.respond(interaction, pages, empty='No triggers yet.')

Only the user who ran the command can flip pages. The buttons switch off after `timeout`.
"""
from typing import Sequence

import discord

from ..messaging import MESSAGE_LIMIT

# List output shows names like <@123> as mentions, but must never actually ping anyone.
NO_MENTIONS = discord.AllowedMentions.none()


def build_pages(lines: Sequence[str], *, title: str = '', max_lines: int = 15,
                max_chars: int = MESSAGE_LIMIT - 100) -> list[str]:
    """Pack `lines` into pages of at most `max_lines` lines and `max_chars` characters.

    `title` is repeated at the top of every page. Lines that are too long on their own are truncated.
    (max_chars leaves some room under Discord's limit for the "Page x/y" footer.)
    """
    header = f'{title}\n' if title else ''
    budget = max_chars - len(header)     # characters left for the lines themselves
    pages: list[str] = []
    current: list[str] = []              # lines on the page being filled
    size = 0                             # characters used on that page so far
    for line in lines:
        # A single line bigger than a whole page gets cut short, marked with "…".
        if len(line) > budget:
            line = line[:budget - 1] + '…'
        # Page full (too many lines, or this line wouldn't fit)? Finish it and start a new one.
        if current and (len(current) >= max_lines or size + 1 + len(line) > budget):
            pages.append(header + '\n'.join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1            # +1 for the newline that joins the lines
    if current:
        pages.append(header + '\n'.join(current))
    return pages


class Paginator(discord.ui.View):
    """A message with ◀ ▶ buttons that flip between pages of text.

    A discord.ui.View is a set of buttons (and other controls) attached to a message. Clicking a
    button calls the matching method below, decorated with @discord.ui.button.
    """

    def __init__(self, pages: Sequence[str], *, user_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError('Paginator needs at least one page')
        self.pages = list(pages)
        self.user_id = user_id          # the only user allowed to press the buttons
        self.index = 0                  # which page is showing (0 = first)
        self.message: discord.Message | None = None     # set after sending, used on timeout
        self._sync_buttons()

    @classmethod
    async def respond(cls, interaction: discord.Interaction, pages: Sequence[str], *,
                      empty: str = 'Nothing to show.', ephemeral: bool = True) -> None:
        """Answer `interaction` with `pages`, adding page buttons only when there's more than one.

        ephemeral=True (the default) means only the user who ran the command sees the reply.
        """
        if not pages:
            await interaction.response.send_message(empty, ephemeral=ephemeral, allowed_mentions=NO_MENTIONS)
            return
        if len(pages) == 1:
            # One page: no need for buttons.
            await interaction.response.send_message(pages[0], ephemeral=ephemeral, allowed_mentions=NO_MENTIONS)
            return
        view = cls(pages, user_id=interaction.user.id)
        await interaction.response.send_message(view.render(), view=view, ephemeral=ephemeral,
                                                allowed_mentions=NO_MENTIONS)
        # Remember the sent message so the buttons can be disabled when they time out.
        view.message = await interaction.original_response()

    def render(self) -> str:
        """The text of the current page, with a small "Page x/y" line under it."""
        # "-# " at the start of a line is Discord markdown for small, gray text.
        return f'{self.pages[self.index]}\n-# Page {self.index + 1}/{len(self.pages)}'

    def _sync_buttons(self) -> None:
        # Grey out ◀ on the first page and ▶ on the last.
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """discord.py calls this before any button handler; returning False blocks the click."""
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message('Only the person who ran the command can change pages.',
                                                ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction, index: int) -> None:
        # Clamp to a valid page number, then edit the message in place.
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
        """After `timeout` seconds without clicks, grey out the buttons (they'd stop working anyway)."""
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass    # message deleted or ephemeral token expired; nothing to update
