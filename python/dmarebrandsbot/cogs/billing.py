from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, clock, code_block, embed, iso_stamp, money
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


STATE_LABEL = {
    "waiting": "Waiting for payment",
    "confirming": "Payment seen, confirming",
    "partially_paid": "Part paid",
    "paid": "Paid, crediting now",
    "credited": "On your balance",
    "expired": "Expired",
    "failed": "Failed",
    "refunded": "Refunded",
}

STATE_TONE = {
    "waiting": WARN,
    "confirming": WARN,
    "partially_paid": WARN,
    "paid": GOOD,
    "credited": GOOD,
    "expired": BAD,
    "failed": BAD,
    "refunded": BAD,
}


def coin_amount(pay: dict) -> str:
    return f"{pay.get('amount') or '?'} {str(pay.get('currency') or '').upper()}"


def payment(t: dict) -> str:
    pay = t.get("pay") or {}
    lines = [f"Send exactly **{coin_amount(pay)}** to", code_block(pay.get("address") or "no address yet")]
    if pay.get("extra_id"):
        lines.append(f"Memo or tag: `{pay['extra_id']}`. The payment needs it.")
    if t.get("expires_at"):
        lines.append(f"Pay before {clock(t['expires_at'])}.")
    lines.append(f"Or pay on the checkout page, with a QR code: {t.get('checkout_url')}")
    return "\n".join(lines)


def topup_view(t: dict, title: str) -> discord.Embed:
    view = embed(title, STATE_TONE.get(t.get("state"), BRAND))
    view.add_field(name="Amount", value=money(t.get("amount_usd")), inline=True)
    view.add_field(name="State", value=STATE_LABEL.get(t.get("state"), str(t.get("state"))), inline=True)
    view.add_field(name="Reference", value=f"`{t.get('ref')}`", inline=True)
    return view


class Topup(commands.GroupCog, name="topup", description="Add money to the partner balance with crypto"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    async def coin_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            result = await self.bot.partner_api.coins()
        except Exception:
            return []

        typed = (current or "").lower()
        coins = [
            c
            for c in result.get("data") or []
            if not typed
            or any(typed in str(c.get(field) or "").lower() for field in ("code", "ticker", "name", "network"))
        ]
        coins.sort(key=lambda c: not c.get("popular"))
        choices = []
        for c in coins[:25]:
            network = f" on {c['network']}" if c.get("network") else ""
            choices.append(app_commands.Choice(name=f"{c['ticker']}{network} · {c['name']}"[:100], value=c["code"]))
        return choices

    @app_commands.command(name="start", description="Open a payment for your balance")
    @app_commands.describe(amount="Dollars to add, 20 to 10000", coin="Which coin to pay with")
    @requires("billing.topup")
    async def start(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[float, 20, 10000],
        coin: str,
    ) -> None:
        t = await self.bot.partner_api.start_topup(
            round(float(amount), 2), coin.strip().lower(), key=f"discord:{interaction.id}"
        )
        view = topup_view(t, "Top-up opened")
        view.description = payment(t)
        await interaction.edit_original_response(embed=view)
        currency = str((t.get("pay") or {}).get("currency") or coin).upper()
        await self.bot.log_action(
            f"**{interaction.user}** opened a {money(t.get('amount_usd'))} top-up in {currency}"
        )

    @start.autocomplete("coin")
    async def start_coin(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await self.coin_autocomplete(interaction, current)

    @app_commands.command(name="status", description="Check where a top-up stands")
    @app_commands.describe(ref="The top-up reference")
    @requires("billing.read")
    async def status(self, interaction: discord.Interaction, ref: str) -> None:
        t = await self.bot.partner_api.get_topup(ref.strip().upper())
        view = topup_view(t, f"Top-up {t.get('ref')}")
        if t.get("state") in ("waiting", "partially_paid"):
            view.description = payment(t)
        elif t.get("state") == "credited":
            view.description = "The money is on your balance."
        view.add_field(name="Opened", value=iso_stamp(t.get("created_at")), inline=True)
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="list", description="Your recent top-ups")
    @requires("billing.read")
    async def list_topups(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.topups(10)
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No top-ups yet. Start one with `/topup start`.")
            return

        view = embed("Recent top-ups", BRAND)
        view.description = "\n".join(
            f"`{t.get('ref')}` · {money(t.get('amount_usd'))} · {STATE_LABEL.get(t.get('state'), t.get('state'))} · "
            f"{str((t.get('pay') or {}).get('currency') or '').upper()} · {iso_stamp(t.get('created_at'))}"
            for t in rows
        )
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Billing(bot))
    await bot.add_cog(Topup(bot))
