from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp  # noqa: E402

from dmarebrandsbot.api import PartnerApi, friendly  # noqa: E402
from dmarebrandsbot.config import GROUPS, SCOPES, load_config  # noqa: E402

DISCORD_API = "https://discord.com/api/v10"

problems = 0


def ok(label: str, detail: str = "") -> None:
    print(f"  PASS  {label}" + (f"  ({detail})" if detail else ""))


def bad(label: str, detail: str = "") -> None:
    global problems
    problems += 1
    print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))


async def main() -> int:
    print("\nchecking your .env")
    config = load_config()
    ok("env parsed", f"{len(config.role_scopes)} role(s) configured")

    print("\nchecking the partner API")
    api = PartnerApi(config.api_key, config.api_base)
    try:
        me = await api.me()
        ok(
            "API key works",
            f"{me.get('username')}, balance ${me.get('balance_usd')}, {me.get('discount_pct')}% off",
        )
    except Exception as err:
        bad("API key rejected", friendly(err))
    finally:
        await api.close()

    print("\nchecking Discord")
    headers = {"authorization": f"Bot {config.token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{DISCORD_API}/applications/@me") as res:
            if res.status == 200:
                app = await res.json()
                ok("token works", f"application {app.get('name')}")
                if str(app.get("id")) != str(config.app_id):
                    bad("DISCORD_APP_ID does not match this token", f"token belongs to {app.get('id')}")
                else:
                    ok("DISCORD_APP_ID matches the token")
            else:
                bad("token rejected", f"HTTP {res.status}")

        url = f"{DISCORD_API}/applications/{config.app_id}/guilds/{config.guild_id}/commands"
        async with session.get(url) as res:
            if res.status == 200:
                commands = await res.json()
                if commands:
                    ok("commands registered in the guild", f"{len(commands)} found")
                else:
                    bad("no commands registered yet", "start the bot once, it syncs on boot")
            elif res.status in (403, 404):
                bad("cannot read guild commands", "is the bot in that guild with applications.commands?")
            else:
                bad("guild lookup failed", f"HTTP {res.status}")

    print("\nchecking permission wiring")
    covered: set[str] = set()
    for scopes in config.role_scopes.values():
        covered.update(scopes)

    unknown = sorted(scope for scope in covered if scope not in SCOPES)
    if unknown:
        bad("unknown scopes granted", ", ".join(unknown))
    else:
        ok("all granted scopes are real")

    for scope in SCOPES:
        if scope in covered:
            ok(f"{scope} is reachable")
        else:
            bad(f"{scope} is unreachable", "no role grants it, those commands will always refuse")

    print("\nrole groups in use")
    for group, scopes in GROUPS.items():
        ids = [
            str(role_id)
            for role_id, granted in config.role_scopes.items()
            if all(scope in granted for scope in scopes)
        ]
        print(f"  {group:<14} {', '.join(ids) if ids else '(none)'}")

    print("\nEverything looks good.\n" if problems == 0 else f"\n{problems} problem(s) to fix.\n")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
