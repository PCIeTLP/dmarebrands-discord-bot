from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discord  # noqa: E402

from dmarebrandsbot.bot import COGS, PartnerBot  # noqa: E402
from dmarebrandsbot.config import load_config  # noqa: E402


async def main() -> int:
    clear = "--clear" in sys.argv
    config = load_config()
    bot = PartnerBot(config)
    guild = discord.Object(id=config.guild_id)

    try:
        await bot.login(config.token)

        if clear:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"Removed every command from guild {config.guild_id}.")
            return 0

        for cog in COGS:
            await bot.load_extension(cog)

        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)

        print(f"Registered {len(synced)} commands in guild {config.guild_id}:")
        for command in sorted(synced, key=lambda c: c.name):
            print(f"  /{command.name}")
        print("\nGuild commands appear immediately. Reload Discord if you do not see them.")
        return 0

    except discord.LoginFailure:
        print("\nRegistration failed. Discord rejected the token. Check DISCORD_TOKEN.")
        return 1
    except discord.Forbidden:
        print(
            "\nRegistration failed. The bot is not in that guild, or was invited without the "
            "applications.commands scope.\nInvite it again: "
            f"https://discord.com/oauth2/authorize?client_id={config.app_id}"
            "&scope=bot%20applications.commands&permissions=0"
        )
        return 1
    except discord.NotFound:
        print("\nRegistration failed. Unknown application or guild. Check DISCORD_APP_ID and DISCORD_GUILD_ID.")
        return 1
    except discord.HTTPException as err:
        print(f"\nRegistration failed. {err}")
        return 1
    finally:
        await bot.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
