from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatting import BAD, BRAND, GOOD, WARN, embed, first_page, iso_stamp
from ..permissions import requires


def hook_line(h: dict) -> str:
    kind = "update notes" if h.get("kind") == "updates" else "status changes"
    state = "on" if h.get("enabled") else "paused"
    sent = f"last post {iso_stamp(h['last_sent_at'])}" if h.get("last_sent_at") else "nothing posted yet"
    error = f"\nLast error: {h['last_error']}" if h.get("last_error") else ""
    products = ", ".join(h.get("products") or [])
    return f"**#{h.get('id')} {h.get('label') or 'Unnamed webhook'}** · {kind} · {state}\n{products} · {sent}{error}"


class Webhooks(
    commands.GroupCog,
    name="webhooks",
    description="Your Discord webhooks for status changes and update notes",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="list", description="List your webhooks")
    @requires("brand.read")
    async def list_hooks(self, interaction: discord.Interaction) -> None:
        result = await self.bot.partner_api.webhooks()
        rows = result.get("data") or []

        if not rows:
            await interaction.edit_original_response(
                content="No webhooks yet. Add one on the Webhooks page of the partner panel."
            )
            return

        view = embed(f"Webhooks ({len(rows)} of {result.get('max', 10)})", BRAND)
        view.description = first_page([hook_line(h) for h in rows])
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="test", description="Send a test post through a webhook")
    @app_commands.describe(id="The webhook number from /webhooks list")
    @requires("brand.write")
    async def test(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]) -> None:
        result = await self.bot.partner_api.test_webhook(id, key=f"discord:{interaction.id}")
        if result.get("sent"):
            view = embed("Test post sent", GOOD)
            view.description = f"Check the channel webhook #{id} posts to."
        else:
            view = embed("Discord refused the test post", BAD)
            paused = (
                "\nThe webhook has been paused. Fix it in Discord, then run `/webhooks resume`."
                if result.get("paused")
                else ""
            )
            view.description = f"{result.get('error') or 'No reason given.'}{paused}"
        await interaction.edit_original_response(embed=view)

    @app_commands.command(name="pause", description="Stop a webhook posting for now")
    @app_commands.describe(id="The webhook number from /webhooks list")
    @requires("brand.write")
    async def pause(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]) -> None:
        await self.switch(interaction, id, False)

    @app_commands.command(name="resume", description="Turn a paused webhook back on")
    @app_commands.describe(id="The webhook number from /webhooks list")
    @requires("brand.write")
    async def resume(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]) -> None:
        await self.switch(interaction, id, True)

    async def switch(self, interaction: discord.Interaction, hook_id: int, on: bool) -> None:
        hook = await self.bot.partner_api.set_webhook_enabled(hook_id, on, key=f"discord:{interaction.id}")
        name = f"**#{hook.get('id')} {hook.get('label') or 'Unnamed webhook'}**"
        view = embed("Webhook back on" if on else "Webhook paused", GOOD if on else WARN)
        view.description = f"{name} posts again." if on else f"{name} will not post until you resume it."
        await interaction.edit_original_response(embed=view)
        await self.bot.log_action(f"**{interaction.user}** {'resumed' if on else 'paused'} webhook #{hook.get('id')}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Webhooks(bot))
