from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

SNOWFLAKE = re.compile(r"^\d{17,20}$")

SCOPES = (
    "account.read",
    "billing.read",
    "keys.read",
    "keys.buy",
    "keys.refund",
    "customers.read",
    "hwid.reset",
    "domains.read",
)

GROUPS: dict[str, tuple[str, ...]] = {
    "ROLES_ADMIN": SCOPES,
    "ROLES_KEYS": ("account.read", "keys.read", "keys.buy", "keys.refund", "customers.read"),
    "ROLES_HWID": ("hwid.reset", "keys.read", "customers.read"),
    "ROLES_BILLING": ("account.read", "billing.read"),
    "ROLES_READ": ("account.read", "keys.read", "customers.read", "domains.read"),
}

TOKEN_PREFIX = "dmarebrands_live_"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    app_id: int
    guild_id: int
    api_key: str
    api_base: str
    role_scopes: dict[int, frozenset[str]] = field(default_factory=dict)
    log_channel_id: int | None = None
    ephemeral: bool = True


def _required(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise ConfigError(f"{name} is missing from your .env")
    return value


def _snowflake(name: str) -> int:
    value = _required(name)
    if not SNOWFLAKE.match(value):
        raise ConfigError(f"{name} must be a Discord ID (17-20 digits), got {value!r}")
    return int(value)


def _optional_snowflake(name: str) -> int | None:
    value = (os.environ.get(name) or "").strip()
    if not value:
        return None
    if not SNOWFLAKE.match(value):
        raise ConfigError(f"{name} must be a Discord ID (17-20 digits), got {value!r}")
    return int(value)


def _id_list(name: str) -> list[int]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    parts = [p for p in re.split(r"[,\s]+", raw) if p]
    bad = [p for p in parts if not SNOWFLAKE.match(p)]
    if bad:
        raise ConfigError(f"{name} contains invalid role IDs: {', '.join(bad)}")
    return [int(p) for p in parts]


def _build_role_scopes() -> dict[int, frozenset[str]]:
    collected: dict[int, set[str]] = {}
    total = 0

    for env_name, scopes in GROUPS.items():
        for role_id in _id_list(env_name):
            total += 1
            collected.setdefault(role_id, set()).update(scopes)

    if total == 0:
        raise ConfigError(
            "No roles configured. Set at least one of ROLES_ADMIN, ROLES_KEYS, "
            "ROLES_HWID, ROLES_BILLING or ROLES_READ."
        )

    return {role_id: frozenset(scopes) for role_id, scopes in collected.items()}


def _load() -> Config:
    base = (os.environ.get("DMAREBRANDS_API_BASE") or "https://api.dmarebrands.st/v1").strip()
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ConfigError(f"DMAREBRANDS_API_BASE is not a valid URL: {base!r}")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ConfigError("DMAREBRANDS_API_BASE must use https so your API key is never sent in the clear.")

    api_key = _required("DMAREBRANDS_API_KEY")
    if not api_key.startswith(TOKEN_PREFIX):
        raise ConfigError(
            f"DMAREBRANDS_API_KEY does not look right. Partner keys start with {TOKEN_PREFIX!r}. "
            "Create one at https://partners.dmarebrands.st/partners/api"
        )

    return Config(
        token=_required("DISCORD_TOKEN"),
        app_id=_snowflake("DISCORD_APP_ID"),
        guild_id=_snowflake("DISCORD_GUILD_ID"),
        api_key=api_key,
        api_base=base.rstrip("/"),
        role_scopes=_build_role_scopes(),
        log_channel_id=_optional_snowflake("LOG_CHANNEL_ID"),
        ephemeral=(os.environ.get("EPHEMERAL") or "true").lower() != "false",
    )


def load_config() -> Config:
    try:
        return _load()
    except ConfigError as err:
        print(f"\nConfiguration problem: {err}\n", file=sys.stderr)
        print("Copy .env.example to .env and fill it in, then try again.\n", file=sys.stderr)
        raise SystemExit(1) from err
