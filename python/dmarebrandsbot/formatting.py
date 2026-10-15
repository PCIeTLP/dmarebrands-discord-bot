from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord

BRAND = 0x4F46E5
GOOD = 0x22C55E
WARN = 0xF59E0B
BAD = 0xEF4444


def money(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"${number:,.2f}"


def stamp(seconds: Any) -> str:
    try:
        number = int(seconds)
    except (TypeError, ValueError):
        return "never"
    if number <= 0:
        return "never"
    return f"<t:{number}:R>"


def iso_stamp(value: Any) -> str:
    if not value:
        return "unknown"
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return f"<t:{int(parsed.timestamp())}:R>"
    except ValueError:
        return "unknown"


def state_label(state: Any) -> str:
    return {"unused": "In stock", "active": "Active", "expired": "Expired"}.get(str(state), str(state))


def embed(title: str, colour: int = BRAND) -> discord.Embed:
    return discord.Embed(title=title, colour=colour, timestamp=datetime.now(timezone.utc))


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(title="That did not work", description=message, colour=BAD)


def code_block(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


def clock(seconds: Any) -> str:
    try:
        number = int(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if number <= 0:
        return "unknown"
    return f"<t:{number}:t> (<t:{number}:R>)"


def clip(text: Any, limit: int) -> str:
    value = str(text or "")
    return f"{value[: limit - 1]}…" if len(value) > limit else value


def first_page(lines: list[str], limit: int = 4000) -> str:
    page = ""
    for line in lines:
        candidate = f"{page}\n{line}" if page else line
        if len(candidate) > limit:
            return page or f"{line[: limit - 1]}…"
        page = candidate
    return page or "Nothing to show."
