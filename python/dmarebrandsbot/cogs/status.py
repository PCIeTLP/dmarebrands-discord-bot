from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, clip, embed, first_page, iso_stamp
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


LANGUAGE_CHOICES = [
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Русский", value="ru"),
    app_commands.Choice(name="中文", value="zh"),
]


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

    @app_commands.command(description="Show the latest game build and the recent patch notes")
    @app_commands.describe(product="Which game, rust or wardogs. Defaults to rust")
    @requires("status.read")
    async def updates(self, interaction: discord.Interaction, product: str | None = None) -> None:
        result = await self.bot.partner_api.updates(product)
        build = result.get("current_build")
        notes = (result.get("updates") or [])[:5]

        view = embed(f"Game updates · {result.get('game') or product or 'rust'}", BRAND)
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


    @app_commands.command(description="What changed in the latest loader and product releases")
    @app_commands.describe(
        product="loader, or a product such as rust. Leave it empty for all",
        language="Language of the notes",
        limit="How many releases (1-10, default 5)",
    )
    @app_commands.choices(language=LANGUAGE_CHOICES)
    @requires("status.read")
    async def changelog(
        self,
        interaction: discord.Interaction,
        product: str | None = None,
        language: app_commands.Choice[str] | None = None,
        limit: app_commands.Range[int, 1, 10] = 5,
    ) -> None:
        result = await self.bot.partner_api.changelogs(
            product=(product or "").strip().lower() or None,
            lang=language.value if language else "en",
            limit=limit,
        )
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No release notes yet.")
            return

        entries = []
        for r in rows:
            since = f" (from {r['previous_version']})" if r.get("previous_version") else ""
            notes = clip(r["notes"], 700) if r.get("notes") else "_No notes for this release._"
            entries.append(
                f"**{r.get('label')} {r.get('version')}**{since} · {iso_stamp(r.get('created_at'))}\n{notes}\n"
            )

        view = embed("Release notes", BRAND)
        view.description = first_page(entries)
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Status(bot))
