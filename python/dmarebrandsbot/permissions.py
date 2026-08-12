from __future__ import annotations

from typing import Iterable

import discord
from discord import app_commands

from .config import SCOPES


class MissingScope(app_commands.CheckFailure):
    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope


def scopes_for(member: object, role_scopes: dict[int, frozenset[str]]) -> frozenset[str]:
    roles: Iterable[object] = getattr(member, "roles", []) or []
    granted: set[str] = set()
    for role in roles:
        role_id = getattr(role, "id", None)
        if role_id is None:
            continue
        granted.update(role_scopes.get(int(role_id), frozenset()))
    return frozenset(granted)


def describe(granted: frozenset[str]) -> str:
    if not granted:
        return "none"
    return ", ".join(scope for scope in SCOPES if scope in granted)


def denied_message(scope: str) -> str:
    return (
        "You do not have permission to do that. This command needs the "
        f"`{scope}` scope, which your roles do not grant."
    )


def requires(scope: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        config = getattr(interaction.client, "partner_config", None)
        if config is None:
            raise MissingScope(scope)
        granted = scopes_for(interaction.user, config.role_scopes)
        if scope in granted:
            return True
        raise MissingScope(scope)

    return app_commands.check(predicate)
