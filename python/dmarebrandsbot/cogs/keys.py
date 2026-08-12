from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..confirm import ask
from ..formatting import BAD, BRAND, GOOD, WARN, code_block, embed, iso_stamp, money, stamp, state_label
from ..permissions import requires

FILTER_LABEL = {
    "all": "everything",
    "unused": "in stock",
    "active": "active",
    "expired": "expired",
}

FILTER_CHOICES = [
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="In stock", value="unused"),
    app_commands.Choice(name="Active", value="active"),
    app_commands.Choice(name="Expired", value="expired"),
]


def key_line(key: dict) -> str:
    customer = key.get("customer")
    owner = f" · {customer['username']}" if customer else ""
    expiry = f" · expires {stamp(key['expires_at'])}" if key.get("expires_at") else ""
    return (
        f"`{key['code']}` — {state_label(key.get('state'))} · "
        f"{key.get('days')}d {key.get('product')}{owner}{expiry}"
    )


class Keys(commands.GroupCog, name="keys", description="Buy, inspect and refund your keys"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    async def plan_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            result = await self.bot.partner_api.plans()
        except Exception:
            return []

        typed = (current or "").lower()
        choices = []
        for plan in result.get("data") or []:
            label = f"{plan['label']} — {money(plan['your_price_usd'])} ({plan['id']})"[:100]
            if typed and typed not in plan["id"].lower() and typed not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=plan["id"]))
        return choices[:25]

    @app_commands.command(name="list", description="List keys you have issued")
    @app_commands.describe(
        filter="Which keys to show",
        search="Match a key code or customer username",
        limit="How many to show (1-25, default 15)",
    )
    @app_commands.choices(filter=FILTER_CHOICES)
    @requires("keys.read")
    async def list_keys(
        self,
        interaction: discord.Interaction,
        filter: app_commands.Choice[str] | None = None,
        search: str | None = None,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        chosen = filter.value if filter else "all"
        result = await self.bot.partner_api.list_keys(filter=chosen, search=search, limit=limit)
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No keys matched that.")
            return

        view = embed(f"Keys — {FILTER_LABEL.get(chosen, 'everything')}", BRAND)
        view.description = "\n".join(key_line(key) for key in rows)
        view.set_footer(text=f"{len(rows)} shown")
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="buy", description="Buy new keys against the partner balance")
    @app_commands.describe(plan="Which plan to buy", count="How many keys (1-25, default 1)")
    @app_commands.autocomplete(plan=plan_autocomplete)
    @requires("keys.buy")
    async def buy(
        self,
        interaction: discord.Interaction,
        plan: str,
        count: app_commands.Range[int, 1, 25] = 1,
    ) -> None:
        plan_list = await self.bot.partner_api.plans()
        chosen = next((p for p in plan_list.get("data") or [] if p["id"] == plan), None)

        if chosen is None:
            await interaction.edit_original_response(
                content=f"There is no plan called `{plan}`. Run `/plans` to see what is available."
            )
            return

        total = round(float(chosen["your_price_usd"]) * count, 2)
        balance = await self.bot.partner_api.balance()
        available = float(balance.get("balance_usd") or 0)

        if available < total:
            view = embed("Not enough balance", BAD)
            view.description = (
                f"{count} × {chosen['label']} costs {money(total)} but the account "
                f"only has {money(available)}."
            )
            await interaction.edit_original_response(embed=view)
            return

        preview = embed("Confirm this purchase", WARN)
        preview.description = (
            f"**{count} × {chosen['label']}** ({chosen['days']} days)\n"
            f"{money(chosen['your_price_usd'])} each · **{money(total)}** total\n"
            f"Balance after: {money(available - total)}"
        )

        if not await ask(interaction, preview, confirm_label=f"Buy for {money(total)}"):
            cancelled = embed("Cancelled", BRAND)
            cancelled.description = "No keys were bought."
            await interaction.edit_original_response(embed=cancelled, view=None)
            return

        bought = await self.bot.partner_api.buy_keys(plan, count)
        codes = [key["code"] for key in bought.get("data") or []]

        done = embed(f"Bought {len(codes)} key{'' if len(codes) == 1 else 's'}", GOOD)
        done.description = code_block("\n".join(codes))
        done.add_field(name="Spent", value=money(bought.get("spent_usd")), inline=True)
        done.add_field(name="Balance", value=money(bought.get("balance_usd")), inline=True)

        await interaction.edit_original_response(embed=done, view=None)
        await self.bot.log_action(
            f"**{interaction.user}** bought {len(codes)} × {chosen['label']} "
            f"for {money(bought.get('spent_usd'))}"
        )

    @app_commands.command(name="info", description="Look up a single key")
    @app_commands.describe(code="The key code")
    @requires("keys.read")
    async def info(self, interaction: discord.Interaction, code: str) -> None:
        key = await self.bot.partner_api.get_key(code.strip())

        view = embed(f"Key {key['code']}", BRAND)
        view.add_field(name="State", value=state_label(key.get("state")), inline=True)
        view.add_field(name="Product", value=f"{key.get('days')}d {key.get('product')}", inline=True)
        view.add_field(name="Cost", value=money(key.get("cost_usd")), inline=True)
        view.add_field(name="Created", value=iso_stamp(key.get("created_at")), inline=True)
        view.add_field(
            name="Redeemed",
            value=stamp(key["redeemed_at"]) if key.get("redeemed_at") else "not yet",
            inline=True,
        )
        view.add_field(
            name="Expires",
            value=stamp(key["expires_at"]) if key.get("expires_at") else "n/a",
            inline=True,
        )

        customer = key.get("customer")
        if customer:
            view.add_field(
                name="Customer", value=f"{customer['username']} (id {customer['id']})", inline=False
            )

        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="refund", description="Refund an unredeemed key back to your balance")
    @app_commands.describe(code="The key code")
    @requires("keys.refund")
    async def refund(self, interaction: discord.Interaction, code: str) -> None:
        clean = code.strip()
        key = await self.bot.partner_api.get_key(clean)

        if key.get("state") != "unused":
            view = embed("Cannot refund that", BAD)
            view.description = (
                "Only keys still in stock can be refunded. That one has already been redeemed."
            )
            await interaction.edit_original_response(embed=view)
            return

        preview = embed("Confirm this refund", WARN)
        preview.description = (
            f"`{key['code']}` — {key['days']}d {key['product']}\n"
            f"This destroys the key and puts **{money(key.get('cost_usd'))}** back on the balance.\n"
            "It cannot be undone and the code will stop working immediately."
        )

        if not await ask(
            interaction, preview, confirm_label=f"Refund {money(key.get('cost_usd'))}", danger=True
        ):
            cancelled = embed("Cancelled", BRAND)
            cancelled.description = "The key was left alone."
            await interaction.edit_original_response(embed=cancelled, view=None)
            return

        result = await self.bot.partner_api.refund_key(clean)
        done = embed("Refunded", GOOD)
        done.description = f"`{result['code']}` is gone."
        done.add_field(name="Returned", value=money(result.get("refunded_usd")), inline=True)
        done.add_field(name="Balance", value=money(result.get("balance_usd")), inline=True)

        await interaction.edit_original_response(embed=done, view=None)
        await self.bot.log_action(
            f"**{interaction.user}** refunded `{result['code']}` for {money(result.get('refunded_usd'))}"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Keys(bot))
