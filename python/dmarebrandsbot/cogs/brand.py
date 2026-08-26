from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BRAND, embed
from ..permissions import requires


def link_line(label: str, url: str | None, is_public: bool) -> str:
    if not url:
        return f"**{label}** · not until your menu domain is live"
    state = "public" if is_public else "sign in required"
    return f"**{label}** · {state}\n{url}"


def summary(b: dict[str, Any]) -> str:
    return (
        f"**{b.get('name') or 'No name set'}**\n"
        + link_line("Features", b.get("features_url"), bool(b.get("public_features")))
        + "\n"
        + link_line("Setup guide", b.get("guide_url"), bool(b.get("public_guide")))
    )


class Brand(commands.Cog):
    group = app_commands.Group(name="brand", description="Read or change your white-label branding")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @group.command(name="show", description="Show your branding and public links")
    @requires("brand.read")
    async def show(self, interaction: discord.Interaction) -> None:
        b = await self.bot.partner_api.brand()
        view = embed("Your branding", BRAND)
        view.description = summary(b)
        view.add_field(name="Brand colour", value=b.get("primary") or "not set", inline=True)
        view.add_field(name="Second colour", value=b.get("accent") or "not set", inline=True)
        view.add_field(name="Logo", value="uploaded" if b.get("has_logo") else "none", inline=True)
        view.add_field(name="Store link", value=b.get("store_url") or "not set")
        await interaction.edit_original_response(embed=view)

    @group.command(
        name="set", description="Change your branding. Only the options you fill in are touched"
    )
    @app_commands.describe(
        name="Brand name, up to 48 characters",
        primary="Brand colour, like #7c5cff",
        accent="Second colour, like #22d3ee",
        store_url="Where your Extend button goes",
        public_features="Let anyone open your features page",
        public_guide="Let anyone open your setup guide",
    )
    @requires("brand.write")
    async def set(
        self,
        interaction: discord.Interaction,
        name: str | None = None,
        primary: str | None = None,
        accent: str | None = None,
        store_url: str | None = None,
        public_features: bool | None = None,
        public_guide: bool | None = None,
    ) -> None:
        patch: dict[str, Any] = {}
        for field, value in (
            ("name", name),
            ("primary", primary),
            ("accent", accent),
            ("store_url", store_url),
            ("public_features", public_features),
            ("public_guide", public_guide),
        ):
            if value is not None:
                patch[field] = value

        if not patch:
            await interaction.edit_original_response(
                content="Fill in at least one option to change something."
            )
            return

        saved = await self.bot.partner_api.update_brand(patch)
        view = embed("Branding saved", BRAND)
        view.description = f"Changed {', '.join(patch)}.\n\n" + summary(saved)
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Brand(bot))
