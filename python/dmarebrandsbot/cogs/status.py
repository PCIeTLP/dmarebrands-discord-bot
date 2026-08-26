from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, embed, iso_stamp
from ..permissions import requires

TONE = {
    "undetected": GOOD,
    "updating": WARN,
    "offline": WARN,
    "detected": BAD,
    "discontinued": BAD,
}

HEADLINE = {
    "undetected": "Up and safe to use",
    "updating": "Updating",
    "offline": "Temporarily offline",
    "detected": "Detected, tell people to stop",
    "discontinued": "Discontinued",
}


class Status(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        description="Show whether a product is up, and whether customer keys are frozen"
    )
    @app_commands.describe(product="Limit it to one product, for example rust")
    @requires("status.read")
    async def status(self, interaction: discord.Interaction, product: str | None = None) -> None:
        result = await self.bot.partner_api.status(product)
        rows = result.get("products") or []

        if not rows:
            await interaction.edit_original_response(content="No products came back.")
            return

        worst = next((p for p in rows if p.get("status") != "undetected"), rows[0])
        blocks = []
        for p in rows:
            head = HEADLINE.get(p.get("status"), p.get("status"))
            beta = " · beta" if p.get("beta") else ""
            frozen = "\nKeys are frozen, so nobody is losing time." if p.get("frozen") else ""
            sale = "" if p.get("sellable") else "\nThis one cannot be sold any more."
            note = f"\n{p['message']}" if p.get("message") else ""
            seen = f"\nChanged {iso_stamp(p['updated_at'])}" if p.get("updated_at") else ""
            blocks.append(f"**{p.get('label')}** · {head}{beta}{frozen}{sale}{note}{seen}")

        view = embed("Product status", TONE.get(worst.get("status"), BRAND))
        view.description = "\n\n".join(blocks)
        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="Show the latest Rust build and the recent patch notes")
    @requires("status.read")
    async def updates(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.updates()
        build = result.get("current_build")
        notes = (result.get("updates") or [])[:5]

        view = embed("Game updates", BRAND)
        if build:
            seen = f" · {iso_stamp(build['at'])}" if build.get("at") else ""
            gap = result.get("average_gap_days")
            extra = f"\nUsually about {gap} days between builds." if gap else ""
            view.description = f"Current build **{build.get('buildid')}**{seen}{extra}"
        else:
            view.description = "No build information yet."

        if notes:
            listed = "\n".join(f"[{n['title']}]({n['url']}) · {n['date']}" for n in notes)
            view.add_field(name="Recent notes", value=listed[:1024])

        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Status(bot))
