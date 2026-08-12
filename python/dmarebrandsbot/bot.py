from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .api import ApiError, PartnerApi, friendly
from .config import Config
from .formatting import error_embed
from .permissions import MissingScope, denied_message

log = logging.getLogger("dmarebrandsbot")

COGS = (
    "dmarebrandsbot.cogs.account",
    "dmarebrandsbot.cogs.billing",
    "dmarebrandsbot.cogs.keys",
    "dmarebrandsbot.cogs.customers",
)


class PartnerTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        config = interaction.client.partner_config

        if interaction.guild_id != config.guild_id:
            await interaction.response.send_message(
                "This bot only works in the server it was set up for.", ephemeral=True
            )
            return False

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=config.ephemeral)
        return True


class PartnerBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            application_id=config.app_id,
            help_command=None,
            tree_cls=PartnerTree,
        )
        self.partner_config = config
        self.partner_api = PartnerApi(config.api_key, config.api_base)
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
        log.info("Loaded %d cogs", len(COGS))

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

        try:
            me = await self.partner_api.me()
            log.info(
                "Partner API connected as %s · balance $%s", me.get("username"), me.get("balance_usd")
            )
        except Exception as err:
            log.error("The partner API rejected the bot's key: %s", friendly(err))
            log.error("Fix DMAREBRANDS_API_KEY in your .env, then restart.")

        guild = discord.Object(id=self.partner_config.guild_id)
        registered = await self.tree.fetch_commands(guild=guild)
        if registered:
            log.info("Serving %d commands in guild %s", len(registered), self.partner_config.guild_id)
        else:
            log.warning(
                "No commands are registered in guild %s. Run: python scripts/register.py",
                self.partner_config.guild_id,
            )

    async def close(self) -> None:
        await self.partner_api.close()
        await super().close()

    async def log_action(self, text: str) -> None:
        channel_id = self.partner_config.log_channel_id
        if not channel_id:
            return
        try:
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if isinstance(channel, discord.abc.Messageable):
                await channel.send(text)
        except Exception:
            pass

    async def on_tree_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, MissingScope):
            message = denied_message(error.scope)
            if interaction.response.is_done():
                await interaction.edit_original_response(content=message, embed=None, view=None)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return

        original = getattr(error, "original", error)
        message = friendly(original)
        if isinstance(original, ApiError) and original.request_id:
            message += f"\nRequest id: `{original.request_id}`"

        if not isinstance(original, ApiError):
            log.exception("command failed", exc_info=original)

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    embed=error_embed(message), content=None, view=None
                )
            else:
                await interaction.response.send_message(embed=error_embed(message), ephemeral=True)
        except discord.HTTPException:
            pass
