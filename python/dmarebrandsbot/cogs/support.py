from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, embed, iso_stamp
from ..permissions import requires

STATUS_TONE = {"open": WARN, "answered": GOOD, "resolved": GOOD, "closed": BRAND}

STATUS_CHOICES = [
    app_commands.Choice(name=s, value=s)
    for s in ("all", "open", "answered", "resolved", "closed")
]
CATEGORY_CHOICES = [
    app_commands.Choice(name=c, value=c)
    for c in ("billing", "technical", "account", "integration", "other")
]
PRIORITY_CHOICES = [
    app_commands.Choice(name=p, value=p) for p in ("low", "normal", "high", "urgent")
]


def line(t: dict[str, Any]) -> str:
    unread = " · unread reply" if t.get("unread") else ""
    return (
        f"`{t.get('ref')}` · **{t.get('subject')}**\n"
        f"{t.get('status')} · {t.get('priority')} · {t.get('messages')} message(s){unread}\n"
        f"Last activity {iso_stamp(t.get('last_message_at'))}"
    )


class Support(commands.Cog):
    group = app_commands.Group(name="tickets", description="Your support threads with us")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @group.command(name="list", description="List your tickets")
    @app_commands.choices(status=STATUS_CHOICES)
    @requires("tickets.read")
    async def list(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] | None = None,
        search: str | None = None,
    ) -> None:
        result = await self.bot.partner_api.list_tickets(
            status=status.value if status else None, search=search
        )
        rows = result.get("tickets") or []
        if not rows:
            await interaction.edit_original_response(content="No tickets match that.")
            return

        view = embed(f"Tickets ({len(rows)})", BRAND)
        view.description = "\n\n".join(line(t) for t in rows)[:4000]
        await interaction.edit_original_response(embed=view)

    @group.command(name="read", description="Read one thread")
    @requires("tickets.read")
    async def read(self, interaction: discord.Interaction, ref: str) -> None:
        t = await self.bot.partner_api.get_ticket(ref.strip().upper())
        thread = "\n\n".join(
            f"**{m.get('author') or 'you' if m.get('role') == 'partner' else 'support'}** "
            f"· {iso_stamp(m.get('created_at'))}\n{m.get('body')}"
            for m in (t.get("thread") or [])
        )
        view = embed(f"{t.get('ref')} · {t.get('subject')}", STATUS_TONE.get(t.get("status"), BRAND))
        head = f"{t.get('status')} · {t.get('priority')} · {t.get('category')}"
        view.description = f"{head}\n\n{thread or 'No messages yet.'}"[:4000]
        await interaction.edit_original_response(embed=view)

    @group.command(name="open", description="Open a new ticket")
    @app_commands.choices(category=CATEGORY_CHOICES, priority=PRIORITY_CHOICES)
    @requires("tickets.write")
    async def open(
        self,
        interaction: discord.Interaction,
        subject: str,
        body: str,
        category: app_commands.Choice[str] | None = None,
        priority: app_commands.Choice[str] | None = None,
    ) -> None:
        made = await self.bot.partner_api.create_ticket(
            subject=subject,
            body=body,
            category=category.value if category else None,
            priority=priority.value if priority else None,
        )
        view = embed("Ticket opened", GOOD)
        view.description = (
            f"`{made.get('ref')}` · **{made.get('subject')}**\n"
            f"We will reply in this thread. Check it with `/tickets read ref:{made.get('ref')}`."
        )
        await interaction.edit_original_response(embed=view)

    @group.command(name="reply", description="Reply to a thread")
    @requires("tickets.write")
    async def reply(self, interaction: discord.Interaction, ref: str, body: str) -> None:
        code = ref.strip().upper()
        t = await self.bot.partner_api.reply_ticket(code, body)
        view = embed("Reply sent", GOOD)
        view.description = f"`{t.get('ref') or code}` now has {t.get('messages', 'more')} message(s)."
        await interaction.edit_original_response(embed=view)

    @group.command(name="close", description="Close a thread you no longer need")
    @requires("tickets.write")
    async def close(self, interaction: discord.Interaction, ref: str) -> None:
        code = ref.strip().upper()
        closed = await self.bot.partner_api.close_ticket(code)
        view = embed("Ticket closed", BAD)
        view.description = f"`{closed.get('ref') or code}` is closed."
        await interaction.edit_original_response(embed=view)


class Activity(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Recent activity on your partner account")
    @app_commands.describe(limit="How many events, 1 to 200")
    @requires("activity.read")
    async def activity(self, interaction: discord.Interaction, limit: int = 15) -> None:
        result = await self.bot.partner_api.activity(limit=max(1, min(limit, 200)))
        events = result.get("events") or []

        if not events:
            await interaction.edit_original_response(content="Nothing has happened yet.")
            return

        listed = []
        for e in events:
            actor = (e.get("actor") or {}).get("username")
            target = (e.get("target") or {}).get("username")
            who = f" by {actor}" if actor else ""
            about = f" · {target}" if target else ""
            listed.append(f"`{e.get('action')}`{who}{about}\n{iso_stamp(e.get('created_at'))}")

        view = embed("Recent activity", BRAND)
        view.description = "\n\n".join(listed)[:4000]
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Support(bot))
    await bot.add_cog(Activity(bot))
