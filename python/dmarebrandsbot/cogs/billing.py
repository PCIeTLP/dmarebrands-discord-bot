from __future__ import annotations

from datetime import datetime, timedelta

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
    "payment": "Payment",
    "usage": "Keys used",
}


def due_line(invoice: dict | None) -> str | None:
    if not invoice:
        return None
    if invoice.get("stock_locked"):
        state = "unused credit keys are locked"
    elif invoice.get("overdue"):
        state = "buying is paused"
    else:
        state = f"due {iso_stamp(invoice.get('due_at'))}"
    return (
        f"Invoice `{invoice.get('number')}`: **{money(invoice.get('due_usd'))}** still due, {state}. "
        "Pay it with `/invoice pay`."
    )


class Billing(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Show the partner balance or credit and how to pay")
    @requires("billing.read")
    async def balance(self, interaction: discord.Interaction) -> None:
        b = await self.bot.partner_api.balance()
        topup = b.get("topup") or {}
        billing = b.get("billing") or {}

        if billing.get("mode") == "credit":
            view = embed("Monthly credit", WARN if billing.get("buying_paused") else BRAND)
            view.add_field(name="Available", value=money(b.get("available_usd")), inline=True)
            view.add_field(name="Credit limit", value=money(billing.get("credit_limit_usd")), inline=True)
            view.add_field(name="Your discount", value=f"{b.get('discount_pct')}%", inline=True)
            view.add_field(name="Unused stock on credit", value=money(billing.get("stock_usd")), inline=True)
            view.add_field(name="Used, not paid yet", value=money(billing.get("used_unpaid_usd")), inline=True)
            view.add_field(
                name="Next invoice",
                value=iso_stamp(billing.get("period_ends_at")) if billing.get("period_ends_at") else "not scheduled",
                inline=True,
            )
            view.description = due_line(billing.get("open_invoice")) or (
                "Keys are charged when a customer redeems them, on the invoice issued on the 1st of each month."
            )
            await interaction.edit_original_response(embed=view)
            return

        view = embed("Balance", BRAND)
        view.add_field(name="Available", value=money(b.get("balance_usd")), inline=True)
        view.add_field(name="Your discount", value=f"{b.get('discount_pct')}%", inline=True)
        view.description = due_line(billing.get("open_invoice")) or (
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
    @requires("billing.topup")
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


def invoice_state(inv: dict) -> str:
    if inv.get("status") == "paid":
        return "Paid"
    if inv.get("stock_locked"):
        return "Keys locked"
    if inv.get("overdue"):
        return "Due"
    return "Unpaid"


def invoice_tone(inv: dict) -> int:
    if inv.get("status") == "paid":
        return GOOD
    if inv.get("stock_locked"):
        return BAD
    return WARN


def day(value: object) -> str:
    return str(value)[:10] if value else "?"


def last_day(value: object) -> str:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00")) - timedelta(seconds=1)
    except ValueError:
        return "?"
    return moment.strftime("%Y-%m-%d")


class Invoice(commands.GroupCog, name="invoice", description="Monthly credit invoices"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="list", description="Your recent invoices")
    @requires("billing.read")
    async def list_invoices(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.invoices(limit=12)
        rows = result.get("data") or []
        if not rows:
            await interaction.edit_original_response(content="No invoices yet.")
            return
        view = embed("Invoices", BRAND)
        view.description = "\n".join(
            f"`{inv.get('number')}` · {day(inv.get('period_start'))} to {last_day(inv.get('period_end'))} · "
            f"{money(inv.get('amount_usd'))} · {invoice_state(inv)}"
            + (f" · {money(inv.get('due_usd'))} due" if inv.get("status") == "open" else "")
            for inv in rows
        )
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="show", description="One invoice with its lines")
    @app_commands.describe(number="The invoice number, like INV-202611-K7QD")
    @requires("billing.read")
    async def show(self, interaction: discord.Interaction, number: str) -> None:
        inv = await self.bot.partner_api.get_invoice(number.strip().upper())
        used = [line for line in inv.get("lines") or [] if line.get("kind") == "usage"]
        view = embed(f"Invoice {inv.get('number')}", invoice_tone(inv))
        view.add_field(name="Amount", value=money(inv.get("amount_usd")), inline=True)
        view.add_field(name="Paid", value=money(inv.get("paid_usd")), inline=True)
        view.add_field(name="Still due", value=money(inv.get("due_usd")), inline=True)
        view.add_field(name="Period", value=f"{day(inv.get('period_start'))} to {last_day(inv.get('period_end'))}", inline=True)
        view.add_field(name="State", value=invoice_state(inv), inline=True)
        view.add_field(name="Due", value=iso_stamp(inv.get("due_at")), inline=True)
        view.description = (
            "\n".join(
                f"{line.get('qty')} × {line.get('duration') or ''} {line.get('product') or ''} at "
                f"{money(line.get('unit_usd'))} · {money(abs(float(line.get('amount_usd') or 0)))}"
                for line in used
            )
            if used
            else "No keys used in this period."
        )
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="pay", description="Open a payment for what is still due on an invoice")
    @app_commands.describe(
        number="The invoice number, like INV-202611-K7QD",
        coin="Which coin to pay with",
        amount="Pay part of it, from 20. Leave empty to pay everything due",
    )
    @requires("billing.topup")
    async def pay(
        self,
        interaction: discord.Interaction,
        number: str,
        coin: str,
        amount: app_commands.Range[float, 1, 250000] | None = None,
    ) -> None:
        clean = number.strip().upper()
        t = await self.bot.partner_api.pay_invoice(
            clean,
            coin.strip().lower(),
            key=f"discord:{interaction.id}",
            amount_usd=round(float(amount), 2) if amount else None,
        )
        view = topup_view(t, f"Payment for {clean}")
        view.description = payment(t)
        await interaction.edit_original_response(embed=view)
        await self.bot.log_action(
            f"**{interaction.user}** opened a {money(t.get('amount_usd'))} payment for invoice {clean}"
        )

    @pay.autocomplete("coin")
    @requires("billing.topup")
    async def pay_coin(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        cog = self.bot.get_cog("topup")
        return await cog.coin_autocomplete(interaction, current) if cog else []


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Billing(bot))
    await bot.add_cog(Topup(bot))
    await bot.add_cog(Invoice(bot))
