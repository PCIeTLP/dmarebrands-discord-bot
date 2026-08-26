from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BRAND, embed, iso_stamp, money
from ..permissions import describe, requires, scopes_for


class Account(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Show the partner account this bot is connected to")
    @requires("account.read")
    async def account(self, interaction: discord.Interaction) -> None:
        me = await self.bot.partner_api.me()
        brand = me.get("brand") or {}
        stats = me.get("stats") or {}

        view = embed(f"Partner account: {me.get('username')}", BRAND)
        view.description = (
            f"Trading as **{brand['name']}**" if brand.get("name") else "No brand name set yet."
        )
        view.add_field(name="Balance", value=money(me.get("balance_usd")), inline=True)
        view.add_field(name="Discount", value=f"{me.get('discount_pct')}%", inline=True)
        view.add_field(name="Customers", value=str(stats.get("customers", 0)), inline=True)
        view.add_field(name="Keys in stock", value=str(stats.get("keys_unused", 0)), inline=True)
        view.add_field(name="Keys active", value=str(stats.get("keys_active", 0)), inline=True)
        view.add_field(name="Spent all time", value=money(stats.get("spent_usd")), inline=True)

        if brand.get("store_url"):
            view.url = brand["store_url"]

        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="List every plan you can buy, with your discounted price")
    @requires("account.read")
    async def plans(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.plans()
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No plans are available right now.")
            return

        view = embed("Plans", BRAND)
        view.description = "\n\n".join(
            f"**{plan['label']}** `{plan['id']}`\n"
            f"{plan['days']} days · {money(plan['your_price_usd'])} for you · "
            f"list {money(plan['list_price_usd'])} · you save {money(plan['saving_usd'])}"
            for plan in rows
        )
        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="Headline numbers for the partner account")
    @requires("account.read")
    async def stats(self, interaction: discord.Interaction) -> None:
        s = await self.bot.partner_api.stats()
        view = embed("Stats", BRAND)
        view.add_field(name="Keys issued", value=str(s.get("keys_total", 0)), inline=True)
        view.add_field(name="In stock", value=str(s.get("keys_unused", 0)), inline=True)
        view.add_field(name="Active", value=str(s.get("keys_active", 0)), inline=True)
        view.add_field(name="Expired", value=str(s.get("keys_expired", 0)), inline=True)
        view.add_field(name="Customers", value=str(s.get("customers", 0)), inline=True)
        view.add_field(name="Balance", value=money(s.get("balance_usd")), inline=True)
        view.add_field(name="Spent all time", value=money(s.get("spent_usd")), inline=True)
        view.add_field(name="HWID resets (30d)", value=str(s.get("hwid_resets_30d", 0)), inline=True)
        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="Show your white-label domains and whether they are live")
    @requires("domains.read")
    async def domains(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.domains()
        rows = result.get("data") or []
        target = result.get("cname_target")

        if not rows:
            await interaction.edit_original_response(
                content=(
                    "No domains set up yet. Add one at "
                    "https://partners.dmarebrands.st/partners/branding\n"
                    f"Point a CNAME at `{target or 'the target shown in the panel'}`."
                )
            )
            return

        lines = []
        for domain in rows:
            state = (
                "Live"
                if domain.get("live")
                else f"Not live yet ({domain.get('status')} / ssl {domain.get('ssl_status')})"
            )
            checked = f" · checked {iso_stamp(domain['checked_at'])}" if domain.get("checked_at") else ""
            error = f"\n{domain['last_error']}" if domain.get("last_error") else ""
            lines.append(f"**{domain['hostname']}** · {domain['kind']}\n{state}{checked}{error}")

        view = embed("Your domains", BRAND)
        view.description = "\n\n".join(lines)
        if target:
            view.set_footer(text=f"CNAME target: {target}")

        await interaction.edit_original_response(embed=view)

    @app_commands.command(description="Show what this bot will let you do")
    async def whoami(self, interaction: discord.Interaction) -> None:
        granted = scopes_for(interaction.user, self.bot.partner_config.role_scopes)
        view = embed("Your access", BRAND)
        view.description = (
            f"You have these scopes:\n`{describe(granted)}`"
            if granted
            else "None of your roles are configured for this bot, so every command will be refused."
        )
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Account(bot))
