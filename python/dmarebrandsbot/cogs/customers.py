from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..confirm import ask
from ..formatting import BRAND, GOOD, WARN, embed, iso_stamp, money, stamp
from ..permissions import requires


def product_lines(customer: dict) -> str:
    rows = customer.get("products") or []
    if not rows:
        return "none"
    return "\n".join(
        f"{p['product']} · "
        + (f"active until {stamp(p['expires_at'])}" if p.get("active") else "expired")
        for p in rows
    )


def machine_lines(customer: dict) -> str:
    machines = customer.get("machines") or []
    if not machines:
        return "Nothing bound right now."
    return "\n".join(
        f"**{m['scope']}** · bound {iso_stamp(m.get('bound_at'))} · "
        f"last seen {iso_stamp(m.get('last_seen'))}"
        for m in machines
    )


class Customers(
    commands.GroupCog, name="customers", description="Look up the people who redeemed your keys"
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="list", description="List your customers")
    @app_commands.describe(search="Match a username", limit="How many to show (1-25, default 15)")
    @requires("customers.read")
    async def list_customers(
        self,
        interaction: discord.Interaction,
        search: str | None = None,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        result = await self.bot.partner_api.list_customers(search=search, limit=limit)
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No customers matched that.")
            return

        lines = []
        for customer in rows:
            state = (
                f"active until {stamp(customer['expires_at'])}"
                if customer.get("active")
                else "expired"
            )
            machines = customer.get("machines") or []
            bound = f" · {len(machines)} machine(s)" if machines else ""
            lines.append(
                f"**{customer['username']}** (id {customer['id']}) · {state} · "
                f"{customer.get('keys', 0)} key(s){bound}"
            )

        view = embed("Customers", BRAND)
        view.description = "\n".join(lines)
        view.set_footer(text=f"{len(rows)} shown")
        await interaction.edit_original_response(embed=view)

    @app_commands.command(
        name="info", description="Look up one customer by id, username or a key they redeemed"
    )
    @app_commands.describe(ref="Customer id, username, or a key code you sold them")
    @requires("customers.read")
    async def info(self, interaction: discord.Interaction, ref: str) -> None:
        customer = await self.bot.partner_api.get_customer(ref.strip())

        view = embed(f"Customer {customer['username']}", GOOD if customer.get("active") else WARN)
        view.add_field(name="Id", value=str(customer["id"]), inline=True)
        view.add_field(
            name="Access", value="Active" if customer.get("active") else "Expired", inline=True
        )
        view.add_field(name="Keys redeemed", value=str(customer.get("keys", 0)), inline=True)
        view.add_field(name="Product", value=customer.get("product") or "none", inline=True)
        view.add_field(
            name="Expires",
            value=stamp(customer["expires_at"]) if customer.get("expires_at") else "n/a",
            inline=True,
        )
        view.add_field(name="Joined", value=iso_stamp(customer.get("created_at")), inline=True)
        view.add_field(name="Products", value=product_lines(customer), inline=False)
        view.add_field(name="Machines", value=machine_lines(customer), inline=False)

        await interaction.edit_original_response(embed=view)


class Hwid(
    commands.GroupCog,
    name="hwid",
    description="Clear a customer's hardware lock so they can move machine",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="key", description="Reset by key code")
    @app_commands.describe(code="The key they redeemed")
    @requires("hwid.reset")
    async def by_key(self, interaction: discord.Interaction, code: str) -> None:
        clean = code.strip()
        key = await self.bot.partner_api.get_key(clean)
        customer = key.get("customer")

        if not customer:
            view = embed("Nobody to reset", WARN)
            view.description = (
                "That key has not been redeemed yet, so there is no machine bound to it."
            )
            await interaction.edit_original_response(embed=view)
            return

        preview = embed("Confirm this reset", WARN)
        preview.description = (
            f"This clears every hardware lock on **{customer['username']}** (id {customer['id']}).\n"
            "They will be able to bind a new machine on their next launch."
        )

        if not await ask(interaction, preview, confirm_label="Reset machine"):
            cancelled = embed("Cancelled", BRAND)
            cancelled.description = "Nothing was cleared."
            await interaction.edit_original_response(embed=cancelled, view=None)
            return

        result = await self.bot.partner_api.reset_by_key(clean)
        cleared = result.get("cleared", 0)

        done = embed("Machine reset", GOOD)
        done.description = (
            f"Cleared {cleared} lock{'' if cleared == 1 else 's'} for **{customer['username']}**."
        )
        await interaction.edit_original_response(embed=done, view=None)
        await self.bot.log_action(
            f"**{interaction.user}** reset HWID for {customer['username']} via key `{clean}`"
        )

    @app_commands.command(
        name="customer", description="Reset by customer id, username or a key they redeemed"
    )
    @app_commands.describe(ref="Customer id, username, or a key code you sold them")
    @requires("hwid.reset")
    async def by_customer(self, interaction: discord.Interaction, ref: str) -> None:
        customer = await self.bot.partner_api.get_customer(ref.strip())

        preview = embed("Confirm this reset", WARN)
        preview.description = (
            f"This clears every hardware lock on **{customer['username']}** (id {customer['id']}).\n"
            "They will be able to bind a new machine on their next launch."
        )

        if not await ask(interaction, preview, confirm_label="Reset machine"):
            cancelled = embed("Cancelled", BRAND)
            cancelled.description = "Nothing was cleared."
            await interaction.edit_original_response(embed=cancelled, view=None)
            return

        result = await self.bot.partner_api.reset_by_customer(customer["id"])
        cleared = result.get("cleared", 0)

        done = embed("Machine reset", GOOD)
        done.description = (
            f"Cleared {cleared} lock{'' if cleared == 1 else 's'} for **{customer['username']}**."
        )
        await interaction.edit_original_response(embed=done, view=None)
        await self.bot.log_action(
            f"**{interaction.user}** reset HWID for {customer['username']} (id {id})"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Customers(bot))
    await bot.add_cog(Hwid(bot))
