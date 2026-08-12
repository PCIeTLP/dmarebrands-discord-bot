from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BRAND, embed, iso_stamp, money
from ..permissions import requires

KIND_LABEL = {
    "topup": "Top-up",
    "purchase": "Keys bought",
    "refund": "Refund",
    "adjust": "Adjustment",
}


class Billing(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Show the partner balance and how to top it up")
    @requires("billing.read")
    async def balance(self, interaction: discord.Interaction) -> None:
        b = await self.bot.partner_api.balance()
        topup = b.get("topup") or {}

        view = embed("Balance", BRAND)
        view.add_field(name="Available", value=money(b.get("balance_usd")), inline=True)
        view.add_field(name="Your discount", value=f"{b.get('discount_pct')}%", inline=True)
        view.description = (
            f"Top up between {money(topup['min_usd'])} and {money(topup['max_usd'])} at {topup['url']}"
            if topup
            else "Top up from the partner panel."
        )
        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="Recent movements on the partner balance")
    @app_commands.describe(limit="How many entries to show (1-25, default 10)")
    @requires("billing.read")
    async def ledger(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 10
    ) -> None:
        result = await self.bot.partner_api.ledger(limit)
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="Nothing on the ledger yet.")
            return

        lines = []
        for entry in rows:
            amount = float(entry.get("amount_usd") or 0)
            sign = "+" if amount >= 0 else "−"
            label = KIND_LABEL.get(entry.get("kind"), entry.get("kind"))
            lines.append(
                f"{sign}{money(abs(amount))[1:]} · **{label}** · {iso_stamp(entry.get('created_at'))}\n"
                f"{entry.get('note') or 'No note'} · balance after {money(entry.get('balance_after_usd'))}"
            )

        view = embed("Ledger", BRAND)
        view.description = "\n\n".join(lines)
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Billing(bot))
