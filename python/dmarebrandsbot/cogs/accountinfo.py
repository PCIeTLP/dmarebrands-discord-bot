from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, embed, first_page, iso_stamp
from ..permissions import requires

REASON_LABEL = {
    "chargeback": "Chargeback",
    "dispute": "Payment dispute",
    "fraud": "Fraud report",
    "other": "Something else",
}

REASON_CHOICES = [app_commands.Choice(name=label, value=value) for value, label in REASON_LABEL.items()]

STATUS_LABEL = {
    "pending": "Waiting for approval",
    "approved": "Ready to download",
    "declined": "Declined",
}

STATUS_TONE = {"pending": WARN, "approved": GOOD, "declined": BAD}

STATUS_CHOICES = [
    app_commands.Choice(name=value, value=value) for value in ("all", "pending", "approved", "declined")
]

ATTACH_LIMIT = 8 * 1024 * 1024


def line(r: dict) -> str:
    who = (r.get("customer") or {}).get("username") or "unknown"
    return (
        f"`{r.get('ref')}` · **{who}** · `{r.get('key')}`\n"
        f"{REASON_LABEL.get(r.get('reason'), r.get('reason'))} · "
        f"{STATUS_LABEL.get(r.get('status'), r.get('status'))} · {iso_stamp(r.get('created_at'))}"
    )


def found(summary: dict) -> str:
    rows = [
        f"{summary.get('website_sign_ins', 0)} website sign-ins · {summary.get('loader_sign_ins', 0)} loader sign-ins",
        f"{summary.get('downloads', 0)} downloads · {summary.get('game_sessions', 0)} game sessions",
        f"{summary.get('ip_addresses', 0)} IP addresses · {summary.get('machines', 0)} machines · "
        f"{summary.get('active_days', 0)} active days",
    ]
    if summary.get("first_use"):
        rows.append(f"First use {iso_stamp(summary['first_use'])} · last seen {iso_stamp(summary.get('last_seen'))}")
    return "\n".join(rows)


class AccountInfo(
    commands.GroupCog,
    name="accountinfo",
    description="A customer's account history, for chargebacks and disputes",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="request", description="Ask for the account history of whoever redeemed a key")
    @app_commands.describe(
        key="A key from your stock that the customer redeemed",
        reason="Why you need it",
        reference="Your order or dispute ID",
        note="Anything we should know",
    )
    @app_commands.choices(reason=REASON_CHOICES)
    @requires("accountinfo.request")
    async def request(
        self,
        interaction: discord.Interaction,
        key: str,
        reason: app_commands.Choice[str],
        reference: app_commands.Range[str, 1, 64] | None = None,
        note: app_commands.Range[str, 1, 2000] | None = None,
    ) -> None:
        made = await self.bot.partner_api.request_account_info(
            code=key.strip(),
            reason=reason.value,
            reference=(reference or "").strip() or None,
            note=(note or "").strip() or None,
            key=f"discord:{interaction.id}",
        )
        ref = made.get("ref")
        who = (made.get("customer") or {}).get("username") or "unknown"

        view = embed("Request sent", WARN)
        view.description = (
            f"We check every request before the zip is made. Check on it with `/accountinfo status ref:{ref}`. "
            f"Our replies show up in `/tickets read ref:{ref}`."
        )
        view.add_field(name="Reference", value=f"`{ref}`", inline=True)
        view.add_field(name="Customer", value=who, inline=True)
        view.add_field(name="Key", value=f"`{made.get('key')}`", inline=True)
        await interaction.edit_original_response(embed=view)
        await self.bot.log_action(f"**{interaction.user}** asked for account info on {who} (`{ref}`)")

    @app_commands.command(name="status", description="Check a request, and get the zip once it is approved")
    @app_commands.describe(ref="The ticket reference, like TKT-8H2QMD")
    @requires("accountinfo.read")
    async def status(self, interaction: discord.Interaction, ref: str) -> None:
        code = ref.strip().upper()
        r = await self.bot.partner_api.get_account_info(code)
        state = r.get("status")

        view = embed(f"Account info {r.get('ref')}", STATUS_TONE.get(state, BRAND))
        view.add_field(name="Status", value=STATUS_LABEL.get(state, str(state)), inline=True)
        view.add_field(name="Customer", value=(r.get("customer") or {}).get("username") or "unknown", inline=True)
        view.add_field(name="Key", value=f"`{r.get('key')}`", inline=True)
        view.add_field(name="Reason", value=REASON_LABEL.get(r.get("reason"), str(r.get("reason"))), inline=True)
        view.add_field(name="Asked", value=iso_stamp(r.get("created_at")), inline=True)
        if r.get("reference"):
            view.add_field(name="Your reference", value=r["reference"], inline=True)
        if state == "declined" and r.get("decline_reason"):
            view.description = r["decline_reason"]
        if r.get("summary"):
            view.add_field(name="What we found", value=found(r["summary"]), inline=False)

        download = r.get("download")
        if state != "approved" or not download:
            await interaction.edit_original_response(embed=view)
            return

        if int(download.get("bytes") or 0) > ATTACH_LIMIT:
            view.description = "The zip is too big to attach here. Download it from the ticket in the partner panel."
            await interaction.edit_original_response(embed=view)
            return

        pack = await self.bot.partner_api.download_account_info(code)
        view.set_footer(text=f"SHA-256 {pack.get('sha256') or download.get('sha256')}")
        attachment = discord.File(io.BytesIO(pack["data"]), filename=pack["name"])
        await interaction.edit_original_response(embed=view, attachments=[attachment])

    @app_commands.command(name="list", description="Your recent requests")
    @app_commands.describe(status="Narrow it down")
    @app_commands.choices(status=STATUS_CHOICES)
    @requires("accountinfo.read")
    async def list_requests(
        self, interaction: discord.Interaction, status: app_commands.Choice[str] | None = None
    ) -> None:
        result = await self.bot.partner_api.list_account_info(
            status=status.value if status else "all", limit=15
        )
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(content="No account info requests match that.")
            return

        view = embed(f"Account info requests ({len(rows)})", BRAND)
        view.description = first_page([line(r) for r in rows])
        await interaction.edit_original_response(embed=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountInfo(bot))
