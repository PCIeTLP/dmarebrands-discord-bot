from __future__ import annotations

import logging

import discord

from .bot import PartnerBot
from .config import load_config


def main() -> None:
    discord.utils.setup_logging(level=logging.INFO, root=False)
    config = load_config()
    bot = PartnerBot(config)

    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure:
        print("\nCould not log in to Discord. Check DISCORD_TOKEN in your .env.\n")
        raise SystemExit(1)
    except discord.PrivilegedIntentsRequired:
        print("\nDiscord refused the intents this bot asks for. It only needs the default ones.\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
